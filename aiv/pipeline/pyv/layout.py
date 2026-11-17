"""画幅级的版式常量与共用绘制入口。

**这一层是「搬运」不是「规范化」。**

横版的历史取值本来就是混的——左边距有 0.06 也有 0.07，标题基线有 0.15
也有 0.16。把它们统一成一个值就是改画面，逐像素基准会红。所以这里的规矩是：

- 常量的值**精确等于现状**，一个都不许动；
- 历史上不同的取值收成**不同的常量**（而不是抹平成一个）；
- **位置仍然属于分镜**：场景用自己的坐标，版式层给的是画幅级的默认值
  与绘制入口。新场景作者从常量表里挑值，而不是随手写 `h * 0.145`。

**两个画幅**：

| | `layout.H` | `layout.V` |
| --- | --- | --- |
| 尺寸 | 1920×1080 | 1080×1920 |
| 用在哪 | 视频号 / B站 | 抖音 |
| 文字要不要收字号 | **不要** | 要（`fit_size`） |
| 右侧让位 | 不让 | 120px（平台 UI） |

**文字要不要收字号这一条是刻意不同的**：横版场景历来直接画字、不收，
竖版每一行都要过一遍 `fit_size`（「宁可字小一点，也不能出框」）。
统一成一种就是改画面——竖版的字会变小，或者横版的字会出框。
`CanvasLayout.fits_text` 把这个差别显式写出来，而不是藏在两处实现里。

**绘制调用一律走 `draw.<函数>` 的模块属性访问**（不是 `from pyv.draw import text`）。
理由：`tests/test_scene_overlap.py` 靠给 `draw.text` / `draw.arrow` 打桩来
记录画面上画过的字与箭头；模块属性访问在调用时才解析，打桩才拦得住。
场景模块自己 `from pyv.draw import text` 绑定的仍是导入时的那个函数，
所以守卫照样要逐个场景模块补桩——两套机制各管各的。
"""
from __future__ import annotations

import cairo

from pyv import draw
from pyv import easing
from pyv import fonts
from pyv.palette import COLORS

#: 收束句浮出用的斜率：场景进度的 1/CLOSING_SLOPE 走完 0 → 1。
CLOSING_SLOPE = 8.0


def closing_alpha(t: float, ready_at: float,
                  slope: float = CLOSING_SLOPE) -> float:
    """收束句（画面底部那行总结）的不透明度。

    **收束句在它指认的东西都出齐之后才浮出，浮出之后一直不透明。**

    两个毛病是同一条毛病的两头：

    - **早浮出**：画面上已经写着「这四条短板」，卡却只摆了三张——
      观众先读到结论，再等证据。
    - **晚浮出**：淡入斜率太缓，这句总结到场景结束都没亮透。
      s05_layers 那一段就是：`(t - 0.80) * 5.0` 走完要 0.2 个场景进度，
      而场景只剩 0.2——这句总结**一次都没亮全过**。

    所以这里给的是「不透明度」，不是一条淡入曲线：`ready_at` 之前是 0
    （一个字都不画），之后按 `slope` 走一遍 `ease_out_cubic`，走完就是 1，
    一直保持到场景结束。

    `ready_at` 由每个场景自己算——它知道自己的东西什么时候出齐
    （`pyv/scenes/` 里那些 `closing_ready()`）。
    """
    return easing.ease_out_cubic(max(0.0, min(1.0, (t - ready_at) * slope)))


