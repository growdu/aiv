"""芯片守卫：字不许从自己那块底色上溢出去。

**为什么要有这一条。** `tests/test_scene_overlap.py` 查的是「字↔字」与
「字↔箭头」——两处墨迹互相压住。它查不出**字↔自己那块底色**：字从芯片
边上溢出去，芯片还在那儿，别的字也没压着它，全绿。

**漏过去的三处（EP03 抽帧实看发现的）**：

| 场景 | 现象 |
| --- | --- |
| s03 操作芯片 | 「COMMIT」28 px 粗体墨迹 127.4 px，芯片只有 119.0 px——左右各溢出约 4 px，溢出的白字压在浅灰槽位面板上，对比度 1.05:1，等于消失，读出来是「OMMIT」加半个 T |
| s05 COMMIT 白芯片 | 芯片 124.8 px，文字 127.4 px——溢出的深蓝字压在深蓝订阅端上，完全看不见 |
| s02 的 SQL 芯片 | 芯片 499 px，文字实测也是 499 px——文首压住左边框，文末被右边框切成一半 |

**怎么查。** 插桩 `pyv.draw.text`（记墨迹包围盒）与 `pyv.draw.rounded_rect`
（记实心底色的矩形）：每处字找出**装着它的最紧的那块实心底色**，字必须
落在它里面。

**为什么找「最紧的」。** 一处字常常同时落在好几块底色上——s03 的操作字
既在芯片里，也在槽位面板里。要紧的是**它自己那块**（最小的那块）。

**覆盖。** 六期契约里的全部场景段，横竖两个画幅，跟
`test_scene_overlap.py` 一样扫 21 个时刻。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import cairo
import pytest

from pyv import contract as contract_mod
from pyv import draw, episodes as episodes_mod, fonts, scene_layout

ROOT = Path(__file__).resolve().parents[2]

LANDSCAPE = (1920, 1080)
PORTRAIT = (1080, 1920)

#: 扫的时刻：0.00 到 1.00，步长 0.05。
TIMES = tuple(round(i * 0.05, 2) for i in range(21))

#: 淡到多少以下就不算「看得见的东西」。
VISIBLE_ALPHA = 0.6

#: 墨迹允许比底色多出几像素（浮点与描边的余量）。
TOLERANCE = 0.5


class Text:
    """一处字：墨迹包围盒 + 它自己的颜色 + 画它时的字号。"""

    def __init__(self, s: str, x0: float, y0: float, x1: float, y1: float,
                 color: str, size: float = 0.0):
        self.label = s
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.color = color
        self.size = size

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def __repr__(self) -> str:
        return (f"<字「{self.label}」 {self.x0:.0f}→{self.x1:.0f} "
                f"@{self.y0:.0f}..{self.y1:.0f}>")


class Rect:
    """一块实心底色。"""

    def __init__(self, x: float, y: float, w: float, h: float, color: str):
        self.x0, self.y0 = x, y
        self.x1, self.y1 = x + w, y + h
        self.color = color

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def holds(self, text: Text) -> bool:
        """这块底色是不是托着这处字（按中心点判）。"""
        return (self.x0 <= text.cx <= self.x1
                and self.y0 <= text.cy <= self.y1)

    def __repr__(self) -> str:
        return f"<底色 {self.x0:.0f},{self.y0:.0f}→{self.x1:.0f},{self.y1:.0f}>"


def _ink_box(ctx, s: str, x: float, y: float, size: float,
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
    """插桩：把这一帧画过的字与实心底色都记下来。"""

    def __init__(self):
        self.texts: list[Text] = []
        self.rects: list[Rect] = []

    def text(self, ctx, s, x, y, size, color, anchor="left", bold=False,
             alpha=1.0):
        if alpha >= VISIBLE_ALPHA and s.strip():
            x0, y0, x1, y1 = _ink_box(ctx, s, x, y, size, anchor, bold)
            self.texts.append(Text(s, x0, y0, x1, y1, color, size))
        return None

    def rounded_rect(self, ctx, x, y, w, h, r, color, alpha=1.0):
        if alpha >= VISIBLE_ALPHA:
            self.rects.append(Rect(x, y, w, h, color))
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


def _probe_frame(renderer, params, t, w, h, monkeypatch, modules=()) -> Probe:
    """画一帧，把这一帧的字与实心底色都记下来。

    **场景模块各自绑着 `draw.text` / `draw.rounded_rect`**
    （`from pyv.draw import …` 是在导入时绑定的），所以只补 `pyv.draw`
    是不够的——每个用到的模块都要单独补一遍。
    """
    probe = Probe()
    original_text = draw.text
    original_rect = draw.rounded_rect

    def recording_text(ctx, s, x, y, size, color, anchor="left", bold=False,
                       alpha=1.0):
        probe.text(ctx, s, x, y, size, color, anchor=anchor, bold=bold,
                   alpha=alpha)
        return original_text(ctx, s, x, y, size, color, anchor=anchor,
                             bold=bold, alpha=alpha)

    def recording_rect(ctx, x, y, w, h, r, color, alpha=1.0):
        probe.rounded_rect(ctx, x, y, w, h, r, color, alpha=alpha)
        return original_rect(ctx, x, y, w, h, r, color, alpha=alpha)

    monkeypatch.setattr(draw, "text", recording_text)
    monkeypatch.setattr(draw, "rounded_rect", recording_rect)
    # `scene_layout.text` 是 `draw.text` 的别名，`scene_layout.line`
    # 走的就是它——不补这一处，走 `scene_layout.line` 画出来的字就
    # 一处都记不上。
    monkeypatch.setattr(scene_layout, "text", recording_text)
    for module in modules:
        if hasattr(module, "text"):
            monkeypatch.setattr(module, "text", recording_text)
        if hasattr(module, "rounded_rect"):
            monkeypatch.setattr(module, "rounded_rect", recording_rect)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    renderer(ctx, t, w, h, params)
    return probe


def _segments():
    """六期契约里的全部场景段（带契约里的真实文案）。"""
    for episode in episodes_mod.EPISODE_ORDER:
        contract = contract_mod.load_contract(
            ROOT / "contracts" / f"{episode}.json")
        for segment in contract.segments:
            yield episode, segment


def _render_segment(segment):
    """场景的画法 + 它自己绑着的模块（补桩要用）。"""
    module = importlib.import_module(segment.renderer)

    def renderer(ctx, t, w, h, params):
        module.render(ctx, t, w, h, params)

    return renderer, (module,)


SEGMENTS = list(_segments())
ORIENTATIONS = (("横版", LANDSCAPE), ("竖版", PORTRAIT))


@pytest.mark.parametrize("episode,segment", SEGMENTS,
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in SEGMENTS])
@pytest.mark.parametrize("orientation,canvas", ORIENTATIONS,
                         ids=[o for o, _ in ORIENTATIONS])
def test_text_stays_inside_its_own_background(episode, segment, orientation,
                                               canvas, monkeypatch):
    """字不许从自己那块底色上溢出去。"""
    w, h = canvas
    renderer, modules = _render_segment(segment)
    params = segment.params
    for t in TIMES:
        probe = _probe_frame(renderer, params, t, w, h, monkeypatch,
                             modules=modules)
        hits = probe.overflows()
        assert not hits, (
            f"{episode} {segment.id} {orientation} t={t}："
            + "；".join(
                f"「{text.label}」墨迹 {text.x0:.1f}→{text.x1:.1f} "
                f"越出 {rect.x0:.1f}→{rect.x1:.1f}（{rect.color}）"
                f"{over:.1f} px"
                for text, rect, over in hits
            )
        )


def _segment_of(episode: str, seg_id: str):
    for ep, segment in SEGMENTS:
        if ep == episode and segment.id == seg_id:
            return segment
    raise AssertionError(f"契约里没有 {episode} 的 {seg_id}")


def test_sql_chip_keeps_its_declared_font_size(monkeypatch):
    """SQL 芯片里的字不许被收小。

    **为什么上面那条守卫还不够。** 它查的是「字溢出芯片」。s02 的芯片
    装了 `fit_size`——放不下就把字号往下收，溢出是收得住的，可**收小
    是静默的**：28 px 悄悄变成 24 px，画面上看不出来，只是芯片里的字
    比旁边的字小一号。

    芯片装得下就该按原字号画；装不下要改的是**盒子**，不是字。
    """
    import pyv.scenes.s02_raw_sql as s02

    segment = _segment_of("structured-ddl", "s02")
    ddl = str(segment.params["ddl_text"])
    renderer, modules = _render_segment(segment)
    w, h = LANDSCAPE
    probe = _probe_frame(renderer, segment.params, 1.0, w, h, monkeypatch,
                         modules=modules)
    drawn = [t for t in probe.texts if t.label == ddl]
    assert drawn, f"画面上没画那段 SQL：{ddl}"
    for text in drawn:
        assert text.size == s02.CHIP_TEXT_SIZE, (
            f"SQL 被收小到 {text.size:.1f} px（应为 {s02.CHIP_TEXT_SIZE}）"
            "——盒子不够宽就加宽盒子，别收字"
        )
