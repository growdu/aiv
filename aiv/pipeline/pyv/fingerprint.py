"""布局指纹的采集。

**为什么要有它**：逐像素基准在 macOS 与 Linux 之间**不可比**——
cairo 在 macOS 走 CoreText、在 Linux 走 FreeType，栅格化不同，像素必然不同。
但下面这四类量**与栅格化无关**，跨机可比：

| 量 | 从哪来 | 跨机 |
| --- | --- | --- |
| 落笔坐标 (x, y) | 场景代码里的纯算术 | 完全一致 |
| 字号 | `fit_size` 收敛后的结果 | 一致 |
| 步进宽度 `x_advance` | 字体文件的 hmtx | 一致 |
| 轮廓包围盒 | `text_path` + `path_extents` | 一致 |

**实测（2026-11-16，macOS / CoreText）**：cairo 量出来的步进宽度与
「从字体文件 hmtx 算出来的」差 **≤ 0.056px**；`text_path` 的轮廓包围盒
与「从字体文件的字形数据算出来的」**逐项相等**（y 轴只是屏幕坐标向下、
字形坐标向上的翻面）。

也就是说这四类量**直接来自字体文件**，不是栅格化的产物——换一台机器、
换一个渲染后端，数值不变。所以「跨机像素一致」做不到，但「跨机版式
一致」做得到，而且是可以**量出来**的。

采集靠插桩拦 `draw.text`。**要拦两处**：

- `pyv.draw.text`——版式层（`pyv.layout`）走的是模块属性访问；
- **所有把 `draw.text` 别名成自己 `text` 属性的模块**——场景模块的
  `from pyv.draw import text`、`pyv.scene_layout` 的 `text = draw.text`。

别名的找法是**扫 `sys.modules`**：凡是 `text` 属性与 `draw.text` 是
**同一个函数对象**的模块都要拦。写死模块名的话，将来谁新增一个别名
就静默漏掉——而漏掉的画字会同时从「基准」和「比对」两侧消失，
守卫看着绿，实际少守了一块。
"""
from __future__ import annotations

import sys

import cairo

from pyv import draw
from pyv import fonts

#: 两个画幅：名字 + 宽 + 高。
CANVASES: tuple[tuple[str, int, int], ...] = (
    ("horizontal", 1920, 1080),
    ("vertical", 1080, 1920),
)

#: 采样的时刻。
#:
#: 动画的中间态才有话说——只在首帧末帧采，动画中途才冒出来的字
#: 就漏了。五个点把「进场 / 到位 / 退场」都盖住。
TIMES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)

#: 指纹里每一项的字段顺序。
FIELDS: tuple[str, ...] = (
    "x", "y", "size", "advance", "x0", "y0", "x1", "y1",
)


def _measure(ctx, s: str, x: float, y: float, size: float,
             anchor: str, bold: bool) -> list[float]:
    """量一行字的四类量。

    **横向偏移要跟 `draw.text` 算的一模一样**（它用 `.width` 而不是
    步进宽度来居中），不然量出来的轮廓位置跟画出来的位置对不上。

    记的是**落笔点 (x, y)**——场景代码算出来的那个，纯算术，跨机完全
    一致；调整过的笔位不用记，它已经体现在轮廓包围盒里了。
    """
    ctx.select_font_face(
        fonts.font_family(),
        cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    ctx.set_font_size(size)
    extents = ctx.text_extents(s)
    origin = x
    if anchor == "center":
        origin = x - extents.width / 2
    elif anchor == "right":
        origin = x - extents.width
    ctx.new_path()
    ctx.move_to(origin, y)
    ctx.text_path(s)
    x0, y0, x1, y1 = ctx.path_extents()
    ctx.new_path()
    return [
        round(x, 3), round(y, 3),
        round(size, 3), round(extents.x_advance, 3),
        round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3),
    ]


class TextProbe:
    """插桩：记录每次绘制的文字的指纹量。

    **只量不画**：量完就把这一行跳过，画不画对指纹没有影响，
    而整轮采集要跑 360 帧，少画一遍就快一截。
    """

    def __init__(self) -> None:
        self.items: list[list[float]] = []
        self.texts: list[str] = []

    def text(self, ctx, s, x, y, size, color, anchor="left", bold=False,
             alpha=1.0):
        if s and s.strip():
            self.items.append(_measure(ctx, s, x, y, size, anchor, bold))
            self.texts.append(s)
        return None


def _alias_modules(original) -> list:
    """把 `draw.text` 别名成自己 `text` 属性的模块。

    **只认「同一个函数对象」**：别名的定义就是「还是那个函数」，
    按名字找会误伤（某个模块自己定义了一个同名的 `text`）。
    """
    out = []
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        if not (name == "pyv" or name.startswith("pyv.")):
            continue
        if getattr(module, "text", None) is original:
            out.append(module)
    return out


def _probe_frame(module, params, width: int, height: int,
                 t: float) -> TextProbe:
    """渲染一帧，把这一帧画出去的字都记下来。

    `module` 是场景模块（`pyv.scenes.xxx`），它自己绑定过 `draw.text`，
    所以别名扫描会把它一起算进去。
    """
    probe = TextProbe()
    original = draw.text
    draw.text = probe.text
    aliases = [m for m in _alias_modules(original) if m is not draw]
    for alias in aliases:
        alias.text = probe.text
    try:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        module.render(ctx, t, width, height, params)
    finally:
        draw.text = original
        for alias in aliases:
            alias.text = original
    return probe


def collect_segment(module, params, width: int, height: int,
                    t: float) -> list[list[float]]:
    """渲染一帧，返回这一帧里每次画字的指纹量。"""
    return _probe_frame(module, params, width, height, t).items


def collect_texts(module, params, width: int, height: int,
                  t: float) -> list[str]:
    """这一帧画出去的文字（给覆盖守卫用）。"""
    return _probe_frame(module, params, width, height, t).texts