class CanvasLayout:
    """一个画幅的版式常量与绘制入口。"""

    def __init__(
        self,
        name: str,
        width: int,
        height: int,
        *,
        margin_x: float,
        title_x: float,
        title_y: float,
        title_size: float,
        caption_y: float,
        caption_size: float,
        content_top: float,
        content_bottom: float,
        rail_right: float,
        fits_text: bool,
    ) -> None:
        self.NAME = name
        self.WIDTH = width
        self.HEIGHT = height
        self.MARGIN_X = margin_x
        self.TITLE_X = title_x
        self.TITLE_Y = title_y
        self.TITLE_SIZE = title_size
        self.CAPTION_Y = caption_y
        self.CAPTION_SIZE = caption_size
        self.CONTENT_TOP = content_top
        self.CONTENT_BOTTOM = content_bottom
        self.RAIL_RIGHT = rail_right
        self.FITS_TEXT = fits_text

    # ---- 几何 ----------------------------------------------------------

    def content_width(self, w: int | None = None) -> float:
        """内容区的宽度：左边距起，右边让出平台 UI 的按钮栏。"""
        width = self.WIDTH if w is None else w
        return width * (1 - self.MARGIN_X) - self.RAIL_RIGHT

    def content_left(self, w: int | None = None) -> float:
        """内容区的左边缘。"""
        width = self.WIDTH if w is None else w
        return width * self.MARGIN_X

    def content_right(self, w: int | None = None) -> float:
        """内容区的右边缘（平台 UI 预留之前那条线）。"""
        return self.content_left(w) + self.content_width(w)

    def content_top_px(self, h: int | None = None) -> float:
        """内容区的上沿（像素）。"""
        height = self.HEIGHT if h is None else h
        return height * self.CONTENT_TOP

    def content_bottom_px(self, h: int | None = None) -> float:
        """内容区的下沿（像素）。"""
        height = self.HEIGHT if h is None else h
        return height * self.CONTENT_BOTTOM

    # ---- 绘制 ----------------------------------------------------------

    def title(
        self,
        ctx: cairo.Context,
        text_value: str,
        w: int,
        h: int,
        *,
        x_ratio: float | None = None,
        y_ratio: float | None = None,
        size: float | None = None,
        color: str | None = None,
        bold: bool = True,
        alpha: float = 1.0,
    ) -> None:
        """这一档的标题。

        `x_ratio` / `y_ratio` / `size` 不给就用画幅级的默认值；给了就是
        **这个分镜自己的位置**——横版各场景的标题基线本来就不统一
        （0.15 与 0.16 都有），版式层不替它们做主。
        """
        x = w * (self.TITLE_X if x_ratio is None else x_ratio)
        y = h * (self.TITLE_Y if y_ratio is None else y_ratio)
        line_size = self.TITLE_SIZE if size is None else size
        line_color = COLORS["primary"] if color is None else color
        if self.FITS_TEXT:
            self.line(ctx, text_value, x, y, self.content_width(w),
                      line_size, line_color, bold=bold, alpha=alpha)
        else:
            draw.text(ctx, text_value, x, y, line_size, line_color,
                      bold=bold, alpha=alpha)

    def caption(
        self,
        ctx: cairo.Context,
        text_value: str,
        w: int,
        h: int,
        *,
        x_ratio: float | None = None,
        size: float | None = None,
        color: str | None = None,
        alpha: float = 1.0,
    ) -> None:
        """这一档底部的说明行（只有横版有——竖版底部让给字幕）。"""
        x = w * (self.MARGIN_X if x_ratio is None else x_ratio)
        y = h * self.CAPTION_Y
        line_size = self.CAPTION_SIZE if size is None else size
        line_color = COLORS["primary"] if color is None else color
        if self.FITS_TEXT:
            self.line(ctx, text_value, x, y, self.content_width(w),
                      line_size, line_color, alpha=alpha)
        else:
            draw.text(ctx, text_value, x, y, line_size, line_color, alpha=alpha)

    def line(
        self,
        ctx: cairo.Context,
        s: str,
        x: float,
        y: float,
        max_width: float,
        size: float,
        color: str,
        *,
        bold: bool = False,
        alpha: float = 1.0,
        anchor: str = "left",
    ) -> None:
        """一行字。收不收字号看这一档画幅的 `FITS_TEXT`。"""
        if self.FITS_TEXT:
            fitted = fit_size(ctx, s, max_width, size, bold=bold)
        else:
            fitted = size
        draw.text(ctx, s, x, y, fitted, color, anchor=anchor, bold=bold,
                  alpha=alpha)


