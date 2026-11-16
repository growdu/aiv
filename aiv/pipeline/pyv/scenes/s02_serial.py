"""段 B：串行排队模板。

左边一列积压块，中间一个处理方，右边一个接收方。
版式在代码里，**这一期的文字在契约里**（`Scene.params`）。

**竖版（1080×1920）**：横版是「左边积压列、中间解码器、右边接收方」
三栏并排；竖版只有 1080 宽，三栏会把每栏压到三分之一——所以改成
上下堆叠：五个积压块排成一行在最上，下面是唯一的解码线程，
再下面是接收方。

**这一版用了两个共用层**：
- `pyv.layout`：画幅级的版式常量与绘制入口（横版 H / 竖版 V）
- `pyv.components`：块、块排、箭头这些可复用的零件

**坐标一个都没改**——迁移只是把「手写的算术」换成「组件的算术」，
结果必须逐像素相同（`tests/test_contract.py` 的基准守着呢）。
"""
from __future__ import annotations

from pyv import components
from pyv import easing
from pyv import layout
from pyv import scene_layout
from pyv.draw import text
from pyv.palette import COLORS
from pyv.params import Params

REQUIRED = ("title", "decoder_label", "decoder_sub", "target_label", "caption")

QUEUE_COUNT = 5
QUEUE_COLORS = ("#F6AD55", "#F8C489", "#F6AD55", "#F8C489", "#F6AD55")


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    p = Params(params, "s02")
    if h > w:
        _render_vertical(ctx, t, w, h, p)
        return

    layout.H.title(ctx, p["title"], w, h, x_ratio=0.07, y_ratio=0.16,
                   color=COLORS["problem"])

    # 排队的事务块：越靠前越接近解码器
    progress = easing.ease_in_out(min(1.0, t * 1.5))
    blocks = components.column(h * 0.28, h * 0.485, QUEUE_COUNT, gap=h * 0.04)
    for i, ((y, block_h), color) in enumerate(zip(blocks, QUEUE_COLORS)):
        # 事务块朝解码器（右侧）推进，不能滑出画面左侧
        shift = progress * w * 0.065 * (i + 1) / QUEUE_COUNT
        components.block(ctx, w * 0.08 + shift, y, w * 0.20, block_h,
                         radius=10, fill=color)

    # 唯一的解码线程
    components.block(ctx, w * 0.36, h * 0.28, w * 0.17, h * 0.42,
                     radius=18, fill=COLORS["primary"])
    text(ctx, p["decoder_label"], w * 0.445, h * 0.53, 46, "#FFFFFF", anchor="center")
    text(ctx, p["decoder_sub"], w * 0.445, h * 0.60, 34, COLORS["secondary"], anchor="center")

    components.arrow_h(ctx, h * 0.49, w * 0.54, w * 0.73,
                       color=COLORS["primary"], width=8, head=24)

    # 接收方
    components.block(ctx, w * 0.75, h * 0.34, w * 0.18, h * 0.30,
                     radius=18, fill="#DCE1E8")
    text(ctx, p["target_label"], w * 0.84, h * 0.52, 40, COLORS["primary"], anchor="center")

    layout.H.caption(ctx, p["caption"], w, h, x_ratio=0.07)


def _render_vertical(ctx, t: float, w: int, h: int, p: Params) -> None:
    """竖版：积压块排成一行放在顶部，下面是解码线程，再下面是接收方。

    五个积压块在横版里本来就没有字（只是一列积压的形状），所以竖版
    把它们横着排成一行，靠宽度撑住；往下依次是那一个解码线程和
    接收方——排队这件事从上往下看更清楚。
    """
    left = scene_layout.content_left(w)
    content_w = scene_layout.content_width(w)

    layout.V.title(ctx, p["title"], w, h, color=COLORS["problem"])

    # 排队的事务块：越靠前越接近解码器
    block_y, block_h = 280.0, 130.0
    gap = 20.0
    progress = easing.ease_in_out(min(1.0, t * 1.5))
    blocks = components.row(left, content_w, QUEUE_COUNT, gap=gap)
    for i, ((x, block_w), color) in enumerate(zip(blocks, QUEUE_COLORS)):
        # 事务块朝解码器（下方）推进，不能滑出画面
        shift = progress * 70.0 * (i + 1) / QUEUE_COUNT
        components.block(ctx, x, block_y + shift, block_w, block_h,
                         radius=12, fill=color)

    # 唯一的解码线程
    app_y, app_h = 520.0, 270.0
    components.block(ctx, left, app_y, content_w, app_h,
                     radius=18, fill=COLORS["primary"])
    scene_layout.line(ctx, p["decoder_label"], left + content_w / 2,
                      app_y + 105, content_w - 80, 48, "#FFFFFF",
                      anchor="center", bold=True)
    scene_layout.line(ctx, p["decoder_sub"], left + content_w / 2,
                      app_y + 185, content_w - 80, 36, COLORS["secondary"],
                      anchor="center")

    components.arrow_v(ctx, left + content_w / 2, app_y + app_h, 900,
                       color=COLORS["primary"], width=8, head=24)

    # 接收方
    tgt_y, tgt_h = 910.0, 210.0
    components.block(ctx, left, tgt_y, content_w, tgt_h,
                     radius=18, fill="#DCE1E8")
    scene_layout.line(ctx, p["target_label"], left + content_w / 2,
                      tgt_y + 125, content_w - 80, 44, COLORS["primary"],
                      anchor="center")
