"""三档守卫：字数、时长、压缩比。

**阈值不许从生产代码 import。** 这份文件里有**两份独立取值**：

1. 抄在下面的常量（照《长视频三档》§三 那张表抄的）；
2. 直接**解析规格文档的表**（`publish/spec/09-长视频三档.md`）。

生产代码（`pyv/tiers.py`）是第三份。三份对拍：
生产代码改了而规格没改 → 红；规格改了而生产代码没改 → 也红。

**为什么值得多抄一份**：阈值是这套三档的**判据**。
它悄悄漂了，片子照样出得来，只是长度变了——没人会发现。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyv import tiers

#: 仓库根：video/pipeline/tests/test_tiers.py → tests → pipeline → video → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]

#: 规格文档——阈值的**权威出处**。
SPEC_PATH = REPO_ROOT / "publish" / "spec" / "09-长视频三档.md"

# ---- 第一份独立取值：照规格 §三 的表抄的 --------------------------------
TIER_SHORT_MAX_SECONDS = 60.0
TIER_SHORT_MAX_CHARS = 431
TIER_SHORT_MAX_RATIO = 100.0

TIER_MID_MIN_SECONDS = 300.0
TIER_MID_MAX_SECONDS = 600.0
TIER_MID_MIN_CHARS = 2157
TIER_MID_MAX_CHARS = 4314
TIER_MID_MAX_RATIO = 12.0

TIER_FULL_MIN_SECONDS = 600.0
TIER_FULL_MIN_CHARS = 4314
TIER_FULL_MAX_RATIO = 1.5

SPEECH_RATE = 7.19


# ---- 第二份独立取值：解析规格文档的表 ----------------------------------

#: §三 那张表的行：`| **精简版** `short` | … |`
_ROW = re.compile(
    r"^\|\s*\*\*(?:精简版|进阶版|完整版)\*\*\s*`(short|mid|full)`\s*\|(.*)$"
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(cell: str) -> list[float]:
    return [float(t.replace(",", "")) for t in _NUMBER.findall(cell)]


def _bounds(cell: str) -> tuple[float | None, float | None]:
    """从一个格子里读出 (下限, 上限)。

    `≤ 431` → (None, 431)；`≥ 4,314（实测 …）` → (4314, None)；
    `300 ~ 600 s` → (300, 600)。
    """
    nums = _numbers(cell)
    assert nums, f"格子里没有数字：{cell!r}"
    if "≥" in cell:
        return nums[0], None
    if "≤" in cell:
        return None, nums[0]
    assert len(nums) >= 2, f"不是区间的格子：{cell!r}"
    return nums[0], nums[1]


def _spec_table() -> dict[str, dict]:
    """把规格 §三 那张表解析成 {档位: {min_seconds, max_seconds, …}}。"""
    assert SPEC_PATH.is_file(), f"规格文档不在：{SPEC_PATH}"
    table: dict[str, dict] = {}
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue
        tier = match.group(1)
        cells = match.group(2).split("|")
        assert len(cells) >= 4, f"{tier} 那行的列数不对：{line!r}"
        seconds_low, seconds_high = _bounds(cells[0])
        chars_low, chars_high = _bounds(cells[1])
        ratio_numbers = _numbers(cells[3])
        assert ratio_numbers, f"{tier} 的压缩比格子没有数字：{cells[3]!r}"
        table[tier] = {
            "min_seconds": seconds_low,
            "max_seconds": seconds_high,
            "min_chars": chars_low,
            "max_chars": chars_high,
            "max_ratio": ratio_numbers[0],
        }
    assert set(table) == {"short", "mid", "full"}, (
        f"规格 §三 的表没解析出三档：{sorted(table)}"
        "（规格改表了？解析器要跟着改）"
    )
    return table


# ---- 夹具 ----------------------------------------------------------------

MOTHER_DOC = """---
title: 母稿
---

# 母稿

