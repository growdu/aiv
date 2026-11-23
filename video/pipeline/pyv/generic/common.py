"""通用渲染器的共用件。

**这一层只做三件事**：把参数变成内容、把文字排成行、把块画出来。
版式常量留在这里，**文案一个字都不写死**——画面上的中文都来自契约
或母稿，系统提示用 ASCII（内置字体是按「仓库用到的字符」子集化的，
往画面模块里加汉字就意味着要重跑字体子集脚本）。

**排版的规矩**（与 `pyv/layout.py` 一致）：

- **宁可字小一点，也不能出框**——放不下就收字号（`layout.fit_size`）；
- 收到下限还放不下，就**明说还差多少**（ASCII 提示行），不静默截断；
- 竖版每一行都过一遍收字号，横版直接画（两个画幅的差别在版式层里，
  这里不重造）。
"""
from __future__ import annotations

import cairo

from pyv import draw
from pyv import fonts
from pyv import layout
from pyv import motherdoc
from pyv.params import MissingParam

#: 面板的底色（比画布底色深一档，让内容有块）。
PANEL_FILL = "#F4F6FA"

#: 面板的描边色。
PANEL_STROKE = "#D7DEE9"

#: 面板内文字的颜色。
PANEL_INK = "#1B2A47"

#: 面板内次要文字（提示行、说明行）。
#:
#: **别调得太浅**：次要文字也是给人读的，压在面板底色上要还有
#: 4.5:1 的对比度（`tests/test_generic_renderers.py` 的对比度守卫盯着）。
PANEL_MUTED = "#646E7E"

#: 面板四周的留白（像素）。
PANEL_PAD = 28.0

#: 代码/正文的基准字号（横版）。放不下会往下收。
BASE_SIZE = 34.0

#: 行高与字号的比例。
LINE_RATIO = 1.55


def content_of(params, kind: str, root=None) -> motherdoc.Block:
    """画面参数 → 母稿里的那一块。

    两种给法：`ref`（引用母稿里的块，规格 §5.3）或 `content`（直接给内容）。
    两种都没有就报错——**不许画一个空面板当画面**：那会让观众看到一段
    没有画面的旁白，而画面照样生成、时长照样对。
    """
    ref = params.get("ref")
    if ref:
        return motherdoc.resolve_ref(ref, kind, root=root)
    if "content" in params:
        return motherdoc.Block(
            kind=kind, nth=0, content=str(params["content"]),
            lang=str(params.get("lang") or ""))
    raise MissingParam(
        f"通用渲染器 {kind} 拿不到内容：params 里既没有 ref 也没有 content")


def text_width(ctx: cairo.Context, s: str, size: float,
               bold: bool = False) -> float:
    """量一行字的**墨迹**宽度（与画的时候用同一套度量）。"""
    return draw.text_width(ctx, s, size, bold=bold)


def advance_width(ctx: cairo.Context, s: str, size: float,
                  bold: bool = False) -> float:
    """量一行字的**步进宽度**（含空格）。

    **墨迹宽度量不出空格**：`text_extents().width` 是墨迹包围盒，
    行尾那个空格一个字宽都不占——按它排版，「SELECT id」会排成
    「SELECTid」。排版要按步进宽度算。
    """
    fonts.select_font(ctx, bold=bold)
    ctx.set_font_size(size)
    return ctx.text_extents(s).x_advance


def wrap_text(ctx: cairo.Context, s: str, size: float, max_width: float,
              bold: bool = False) -> list[str]:
    """把一段文字排成若干行。

    **中文逐字断，英文尽量在空格处断**——英文单词被劈成两半很难看，
    中文没有空格，逐字断才对。

    硬断（一个词都断不开）也是一种可能：宁可断在词中间，也不能出框。
    """
    lines: list[str] = []
    for paragraph in s.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            candidate = current + ch
            if current and advance_width(ctx, candidate, size, bold) > max_width:
                cut = current.rfind(" ")
                if cut > 0 and len(current) - cut <= 12:
                    lines.append(current[:cut].rstrip())
                    current = current[cut + 1:] + ch
                else:
                    lines.append(current)
                    current = ch
            else:
                current = candidate
        lines.append(current)
    return lines


def panel(ctx: cairo.Context, x: float, y: float, w: float, h: float,
          *, radius: float = 18.0, fill: str = PANEL_FILL,
          stroke: str = PANEL_STROKE, alpha: float = 1.0) -> None:
    """一块底色（圆角 + 描边）。

    **字要落在这块底色里**——守卫（`tests/scene_probe.py` 的 `overflows`）
    就是按「字落在托着它的那块底色里」判出框的。
    """
    draw.rounded_rect(ctx, x, y, w, h, radius, fill, alpha=alpha)
    draw.stroke_rect(ctx, x, y, w, h, radius, stroke, width=2.0, alpha=alpha)


def content_box(w: int, h: int) -> tuple[float, float, float, float]:
    """内容区（左边距起，右边让出平台 UI，竖版）。

    返回 `(x, y, 宽, 高)`。标题占的那一行不算在里面——
    有标题时调用方自己把上沿往下挪。
    """
    lay = layout.for_canvas(w, h)
    x = lay.content_left(w)
    width = lay.content_width(w)
    top = lay.content_top_px(h)
    bottom = lay.content_bottom_px(h)
    return x, top, width, bottom - top


def title_area(w: int, h: int) -> float:
    """有标题时，内容区从哪儿往下挪。"""
    lay = layout.for_canvas(w, h)
    return lay.content_top_px(h) + lay.TITLE_SIZE * 1.15


def fit_lines(ctx: cairo.Context, lines: list[str], box_h: float,
              size: float, floor: float = None) -> tuple[float, int]:
    """一批行放不下 → 收字号。返回 `(字号, 放得下的行数)`。

    **收到下限还放不下，就返回放得下的行数**——调用方要**明说**还差多少行，
    不许静默截断。
    """
    floor = layout.MIN_SIZE if floor is None else floor
    if not lines:
        return size, 0
    usable = box_h - 2 * PANEL_PAD
    current = size
    for _ in range(6):
        line_h = current * LINE_RATIO
        fits = int(usable // line_h) if line_h > 0 else 0
        if fits >= len(lines) or current <= floor:
            return max(current, floor), max(0, min(fits, len(lines)))
        current = max(floor, current * 0.85)
    line_h = current * LINE_RATIO
    fits = int(usable // line_h) if line_h > 0 else 0
    return current, max(0, min(fits, len(lines)))
