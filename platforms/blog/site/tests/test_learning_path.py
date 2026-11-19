"""学习流的守卫：每个内容单元都**恰好**落在一条赛道的一个阶段里。

**背景**
------
学习流（``/learning/``）是站点的门面——它告诉读者「从哪儿开始、下一站在哪」。
它是由规则表（``data/learning-path.json``）算出来的（``tools/build-learning-path.py``），
所以它有三种坏法，每一种都得有人拦：

1. **漏归类** —— 新加一篇稿子，忘了写规则，它就悄悄从学习流里消失了。
   读者看到的阶梯是「完整」的，实际上少了一块。
2. **重复归类** —— 同一篇落进两条赛道或两个阶段，读者要读两遍，
   而且「这一级有多少篇」这个数字开始骗人。
3. **落到兜底桶** —— 规则没命中，单元被扔进 ``fallback_stage``。
   兜底桶是**构建期就该炸**的东西：它意味着「这篇我也不知道该放哪」。

**契约**
--------
1. 每个 ``kind=document|video`` 的内容单元都归到了**恰好一条**赛道的一个阶段。
2. 兜底桶是空的。
3. 规则表结构合法：赛道 id 唯一、阶段 id 递增、``fallback_stage`` 存在、
   ``catch_all`` 只出现在**最后一个**阶段（写在中间会把后面阶段全吞掉）。
4. 编译产物与内容单元对得上（``--check`` 通过）。

**这一层只看站点自己的东西**：内容单元（``content/units/``）与编译结果。
内容单元本身是不是最新的，是根级 ``tools/build-content-units.py --check`` 的事，
不在这儿越界。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE, SITE_DATA

SITE_ROOT = SITE
RULES_FILE = SITE_DATA / "learning-path.json"
COMPILED_FILE = SITE_DATA / "learning-path.compiled.json"
TOOL = SITE_ROOT / "tools" / "build-learning-path.py"


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path} 不存在（先跑编译）")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rules():
    return _load(RULES_FILE)


@pytest.fixture(scope="module")
def compiled():
    return _load(COMPILED_FILE)


def _unit_ids() -> list[str]:
    """内容单元里所有**要上站**的单元 id（分类页不进学习流）。"""
    ids = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        if rel.endswith("/_index.md") or rel == "_index.md":
            continue  # 分类页
        ids.append(rel.removesuffix(".md"))
    return ids


# ── 规则表本身的结构 ─────────────────────────────────────


def test_track_ids_are_unique(rules):
    ids = [t["id"] for t in rules["tracks"]]
    assert len(ids) == len(set(ids)), f"赛道 id 重复：{ids}"


def test_stage_ids_increase_within_a_track(rules):
    for track in rules["tracks"]:
        numbers = [int(s["id"][1:]) for s in track["stages"]]
        assert numbers == sorted(numbers), f"{track['id']} 的阶段 id 不是递增的：{numbers}"


def test_fallback_stage_exists(rules):
    for track in rules["tracks"]:
        fallback = track.get("fallback_stage")
        if fallback is None:
            continue
        stage_ids = [s["id"] for s in track["stages"]]
        assert fallback in stage_ids, f"{track['id']} 的兜底阶段 {fallback} 不存在"


def test_catch_all_only_in_last_stage(rules):
    """兜底规则写在中间阶段会把后面阶段的内容全吞掉——真踩过的坑。"""
    for track in rules["tracks"]:
        stages = track["stages"]
        for index, stage in enumerate(stages):
            has_catch_all = "catch_all" in stage.get("match", {})
            if has_catch_all:
                assert index == len(stages) - 1, (
                    f"{track['id']} 的 {stage['id']} 里有 catch_all，"
                    f"但它不是最后一个阶段"
                )


# ── 归属：每个单元恰好一处，没有兜底 ───────────────────────


def test_every_unit_is_assigned_exactly_once(compiled):
    assignment = compiled["assignment"]
    unit_ids = _unit_ids()

    missing = [uid for uid in unit_ids if uid not in assignment]
    assert not missing, f"这些单元没被归类（学习流里会凭空少一块）：{missing}"

    extra = [uid for uid in assignment if uid not in unit_ids]
    assert not extra, f"编译结果里有内容单元不存在的条目：{extra}"


def test_no_unit_relies_on_fallback(compiled):
    fallbacks = [
        uid for uid, a in compiled["assignment"].items() if a.get("fallback")
    ]
    assert not fallbacks, f"这些单元落进了兜底桶（规则没命中）：{fallbacks}"


def test_a_unit_is_not_in_two_tracks(compiled):
    """一个单元只能属于一条赛道。规则表里两条赛道的 path_prefix 撞了就会犯。"""
    seen: dict[str, str] = {}
    for uid, a in compiled["assignment"].items():
        key = f"{a['track']}/{a['stage']}"
        assert uid not in seen or seen[uid] == key, (
            f"{uid} 同时出现在 {seen.get(uid)} 和 {key}"
        )
        seen[uid] = key


def test_stage_counts_match_the_unit_lists(compiled):
    for track in compiled["tracks"]:
        for stage in track["stages"]:
            assert stage["count"] == len(stage["units"]), (
                f"{track['id']}/{stage['id']} 的 count 与 units 长度对不上"
            )


# ── 编译产物是最新的 ─────────────────────────────────────


def test_compiled_output_is_up_to_date():
    """编译结果必须跟内容单元对得上（`--check` 通过）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        cwd=str(SITE_ROOT),
    )
    assert result.returncode == 0, (
        "学习流编译结果不是最新的，先跑 build-learning-path.py：\n"
        f"{result.stdout}\n{result.stderr}"
    )
