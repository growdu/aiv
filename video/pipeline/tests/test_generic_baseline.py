"""通用渲染器的**逐像素基准**。

**为什么现在有基准了**：`pyv/generic/` 的四个渲染器不进 `pyv/scenes/`
（计划十的 D2 口径），所以它们一直没有场景那套逐像素基准——画面改坏了
只有元素级守卫能看出来（字压字、字出框），**版面整体挪了没人管**。

**基准靠合成夹具**：内容不入库（母稿与期目录都不在仓库里），基准不能
靠它们——母稿一换，基准就红。改用一份合成的母稿 + 一份合成的契约
（都在 `tests/fixtures/`）。

**基准绑在字体族与平台上**：换字体、换平台像素就不同，比出来的是噪声。
不适用的时候**跳过并说明原因**，不假装绿。

**抓取口径与场景基准共用一处**：`pyv/baseline.py`——帧指纹怎么算、
基准绑在什么上、什么时候跳过，都只写一份。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pyv import baseline
from pyv import contract as contract_mod

PIPELINE_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASELINE = FIXTURES / "generic_baseline.json"
CONTRACT = FIXTURES / "通用契约.json"
GENERIC_DIR = PIPELINE_DIR / "pyv" / "generic"


def _baseline() -> dict:
    return baseline.load_baseline(BASELINE)


def _renderers_on_disk() -> set[str]:
    """`pyv/generic/` 下的渲染器模块（`gen_*`）。"""
    return {f"pyv.generic.{path.stem}"
            for path in GENERIC_DIR.glob("gen_*.py")}


def _renderers_in_baseline() -> set[str]:
    """基准里出现的渲染器集合。"""
    out = set()
    for key in _baseline()["frames"]:
        tail = key.split("/")[2]
        out.add(tail.partition("@")[0])
    return out


def test_the_baseline_covers_every_generic_renderer():
    """基准里的渲染器集合必须等于目录里的渲染器集合。

    **集合相等，不是子集**：新加一个渲染器却没进基准，
    守卫就覆盖不到它——覆盖不到的那部分，坏了也不会红。
    """
    on_disk = _renderers_on_disk()
    in_baseline = _renderers_in_baseline()
    assert in_baseline == on_disk, (
        f"基准没盖住全部通用渲染器：目录有基准没有 "
        f"{sorted(on_disk - in_baseline)}；基准有目录没有 "
        f"{sorted(in_baseline - on_disk)}"
    )


def test_the_synthetic_contract_covers_every_generic_renderer():
    """**合成契约也要盖住全部渲染器**——基准是从契约推出来的。

    契约漏了一个渲染器，基准就少一帧，守卫跟着漏。
    """
    contract = contract_mod.load_contract(CONTRACT)
    used = {segment.renderer for segment in contract.segments}
    assert used == _renderers_on_disk(), (
        f"合成契约没盖住全部通用渲染器：目录有契约没有 "
        f"{sorted(_renderers_on_disk() - used)}；"
        f"契约有目录没有 {sorted(used - _renderers_on_disk())}"
    )


def test_the_baseline_keys_are_well_formed():
    """基准的键必须是 `画幅/段 id/渲染器@时刻`。

    **键写错了，比对时一条都匹配不上**——守卫看着绿，实际什么都没比。
    """
    data = _baseline()
    canvases = {f"{w}x{h}" for w, h in baseline.CANVASES}
    for key in data["frames"]:
        parts = key.split("/")
        assert len(parts) == 3, f"基准的键不是三段：{key}"
        canvas, segment, tail = parts
        assert canvas in canvases, f"基准的键里的画幅不认识：{key}"
        assert segment, key
        renderer, _, moment = tail.partition("@")
        assert renderer.startswith("pyv.generic."), key
        assert float(moment) in baseline.TIMES, (
            f"{key} 的时刻不在基准抓取的时刻里：{baseline.TIMES}"
        )


def test_the_baseline_covers_both_canvases():
    """**两个画幅都要抓**——竖版是抖音那一档，版式跟横版不一样。"""
    data = _baseline()
    canvases = {key.split("/")[0] for key in data["frames"]}
    assert canvases == {f"{w}x{h}" for w, h in baseline.CANVASES}


def test_the_frames_match_the_baseline(tmp_path):
    """**帧指纹一致**——画面改坏了就红。

    基准不适用于当前机器时（换过字体、换过平台、没装等宽字体）
    **跳过并说明原因**：跨平台比像素是拿噪声当信号。
    """
    data = _baseline()
    reason = baseline.skip_reason(data)
    if reason:
        pytest.skip(reason)

    contract = contract_mod.load_contract(CONTRACT)
    segments = {segment.id: segment for segment in contract.segments}

    baseline.stub_mermaid(tmp_path)

    for key, expected in data["frames"].items():
        canvas_text, segment_id, tail = key.split("/")
        renderer, _, moment = tail.partition("@")
        width, height = (int(part) for part in canvas_text.split("x"))
        segment = segments[segment_id]
        actual = baseline.frame_hash(renderer, segment.params, float(moment),
                                     width, height)
        assert actual == expected, (
            f"{key} 的画面变了：{expected[:16]} → {actual[:16]}。"
            f"确认是有意的改动再重抓："
            f"python3 scripts/capture_generic_baseline.py"
        )


def test_both_baselines_use_the_same_capture_convention():
    """**抓取口径共用一处**（`pyv/baseline.py`）——不各写一份。

    两边各写一份的话，过一阵两边就不一样：那时候「基准」只是个文件，
    比出来的差异说明不了任何事。

    这条用**读源码**的方式查（不 import 那些脚本）：两个脚本都得从
    `pyv.baseline` 取帧指纹与基准元信息，谁都不许自己再写一份。
    """
    scripts = [PIPELINE_DIR / "scripts" / "capture_scene_baseline.py",
               PIPELINE_DIR / "scripts" / "capture_generic_baseline.py"]
    for script in scripts:
        source = script.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # 谁都不许自己定义一份帧指纹的算法
        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "frame_hash" not in defined, (
            f"{script.name} 自己定义了一份 frame_hash——"
            f"口径要共用 pyv/baseline.py 里那一处"
        )

        # 也得真的用上共享的那一处
        assert "from pyv import baseline" in source, (
            f"{script.name} 没有用 pyv.baseline 的共用口径"
        )
