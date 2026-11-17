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

插桩本身在 `tests/scene_probe.py`——那里还有做时序检查要用的不透明度。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod

from scene_probe import LANDSCAPE, PORTRAIT, TIMES, Session

ROOT = Path(__file__).resolve().parents[2]


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
    session = Session(monkeypatch, modules=modules)
    for t in TIMES:
        probe = session.frame(renderer, params, t, w, h)
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
    session = Session(monkeypatch, modules=modules)
    probe = session.frame(renderer, segment.params, 1.0, w, h)
    drawn = [t for t in probe.texts if t.label == ddl]
    assert drawn, f"画面上没画那段 SQL：{ddl}"
    for text in drawn:
        assert text.size == s02.CHIP_TEXT_SIZE, (
            f"SQL 被收小到 {text.size:.1f} px（应为 {s02.CHIP_TEXT_SIZE}）"
            "——盒子不够宽就加宽盒子，别收字"
        )