正文一句。
"""

DOC = "系列甲/合集甲/文档甲"


def _write_motherdoc(tmp_path, prose: str) -> Path:
    path = tmp_path / "母稿.md"
    path.write_text(
        "---\ntitle: 母稿\n---\n\n# 母稿\n\n" + prose + "\n",
        encoding="utf-8",
    )
    return path


def _write_doc(root: Path, mother: Path, lines: list[str], role: str = "hook") -> str:
    """在 `root` 下建一篇文档（骨架 + 母稿引用）。"""
    doc_dir = root / DOC
    doc_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for index, line in enumerate(lines, start=1):
        segments.append(
            f"  - id: s{index:02d}\n"
            f"    role: {role}\n"
            "    visual:\n"
            "      kind: scene\n"
            "      renderer: pyv.scenes.s01_intro\n"
            '      params: {title: "甲"}\n'
            "    narration:\n"
            f'      - "{line}"\n'
            "    subtitles:\n"
            f'      - "{line}"\n'
        )
    (doc_dir / "skeleton.yaml").write_text(
        f"episode: {DOC}\n"
        f'source: "{mother}"\n'
        "segments:\n" + "".join(segments),
        encoding="utf-8",
    )
    return DOC


# ---- 阈值的三份取值要对拍 ------------------------------------------------

def test_the_production_limits_match_the_independent_constants():
    """生产代码里的阈值必须与本文件抄的独立取值一致。

    两边各写一份，是故意的——生产代码改了而这里没改，这条会红。
    """
    limits = tiers.TIER_LIMITS
    assert limits["short"]["max_seconds"] == TIER_SHORT_MAX_SECONDS
    assert limits["short"]["max_chars"] == TIER_SHORT_MAX_CHARS
    assert limits["short"]["max_ratio"] == TIER_SHORT_MAX_RATIO
    assert limits["mid"]["min_seconds"] == TIER_MID_MIN_SECONDS
    assert limits["mid"]["max_seconds"] == TIER_MID_MAX_SECONDS
    assert limits["mid"]["min_chars"] == TIER_MID_MIN_CHARS
    assert limits["mid"]["max_chars"] == TIER_MID_MAX_CHARS
    assert limits["mid"]["max_ratio"] == TIER_MID_MAX_RATIO
    assert limits["full"]["min_seconds"] == TIER_FULL_MIN_SECONDS
    assert limits["full"]["min_chars"] == TIER_FULL_MIN_CHARS
    assert limits["full"]["max_ratio"] == TIER_FULL_MAX_RATIO


def test_the_independent_constants_match_the_spec_table():
    """本文件抄的取值必须与**规格文档的表**一致。

    这一条把抄写这件事也钉住：规格改了表而没人改代码（也没人改这里），
    那就红。少了它，两份手工抄的常量可能一起漂，而守卫照样绿。
    """
    table = _spec_table()
    assert table["short"]["max_seconds"] == TIER_SHORT_MAX_SECONDS
    assert table["short"]["max_chars"] == TIER_SHORT_MAX_CHARS
    assert table["short"]["max_ratio"] == TIER_SHORT_MAX_RATIO
    assert table["mid"]["min_seconds"] == TIER_MID_MIN_SECONDS
    assert table["mid"]["max_seconds"] == TIER_MID_MAX_SECONDS
    assert table["mid"]["min_chars"] == TIER_MID_MIN_CHARS
    assert table["mid"]["max_chars"] == TIER_MID_MAX_CHARS
    assert table["mid"]["max_ratio"] == TIER_MID_MAX_RATIO
    assert table["full"]["min_seconds"] == TIER_FULL_MIN_SECONDS
    assert table["full"]["min_chars"] == TIER_FULL_MIN_CHARS
    assert table["full"]["max_ratio"] == TIER_FULL_MAX_RATIO


def test_the_speech_rate_is_the_one_in_the_spec():
    """语速常数 7.19 字/秒——规格里写着同一个数。"""
    assert tiers.SPEECH_RATE == SPEECH_RATE
    assert "7.19 字/秒" in SPEC_PATH.read_text(encoding="utf-8")


def test_the_tier_names_come_from_the_skeleton():
    """档位名只有一份——从 skeleton 拿，不另抄。"""
    assert tiers.TIER_NAMES == ("short", "mid", "full")


# ---- 判据本身 ------------------------------------------------------------

def test_check_reports_the_problems_instead_of_raising():
    """不合规要返回问题清单，不抛异常。"""
    problems = tiers.check_numbers(
        tier="short", seconds=90.0, chars=500, ratio=3.0)
    assert problems
    assert any("时长" in p for p in problems)
    assert any("字数" in p for p in problems)


def test_check_passes_a_conforming_short_episode():
    assert tiers.check_numbers(
        tier="short", seconds=34.6, chars=241, ratio=65.1) == []


def test_the_boundary_values_are_inclusive():
    """恰好压线算过——超一点才算不过。

    压线判红会让人把阈值往宽里挪，挪着挪着这守卫就没人信了。
    """
    assert tiers.check_numbers(
        tier="short", seconds=60.0, chars=431, ratio=100.0) == []
    assert tiers.check_numbers(
        tier="mid", seconds=300.0, chars=2157, ratio=12.0) == []
    assert tiers.check_numbers(
        tier="full", seconds=600.0, chars=4314, ratio=1.5) == []


def test_one_step_over_the_boundary_is_reported():
    assert tiers.check_numbers(
        tier="short", seconds=60.1, chars=432, ratio=100.1)
    assert tiers.check_numbers(
        tier="mid", seconds=299.9, chars=2156, ratio=12.1)
    assert tiers.check_numbers(
        tier="full", seconds=599.9, chars=4313, ratio=1.51)


def test_the_full_tier_has_no_upper_bound():
    """完整版只有下限——它是「母稿散文全读」，没有上限这回事。"""
    assert tiers.TIER_LIMITS["full"]["max_seconds"] is None
    assert tiers.TIER_LIMITS["full"]["max_chars"] is None
    assert tiers.check_numbers(
        tier="full", seconds=5000.0, chars=20000, ratio=1.0) == []


def test_an_unknown_tier_is_refused():
    """档位拼错就是拼错——不能当成「什么都不查」。"""
    with pytest.raises(ValueError):
        tiers.check_numbers(tier="medium", seconds=10.0, chars=100, ratio=1.0)


def test_count_chars_ignores_the_whitespace():
    assert tiers.count_chars(["一 二", "三\n四"]) == 4


# ---- 端到端：真的文档走一遍 ----------------------------------------------

def test_a_conforming_short_document_passes(tmp_path):
    """一篇合规的精简版：没有问题清单。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["这是一句话。", "那也是一句话。"])
    assert tiers.check_episode(doc, "short", root=root) == []


