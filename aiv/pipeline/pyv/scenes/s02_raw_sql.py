"""段 B：原样发一段文本的模板。

左边写进日志，右边收到同一段文本——中间什么结构都没有。
这条最省事的路子，先把它画出来，后面的问题才好说。

版式在代码里，**这一期的文本、标签与文案在契约里**（`Scene.params`）。

**竖版（1080×1920）**：横版是左右两个盒子对坐、中间一条横箭头；
竖版改成上下两个盒子对立、中间一条竖箭头——同一段文本出现在
上下两端，一模一样，中间什么结构都没有。
"""
from __future__ import annotations

from pyv import easing
from pyv import scene_layout
from pyv.draw import arrow, rounded_rect, text
from pyv.palette import COLORS
from pyv.params import Params

REQUIRED = ("title", "ddl_text", "source_label", "wal_label", "target_label",
            "caption")

#: 两端盒子的宽。**盒子要装得下那一段文本**：芯片是盒子里的一块白底，
#: 文本再宽一点就会从芯片边上溢出去——白字压深蓝底，等于看不见。
BOX_W_RATIO = 0.32
#: 芯片与盒子边缘的留白（画幅比例）。之前是 0.05，芯片只剩 499 px，
#: 而「ALTER TABLE t ADD COLUMN c int;」28 px 实测就是 499 px——
#: 左右一点留白都没有，文首压住左边框、文末被右边框切成一半。
CHIP_INSET_RATIO = 0.012
#: 芯片里的字与芯片边缘的留白。
CHIP_PADDING = 12.0
#: 芯片里的字有多大（装不下就往下收）。
CHIP_TEXT_SIZE = 28


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    p = Params(params, "s02")
    if h > w:
        _render_vertical(ctx, t, w, h, p)
        return

    ddl = str(p["ddl_text"])

    text(ctx, p["title"], w * 0.06, h * 0.145, 58, COLORS["primary"], bold=True)

    box_y = h * 0.30
    box_h = h * 0.30
    box_w = w * BOX_W_RATIO
    inset = w * CHIP_INSET_RATIO
    chip_w = box_w - 2 * inset

    # ---- 两端 ----
    for index, (label, x) in enumerate((
            (str(p["source_label"]), w * 0.06),
            (str(p["target_label"]), w * 0.62))):
        appear = easing.ease_out_cubic(
            max(0.0, min(1.0, (t - 0.08 - index * 0.18) * 3.0))
        )
        rounded_rect(ctx, x, box_y, box_w, box_h, 16, COLORS["primary"],
                     alpha=appear)
        text(ctx, label, x + box_w / 2, box_y + h * 0.075, 38, "#FFFFFF",
             anchor="center", bold=True, alpha=appear)
        # 里面就是那一段文本
        chip_y = box_y + h * 0.12
        chip_h = h * 0.11
        rounded_rect(ctx, x + inset, chip_y, chip_w, chip_h, 10,
                     "#FFFFFF", alpha=0.92 * appear)
        # 放不下就把字号往下收——宁可字小一点，也不能从芯片边上溢出去。
        scene_layout.line(ctx, ddl, x + box_w / 2, chip_y + chip_h * 0.68,
                          chip_w - 2 * CHIP_PADDING, CHIP_TEXT_SIZE,
                          COLORS["primary"], anchor="center", alpha=appear)

    # ---- 中间：写进日志，原样发过去 ----
    lane_y = box_y + box_h * 0.5
    arrow(ctx, w * 0.40, lane_y, w * 0.60, lane_y, COLORS["accent"], 7, 24)
    text(ctx, p["wal_label"], w * 0.50, lane_y - h * 0.045, 38, COLORS["accent"],
         anchor="center", bold=True)

    text(ctx, p["caption"], w * 0.06, h * 0.86, 44, COLORS["primary"])


def _render_vertical(ctx, t: float, w: int, h: int, p: Params) -> None:
    """竖版：上下两个盒子对坐，中间一段竖箭头。

    两个盒子都占满内容区宽度，那一段文本在上下两端各出现一次，
    两次一模一样——中间那条箭头就是全部的「结构」。
    """
    ddl = str(p["ddl_text"])

    left = w * scene_layout.MARGIN_X
    content_w = scene_layout.content_width(w)

    scene_layout.title(ctx, p["title"], w, h)

    box_h = 320.0
    chip_h = 130.0

    # ---- 两端 ----
    for index, (label, y) in enumerate((
            (str(p["source_label"]), 250.0),
            (str(p["target_label"]), 790.0))):
        appear = easing.ease_out_cubic(
            max(0.0, min(1.0, (t - 0.08 - index * 0.18) * 3.0))
        )
        rounded_rect(ctx, left, y, content_w, box_h, 16, COLORS["primary"],
                     alpha=appear)
        scene_layout.line(ctx, label, left + content_w / 2, y + 70,
                          content_w - 80, 40, "#FFFFFF", anchor="center",
                          bold=True, alpha=appear)
        # 里面就是那一段文本
        chip_y = y + 120
        rounded_rect(ctx, left + 40, chip_y, content_w - 80, chip_h, 10,
                     "#FFFFFF", alpha=0.92 * appear)
        scene_layout.line(ctx, ddl, left + content_w / 2, chip_y + 85,
                          content_w - 160, 34, COLORS["primary"],
                          anchor="center", alpha=appear)

    # ---- 中间：写进日志，原样发过去 ----
    # 这一行用主色而不是 accent：橙色小字压在白底上太轻，手机上快看不清；
    # 橙色留给箭头。
    scene_layout.line(ctx, p["wal_label"], left + content_w / 2, 660,
                      content_w - 80, 38, COLORS["primary"], anchor="center",
                      bold=True)
    arrow(ctx, left + content_w / 2, 690, left + content_w / 2, 780,
          COLORS["accent"], 7, 24)

