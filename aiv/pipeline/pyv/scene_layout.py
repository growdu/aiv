"""竖版（1080×1920）的版式件——现在是 `pyv.layout` 的兼容层。

**这个文件为什么还在**：26 个场景模块里有 23 个还没迁到新版式层，
它们 `from pyv import scene_layout` 之后用的是这里的 `title` / `line` /
`content_*`。与其一次改 23 个文件（改动面大、风险高），不如让这里
**转发**到 `layout.V`——常量与行为一字不差，场景一个字都不用动。

**真正的规矩在 `pyv/layout.py`**：两个画幅（横版 H / 竖版 V）的版式常量
与绘制入口都在那里，这里只是竖版那一档的旧名字。

**竖版的四条规矩**（见 `layout.V`）：

| 规矩 | 说明 |
| --- | --- |
| 字号不缩，框变宽 | 竖版画布只有 1080 宽，同一档字号相对画面更大 |
| 字要放得下 | 每行字都过一遍 `fit_size`——宁可字小一点，也不能出框 |
| 底部只留字幕 | 竖版不画说明行（说明行与字幕讲的是同一句话） |
| 右侧让出平台 UI | 右边让出 120px 的点赞/评论/分享栏 |

**竖版的三个位置**（比例相对画面高度 1920）：

| 位置 | 比例 | 像素 | 说明 |
| --- | --- | --- | --- |
| 标题基线 | 0.075 | 144 | 所有场景统一 |
| 内容区上沿 | 0.130 | 250 | 内容从这里开始 |
| 内容区下沿 | 0.700 | 1344 | 内容到这里为止 |
| 字幕带 | — | 1393 | 字幕烧在这里 |

**这些数字不是随手定的**：内容区下沿 1344 与字幕带 1393 之间留 49px，
画面内容掉下去就压在字幕上；右缘 960 与画面边缘 1080 之间是给按钮栏
预留的 120px。

**绘制调用走 `draw.<函数>` 的模块属性访问**（不是 `from pyv.draw import text`），
这样 `tests/test_scene_overlap.py` 给 `draw.text` 打桩才拦得住。
"""
from __future__ import annotations

import cairo

from pyv import draw
from pyv import layout
from pyv.palette import COLORS

# ---- 常量：从 layout.V 取，值一字不差 --------------------------------------

MARGIN_X = layout.V.MARGIN_X
TITLE_Y = layout.V.TITLE_Y
TITLE_SIZE = layout.V.TITLE_SIZE
CONTENT_TOP = layout.V.CONTENT_TOP
CONTENT_BOTTOM = layout.V.CONTENT_BOTTOM
RAIL_RIGHT = layout.V.RAIL_RIGHT
MIN_SIZE = layout.MIN_SIZE

#: `draw.text` 的别名。
#:
#: **这个属性必须留着**：`tests/test_scene_overlap.py` 靠给
#: `scene_layout.text` 打桩来记录画面上画过的字。少了它，守卫会在
#: 补桩那一步直接报错——宁可报错，也不要悄悄变成「什么都看不见」。
text = draw.text


# ---- 入口：转发到 layout.V -----------------------------------------------


def fit_size(ctx: cairo.Context, s: str, max_width: float, size: float,
             floor: float = MIN_SIZE, bold: bool = False) -> float:
    """把字号往下收，直到这行字放得进 `max_width`。"""
    return layout.fit_size(ctx, s, max_width, size, floor=floor, bold=bold)


def line(ctx: cairo.Context, s: str, x: float, y: float, max_width: float,
         size: float, color: str, bold: bool = False, alpha: float = 1.0,
         anchor: str = "left") -> None:
    """一行字：放不下就收字号。"""
    fitted = fit_size(ctx, s, max_width, size, bold=bold)
    text(ctx, s, x, y, fitted, color, anchor=anchor, bold=bold, alpha=alpha)


def title(ctx: cairo.Context, text_value: str, w: int, h: int,
          size: float = TITLE_SIZE, color: str = COLORS["primary"],
          bold: bool = True, alpha: float = 1.0) -> None:
    """竖版的标题：左对齐，与横版一样从边距起排。"""
    line(ctx, text_value, w * MARGIN_X, h * TITLE_Y, content_width(w),
         size, color, bold=bold, alpha=alpha)


def content_width(w: int) -> float:
    """内容区的宽度：左边距起，右边让出平台 UI 的按钮栏。"""
    return layout.V.content_width(w)


def content_left(w: int) -> float:
    """内容区的左边缘。"""
    return layout.V.content_left(w)


def content_right(w: int) -> float:
    """内容区的右边缘（平台 UI 预留之前那条线）。"""
    return layout.V.content_right(w)


def content_top(h: int) -> float:
    """内容区的上沿。"""
    return layout.V.content_top_px(h)


def content_bottom(h: int) -> float:
    """内容区的下沿。"""
    return layout.V.content_bottom_px(h)
