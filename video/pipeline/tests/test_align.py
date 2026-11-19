import subprocess
from pathlib import Path

import numpy as np
import pytest

from pyv import align

# 真实口播稿在期目录里（`video/episodes/<期路径>/口播稿.md`）。
# 视频线清空重来之后磁盘上没有期——下面那两条「真实契约」的用例
# 在没有期时跳过，有期时自动盯上那一期。
AIV_ROOT = Path(__file__).resolve().parents[2]


def _real_episode():
    """磁盘上的第一期：`(slug, 口播稿路径, 契约路径)`。没有期就返回 None。"""
    from pyv import episodes

    slugs = episodes.known_eps()
    if not slugs:
        return None
    slug = slugs[0]
    return slug, episodes.script_path(slug), episodes.contract_path(slug)


def _make_audio(tmp_path, segments, sr=32000):
    """segments: [(start, end), ...]，段间留静音。生成单声道 wav。"""
    total = int((segments[-1][1] + 0.4) * sr)
    buf = np.zeros(total, dtype=np.int16)
    for start, end in segments:
        s, e = int(start * sr), int(end * sr)
        t = np.arange(e - s) / sr
        buf[s:e] = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    path = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-", str(path)],
        input=buf.tobytes(), check=True,
    )
    return str(path)


SAMPLE_MD = """# 标题

## 二、口播稿（2 句）

```
第一句内容。
第二句内容。
```

## 三、字幕文本

| # | 字幕 | 备注 |
| --- | --- | --- |
| 1 | 字幕甲 | 甲 |
| 2 | 字幕乙 | 乙 |
"""


def test_detect_sentences_finds_three_spans(tmp_path):
    audio = _make_audio(tmp_path, [(0.1, 0.9), (1.4, 2.1), (2.6, 3.4)])
    spans = align.detect_sentences(audio, threshold_db=-32, min_silence=0.2)
    assert len(spans) == 3
    assert spans[0][0] == pytest.approx(0.1, abs=0.15)
    assert spans[-1][1] == pytest.approx(3.4, abs=0.2)


def test_assign_sentences_requires_matching_count():
    with pytest.raises(ValueError, match="句数"):
        align.assign_sentences([(0, 1)], ["第一句", "第二句"])


def test_assign_sentences_pairs_by_order():
    spans = [(0.0, 1.0), (1.0, 2.0)]
    texts = ["第一句", "第二句"]
    assert align.assign_sentences(spans, texts) == [(0.0, 1.0, "第一句"), (1.0, 2.0, "第二句")]


def test_parse_script_extracts_code_block_lines(tmp_path):
    md = tmp_path / "脚本.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    assert align.parse_script(md) == ["第一句内容。", "第二句内容。"]


def test_parse_subtitle_table_extracts_second_column(tmp_path):
    md = tmp_path / "脚本.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    assert align.parse_subtitle_table(md) == ["字幕甲", "字幕乙"]


def test_parse_script_requires_section(tmp_path):
    md = tmp_path / "脚本.md"
    md.write_text("# 只有标题\n", encoding="utf-8")
    with pytest.raises(ValueError, match="口播稿"):
        align.parse_script(md)


def test_build_storyboard_rejects_mismatched_counts(tmp_path, fixture_episode):
    md = tmp_path / "脚本.md"
    md.write_text(SAMPLE_MD.replace("第二句内容。", "第二句内容。\n第三句内容。"),
                  encoding="utf-8")
    with pytest.raises(ValueError, match="不一致"):
        align.build_storyboard(tmp_path / "nope.wav", md, tmp_path / "out.json",
                               contract_path=fixture_episode.contract)


def test_real_contract_has_matching_counts():
    """真实契约：口播句数、字幕行数、视觉分镜契约期望的句数三者一致。"""
    from pyv.contract import load_contract
    episode = _real_episode()
    if episode is None:
        pytest.skip("磁盘上没有期，跳过")
    _, script, contract_path = episode
    sentences = align.parse_script(script)
    subtitles = align.parse_subtitle_table(script)
    contract = load_contract(contract_path)
    assert len(sentences) == len(subtitles) == contract.sentence_count


def test_real_contract_subtitles_fit_width():
    """真实契约：每条字幕的视觉宽度都不超过 14。"""
    from pyv.timeline import display_width, MAX_SUBTITLE_LINE
    episode = _real_episode()
    if episode is None:
        pytest.skip("磁盘上没有期，跳过")
    _, script, _ = episode
    for text in align.parse_subtitle_table(script):
        assert display_width(text) <= MAX_SUBTITLE_LINE, text


def test_align_by_weight_splits_proportionally():
    spans = [(0.0, 1.0), (1.2, 2.2), (2.4, 3.4), (3.6, 4.6)]
    texts = ["一", "二"]
    result = align.align_by_weight(spans, texts, weights=[1.0, 1.0])
    assert len(result) == 2
    assert result[0][0] == 0.0
    assert result[-1][1] == 4.6
    for index in range(len(result) - 1):
        assert result[index][1] <= result[index + 1][0] + 1e-9


def test_align_by_weight_keeps_boundaries_on_span_edges():
    spans = [(0.0, 1.0), (1.2, 2.2), (2.4, 3.4), (3.6, 4.6)]
    texts = ["一", "二", "三"]
    result = align.align_by_weight(spans, texts, weights=[1.0, 1.0, 1.0])
    edges = {s for span in spans for s in span}
    for start, end, _ in result:
        assert start in edges
        assert end in edges


def test_align_by_weight_rejects_too_few_spans():
    with pytest.raises(ValueError, match="少于句子数"):
        align.align_by_weight([(0.0, 1.0)], ["一", "二"])


def test_align_by_weight_requires_two_sentences():
    with pytest.raises(ValueError, match="至少需要两句"):
        align.align_by_weight([(0.0, 1.0)], ["一"])
