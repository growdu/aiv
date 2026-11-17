"""场景插桩：把一帧里画过的字、实心底色与箭头都记下来。

**为什么要有这一层。** 画面上的缺陷有三类，三类都得**量**：

| 缺陷 | 怎么量 | 谁在管 |
| --- | --- | --- |
| 字↔字、字↔箭头 | 两处墨迹包围盒求交 | `test_scene_overlap.py` |
| 字↔自己那块底色 | 字落在托着它的**最紧**那块底色里 | `test_text_fits_chip.py` |
| 元素↔它出现的时间 | 记下每一处东西的不透明度，比「谁先亮」 | `test_closing_caption.py` |

第三类只有这一层管。**顺序不对的动画，单帧看着全对**——收束句先亮、
箭头指向还没出现的东西，画面照样生成、时长照样对，逐帧看图才发现。

**一处插桩，各处复用。** 场景模块各自 `from pyv.draw import text`
（导入时绑定的），所以补桩要逐个模块补——见 `probe_frame`。
"""
from __future__ import annotations

import cairo

from pyv import draw, fonts, scene_layout

#: 画幅
LANDSCAPE = (1920, 1080)
PORTRAIT = (1080, 1920)

#: 扫的时刻：0.00 到 1.00，步长 0.05。
#:
#: 一段动画的中间态才是出事的地方——只看首帧和末帧等于没看。
TIMES = tuple(round(i * 0.05, 2) for i in range(21))

#: 淡到多少以下就不算「看得见的东西」。
#:
#: 让位、影子、幽灵这些是背景，它跟别的东西压在一起是**故意**的。
VISIBLE_ALPHA = 0.6

#: 墨迹允许比底色多出几像素（浮点与描边的余量）。
TOLERANCE = 0.5

#: 短边小于这个数的底色算「连接线」，不算「内容」。
#:
#: s05_scheduler 的提交通道底下压着一条 6 px 高的灰线，箭头的尖头正好
#: 落在这条线上——把它当成箭头指着的东西，这条线从第一帧起就是满的，
#: 于是「箭头不许早于它指着的东西」这条守卫就永远管不着真正的芯片了。
MIN_BLOCK_SIDE = 16.0


class Text:
    """一处字：墨迹包围盒 + 它自己的颜色、字号与不透明度。"""

    def __init__(self, label: str, x0: float, y0: float, x1: float, y1: float,
                 color: str, size: float = 0.0, alpha: float = 1.0):
        self.label = label
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.color = color
        self.size = size
        self.alpha = alpha

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def key(self) -> tuple:
        """跨帧认出「还是那一处字」。"""
        return ("text", self.label, round(self.x0, 1), round(self.y0, 1))

    def __repr__(self) -> str:
        return (f"<字「{self.label}」 {self.x0:.0f}→{self.x1:.0f} "
                f"@{self.y0:.0f}..{self.y1:.0f} a={self.alpha:.2f}>")


class Rect:
    """一块实心底色。"""

    def __init__(self, x: float, y: float, w: float, h: float, color: str,
                 alpha: float = 1.0):
        self.x0, self.y0 = x, y
        self.x1, self.y1 = x + w, y + h
        self.color = color
        self.alpha = alpha

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    @property
    def is_block(self) -> bool:
        """这块底色是不是「内容」（而不是一根连接线）。

        判据：短边不小于 `MIN_BLOCK_SIDE`。细长的灰线是轨道、是分隔，
        不是箭头指着的东西。
        """
        return min(self.x1 - self.x0, self.y1 - self.y0) >= MIN_BLOCK_SIDE

    def holds(self, text: Text) -> bool:
        """这块底色是不是托着这处字（按中心点判）。"""
        return (self.x0 <= text.cx <= self.x1
                and self.y0 <= text.cy <= self.y1)

    @property
    def key(self) -> tuple:
        """跨帧认出「还是那一块底色」。"""
        return ("rect", round(self.x0, 1), round(self.y0, 1),
                round(self.x1, 1), round(self.y1, 1))

    def __repr__(self) -> str:
        return (f"<底色 {self.x0:.0f},{self.y0:.0f}→{self.x1:.0f},{self.y1:.0f} "
                f"a={self.alpha:.2f}>")


class Arrow:
    """一条箭头：线段两头的坐标 + 它自己的不透明度。"""

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, alpha: float = 1.0):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.color = color
        self.alpha = alpha

    def __repr__(self) -> str:
        return (f"<箭头 {self.x1:.0f},{self.y1:.0f}→{self.x2:.0f},{self.y2:.0f} "
                f"a={self.alpha:.2f}>")


def ink_box(ctx: cairo.Context, s: str, x: float, y: float, size: float,
            anchor: str, bold: bool) -> tuple[float, float, float, float]:
    """量出这行字的**墨迹**包围盒。

    跟 `draw.text` 用同一套度量（`fonts.select_font` 关 hinting、
    `.width` 居中），不然量出来的位置跟画出来的位置对不上。
    """
    fonts.select_font(ctx, bold=bold)
    ctx.set_font_size(size)
    width = ctx.text_extents(s).width
    if anchor == "center":
        origin = x - width / 2
    elif anchor == "right":
        origin = x - width
    else:
        origin = x
    ctx.new_path()
    ctx.move_to(origin, y)
    ctx.text_path(s)
    x0, y0, x1, y1 = ctx.path_extents()
    ctx.new_path()
    return x0, y0, x1, y1


