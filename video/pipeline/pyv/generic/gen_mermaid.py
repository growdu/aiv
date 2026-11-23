"""mermaid 图：渲染成 PNG 贴进画面；渲染不出来就**看得见地**降级。

**降级是必须的一条路**，不是边角情形：母稿里约 8% 的 mermaid 图解析不出来
（规格 §6.2）。渲染不出来时画面上要画出**图表源码**与**失败原因**——
静默跳过会让观众看到一段没有画面的旁白，而成片照样生成、时长照样对。

**渲染只跑一次**：PNG 按源码 hash 缓存（`pyv/mermaid.py`），进程内再缓存一次
（失败也缓存）——不然每一帧都要重跑 mermaid-cli，一段十秒的画面就是几百次。
"""
from __future__ import annotations

import cairo

from pyv import draw
from pyv import layout
from pyv import mermaid
from pyv.generic import common
from pyv.palette import COLORS
from pyv.params import Params

#: 内容来自 `ref` 或 `content`，两者都没有时由 `common.content_of` 报错。
REQUIRED = ()

#: 降级提示的颜色。
NOTICE_COLOR = COLORS["accent"]

#: 图表源码的颜色（降级时画的那段字）。
SOURCE_INK = common.PANEL_INK

#: 进程内的缓存：源码指纹 → 渲染结果（**失败的也缓存**）。
_ASSETS: dict[str, mermaid.MermaidAsset] = {}


def asset_for(source: str) -> mermaid.MermaidAsset:
    """渲染一张图（进程内缓存，失败也缓存）。"""
    key = mermaid.mermaid_key(source)
    cached = _ASSETS.get(key)
    if cached is not None:
        return cached
    asset = mermaid.render_one(source)
    _ASSETS[key] = asset
    return asset


def _draw_png(ctx: cairo.Context, png, x: float, y: float, box_w: float,
               box_h: float) -> None:
    """把 PNG 等比缩放贴进内容区（居中）。"""
    image = cairo.ImageSurface.create_from_png(str(png))
    iw, ih = image.get_width(), image.get_height()
    if iw <= 0 or ih <= 0:
        raise ValueError("图是空的")
    limit_w = box_w - 2 * common.PANEL_PAD
    limit_h = box_h - 2 * common.PANEL_PAD
    scale = min(limit_w / iw, limit_h / ih)
    width = iw * scale
    height = ih * scale
    ctx.set_source_surface(image, x + (box_w - width) / 2,
                           y + (box_h - height) / 2)
    ctx.paint()


def _draw_degraded(ctx: cairo.Context, source: str, reason: str, x: float,
                   y: float, box_w: float, box_h: float) -> None:
    """降级：画出图表源码 + 失败原因。"""
    common.panel(ctx, x, y, box_w, box_h)

    inner_x = x + common.PANEL_PAD
    inner_w = box_w - 2 * common.PANEL_PAD
    inner_y = y + common.PANEL_PAD
    inner_h = box_h - 2 * common.PANEL_PAD

    size = common.BASE_SIZE * 0.8
    notice = f"mermaid failed: {reason}"
    notice_lines = common.wrap_text(ctx, notice, size * 0.7, inner_w)
    source_lines = common.wrap_text(ctx, source, size, inner_w)

    # 提示行占的高度要留出来——源码不许把提示行顶出去。
    notice_h = len(notice_lines) * size * 0.7 * common.LINE_RATIO
    room = max(0.0, inner_h - notice_h)
    line_h = size * common.LINE_RATIO
    fits = max(0, int(room // line_h))

    baseline = inner_y + size
    for index, line in enumerate(source_lines[:fits]):
        draw.text(ctx, line, inner_x, baseline + index * line_h, size,
                  SOURCE_INK)

    dropped = len(source_lines) - fits
    notice_text = notice if dropped <= 0 else f"{notice} (+{dropped} lines)"
    baseline = inner_y + inner_h - notice_h + size * 0.7
    for index, line in enumerate(notice_lines):
        draw.text(ctx, line, inner_x, baseline + index * size * 0.7
                  * common.LINE_RATIO, size * 0.7, NOTICE_COLOR)


def render(ctx, t: float, w: int, h: int, params=None) -> None:
    """画一张图。`t` 不参与——通用渲染器不自己做动画。"""
    p = Params(params, "gen_mermaid")
    block = common.content_of(p, "mermaid")
    lay = layout.for_canvas(w, h)

    title = str(p.get("title") or "")
    if title:
        lay.title(ctx, title, w, h)

    x, top, box_w, box_h = common.content_box(w, h)
    if title:
        top = common.title_area(w, h)
        box_h = lay.content_bottom_px(h) - top

    asset = asset_for(block.content)
    if asset.png is not None and asset.png.is_file():
        try:
            common.panel(ctx, x, top, box_w, box_h)
            _draw_png(ctx, asset.png, x, top, box_w, box_h)
            return
        except (cairo.Error, ValueError):
            # PNG 读不出来（文件坏了）——照样降级，不静默跳过。
            pass

    _draw_degraded(ctx, block.content, asset.error or "unknown error",
                   x, top, box_w, box_h)
