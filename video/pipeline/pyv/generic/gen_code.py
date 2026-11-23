"""代码块：母稿里的代码直接变成画面。

**内容从母稿取**（`ref` 或 `content`），**语言标注决定词法**——
```python 的块按 Python 高亮，```sql 的块按 SQL 高亮，
不认识的语言按纯文本画（不猜：猜错了高亮全是错的颜色）。

**排版的三条规矩**：

- **字号统一**——代码块里的字号必须一样，逐行收字号会让这段代码参差不齐；
- **放不下就往下收**，收到下限还放不下就**明说还差几行**（不许静默截断）；
- **一行太长就换行**，换行之后的那几行不不高亮（高亮是按整行切的，
  折行的高亮会串色）。
"""
from __future__ import annotations

import cairo

from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.token import Token
from pygments.util import ClassNotFound

from pyv import draw
from pyv import layout
from pyv.generic import common
from pyv.palette import COLORS
from pyv.params import Params

#: 内容来自 `ref` 或 `content`，两者都没有时由 `common.content_of` 报错。
REQUIRED = ()

#: pygments 的 token → 颜色。够用就好——高亮是为了看得懂，不是为了炫。
#:
#: **键是 token 类型本身，不是它的名字**：pygments 的 token 打印出来是
#: `Token.Keyword`，按字符串查表永远查不到——查不到就全退回正文色，
#: 高亮看着像没生效（每一段代码都是同一种深色）。
TOKEN_COLORS = {
    Token.Keyword: COLORS["primary"],
    Token.Keyword.Constant: COLORS["primary"],
    Token.Keyword.Type: COLORS["primary"],
    Token.String: "#2F855A",
    Token.Literal.Number: "#B7791F",
    Token.Comment: "#8A94A6",
    Token.Name.Function: "#6B46C1",
    Token.Name.Class: "#6B46C1",
    Token.Name.Builtin: "#2C7A7B",
    Token.Operator: "#4A5568",
    Token.Name: common.PANEL_INK,
    Token.Text: common.PANEL_INK,
}

#: 提示行（还差几行、什么语言）的颜色。
NOTICE_COLOR = COLORS["accent"]


def _lexer_for(lang: str):
    """按语言标注取词法。取不到就 `None`（按纯文本画）。"""
    if not lang:
        return None
    try:
        return get_lexer_by_name(lang)
    except ClassNotFound:
        return None


def _token_color(token) -> str:
    """token → 颜色。按 token 的**族**逐级往上找。

    `Token.Keyword.Constant` 往上找是 `Token.Keyword`——键与值都是
    pygments 的 token 类型（`Token.Keyword in TOKEN_COLORS` 这种比较
    才对得上；拿字符串比永远比不上）。
    """
    current = token
    while current is not None:
        if current in TOKEN_COLORS:
            return TOKEN_COLORS[current]
        current = current.parent
    return common.PANEL_INK


def _runs_by_line(code: str, lexer) -> list[list[tuple[object, str]]]:
    """整段代码 → 逐行的 token 片段。

    **整段一起词法分析**（不是一行一行）：多行字符串与块注释跨行，
    逐行分析会把它们截断。
    """
    code = code.replace("\t", "    ")
    if lexer is None:
        return [[(None, line)] for line in code.split("\n")]
    lines: list[list[tuple[object, str]]] = [[]]
    for token, value in lex(code, lexer):
        parts = value.split("\n")
        for index, part in enumerate(parts):
            if index:
                lines.append([])
            if part:
                lines[-1].append((token, part))
    return lines


def _plain(lines: list[list[tuple[object, str]]]) -> list[str]:
    return ["".join(part for _, part in runs) for runs in lines]


def _fit(ctx: cairo.Context, raw: list[str],
         runs_by_line: list[list[tuple[object, str]]], inner_w: float,
         box_h: float, base_size: float) -> tuple[float, list[tuple[str, object]],
                                                  int]:
    """把代码块排进面板。返回 `(字号, 显示用的行, 放不下的行数)`。

    字号取两个方向的较小值：竖着放得下（高度）、横着放得下（宽度）。
    横着放不下的行会**折行**（不截断）；折完还放不下，就报还差几行。

    每行带着自己的 token 片段；折出来的续行没有高亮（`None`）。
    """
    size = base_size
    for _ in range(5):
        # 竖着放不下 → 收字号
        _, fits = common.fit_lines(ctx, raw, box_h, size)
        if fits >= len(raw):
            break
        size = max(layout.MIN_SIZE, size * 0.85)
        if size <= layout.MIN_SIZE:
            break

    # 横着放不下 → 收字号（折行是最后一步）
    widest = max((common.advance_width(ctx, line, size) for line in raw),
                 default=0.0)
    if widest > inner_w and widest > 0:
        size = max(layout.MIN_SIZE, size * inner_w / widest)

    display: list[tuple[str, object]] = []
    for index, line in enumerate(raw):
        if common.advance_width(ctx, line, size) <= inner_w:
            display.append((line, runs_by_line[index]))
        else:
            for part in common.wrap_text(ctx, line, size, inner_w):
                display.append((part, None))

    _, fits = common.fit_lines(ctx, [text for text, _ in display], box_h, size)
    return size, display, max(0, len(display) - fits)


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    """画一段代码。`t` 不参与——通用渲染器不自己做动画（那是分镜的事）。"""
    p = Params(params, "gen_code")
    block = common.content_of(p, "code")
    lay = layout.for_canvas(w, h)

    title = str(p.get("title") or "")
    if title:
        lay.title(ctx, title, w, h)

    x, top, box_w, box_h = common.content_box(w, h)
    if title:
        top = common.title_area(w, h)
        box_h = lay.content_bottom_px(h) - top

    inner_x = x + common.PANEL_PAD
    inner_w = box_w - 2 * common.PANEL_PAD
    inner_h = box_h - 2 * common.PANEL_PAD

    lexer = _lexer_for(block.lang)
    runs_by_line = _runs_by_line(block.content, lexer)
    raw_lines = _plain(runs_by_line)
    size, display, dropped = _fit(ctx, raw_lines, runs_by_line, inner_w,
                                  inner_h, common.BASE_SIZE)

    line_h = size * common.LINE_RATIO
    # **面板贴着内容长**：一屏代码三行，面板却占满整屏——那不是代码块，
    # 是一块空地。
    panel_h = min(box_h, len(display) * line_h + 2 * common.PANEL_PAD)
    common.panel(ctx, x, top, box_w, panel_h)

    inner_y = top + common.PANEL_PAD
    baseline = inner_y + size
    for index, (line, runs) in enumerate(display):
        if index * line_h + size > inner_h:
            break
        if runs is None:
            draw.text(ctx, line, inner_x, baseline + index * line_h, size,
                      common.PANEL_INK)
            continue
        cursor = inner_x
        for token, value in runs:
            draw.text(ctx, value, cursor, baseline + index * line_h, size,
                      _token_color(token))
            cursor += common.advance_width(ctx, value, size)

    # 语言标注（右上角）——让人知道这段是什么语言的代码。
    if block.lang:
        draw.text(ctx, block.lang, x + box_w - common.PANEL_PAD * 1.2,
                  top + common.PANEL_PAD * 1.1, size * 0.62,
                  common.PANEL_MUTED, anchor="right")

    # **放不下的部分要看得见**：不许静默截断。
    if dropped > 0:
        draw.text(ctx, f"+{dropped} more lines", inner_x,
                  top + panel_h - common.PANEL_PAD * 0.5, size * 0.8,
                  NOTICE_COLOR)
