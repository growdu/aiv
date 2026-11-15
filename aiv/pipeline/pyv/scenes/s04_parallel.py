"""段 D：多路并行分支模板。

左边一个来源方，中间一列并行分支，右边一个汇聚方。
版式在代码里，**这一期的数量与文案在契约里**（`Scene.params`）。

**竖版（1080×1920）**：横版是「来源在左、分支在中、汇聚在右」三栏并排；
竖版只有 1080 宽，三栏并排每栏只剩 300 宽，标签全得缩。
竖版改成上下三段：来源一条横带、四个分支并排一行、汇聚一条横带，
箭头竖着走（见 `pyv/scene_layout.py` 的三条规矩）。
"""
from __future__ import annotations

from pyv import easing
from pyv import scene_layout
from pyv.draw import arrow, rounded_rect, text
from pyv.palette import COLORS
from pyv.params import Params

REQUIRED = ("title", "source_label", "source_sub", "worker_count",
            "worker_prefix", "target_label", "target_sub", "caption")

# 竖版：上下三段的版式常量（像素——竖版只有这一档画布）。
#
# **箭头段从 154 收到 100**：三条带之间不留大白，链路才连成一条。
V_SOURCE_TOP, V_SOURCE_H = 250, 280
V_ARROW_H = 100
V_WORKER_TOP, V_WORKER_H = 630, 300
V_TARGET_TOP, V_TARGET_H = 1030, 280
V_WORKER_GAP_RATIO = 0.021    # 分支之间的列距（相对内容区宽度）


def worker_count(params=None) -> int:
    """并行分支的数量。"""
    p = Params(params, "s04")
    return int(p["worker_count"])


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    p = Params(params, "s04")
    if h > w:
        _render_vertical(ctx, t, w, h, p)
        return

    text(ctx, p["title"], w * 0.06, h * 0.15, 60, COLORS["primary"], bold=True)

    # 来源方
    rounded_rect(ctx, w * 0.05, h * 0.26, w * 0.19, h * 0.24, 18, COLORS["primary"])
    text(ctx, p["source_label"], w * 0.145, h * 0.41, 48, "#FFFFFF", anchor="center")
    text(ctx, p["source_sub"], w * 0.145, h * 0.545, 28, COLORS["primary"], anchor="center")

    # 并行分支
    worker_h = h * 0.115
    worker_gap = h * 0.04
    top = h * 0.20
    for i in range(worker_count(params)):
        y = top + i * (worker_h + worker_gap)
        delay = 0.10 * i
        grow = easing.ease_out_cubic(max(0.0, min(1.0, (t - delay) * 3.0)))
        box_w = w * 0.17 * (0.4 + 0.6 * grow)
        rounded_rect(ctx, w * 0.47, y, box_w, worker_h,
                     14, COLORS["secondary"])
        # 标签跟着盒子一起长：居中于当前盒子宽度，盒子没展开到位就先不显示
        label_alpha = max(0.0, min(1.0, (grow - 0.55) / 0.45))
        text(ctx, f"{p['worker_prefix']} {i + 1}", w * 0.47 + box_w / 2, y + worker_h * 0.68,
             34, "#FFFFFF", anchor="center", alpha=label_alpha)

        arrow(ctx, w * 0.25, h * 0.38, w * 0.46, y + worker_h / 2,
              COLORS["accent"], 5, 16)
        arrow(ctx, w * 0.65, y + worker_h / 2, w * 0.72, h * 0.50,
              COLORS["secondary"], 4, 14)

    # 汇聚方
    rounded_rect(ctx, w * 0.73, h * 0.30, w * 0.19, h * 0.40, 18, "#DCE1E8")
    text(ctx, p["target_label"], w * 0.825, h * 0.50, 40, COLORS["primary"], anchor="center")
    text(ctx, p["target_sub"], w * 0.825, h * 0.60, 28, COLORS["secondary"], anchor="center")

    text(ctx, p["caption"], w * 0.06, h * 0.86, 44, COLORS["primary"])


def _render_vertical(ctx, t: float, w: int, h: int, p: Params) -> None:
    """竖版：来源在上、并行分支在中间一行、汇聚在下。

    **字号不缩、框变宽**：来源与汇聚各占一条整行（内容区宽 895），
    分支并排一行、每个 205 宽，标签字号跟横版同档。

    **链路要连成一条**：带与带之间只留 100px 给箭头（原来留 154），
    三条带从 250 排到 1310，整条链路贯穿内容区，不再散成三段图。
    """
    left = scene_layout.content_left(w)
    width = scene_layout.content_width(w)
    right = left + width

    scene_layout.title(ctx, p["title"], w, h)

    # ---- 来源方：一条横带 ----
    src_y, src_h = V_SOURCE_TOP, V_SOURCE_H
    rounded_rect(ctx, left, src_y, width, src_h, 18, COLORS["primary"])
    baseline = src_y + src_h * 0.63
    scene_layout.line(ctx, p["source_label"], left + width * 0.045, baseline,
                      width * 0.45, 52, "#FFFFFF", bold=True)
    scene_layout.line(ctx, p["source_sub"], right - width * 0.045, baseline,
                      width * 0.35, 34, "#FFFFFF", anchor="right")

    # ---- 并行分支：并排一行 ----
    count = int(p["worker_count"])
    gap = width * V_WORKER_GAP_RATIO
    box_w = (width - (count - 1) * gap) / count
    worker_y, worker_h = V_WORKER_TOP, V_WORKER_H
    for i in range(count):
        cx = left + i * (box_w + gap)
        delay = 0.10 * i
        grow = easing.ease_out_cubic(max(0.0, min(1.0, (t - delay) * 3.0)))
        box_h = worker_h * (0.4 + 0.6 * grow)
        rounded_rect(ctx, cx, worker_y, box_w, box_h, 14, COLORS["secondary"])
        # 标签跟着盒子一起长：盒子没展开到位就先不显示
        label_alpha = max(0.0, min(1.0, (grow - 0.55) / 0.45))
        scene_layout.line(ctx, f"{p['worker_prefix']} {i + 1}", cx + box_w / 2,
                          worker_y + worker_h * 0.52, box_w, 40, "#FFFFFF",
                          alpha=label_alpha, anchor="center")
        # 来源 → 分支：竖着的箭头，从来源带底边落到分支顶边
        arrow(ctx, cx + box_w / 2, src_y + src_h + 12,
              cx + box_w / 2, worker_y - 12, COLORS["accent"], 5, 16)
        # 分支 → 汇聚：从分支底边落到汇聚带顶边
        arrow(ctx, cx + box_w / 2, worker_y + worker_h + 12,
              cx + box_w / 2, V_TARGET_TOP - 12, COLORS["secondary"], 4, 14)

    # ---- 汇聚方：一条横带 ----
    tgt_y, tgt_h = V_TARGET_TOP, V_TARGET_H
    rounded_rect(ctx, left, tgt_y, width, tgt_h, 18, "#DCE1E8")
    baseline = tgt_y + tgt_h * 0.63
    scene_layout.line(ctx, p["target_label"], left + width * 0.045, baseline,
                      width * 0.45, 48, COLORS["primary"], bold=True)
    scene_layout.line(ctx, p["target_sub"], right - width * 0.045, baseline,
                      width * 0.35, 34, COLORS["secondary"], anchor="right")

