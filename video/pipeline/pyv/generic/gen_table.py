"""表格：母稿里的表格直接变成画面。

**内容从母稿取**（`ref` 或 `content`），解析的是 markdown 表格
（表头 + 分隔行 + 数据行）。母稿里的表格行本来就是要给人看的，
这里只是把它排成画面。

**排版的四条规矩**：

- **列宽按内容算**——某一列的字多，那一列就宽；
- **总宽超了按比例收**，收到底（字号下限）还超，就**明说收不下**；
- **字号统一**——一张表里字号必须一样；
- **放不下的行要看得见**（`+N rows`），不许静默截断。
"""
from __future__ import annotations

import re

import cairo

from pyv import draw
from pyv import layout
from pyv.generic import common
from pyv.palette import COLORS
from pyv.params import Params

#: 内容来自 `ref` 或 `content`，两者都没有时由 `common.content_of` 报错。
REQUIRED = ()

#: markdown 的分隔行（`| --- | :---: |`）。
SEPARATOR_RE = re.compile(r"^:?-{2,}:?$")

#: 单元格左右留白。
CELL_PAD = 16.0

#: 表头底色与表头文字色。
HEADER_FILL = COLORS["primary"]
HEADER_INK = "#FFFFFF"

#: 数据行的两种底色（隔行换色，长表格看得清行）。
ROW_FILLS = ("#FFFFFF", "#F1F4F9")

#: 单元格文字颜色。
CELL_INK = common.PANEL_INK

#: 提示行的颜色。
NOTICE_COLOR = COLORS["accent"]

#: 一列最窄多少（像素）——窄到放不下一个字的列没有意义。
MIN_COL_W = 60.0


def parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """markdown 表格 → `(表头, 数据行)`。

    分隔行（`| --- |`）不算数据行。列数按表头定——数据行短了补空，
    长了截到表头的列数（多出来的那格是母稿写错了，不该画到画面上）。
    """
    rows: list[list[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    if not rows:
        raise ValueError("表格块里没有表格行")
    header = rows[0]
    body: list[list[str]] = []
    for row in rows[1:]:
        if row and all(SEPARATOR_RE.match(cell) for cell in row):
            continue
        body.append(row[:len(header)] + [""] * max(0, len(header) - len(row)))
    return header, body


def _column_widths(ctx: cairo.Context, header: list[str],
                   body: list[list[str]], size: float) -> list[float]:
    """每一列要多宽（字宽 + 留白）。"""
    widths = []
    for index, name in enumerate(header):
        widest = common.advance_width(ctx, name, size, bold=True)
        for row in body:
            if index < len(row):
                widest = max(widest, common.advance_width(ctx, row[index], size))
        widths.append(max(MIN_COL_W, widest + 2 * CELL_PAD))
    return widths


def _fit(ctx: cairo.Context, header: list[str], body: list[list[str]],
         inner_w: float, inner_h: float,
         base_size: float) -> tuple[float, list[float], int]:
    """字号与列宽。返回 `(字号, 列宽, 放不下的行数)`。

    宽与高两个方向都要装下——装不下的方向按比例收字号，
    收到下限还是装不下，就报放不下的行数。
    """
    size = base_size
    for _ in range(6):
        widths = _column_widths(ctx, header, body, size)
        total_w = sum(widths)
        row_h = size * 1.8
        total_h = row_h * (len(body) + 1)
        too_wide = total_w > inner_w
        too_tall = total_h > inner_h
        if not too_wide and not too_tall:
            break
        factor = 1.0
        if too_wide:
            factor = min(factor, inner_w / total_w)
        if too_tall:
            factor = min(factor, inner_h / total_h)
        nxt = max(layout.MIN_SIZE, size * factor * 0.98)
        if nxt >= size:
            break
        size = nxt

    widths = _column_widths(ctx, header, body, size)
    # 列宽按比例收一收，铺满可用宽度（多出来的还给右边）。
    total = sum(widths)
    if total > inner_w and total > 0:
        widths = [max(MIN_COL_W, width * inner_w / total) for width in widths]
    elif 0 < total < inner_w:
        # **表格铺满内容区**：三列短表格缩在左边、右边空一大块，
        # 看着像没排完。富余的宽度按列的比例分下去。
        widths = [width * inner_w / total for width in widths]

    row_h = size * 1.8
    fits = max(0, int(inner_h // row_h) - 1)  # 表头占一行
    return size, widths, max(0, len(body) - fits)


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    """画一张表。`t` 不参与——通用渲染器不自己做动画。"""
    p = Params(params, "gen_table")
    block = common.content_of(p, "table")
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
    inner_y = top + common.PANEL_PAD
    inner_h = box_h - 2 * common.PANEL_PAD

    header, body = parse_table(block.content)
    size, widths, dropped = _fit(ctx, header, body, inner_w, inner_h,
                                 common.BASE_SIZE)

    row_h = size * 1.8
    # **面板贴着表格长**：三行的表占满一屏，那不是表格，是一块空地。
    shown = max(1, len(body) - dropped)
    panel_h = min(box_h, (shown + 1) * row_h + 2 * common.PANEL_PAD)
    common.panel(ctx, x, top, box_w, panel_h)

    # 表头
    draw.rounded_rect(ctx, inner_x, inner_y, sum(widths), row_h, 8.0,
                      HEADER_FILL)
    cursor = inner_x
    for index, name in enumerate(header):
        draw.text(ctx, name, cursor + CELL_PAD, inner_y + row_h * 0.72, size,
                  HEADER_INK, bold=True)
        cursor += widths[index]

    # 数据行
    for row_index, row in enumerate(body[:shown]):
        y = inner_y + row_h * (row_index + 1)
        fill = ROW_FILLS[row_index % len(ROW_FILLS)]
        draw.rounded_rect(ctx, inner_x, y, sum(widths), row_h, 6.0, fill)
        cursor = inner_x
        for index, cell in enumerate(row):
            draw.text(ctx, cell, cursor + CELL_PAD, y + row_h * 0.72, size,
                      CELL_INK)
            cursor += widths[index]

    if dropped > 0:
        draw.text(ctx, f"+{dropped} rows", inner_x,
                  top + panel_h - common.PANEL_PAD * 0.5, size * 0.8,
                  NOTICE_COLOR)
