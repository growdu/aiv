"""时序守卫：总结那句话不许早于它总结的东西，箭头不许早于它指着的东西。

**为什么要有这一条。** 画面上的缺陷有三类，此前只管了两类：

| 缺陷 | 谁在管 |
| --- | --- |
| 字↔字、字↔箭头（同一帧里的压盖） | `test_scene_overlap.py` |
| 字↔自己那块底色（同一帧里的溢出） | `test_text_fits_chip.py` |
| **谁先亮**（这一条） | 这里 |

**时序错了，单帧看着全对。** 收束句从 t=0 就满不透明地写着，而它指认的
四张卡要陆续淡入近 3 秒——单帧每一帧都合规，抽帧实看才发现「画面上写着
『这四条短板』，卡却只摆了三张半」。画面照样生成、时长照样对。

**四条规矩**：

1. **收束句不许早于画面上的其他东西**——它指认的内容亮齐之后才浮出；
2. **收束句要亮透着待够一阵子**——不能是永远半透明的影子
   （s05_layers 那句总结原来要到 t=1.0 才亮，等于一次都没亮全过）；
3. **收束句与上方那块内容要留得开**——5 px 的缝读起来就是一行；
4. **箭头不许比它指着的那块内容先亮**——箭头指着下一步，就得跟着下一步亮。

**覆盖。** 第 1~3 条管**自己声明了收束句出场时刻**（`closing_ready()`）
的场景段——别的场景的收束句还是从 t=0 就写死的，那是各期记录里
「优先修改」另一批改动，等它们也声明了，这里自动就管到。
第 4 条管全部场景段。
"""
from __future__ import annotations

import importlib
import math
from pathlib import Path

import pytest

from pyv import contract as contract_mod

from scene_probe import LANDSCAPE, PORTRAIT, TIMES, Session
import scene_segments

ROOT = Path(__file__).resolve().parents[2]

#: 收束句与上方内容之间至少留这么多像素。
#:
#: 原来 s05_layers 的收束句与 L6 徽标只差 5 px——在 1080 高的画面上，
#: 那句话读起来就是 L6 这一行的说明，不是全片的一句收束。
MIN_GAP = 40.0

#: 亮透算多少：1.0 才算亮透。
FULL = 0.99

#: 收束句至少要亮透这么长一段（相对场景进度）。
#:
#: 原来 s05_layers 那句总结的淡入斜率是 5.0，要到 t=1.0 才亮透——
#: 亮透的时长是 0，等于这句话一次都没完整出现过。
MIN_OPAQUE_SPAN = 0.15

#: 箭头与它指着的东西比，允许的误差。
ALPHA_TOLERANCE = 0.01


def _segments():
    """全部场景段（带契约里的真实文案）。

    磁盘上有期就读期目录里的契约；没有期就按场景模块合成一段
    （见 `scene_segments.py`）。
    """
    return scene_segments.segments()


def _module(segment):
    return importlib.import_module(segment.renderer)


def _render_segment(segment):
    """场景的画法 + 它自己绑着的模块（补桩要用）。"""
    module = _module(segment)

    def renderer(ctx, t, w, h, params):
        module.render(ctx, t, w, h, params)

    return renderer, (module,)


SEGMENTS = list(_segments())

#: 自己声明了收束句出场时刻的场景段。
DELAYED = [(ep, seg) for ep, seg in SEGMENTS
           if hasattr(_module(seg), "closing_ready")]

ORIENTATIONS = (("横版", LANDSCAPE), ("竖版", PORTRAIT))


def _frames(segment, canvas, monkeypatch):
    """把这一段扫一遍 21 个时刻，每一帧都插桩。

    **记到 alpha=0**：做时序的活儿要看得见「还没出现的东西」——
    淡到 0 以下的字不记的话，就没法判断「箭头指着的东西还没亮」。
    """
    renderer, modules = _render_segment(segment)
    w, h = canvas
    session = Session(monkeypatch, modules=modules, alpha_floor=0.0)
    return [session.frame(renderer, segment.params, t, w, h)
            for t in TIMES]