def test_a_document_that_is_too_long_is_reported(tmp_path):
    """字超了、时长超了——两条都要说出来。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["字" * 500])
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("字数" in p for p in problems)
    assert any("时长" in p for p in problems)


def test_a_document_with_too_low_a_compression_ratio_is_reported(tmp_path):
    """口播太少、母稿太多——压缩比超限。"""
    mother = _write_motherdoc(tmp_path, "母" * 5000)
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["一句话。", "另一句。"])
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("压缩比" in p for p in problems)


def test_a_conforming_full_document_passes(tmp_path):
    """完整版端到端：口播 ≥ 4,314 字，压缩比 ~1:1。"""
    mother = _write_motherdoc(tmp_path, "母" * 4314)
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["字" * 4314])
    assert tiers.check_episode(doc, "full", root=root) == []


def test_a_tier_with_no_segments_is_reported(tmp_path):
    """这一档没有段——「没有口播」要说出来，不能当成零字合规。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["支线一句。"], role="aside")
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("口播都没有" in p for p in problems)


def test_a_document_without_a_skeleton_is_reported(tmp_path):
    """没有骨架——问题清单，不是异常。"""
    root = tmp_path / "episodes"
    problems = tiers.check_episode(DOC, "short", root=root)
    assert len(problems) == 1
    assert "没有骨架文件" in problems[0]


def test_a_document_without_a_motherdoc_is_reported(tmp_path):
    """母稿没了——要说出来，不能默默当成零散文。"""
    root = tmp_path / "episodes"
    doc = _write_doc(root, tmp_path / "没有的母稿.md", ["一句话。"])
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("母稿不存在" in p for p in problems)


def test_a_broken_skeleton_is_reported(tmp_path):
    """骨架坏了——问题清单，不是异常。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["一句话。"])
    (root / doc / "skeleton.yaml").write_text(
        "episode: 甲\nsegments:\n  - id: s01\n    role: 没有这个role\n",
        encoding="utf-8",
    )
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("派生失败" in p for p in problems)


# ---- 豁免 ----------------------------------------------------------------

def test_an_exempt_tier_returns_the_reason(monkeypatch, tmp_path):
    """豁免要说清为什么——空字符串的豁免等于没豁免。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["字" * 500])
    monkeypatch.setitem(
        tiers.TIER_EXEMPT, doc, {"mid": "尚未产出进阶版（2026-11-23）"})
    problems = tiers.check_episode(doc, "mid", root=root)
    assert problems == ["豁免：尚未产出进阶版（2026-11-23）"]


def test_the_exemption_only_covers_the_tier_it_names(monkeypatch, tmp_path):
    """豁免是**某一档**的事——别的档照样要查。"""
    mother = _write_motherdoc(tmp_path, "正文一句。")
    root = tmp_path / "episodes"
    doc = _write_doc(root, mother, ["字" * 500])
    monkeypatch.setitem(
        tiers.TIER_EXEMPT, doc, {"mid": "尚未产出进阶版（2026-11-23）"})
    problems = tiers.check_episode(doc, "short", root=root)
    assert any("字数" in p for p in problems)


def test_every_exemption_names_a_known_tier_and_a_reason():
    """豁免名单里的档位得是认识的档位，理由不能是空字符串。

    豁免是临时的后门——名字不认识、理由说不清，等于没豁免。
    """
    for doc, exempt in tiers.TIER_EXEMPT.items():
        for tier, reason in exempt.items():
            assert tier in tiers.TIER_NAMES, f"{doc} 的豁免档位 {tier!r} 不认识"
            assert reason.strip(), f"{doc} 的 {tier} 豁免没有写理由"
