"""骨架 → (口播稿, 字幕表, 视觉契约)。

**派生出来的必须是「流水线认得的样子」**——所以这里不只查字段，
还用 `pyv.contract.parse_contract` 与 `pyv.align.parse_script` /
`parse_subtitle_table` 亲自读一遍：读得进去才算数。

**母稿引用错了要当场报错**：画面那一环会静默缺一块，
而片子里看不出少了什么。
"""
from __future__ import annotations

import pytest

from pyv import align
from pyv import contract
from pyv import derive
from pyv.skeleton import TierError

MOTHER_DOC = """---
title: 母稿
---

# 母稿

正文一句。

```mermaid
graph TD
  A --> B
```

```python
x = 1
```
"""


def _motherdoc(tmp_path):
    path = tmp_path / "母稿.md"
    path.write_text(MOTHER_DOC, encoding="utf-8")
    return path


def _skeleton(doc_path):
    """一份两段的骨架：一段手写场景，一段引用母稿里的 mermaid。"""
    return {
        "episode": "系列甲/合集甲/文档甲",
        "source": str(doc_path),
        "title": "甲文档",
        "segments": [
            {
                "id": "s01",
                "role": "hook",
                "visual": {
                    "kind": "scene",
                    "renderer": "pyv.scenes.s01_intro",
                    "params": {"title": "甲"},
                },
                "narration": ["第一句。", "第二句。"],
                "subtitles": ["字幕一", "字幕二"],
            },
            {
                "id": "s02",
                "role": "mechanism",
                "visual": {
                    "kind": "mermaid",
                    "ref": {"doc": str(doc_path), "nth": 1},
                },
                "narration": ["第三句。"],
                "subtitles": ["字幕三"],
            },
        ],
    }


def test_derive_flattens_the_sentences_across_segments(tmp_path):
    """口播与字幕都是**跨段拍平**的列表，顺序就是段序。"""
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "full")
    assert result.narration == ["第一句。", "第二句。", "第三句。"]
    assert result.subtitles == ["字幕一", "字幕二", "字幕三"]


def test_the_derived_contract_is_accepted_by_the_existing_loader(tmp_path):
    """派生出来的契约必须能被 `pyv.contract` 认——否则流水线认不出来。"""
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "full")
    parsed = contract.parse_contract(result.contract)
    assert parsed.sentence_count == 3
    assert parsed.title == "甲文档"
    assert [s.id for s in parsed.segments] == ["s01", "s02"]
    assert parsed.segments[0].sentences == (0, 1)
    assert parsed.segments[1].sentences == (2,)


def test_the_contract_episode_is_the_four_layer_episode_path(tmp_path):
    """骨架的 episode 是**文档路径**（三层），契约的是**期路径**（四层）。

    档位在路径里，不在骨架里——骨架是三档共用的。
    """
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "short")
    assert result.contract["episode"] == "系列甲/合集甲/文档甲/short"


def test_a_mermaid_segment_points_at_the_generic_renderer(tmp_path):
    """母稿引用的段走通用渲染器，参数里带着 ref。"""
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "full")
    segment = result.contract["segments"][1]
    assert segment["renderer"] == "pyv.scenes.gen_mermaid"
    assert segment["params"]["ref"]["nth"] == 1


def test_a_scene_segment_keeps_its_own_renderer_and_params(tmp_path):
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "full")
    segment = result.contract["segments"][0]
    assert segment["renderer"] == "pyv.scenes.s01_intro"
    assert segment["params"] == {"title": "甲"}


def test_cropping_to_short_drops_the_mechanism_segment(tmp_path):
    """裁剪只看 role——精简版不要 mechanism。"""
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "short")
    assert [s["id"] for s in result.contract["segments"]] == ["s01"]
    assert result.narration == ["第一句。", "第二句。"]


def test_the_narration_markdown_is_one_sentence_per_line():
    text = derive.narration_markdown(["第一句。", "第二句。"])
    assert "第一句。" in text and "第二句。" in text
    assert text.count("\n") >= 2
    # 流水线是按「标题里含『口播稿』」找这一节的
    assert "口播稿" in text.splitlines()[0]


def test_the_subtitle_table_has_one_row_per_sentence():
    text = derive.subtitle_table(["甲", "乙", "丙"])
    rows = [line for line in text.splitlines() if line.startswith("|")]
    # 表头 + 分隔行 + 3 行数据
    assert len(rows) == 5
    assert "字幕文本" in text.splitlines()[0]


def test_the_derived_script_is_readable_by_the_pipeline(tmp_path):
    """**端到端**：派生出来的两节拼成口播稿，`align` 读得回去。

    这是「派生出来的格式与现在完全一致」那句话的落地检查——
    格式差一个字符，流水线就会报「口播稿 N 句与字幕表 M 行不一致」。
    """
    doc = _motherdoc(tmp_path)
    result = derive.derive(_skeleton(doc), "full")
    script = tmp_path / "口播稿.md"
    script.write_text(
        "# 甲文档\n\n"
        + derive.narration_markdown(result.narration)
        + "\n"
        + derive.subtitle_table(result.subtitles),
        encoding="utf-8",
    )
    assert align.parse_script(script) == result.narration
    assert align.parse_subtitle_table(script) == result.subtitles


def test_a_ref_to_a_missing_motherdoc_is_refused(tmp_path):
    """母稿没了 → 当场报错，不是一条静默缺画面的片子。"""
    skeleton = _skeleton(tmp_path / "母稿.md")
    with pytest.raises(FileNotFoundError):
        derive.derive(skeleton, "full")


def test_a_ref_whose_nth_is_out_of_range_is_refused(tmp_path):
    """`nth` 超范围 → 当场报错。"""
    doc = _motherdoc(tmp_path)
    skeleton = _skeleton(doc)
    skeleton["segments"][1]["visual"]["ref"]["nth"] = 99
    with pytest.raises(ValueError):
        derive.derive(skeleton, "full")


def test_a_ref_without_a_nth_is_refused(tmp_path):
    doc = _motherdoc(tmp_path)
    skeleton = _skeleton(doc)
    skeleton["segments"][1]["visual"]["ref"] = {"doc": str(doc)}
    with pytest.raises(ValueError):
        derive.derive(skeleton, "full")


def test_a_segment_without_a_ref_is_refused(tmp_path):
    """mermaid 段没有 ref → 画面那一环不知道去母稿哪里取。"""
    doc = _motherdoc(tmp_path)
    skeleton = _skeleton(doc)
    skeleton["segments"][1]["visual"] = {"kind": "mermaid"}
    with pytest.raises(ValueError):
        derive.derive(skeleton, "full")


def test_a_segment_whose_subtitles_do_not_match_its_narration_is_refused(tmp_path):
    doc = _motherdoc(tmp_path)
    skeleton = _skeleton(doc)
    skeleton["segments"][0]["subtitles"] = ["只有一行"]
    with pytest.raises(ValueError):
        derive.derive(skeleton, "full")


def test_an_unknown_tier_is_refused(tmp_path):
    """档位拼错就是拼错——不能当成「什么都不讲」。"""
    doc = _motherdoc(tmp_path)
    with pytest.raises(TierError):
        derive.derive(_skeleton(doc), "medium")