def _caption_of(probe, caption: str):
    """这一帧里的收束句。"""
    return [t for t in probe.texts if t.label == caption]


def _peaks(frames):
    """每处东西「最多能有多不透明」。

    **本来就是半透明的底要认出来**（比如 s02 那块白芯片是 0.92）——
    拿它当「亮齐了」的标准，就会把「底是半透明的」误判成
    「东西没亮」。
    """
    peak: dict = {}
    for probe in frames:
        for element in list(probe.texts) + list(probe.rects):
            peak[element.key] = max(peak.get(element.key, 0.0), element.alpha)
    return peak


@pytest.mark.parametrize("episode,segment", DELAYED,
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in DELAYED])
def test_closing_caption_waits_for_the_content(episode, segment, monkeypatch):
    """收束句不许早于画面上的其他东西。

    判据：收束句只要开始出现（alpha > 0），画面上别的、能亮透的东西
    就必须**已经亮透**（alpha ≥ 0.99）。

    **本来就半透明的底不算**（比如 s02 那块白芯片是 0.92）——
    拿它当标准会把「底是半透明的」误判成「东西没亮齐」。
    """
    caption = str(segment.params["caption"])
    frames = _frames(segment, LANDSCAPE, monkeypatch)
    peak = _peaks(frames)

    for t, probe in zip(TIMES, frames):
        for closing in _caption_of(probe, caption):
            if closing.alpha <= 0.0:
                continue
            for other in list(probe.texts) + list(probe.rects):
                if other.key == closing.key:
                    continue
                if peak[other.key] < FULL:
                    continue
                assert other.alpha >= FULL, (
                    f"{episode} {segment.id} t={t}：收束句"
                    f"「{closing.label}」开始出现（alpha={closing.alpha:.2f}），"
                    f"可「{other.label}」才亮到 {other.alpha:.2f}"
                    "——结论不许早于它总结的东西"
                )


@pytest.mark.parametrize("episode,segment", DELAYED,
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in DELAYED])
def test_closing_caption_stays_readable_long_enough(
        episode, segment, monkeypatch):
    """收束句要亮透着待够一阵子。

    **半透明的收束句等于没有。** s05_layers 原来那句总结的淡入斜率
    是 5.0，要到 t=1.0 才亮透——亮透的时长是 0，观众从头到尾没见过
    一句完整的话。

    判据：**亮透的那一段**（场景进度的比例）至少 `MIN_OPAQUE_SPAN`。
    """
    caption = str(segment.params["caption"])
    frames = _frames(segment, LANDSCAPE, monkeypatch)
    lit = [t for t, probe in zip(TIMES, frames)
           for closing in _caption_of(probe, caption)
           if closing.alpha >= FULL]
    assert lit, (
        f"{episode} {segment.id}：收束句「{caption}」从头到尾没亮透过"
        "——这句总结等于没写过"
    )
    span = lit[-1] - lit[0]
    assert span >= MIN_OPAQUE_SPAN, (
        f"{episode} {segment.id}：收束句只亮透了 {span:.2f} 的场景进度"
        f"（要 ≥ {MIN_OPAQUE_SPAN:.2f}）——这句话等于没写过"
    )


@pytest.mark.parametrize("episode,segment", DELAYED,
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in DELAYED])
def test_closing_caption_has_room_above_it(episode, segment, monkeypatch):
    """收束句与上方那块内容要留得开。

    判据：收束句的**墨迹上沿**与它上方最近的一块实心底色之间，
    至少留 `MIN_GAP` 像素。留不住，那句话读起来就是上一行的一部分。
    """
    caption = str(segment.params["caption"])
    frames = _frames(segment, LANDSCAPE, monkeypatch)
    last = frames[-1]
    drawn = _caption_of(last, caption)
    assert drawn, f"{episode} {segment.id}：画面上根本没有收束句「{caption}」"
    for closing in drawn:
        above = [r for r in last.rects if r.y1 <= closing.y0 + 1.0]
        bottom = max((r.y1 for r in above), default=0.0)
        gap = closing.y0 - bottom
        assert gap >= MIN_GAP, (
            f"{episode} {segment.id}：收束句与上方内容只隔 {gap:.1f} px"
            f"（要 ≥ {MIN_GAP:.0f} px）——读起来就是上一行的一部分"
        )


