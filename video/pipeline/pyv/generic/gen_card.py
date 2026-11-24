"""章节卡 / 要点卡：一块通用的「标题 + 要点」版式。

**内容全在契约里**（`title` / `subtitle` / `items`）——通用渲染器不写死
任何一句文案（这是仓库的老规矩：文案归契约，版式常量留代码）。

**排版的规矩**：

- 卡片竖着**居中**——一张卡在画面中间比顶在上边好看；
- **标题压在深色小牌上**（不是整张卡涂成深色）：卡片本身是浅底，
  标题是深底白字，要点是浅底深字——深底浅字与浅底深字两套对比，
  混在一张卡上就会有一半读不出来；
- 要点逐条排版，**装不下就收字号**；
- 要点里的长句会**折行**，折行后仍然挂在同一个项目符号下；
- 一条要点都没有时，**只画卡头**（那就是「章节卡」），不炸。
"""
from __future__ import annotations

import cairo

from pyv import draw
from pyv import layout
from pyv.generic import common
from pyv.palette import COLORS
from pyv.params import Params

#: 卡片必填标题。
REQUIRED = ("title",)

#: 标题牌底色与文字色。
HEADER_FILL = COLORS["primary"]
HEADER_INK = "#FFFFFF"

#: 标题牌左右留白（字离牌边多远）。
CHIP_PAD = 20.0

#: 项目符号的颜色与大小。
BULLET_COLOR = COLORS["accent"]
BULLET_SIZE = 12.0

#: 项目符号与文字之间的间距。
BULLET_GAP = 26.0

#: 要点文字的颜色。
ITEM_INK = common.PANEL_INK

#: 标题牌高度相对字号的比例。
CHIP_RATIO = 1.9

#: 副标题字号相对正文字号的比例。
SUBTITLE_RATIO = 0.72

#: 副标题那一行的高度相对副标题字号的比例。
SUBTITLE_LINE_RATIO = 1.6


def _items_of(p) -> list[str]:
    """要点列表。字符串当一条；不是列表就当一条。"""
    raw = p.get("items")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item) for item in raw]


def _fit_title(ctx: cairo.Context, title: str, size: float,
               max_w: float) -> float:
    """标题太宽就收字号——标题牌放不下就得缩，牌不许越出卡片。"""
    for _ in range(4):
        width = common.advance_width(ctx, title, size, bold=True)
        if width <= max_w or width <= 0:
            break
        size = max(layout.MIN_SIZE, size * max_w / width)
    return size


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    """画一张卡。`t` 不参与——通用渲染器不自己做动画。"""
    p = Params(params, "gen_card")
    title = str(p["title"])
    subtitle = str(p.get("subtitle") or "")
    items = _items_of(p)

    x, top, box_w, box_h = common.content_box(w, h)
    pad = common.PANEL_PAD
    inner_w = box_w - 2 * pad
    text_w = inner_w - BULLET_GAP

    size = common.BASE_SIZE
    title_size = _fit_title(ctx, title, size, inner_w - 2 * CHIP_PAD)

    def _wrap_all(current: float) -> list[tuple[str, bool]]:
        """要点 → `(行, 是不是这条要点的头一行)`。"""
        out: list[tuple[str, bool]] = []
        for item in items:
            parts = common.wrap_text(ctx, item, current, text_w) or [""]
            for index, part in enumerate(parts):
                out.append((part, index == 0))
        return out

    wrapped = _wrap_all(size)

    def _metrics(current: float, lines: list[tuple[str, bool]]) -> tuple:
        chip_h = title_size * CHIP_RATIO
        sub_size = current * SUBTITLE_RATIO
        sub_h = sub_size * SUBTITLE_LINE_RATIO if subtitle else 0.0
        line_h = current * common.LINE_RATIO
        body_h = len(lines) * line_h + 2 * pad if lines else 0.0
        card_h = pad + chip_h + sub_h + body_h
        return chip_h, sub_size, sub_h, line_h, body_h, card_h

    chip_h, sub_size, sub_h, line_h, body_h, card_h = _metrics(size, wrapped)

    # 装不下 → 收字号（最多收到下限）。
    for _ in range(6):
        if card_h <= box_h:
            break
        nxt = max(layout.MIN_SIZE, size * 0.85)
        if nxt >= size:
            break
        size = nxt
        title_size = _fit_title(ctx, title, size, inner_w - 2 * CHIP_PAD)
        wrapped = _wrap_all(size)
        chip_h, sub_size, sub_h, line_h, body_h, card_h = _metrics(size, wrapped)

    # 竖着居中。
    y = top + max(0.0, (box_h - card_h) / 2)

    # 卡片本体：浅底 + 描边。
    common.panel(ctx, x, y, box_w, card_h)

    # 标题牌：深色小牌，白字。
    chip_y = y + pad
    chip_w = min(inner_w,
                 common.advance_width(ctx, title, title_size, bold=True)
                 + 2 * CHIP_PAD)
    draw.rounded_rect(ctx, x + pad, chip_y, chip_w, chip_h, 10.0, HEADER_FILL)
    draw.text(ctx, title, x + pad + CHIP_PAD, chip_y + chip_h * 0.72,
              title_size, HEADER_INK, bold=True)

    # 副标题：单独一行，不跟要点挤在一起。
    if subtitle:
        draw.text(ctx, subtitle, x + pad, chip_y + chip_h + sub_size * 1.05,
                  sub_size, common.PANEL_MUTED)

    if not items:
        return

    text_x = x + pad + BULLET_GAP
    baseline = chip_y + chip_h + sub_h + pad + size
    for line, is_first in wrapped:
        if is_first:
            draw.rounded_rect(ctx, x + pad + 2, baseline - size * 0.72,
                              BULLET_SIZE, BULLET_SIZE, BULLET_SIZE / 2,
                              BULLET_COLOR)
        draw.text(ctx, line, text_x, baseline, size, ITEM_INK)
        baseline += line_h
