"""段 E：六层一览模板。

六行，每行一层：层号徽标 + 机制名 + 这层管住什么。
从上到下就是链路本身的顺序，逐层点亮——观众跟着出现顺序读，不用一次全看完。

版式在代码里，**这一期的层号、机制名与作用说明在契约里**（`Scene.params`）。

**竖版（1080×1920）**：横版一行是「徽标 + 机制名 + 作用」三样并排，竖版
只有 1080 宽，并排会把作用说明压到放不下——所以每层改成两行：徽标在左，
机制名与作用说明上下摞在右边（见 `pyv/scene_layout.py` 的三条规矩）。
"""
from __future__ import annotations

from pyv import easing
from pyv import layout
from pyv import scene_layout
from pyv.draw import rounded_rect, text
from pyv.palette import COLORS
from pyv.params import Params

REQUIRED = ("title", "layer_ids", "layer_names", "layer_roles", "caption")

# 版式常量：每层一行，行的起点与步长
#
# **六行整体上收**：原来最后一行（L6）的底在 0.822h = 888 px，而收束句
# 的基线固定在 0.86h = 929 px——上下只差 5 px，那句总结读起来像 L6 这一行
# 的说明。上收到 0.19h 起步、步长 0.096、每行 0.078，最后一行落在 0.748h
# = 808 px，收束句与它隔开 84 px。
ROW_TOP = 0.19
ROW_STEP = 0.096
ROW_H = 0.078
# 层与层之间的点亮间隔（场景进度）：六层铺满整个场景，读完一层才出下一层
#
# **间隔收窄、点亮变快**：原来间隔 0.12、点亮斜率 3.5，最后一层要到
# t=0.886 才亮齐——收束句根本没有出场的时间。现在间隔 0.075、斜率 6.0，
# 最后一层 t=0.542 就亮齐，收束句 t=0.542 之后浮出，亮透之后还剩
# 1.05 秒（这一段只有 3.24 s）。
ROW_STAGGER = 0.075
ROW_SPEED = 6.0


def layer_count(params=None) -> int:
    """层数。"""
    p = Params(params, "s05")
    return len(p["layer_ids"])


def closing_ready(count: int) -> float:
    """收束句最早能出场的时刻：最后一层亮齐之后。"""
    return ROW_STAGGER * max(0, count - 1) + 1.0 / ROW_SPEED


def _appear(t: float, index: int) -> float:
    """第 index 层的不透明度。"""
    return easing.ease_out_cubic(
        max(0.0, min(1.0, (t - ROW_STAGGER * index) * ROW_SPEED)))


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    p = Params(params, "s05")
    if h > w:
        _render_vertical(ctx, t, w, h, p)
        return
    ids = [str(x) for x in p["layer_ids"]]
    names = [str(x) for x in p["layer_names"]]
    roles = [str(x) for x in p["layer_roles"]]

    text(ctx, p["title"], w * 0.06, h * 0.13, 58, COLORS["primary"], bold=True)

    for index in range(layer_count(params)):
        y = h * ROW_TOP + index * h * ROW_STEP
        row_h = h * ROW_H
        appear = _appear(t, index)
        badge = COLORS["accent"] if index % 2 == 0 else COLORS["secondary"]
        rounded_rect(ctx, w * 0.07, y, w * 0.066, row_h, 10, badge, alpha=appear)
        text(ctx, ids[index], w * 0.103, y + row_h * 0.66, 34, "#FFFFFF",
             anchor="center", bold=True, alpha=appear)
        text(ctx, names[index], w * 0.16, y + row_h * 0.64, 40,
             COLORS["primary"], bold=True, alpha=appear)
        text(ctx, roles[index], w * 0.42, y + row_h * 0.64, 33,
             COLORS["secondary"], alpha=appear)

    # 收束句最后才出，六层亮完再落一句——亮透之后一直亮着（见 layout.closing_alpha）
    closing = layout.closing_alpha(t, closing_ready(len(ids)))
    text(ctx, p["caption"], w * 0.06, h * 0.86, 44, COLORS["primary"],
         alpha=closing)


def _render_vertical(ctx, t: float, w: int, h: int, p: Params) -> None:
    """竖版：六层，每层一块卡片，徽标在左、机制名与作用上下摞。

    横版一行是三样并排，竖版只有 1080 宽，并排会把作用说明挤到放不下
    （这一期的说明最长 13 个字，横版占 0.26w，竖版放不下）——所以每层
    改成两行：

    - **字号不缩、框变宽**：卡片撑满 0.88w，机制名 40、作用 32，
      都比横版大一号。
    - **字要放得下**：每一行字都过 `scene_layout.line`。
    """
    ids = [str(x) for x in p["layer_ids"]]
    names = [str(x) for x in p["layer_names"]]
    roles = [str(x) for x in p["layer_roles"]]

    left = w * scene_layout.MARGIN_X
    max_width = scene_layout.content_width(w)

    scene_layout.title(ctx, p["title"], w, h, size=60)

    row_top = h * 0.127
    row_h = h * 0.078
    row_gap = h * 0.0052
    badge_w = w * 0.078
    badge_h = h * 0.0437
    text_x = left + badge_w + w * 0.030

    for index in range(len(ids)):
        y = row_top + index * (row_h + row_gap)
        appear = _appear(t, index)
        badge = COLORS["accent"] if index % 2 == 0 else COLORS["secondary"]
        rounded_rect(ctx, left, y, max_width, row_h, 12, "#F2F5F9", alpha=appear)
        badge_y = y + (row_h - badge_h) / 2
        rounded_rect(ctx, left + w * 0.020, badge_y, badge_w, badge_h, 10,
                     badge, alpha=appear)
        scene_layout.line(ctx, ids[index], left + w * 0.020 + badge_w / 2,
                          badge_y + badge_h * 0.70, badge_w, 34, "#FFFFFF",
                          anchor="center", bold=True, alpha=appear)
        scene_layout.line(ctx, names[index], text_x, y + h * 0.0315,
                          max_width - (text_x - left) - w * 0.020, 40,
                          COLORS["primary"], bold=True, alpha=appear)
        scene_layout.line(ctx, roles[index], text_x, y + h * 0.0612,
                          max_width - (text_x - left) - w * 0.020, 32,
                          COLORS["secondary"], alpha=appear)