class Probe:
    """插桩：把这一帧画过的字、实心底色与箭头都记下来。"""

    def __init__(self, alpha_floor: float = VISIBLE_ALPHA):
        #: 淡到多少以下就不记（做时序的活儿要记到 0）。
        self.alpha_floor = alpha_floor
        self.texts: list[Text] = []
        self.rects: list[Rect] = []
        self.arrows: list[Arrow] = []

    # -- 记录 ----------------------------------------------------------
    def text(self, ctx, s, x, y, size, color, anchor="left", bold=False,
             alpha=1.0):
        if alpha >= self.alpha_floor and s.strip():
            x0, y0, x1, y1 = ink_box(ctx, s, x, y, size, anchor, bold)
            self.texts.append(Text(s, x0, y0, x1, y1, color, size, alpha))
        return None

    def rounded_rect(self, ctx, x, y, w, h, r, color, alpha=1.0):
        if alpha >= self.alpha_floor:
            self.rects.append(Rect(x, y, w, h, color, alpha))
        return None

    def arrow(self, ctx, x1, y1, x2, y2, color, width=6.0, head=22.0,
              alpha=1.0):
        if alpha >= self.alpha_floor:
            self.arrows.append(Arrow(x1, y1, x2, y2, color, alpha))
        return None

    # -- 判据 ----------------------------------------------------------
    def overflows(self) -> list[tuple[Text, Rect, float]]:
        """字从自己那块底色上溢出去的地方。

        判据：字落在**托着它的最紧那块底色**里（按中心点找，候选里
        面积最小的那个），但墨迹的左右两边超出了它。
        """
        hits = []
        for text in self.texts:
            candidates = [r for r in self.rects if r.holds(text)]
            if not candidates:
                continue
            tightest = min(candidates, key=lambda r: r.area)
            over = max(tightest.x0 - text.x0, text.x1 - tightest.x1)
            if over > TOLERANCE:
                hits.append((text, tightest, over))
        return hits


class Session:
    """一次插桩，画很多帧。

    **为什么不能一帧装一次。** `monkeypatch.setattr` 装第二次时，它包住
    的「原函数」已经是上一次装的那个——于是第二帧的记录会一层层落回
    第一帧的探针里。第一帧的探针最后装着全部 21 帧，做时序的活儿时
    看出来的就是「画面上同时有 21 个收束句」这种胡说。

    所以：**插桩装一次，每帧换一个探针**。
    """

    def __init__(self, monkeypatch, modules=(), alpha_floor: float = VISIBLE_ALPHA):
        self.alpha_floor = alpha_floor
        self.probe = Probe(alpha_floor=alpha_floor)
        self._install(monkeypatch, modules)

    def _install(self, monkeypatch, modules) -> None:
        original_text = draw.text
        original_rect = draw.rounded_rect
        original_arrow = draw.arrow
        session = self

        def recording_text(ctx, s, x, y, size, color, anchor="left", bold=False,
                           alpha=1.0):
            session.probe.text(ctx, s, x, y, size, color, anchor=anchor,
                               bold=bold, alpha=alpha)
            return original_text(ctx, s, x, y, size, color, anchor=anchor,
                                 bold=bold, alpha=alpha)

        def recording_rect(ctx, x, y, w, h, r, color, alpha=1.0):
            session.probe.rounded_rect(ctx, x, y, w, h, r, color, alpha=alpha)
            return original_rect(ctx, x, y, w, h, r, color, alpha=alpha)

        def recording_arrow(ctx, x1, y1, x2, y2, color, width=6.0, head=22.0,
                            alpha=1.0):
            session.probe.arrow(ctx, x1, y1, x2, y2, color, width=width,
                                head=head, alpha=alpha)
            return original_arrow(ctx, x1, y1, x2, y2, color, width=width,
                                  head=head, alpha=alpha)

        monkeypatch.setattr(draw, "text", recording_text)
        monkeypatch.setattr(draw, "rounded_rect", recording_rect)
        monkeypatch.setattr(draw, "arrow", recording_arrow)
        # `scene_layout.text` 是 `draw.text` 的别名，`scene_layout.line`
        # 走的就是它——不补这一处，走 `scene_layout.line` 画出来的字就
        # 一处都记不上。
        monkeypatch.setattr(scene_layout, "text", recording_text)
        for module in modules:
            if hasattr(module, "text"):
                monkeypatch.setattr(module, "text", recording_text)
            if hasattr(module, "rounded_rect"):
                monkeypatch.setattr(module, "rounded_rect", recording_rect)
            if hasattr(module, "arrow"):
                monkeypatch.setattr(module, "arrow", recording_arrow)

    def frame(self, renderer, params, t, w, h) -> Probe:
        """画一帧，返回这一帧记下来的东西。"""
        self.probe = Probe(alpha_floor=self.alpha_floor)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        renderer(ctx, t, w, h, params)
        return self.probe


def probe_frame(renderer, params, t, w, h, monkeypatch, modules=(),
                alpha_floor: float = VISIBLE_ALPHA) -> Probe:
    """画**一帧**，把这一帧的字、实心底色与箭头都记下来。

    **场景模块各自绑着 `draw.text` / `draw.rounded_rect`**
    （`from pyv.draw import …` 是在导入时绑定的），所以只补 `pyv.draw`
    是不够的——每个用到的模块都要单独补一遍。

    **要连着画很多帧就别用这个**，用 `Session`（见上面的说明）。
    """
    session = Session(monkeypatch, modules=modules, alpha_floor=alpha_floor)
    return session.frame(renderer, params, t, w, h)