#: 横版（1920×1080）：视频号 / B站那一档。
#:
#: 取值来自横版现状：标题字号 60（三处一致）、标题基线 0.15（两处 0.15、
#: 一处 0.16，默认取众数）、左边距 0.06（仓库里 56 处）、
#: 说明行基线 0.86、说明行字号 44。
H = CanvasLayout(
    "horizontal",
    1920,
    1080,
    margin_x=0.06,
    title_x=0.06,
    title_y=0.15,
    title_size=60,
    caption_y=0.86,
    caption_size=44,
    content_top=0.25,
    content_bottom=0.86,
    rail_right=0,
    fits_text=False,
)

#: 竖版（1080×1920）：抖音那一档。
#:
#: **与原 `scene_layout.py` 的常量一字不差**——那边是竖版的唯一事实源，
#: 这边只是把两个画幅摆到同一个屋檐下。
V = CanvasLayout(
    "vertical",
    1080,
    1920,
    margin_x=0.06,
    title_x=0.06,
    title_y=0.075,
    title_size=68,
    caption_y=0.86,
    caption_size=44,
    content_top=0.130,
    content_bottom=0.700,
    rail_right=120,
    fits_text=True,
)


def for_canvas(width: int, height: int) -> CanvasLayout:
    """按画布尺寸挑一个画幅。

    **判据只看高宽比**，不认画布名字——以后加 4:5 之类的档，
    场景不用改。
    """
    return V if height > width else H


#: 字号收小的下限。再小就不是「字」了，宁可让版式重排。
MIN_SIZE = 20.0


def _select_face(ctx: cairo.Context, bold: bool) -> None:
    """把 ctx 的字体族设成**画的时候真正用的那一个**。

    `draw.text` 画之前会自己 `fonts.select_font(...)`，所以量宽度必须用
    同一个族与同一个字重——量出来的宽度要和画出来的宽度一致，否则
    「收字号」就是在跟一个假的宽度较劲。

    **走 `fonts.select_font` 而不是直接 `ctx.select_font_face`**：那边
    顺带把 hinting 关掉，量出来的宽度才是「只由字体文件决定」的宽度
    （见 `pyv/fonts.py` 里的说明）。
    """
    fonts.select_font(ctx, bold=bold)


def _ink_extent(ctx: cairo.Context, s: str, size: float,
                bold: bool) -> float:
    """从落笔点算起，这行字的墨迹右沿有多远。

    **量的是墨迹右沿，不是步进宽度。** cairo 的 `text_extents().width`
    是墨迹包围盒的宽，`x_bearing` 是从落笔点到最左墨迹的距离——
    两者相加才是墨迹真正占到的右沿（实测中文左边距约 2 px）。
    少算这一截，字就会画出框外几个像素。
    """
    _select_face(ctx, bold)
    ctx.set_font_size(size)
    ext = ctx.text_extents(s)
    return ext.x_bearing + ext.width


def fit_size(ctx: cairo.Context, s: str, max_width: float, size: float,
             floor: float = MIN_SIZE, bold: bool = False) -> float:
    """把字号往下收，直到这行字放得进 `max_width`。

    **宁可字小一点，也不能出框。** 出框的标题在手机上就是「被裁掉
    半个字」，而渲染图上一眼看不出来——画面照样生成、时长照样对。

    **测量前必须先选定字体族**（见 `_select_face`）：cairo 的 toy API
    默认族是 sans，没有中文字形，量中文只能量到 .notdef 的宽度——
    实测只有真实宽度的 63%。拿这个宽度去收字号，中文标题就会被判成
    「放得下」，实际画出去却是出框的。

    **要迭代，不能只缩一次。** 字体 hinting 会把每个字的步进宽度取整，
    所以「宽度正比于字号」只是近似：缩一次之后量出来仍可能超几个像素。
    所以收完再量一次，直到真的放下。
    """
    if not s or size <= floor:
        return floor
    for _ in range(4):
        extent = _ink_extent(ctx, s, size, bold)
        if extent <= max_width or extent <= 0:
            break
        size = max(floor, size * max_width / extent)
        if size <= floor:
            break
    return size