def _first_full(frames):
    """每块底色「第一帧亮透」的时刻（帧号）。

    没有亮透过的（本来就半透明的）不在表里。
    """
    table: dict = {}
    for index, probe in enumerate(frames):
        for rect in probe.rects:
            if rect.alpha >= FULL and rect.key not in table:
                table[rect.key] = index
    return table


def _arrow_target(arrow, rects, first_full):
    """箭头指着的那块内容。

    判据：**尖头前方、最早亮透的那块底色**。

    - 「尖头前方」：从箭头指的那一端找（横的找右、竖的找下、
      斜的按方向算）。只按横带去找会认错目标——s02 那条斜着扎进
      表里的箭头，会被同一横带上更远的另一块底色认领。
    - 「最早亮透」：箭头指着的常常是**一组**东西（s02 那条箭头指着
      整个接收队列），拿最早亮透的那块当标准——箭头等的是这一组
      开始出现，不是等最后一块亮完。
    - 本来就半透明的底不算（比如 s02 那块 0.92 的白芯片）：
      拿它当标准会把「底是半透明的」误判成「东西没亮」。
    - **连接线不算目标**：s05_scheduler 的提交通道底下压着一条 6 px 高的
      灰线，箭头的尖头正好落在它上面——把它当目标，这条线从第一帧起
      就是满的，守卫就再也看不见真正的芯片了。
    """
    dx, dy = arrow.x2 - arrow.x1, arrow.y2 - arrow.y1
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    candidates = []
    for rect in rects:
        if rect.key not in first_full:
            continue
        if not rect.is_block:
            continue
        # 尖头到这块底的最近点
        near_x = min(max(arrow.x2, rect.x0), rect.x1)
        near_y = min(max(arrow.y2, rect.y0), rect.y1)
        vx, vy = near_x - arrow.x2, near_y - arrow.y2
        distance = math.hypot(vx, vy)
        if distance == 0.0:
            # 尖头就落在这块底里——它就是目标
            return rect
        if vx * ux + vy * uy <= 0:
            continue
        candidates.append((first_full[rect.key], distance, rect))
    if not candidates:
        return None
    return min(candidates)[2]


@pytest.mark.parametrize("episode,segment", SEGMENTS,
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in SEGMENTS])
@pytest.mark.parametrize("orientation,canvas", ORIENTATIONS,
                         ids=[o for o, _ in ORIENTATIONS])
def test_arrow_never_outruns_the_element_it_points_at(
        episode, segment, orientation, canvas, monkeypatch):
    """箭头不许比它指着的那块内容先亮。

    箭头指着下一步，就得跟着下一步亮——原来 s04 的箭头用的是**这一步**
    的透明度，于是第 4 步淡入时，它右边那条箭头已经画出来了，
    而第 5 步还没出现：箭头悬空指着空气。
    """
    frames = _frames(segment, canvas, monkeypatch)
    first_full = _first_full(frames)
    for t, probe in zip(TIMES, frames):
        for arrow in probe.arrows:
            target = _arrow_target(arrow, probe.rects, first_full)
            if target is None:
                continue
            assert arrow.alpha <= target.alpha + ALPHA_TOLERANCE, (
                f"{episode} {segment.id} {orientation} t={t}："
                f"箭头亮到 {arrow.alpha:.2f}，可它指着的东西"
                f"（{target.x0:.0f},{target.y0:.0f}→{target.x1:.0f},"
                f"{target.y1:.0f}）只亮到 {target.alpha:.2f}"
                "——箭头不许早于它指着的东西"
            )
