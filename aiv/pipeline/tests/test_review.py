"""视频审核模块的守卫。

**每条规则都要能被注入缺陷验证它会红**——只会绿不会红的守卫等于没有。

分三组：

1. 文本层六条规则（`VT-*`）：用造出来的 `Materials` 注入缺陷；
2. 成片层七条规则（`VV-*`）：用造出来的帧 / 音频 / 替身函数注入缺陷；
3. 跨模块一致性：视频侧的词表与阈值必须与文档侧 `tools/review-check.py`
   **逐字相同**——改一边，另一边要红。

另有一条盯记录与进度表的对应关系（六期记录 ↔ `INDEX.md` 六行）。
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyv import episodes
from pyv import review

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_CHECKER = REPO_ROOT / "tools" / "review-check.py"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ---------------------------------------------------------------- 夹具


def _materials(sentences: list[str], subtitles: list[str] | None = None,
               motherdocs: list[Path] | None = None,
               evidence: list[tuple[str, str, str]] | None = None,
               ) -> review.Materials:
    return review.Materials(
        episode="test-ep",
        ep_number="ep99",
        title="测试",
        sentences=sentences,
        subtitles=subtitles if subtitles is not None else list(sentences),
        segments=[],
        motherdocs=motherdocs or [],
        evidence=evidence or [],
    )


def _rules(signals: list[review.Signal]) -> set[str]:
    return {s.rule for s in signals}


# ---------------------------------------------------------------- 文本层


def test_vt_01_flags_connectors_at_the_head_of_sentences():
    """句首连接词超过 15% → 命中。"""
    sentences = [
        "首先看发布端的线程数。",
        "其次看解码线程怎么分工。",
        "最后看订阅端怎么收口。",
        "这一句没有连接词。",
        "这一句也没有。",
        "收尾的句子。",
    ]
    signals = review.vt_01_connectors(_materials(sentences))
    assert _rules(signals) == {"VT-01"}
    assert "3/6" in signals[0].detail


def test_vt_01_ignores_connectors_inside_a_sentence():
    """句中的「最后」不是结构连接词，不该命中。"""
    sentences = [f"我说的是最后第{i}步。" for i in range(10)]
    assert review.vt_01_connectors(_materials(sentences)) == []


def test_vt_02_flags_vague_praise_without_numbers():
    signals = review.vt_02_vague(_materials(["这套方案非常高效，各方面都很好。"]))
    assert _rules(signals) == {"VT-02"}


def test_vt_02_accepts_vague_praise_backed_by_a_number():
    """有数字支撑就不报——这正是文档侧 `AIF-02` 的口径。"""
    sentences = ["这套方案非常高效，吞吐提升了 3 倍。"]
    assert review.vt_02_vague(_materials(sentences)) == []


def test_vt_03_flags_generic_closing():
    sentences = ["讲完了机制。", "讲完了证据。", "以上就是全部内容。"]
    signals = review.vt_03_generic_ending(_materials(sentences))
    assert _rules(signals) == {"VT-03"}


def test_vt_03_ignores_generic_closing_in_the_middle():
    """只查结尾三句——中间的泛化收尾语不算。"""
    sentences = [
        "以上就是全部内容。",
        "再补一句机制。",
        "再说一句证据。",
        "再补一句实验。",
        "再补一句取舍。",
    ]
    assert review.vt_03_generic_ending(_materials(sentences)) == []


def test_vt_04_flags_near_duplicate_sentences():
    sentences = [
        "发布端只有一个解码线程，串行处理所有事务。",
        "发布端只有一个解码线程，串行处理所有事务。",
        "换成三层结构之后就不一样了。",
    ]
    signals = review.vt_04_duplicate(_materials(sentences))
    assert _rules(signals) == {"VT-04"}


def test_vt_04_accepts_different_sentences():
    sentences = [
        "发布端只有一个解码线程，串行处理所有事务。",
        "订阅端拿到号就知道该不该先应用这条变更。",
    ]
    assert review.vt_04_duplicate(_materials(sentences)) == []


def test_vt_05_flags_a_number_missing_from_the_motherdoc(tmp_path):
    motherdoc = tmp_path / "母稿.md"
    motherdoc.write_text("这里写的是 32 核机器。\n", encoding="utf-8")
    materials = _materials(["32 核机器上解码只占 1 核。"],
                           motherdocs=[motherdoc])
    signals = review.vt_05_number_evidence(materials)
    assert _rules(signals) == {"VT-05"}
    assert "1" in signals[0].detail


def test_vt_05_accepts_a_number_present_in_the_motherdoc(tmp_path):
    motherdoc = tmp_path / "母稿.md"
    motherdoc.write_text("这里写的是 32 核机器与 1 核占用。\n", encoding="utf-8")
    materials = _materials(["32 核机器上解码只占 1 核。"],
                           motherdocs=[motherdoc])
    assert review.vt_05_number_evidence(materials) == []


def test_vt_05_skips_when_there_is_nothing_to_compare_against():
    """没有母稿可比 → 跳过（并在报告里留 note），不报成「没问题」。"""
    materials = _materials(["32 核机器上解码只占 1 核。"])
    assert review.vt_05_number_evidence(materials) == []


def test_vt_06_flags_a_number_dropped_by_the_subtitle():
    materials = _materials(["整体性能提升 2 到 5 倍。"],
                           ["性能提升明显"])
    signals = review.vt_06_subtitle_drops_number(materials)
    assert _rules(signals) == {"VT-06"}


def test_vt_06_accepts_a_subtitle_keeping_the_number():
    materials = _materials(["整体性能提升 2 到 5 倍。"],
                           ["性能提升 2–5 倍"])
    assert review.vt_06_subtitle_drops_number(materials) == []


def test_vt_06_ignores_non_numeric_differences():
    """字幕本来就是口播的压缩版——只有**数字**丢了才算问题。"""
    materials = _materials(["不是 PostgreSQL 18 的能力。"],
                           ["这是 openGauss 的做法"])
    signals = review.vt_06_subtitle_drops_number(materials)
    # 「18」是两位数，按口径算「有意义的数字」，所以这里会命中；
    # 而纯字面差异（没有数字）不命中。
    assert _rules(signals) == {"VT-06"}

    materials = _materials(["不过它的边界很清楚。"], ["边界清楚"])
    assert review.vt_06_subtitle_drops_number(materials) == []


def test_number_phrase_extraction_skips_meaningless_single_digits():
    """一位数没单位（「第 3 期」）不进规则——报了也是噪声。"""
    assert review._number_phrases("第 3 期") == []
    assert review._number_phrases("32 核机器") == [("32", "核")]


def test_vt_07_flags_a_banned_word_in_the_subtitle_table():
    materials = _materials(["一句"], ["海量数据库很强"])
    signals = review.vt_07_subtitle_format(materials)
    assert _rules(signals) == {"VT-07"}
    assert "禁止词" in signals[0].detail


def test_vt_07_flags_a_subtitle_line_that_is_too_wide():
    materials = _materials(["一句"], ["字" * 15])
    signals = review.vt_07_subtitle_format(materials)
    assert _rules(signals) == {"VT-07"}
    assert "视觉宽度" in signals[0].detail


def test_vt_07_accepts_a_clean_subtitle_table():
    materials = _materials(["一句"], ["四个字够了"])
    assert review.vt_07_subtitle_format(materials) == []


def test_vt_07_follows_the_timeline_threshold(monkeypatch):
    """阈值只有一份。

    改了 `timeline.MAX_SUBTITLE_LINE`，规则跟着变——**不抄一份**。
    抄一份的话，两边会漂。
    """
    from pyv import timeline

    monkeypatch.setattr(timeline, "MAX_SUBTITLE_LINE", 3)
    materials = _materials(["一句"], ["四个字够了"])
    assert _rules(review.vt_07_subtitle_format(materials)) == {"VT-07"}


def test_vt_07_checks_the_source_table_not_the_stale_storyboard():
    """查的是**源字幕表**。

    `make validate` 查的是上一次 align 出来的 storyboard；源文件改了
    但没重跑 align 时，那个门禁看到的还是旧字幕。
    """
    materials = _materials(["一句"], ["字" * 15])
    signals = review.vt_07_subtitle_format(materials)
    assert signals[0].target == "第1句"


def test_check_text_runs_every_text_rule():
    """文本层跑一遍，报出的信号编号都在已知的规则表里。"""
    report = review.check_text("pg-parallel-decode")
    assert report.layer == review.TEXT_LAYER
    assert report.episode == "pg-parallel-decode"
    for signal in report.signals:
        assert signal.rule in review.TEXT_RULES or signal.rule.startswith("persona."), \
            signal.rule
    assert isinstance(report.to_dict(), dict)


def test_check_text_reports_persona_findings_without_rewriting_them():
    """人格结论并入报告，但**判据只有一份**（pyv/persona.py）。"""
    report = review.check_text("pg-parallel-decode")
    rules = {s.rule for s in report.signals}
    assert any(rule.startswith("persona.") for rule in rules)
    assert any("人格检查" in note for note in report.notes)


# ---------------------------------------------------------------- 成片层


def _frame(path: Path, index: int = 1, time: float = 1.0,
           subtitle: str = "", scene_id: str = "s01") -> review.Frame:
    return review.Frame(index=index, time=time, scene_id=scene_id,
                        path=path, kind="scene", subtitle=subtitle)


def _png(path: Path, color: tuple[int, int, int], band: bool = False) -> Path:
    from PIL import Image

    image = Image.new("RGB", (320, 180), color)
    if band:
        # 底部字幕带里画一块深色，模拟烧上去的字幕。
        for x in range(40, 200):
            for y in range(150, 170):
                image.putpixel((x, y), (27, 42, 71))
    image.save(path)
    return path


def _png_with_content(path: Path) -> Path:
    """一张**有内容**的帧：横向渐变，标准差够大。"""
    from PIL import Image

    image = Image.new("RGB", (320, 180))
    for x in range(320):
        for y in range(180):
            image.putpixel((x, y), (x, y, (x + y) % 256))
    image.save(path)
    return path


def test_vv_01_flags_a_blank_frame(tmp_path):
    path = _png(tmp_path / "blank.png", (255, 255, 255))
    signals = review.vv_01_blank_frames([_frame(path)])
    assert _rules(signals) == {"VV-01"}


def test_vv_01_accepts_a_frame_with_content(tmp_path):
    path = _png_with_content(tmp_path / "full.png")
    assert review.vv_01_blank_frames([_frame(path)]) == []


def test_vv_02_flags_a_frame_without_subtitle_pixels(tmp_path):
    path = _png(tmp_path / "nosub.png", (255, 255, 255))
    signals = review.vv_02_missing_subtitle([_frame(path, subtitle="一句字幕")])
    assert _rules(signals) == {"VV-02"}


def test_vv_02_accepts_a_frame_with_subtitle_pixels(tmp_path):
    path = _png(tmp_path / "sub.png", (255, 255, 255), band=True)
    assert review.vv_02_missing_subtitle([_frame(path, subtitle="一句字幕")]) == []


def test_vv_02_skips_frames_without_a_subtitle(tmp_path):
    """没有字幕的帧（片头片尾）不该被查。"""
    path = _png(tmp_path / "plain.png", (255, 255, 255))
    assert review.vv_02_missing_subtitle([_frame(path, subtitle="")]) == []


def test_vv_03_flags_a_gap_in_the_narration(monkeypatch):
    """旁白中间断了一句 → 命中。

    判据是「句与句之间的空档」，所以这里注入的是有声片段序列。
    """
    from pyv import align

    monkeypatch.setattr(align, "detect_sentences",
                        lambda path, **kwargs: [(0.0, 1.0), (2.5, 4.0)])
    media = review.Media(episode="test-ep", video=None, storyboard=None,
                          narration=Path("/tmp/n.mp3"), bgm=None)
    signals = review.vv_03_narration_silence(media)
    assert _rules(signals) == {"VV-03"}


def test_vv_03_ignores_the_leading_and_trailing_silence(monkeypatch):
    """开头与结尾的静音是录音的边，不是断句。"""
    from pyv import align

    monkeypatch.setattr(align, "detect_sentences",
                        lambda path, **kwargs: [(0.0, 3.0)])
    media = review.Media(episode="test-ep", video=None, storyboard=None,
                          narration=Path("/tmp/n.mp3"), bgm=None)
    assert review.vv_03_narration_silence(media) == []


def test_vv_03_on_a_real_audio_file(tmp_path):
    """真音频：1 秒正弦 + 1.5 秒静音 + 1 秒正弦。

    需要 ffprobe（本机可能没装）——**没有就跳过，不假装验过**。
    """
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("本机缺 ffmpeg 或 ffprobe")
    audio = tmp_path / "gap.wav"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1",
        str(audio),
    ], check=True, capture_output=True)
    media = review.Media(episode="test-ep", video=None, storyboard=None,
                          narration=audio, bgm=None)
    assert _rules(review.vv_03_narration_silence(media)) == {"VV-03"}


def test_vv_04_flags_a_duration_mismatch(monkeypatch):
    """时长对不上 → error 级（不是 warn：这条会让平台拒收）。"""
    monkeypatch.setattr(review, "_probe_duration", lambda path: 10.0)
    storyboard = _storyboard(duration=12.0)
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=storyboard, narration=None, bgm=None)
    signals = review.vv_04_duration(media)
    assert _rules(signals) == {"VV-04"}
    assert signals[0].severity == review.ERROR


def test_vv_04_accepts_a_matching_duration(monkeypatch):
    monkeypatch.setattr(review, "_probe_duration", lambda path: 12.0)
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=_storyboard(duration=12.0),
                          narration=None, bgm=None)
    assert review.vv_04_duration(media) == []


def _storyboard(duration: float = 10.0):
    from pyv.timeline import Audio, Scene, SubtitleStyle, Video, Storyboard

    return Storyboard(
        version=1,
        video=Video(width=1920, height=1080, fps=24, duration=duration),
        audio=Audio(narration="n.mp3"),
        subtitle_style=SubtitleStyle(primary="#1B2A47", outline="#FFFFFF"),
        scenes=[Scene(id="s01", start=0.0, end=duration, type="code",
                      subtitle="一句")],
    )


def test_vv_07_maps_a_platform_failure_to_an_error(monkeypatch):
    """平台门槛不合格 → error。判据调 `preflight.py`，这里只验接缝。"""
    from pyv import preflight
    from pyv.epmeta import Finding

    info = preflight.VideoInfo(
        width=320, height=240, fps=24.0, duration=10.0, video_codec="h264",
        pix_fmt="yuv420p", audio_codec="aac", sample_rate=48000,
        channels=2, audio_bitrate=192000, video_bitrate=1000000,
        size_bytes=1000)
    monkeypatch.setattr(preflight, "probe", lambda path: info)
    monkeypatch.setattr(preflight, "check_video",
                        lambda info, platform, capabilities_dir=None: [
                            Finding("preflight.resolution", "error", "太小了")])
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=None, narration=None, bgm=None)
    signals = review.vv_07_platform(media)
    assert _rules(signals) == {"VV-07"}
    assert signals[0].severity == review.ERROR


def test_vv_06_flags_a_bad_mix(monkeypatch):
    """混音不合格 → 命中。判据调 `bgm.py`，这里只验接缝。"""
    from pyv import bgm

    monkeypatch.setattr(bgm, "measure_mix", lambda *args, **kwargs: object())
    monkeypatch.setattr(bgm, "check_mix", lambda report: [
        bgm.Finding("bgm.mix-duck-depth", bgm.ERROR,
                    "稳态 duck 深度实测 3.20 dB，应为 18.0 ± 1.0 dB")])
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=_storyboard(duration=12.0),
                          narration=Path("/tmp/n.mp3"), bgm=Path("/tmp/b.wav"))
    signals = review.vv_06_mix(media)
    assert _rules(signals) == {"VV-06"}


def test_vv_06_accepts_a_good_mix(monkeypatch):
    from pyv import bgm

    monkeypatch.setattr(bgm, "measure_mix", lambda *args, **kwargs: object())
    monkeypatch.setattr(bgm, "check_mix", lambda report: [
        bgm.Finding("bgm.mix-info", bgm.WARNING, "差一点点")])
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=_storyboard(duration=12.0),
                          narration=Path("/tmp/n.mp3"), bgm=Path("/tmp/b.wav"))
    assert review.vv_06_mix(media) == []


def test_vv_04_says_so_when_it_cannot_run(monkeypatch):
    """规则跑不动的时候必须说话。

    静默返回空列表和「查了没问题」在报告里长得一模一样——
    混起来就成了假装绿。
    """
    monkeypatch.setattr(review, "_probe_duration", lambda path: None)
    notes: list[str] = []
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=_storyboard(duration=12.0),
                          narration=None, bgm=None)
    assert review.vv_04_duration(media, notes) == []
    assert notes and "VV-04" in notes[0]


def test_brand_frames_are_not_judged_as_blank():
    """品牌片是共享素材，片头第一帧的黑场是淡入，不是漏画。

    拿 VV-01 去判它，每期都会报一条假警。
    """
    brand = review.Frame(index=1, time=0.0, scene_id="brand_intro",
                         path=Path("/tmp/x.png"), kind="keyframe")
    body = review.Frame(index=2, time=5.0, scene_id="s01",
                         path=Path("/tmp/y.png"), kind="scene")
    assert review._is_brand_frame(brand)
    assert not review._is_brand_frame(body)


def test_the_frame_on_the_brand_boundary_counts_as_brand():
    """品牌片淡出到白场，最后那一帧落在正文段上——它是品牌片的淡出。

    实测 ep01：品牌片 2.833 s 结束，2.79 s 之后已是纯白；
    编码器切出来的关键帧落在 2.8333 s（属于 s01），
    VV-01 报了一条假警。边界要给半帧多的容差。
    """
    from pyv.timeline import Scene

    storyboard = _storyboard(duration=10.0)
    storyboard.scenes.insert(0, Scene(id="brand_intro", start=0.0, end=2.833,
                                       type="clip", subtitle=""))
    boundary = review.Frame(index=1, time=2.8333, scene_id="s01",
                            path=Path("/tmp/x.png"), kind="keyframe")
    inside = review.Frame(index=2, time=5.0, scene_id="s01",
                          path=Path("/tmp/y.png"), kind="scene")
    assert review._is_brand_frame(boundary, storyboard)
    assert not review._is_brand_frame(inside, storyboard)


def test_narration_gaps_stay_below_the_silence_threshold():
    """阈值是**量出来的**，不是拍的。

    六期旁白共 74 处句间间隙，实测全部落在 0.25~0.748 s。
    阈值必须高于这个最大值，否则会把正常的换气报成「静音」——
    这条测试就是钉住它的：阈值一降，这里就红。
    """
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("本机缺 ffmpeg 或 ffprobe")
    from pyv import align

    worst = 0.0
    for episode in episodes.EPISODE_ORDER:
        spans = align.detect_sentences(episodes.narration_path(episode))
        for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
            worst = max(worst, next_start - prev_end)
    assert worst < review.NARRATION_SILENCE_S, (
        f"实测最大句间间隙 {worst:.3f}s ≥ 阈值 {review.NARRATION_SILENCE_S}s："
        "阈值会误报正常的换气")


# ---------------------------------------------------------------- 抽帧


def test_every_scene_gets_a_mid_frame_and_a_late_frame(monkeypatch, tmp_path):
    """每段抽两帧：段中点 + 段尾。

    只抽段中点会把「结论还在淡入」当成「漏字」——实测 ep06 的 s02：
    段中点上结论框已经画出来了，框里的字还没显影。
    """
    grabbed: list[float] = []

    def fake_grab(video, t, out):
        grabbed.append(t)
        out.write_bytes(b"png")
        return True

    monkeypatch.setattr(review, "_grab", fake_grab)
    monkeypatch.setattr(review, "_keyframe_times", lambda video: [])
    video = tmp_path / "x.mp4"
    video.write_bytes(b"mp4")
    media = review.Media(episode="test-ep", video=video,
                          storyboard=_storyboard(duration=10.0),
                          narration=None, bgm=None)
    frames = review.extract_frames(media, tmp_path)
    assert [frame.kind for frame in frames] == ["scene", "late"]
    assert [round(frame.time, 3) for frame in frames] == [5.0, 8.5]


def test_expected_text_flattens_nested_params():
    """契约里的文案不只在顶层。

    `s03.modes` 是 `[["KEY SHARE", "FOR KEY SHARE"], …]`，只取顶层字符串，
    清单会漏掉一半以上该有的字——「字对不对」这一问就无从回答。
    """
    from pyv import contract as contract_mod

    segment = contract_mod.Segment(
        id="s03",
        renderer="pyv.scenes.s03_lock_modes",
        sentences=(0,),
        params={"title": "MVCC 之上", "modes": [["KEY SHARE", "FOR KEY SHARE"]],
                "matrix": [[True, False]]},
    )
    text = review._expected_text([segment], "s03")
    assert "MVCC 之上" in text
    assert "KEY SHARE" in text
    assert "FOR KEY SHARE" in text


def test_vv_05_flags_a_long_keyframe_gap(monkeypatch):
    from pyv import preflight

    monkeypatch.setattr(preflight, "keyframe_gaps",
                        lambda video: (3.0, 12.5))
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=None, narration=None, bgm=None)
    signals = review.vv_05_keyframes(media)
    assert _rules(signals) == {"VV-05"}


def test_vv_05_accepts_a_short_keyframe_gap(monkeypatch):
    from pyv import preflight

    monkeypatch.setattr(preflight, "keyframe_gaps", lambda video: (3.0, 8.0))
    media = review.Media(episode="test-ep", video=Path("/tmp/x.mp4"),
                          storyboard=None, narration=None, bgm=None)
    assert review.vv_05_keyframes(media) == []


def test_video_layer_says_what_it_skipped_when_artifacts_are_missing(monkeypatch):
    """产物不在 → note 说清跳过什么。**不静默跳过，也不假装绿。**"""
    monkeypatch.setattr(review, "load_media", lambda episode: review.Media(
        episode=episode, video=None, storyboard=None, narration=None, bgm=None,
        notes=["成片不在本机"]))
    report = review.check_video("pg-parallel-decode")
    assert report.notes
    assert any("跳过" in note or "不在本机" in note for note in report.notes)


def test_a_frame_on_a_segment_boundary_belongs_to_the_later_segment():
    """边界上的那一帧，画面上已经是后一段了。

    相邻两段共用一个端点；编码器切出来的关键帧常正好落在端点上。
    按「先到先得」找第一个包含 t 的段，会把清单里的「视觉段」列
    整体错位一格——实测 ep03 有四个关键帧这么错。
    """
    from pyv.timeline import Scene

    storyboard = _storyboard(duration=10.0)
    storyboard.scenes = [
        Scene(id="s01", start=0.0, end=6.0, type="code", subtitle=""),
        Scene(id="s02", start=6.0, end=10.0, type="code", subtitle=""),
    ]
    assert review._scene_at(storyboard, 6.0) == "s02"
    assert review._scene_at(storyboard, 5.999) == "s01"


def test_a_keyframe_on_the_real_cut_belongs_to_the_later_segment():
    """关键帧常正好落在**成片里的真实切点**上，而真实切点比名义边界早一帧。

    实测 parallel-apply：名义 s01→s02 在 5.977 s，真实切点在 5.958 s
    （s01 渲染 round(3.144*24) = 75 帧 = 3.125 s），而关键帧就在 5.958 s。
    按名义秒归属，画面上已经是 s02、归属却记成 s01，抽帧清单就拿 s01 的
    文案去核对 s02 的画面——一整片假漏字。
    """
    from pyv.timeline import Scene

    storyboard = _storyboard(duration=10.0)
    storyboard.scenes = [
        Scene(id="s01", start=0.0, end=3.144, type="code", subtitle=""),
        Scene(id="s02", start=3.144, end=7.144, type="code", subtitle=""),
    ]
    assert review._scene_at(storyboard, 3.125) == "s02"
    assert review._scene_at(storyboard, 3.1249) == "s01"


def test_a_keyframe_one_microsecond_early_still_belongs_to_the_later_segment(monkeypatch, tmp_path):
    """ffprobe 的关键帧时间差最后一位小数，归属要吸附到帧网格。

    真实切点在 143/24 = 5.9583333…，ffprobe 报的是 5.958333（差 3e-7）。
    不吸附就判给上一段，而画面上已经是下一段了。
    """
    from pyv.timeline import Scene

    storyboard = _storyboard(duration=10.0)
    storyboard.scenes = [
        Scene(id="s01", start=0.0, end=5.977, type="code", subtitle=""),
        Scene(id="s02", start=5.977, end=9.977, type="code", subtitle=""),
    ]
    # s01 渲染 round(5.977*24) = 143 帧 = 5.9583333 s。
    assert review._scene_at(storyboard, 143 / 24) == "s02"
    assert review._scene_at(storyboard, 5.958333) == "s01"  # 未吸附：差 3e-7

    grabbed: list[tuple[float, str]] = []

    def fake_grab(video, t, out):
        grabbed.append((t, ""))
        out.write_bytes(b"png")
        return True

    monkeypatch.setattr(review, "_grab", fake_grab)
    monkeypatch.setattr(review, "_keyframe_times", lambda video: [5.958333])
    video = tmp_path / "x.mp4"
    video.write_bytes(b"mp4")
    media = review.Media(episode="test-ep", video=video, storyboard=storyboard,
                          narration=None, bgm=None)
    frames = review.extract_frames(media, tmp_path)
    keyframe = [f for f in frames if f.kind == "keyframe"]
    assert [f.scene_id for f in keyframe] == ["s02"]
    assert keyframe[0].time == pytest.approx(143 / 24)


def test_the_mid_and_late_frames_are_taken_from_the_real_span(monkeypatch, tmp_path):
    """抽帧时间按成片里的真实区间算，不按时间轴上的名义秒。

    名义秒与真实切点差最多一帧；按名义秒抽出来的「段中点」可能落在
    上一段的尾巴上——那一帧画的是上一段，清单却拿这一段的文案去核对。
    """
    grabbed: list[float] = []

    def fake_grab(video, t, out):
        grabbed.append(t)
        out.write_bytes(b"png")
        return True

    monkeypatch.setattr(review, "_grab", fake_grab)
    monkeypatch.setattr(review, "_keyframe_times", lambda video: [])
    video = tmp_path / "x.mp4"
    video.write_bytes(b"mp4")

    from pyv.timeline import Scene

    storyboard = _storyboard(duration=10.0)
    storyboard.scenes = [
        Scene(id="s01", start=0.0, end=3.144, type="code", subtitle=""),
        Scene(id="s02", start=3.144, end=7.144, type="code", subtitle=""),
    ]
    media = review.Media(episode="test-ep", video=video, storyboard=storyboard,
                          narration=None, bgm=None)
    frames = review.extract_frames(media, tmp_path)
    # s01 真实区间 0~3.125，s02 真实区间 3.125~7.125（名义起点是 3.144）。
    # 时间码吸附到帧网格上：清单里每个时间码都是成片里的一帧号。
    assert [round(frame.time, 4) for frame in frames] == [
        1.5833, 2.6667, 5.1250, 6.5417,
    ]


# ---------------------------------------------------------------- 跨模块一致性


def _load_document_checker():
    """按路径加载 `tools/review-check.py`。

    `tools/` 不是包，跨目录 import 靠 sys.path 补丁——那是最容易在换机器时
    断掉的接缝。这里按文件路径加载，只在**测试**里做。
    """
    spec = importlib.util.spec_from_file_location("doc_review_check", TOOLS_CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 先进 sys.modules：`@dataclass` 装饰器要回头查模块自己的 __dict__，
    # 没登记会 AttributeError。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_text_rule_vocabulary_matches_the_document_checker():
    """视频侧的词表与文档侧**逐字相同**。改一边，另一边要红。"""
    document = _load_document_checker()
    assert review.CONNECTORS == document.CONNECTORS
    assert review.VAGUE_WORDS == document.VAGUE_WORDS
    assert review.GENERIC_ENDINGS == document.GENERIC_ENDINGS
    assert review.GENERIC_ENDING_RE.pattern == document.GENERIC_ENDING_RE.pattern


def test_text_rule_thresholds_match_the_document_checker():
    """阈值也要相同——阈值跟着生产常量走，守卫就永远是绿的。"""
    document = _load_document_checker()
    assert review.CONNECTOR_RATIO == document.CONNECTOR_RATIO
    assert review.DUPLICATE_THRESHOLD == document.DUPLICATE_THRESHOLD
    assert review.DUPLICATE_MIN_LEN == document.DUPLICATE_MIN_LEN
    assert review.DUPLICATE_MIN_CJK == document.DUPLICATE_MIN_CJK


def test_review_module_does_not_import_the_tools_checker():
    """词表是**抄**的，不是 import 的。

    `tools/` 不是包；靠 sys.path 补丁 import 它，换机器就会断。
    """
    source = Path(review.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+tools", source, re.MULTILINE)
    assert not re.search(r"sys\.path\s*\.(insert|append)", source)
    assert "importlib" not in source


# ---------------------------------------------------------------- 记录与进度表


def test_every_episode_has_a_review_record():
    """六期一期一条记录。"""
    records = review.REVIEW_DIR / "episodes"
    assert records.is_dir()
    for episode in episodes.EPISODE_ORDER:
        path = records / f"{episode}.md"
        assert path.is_file(), f"缺审核记录：{path}"


def test_review_records_match_the_index():
    """进度表与记录一一对应。

    **两处维护必然不一致**，而索引会变成噪声源——所以它由测试钉住。
    """
    index = (review.REVIEW_DIR / "INDEX.md").read_text(encoding="utf-8")
    rows = [line for line in index.splitlines()
            if re.match(r"^\|\s*ep\d\d\s*\|", line)]
    assert len(rows) == len(episodes.EPISODE_ORDER)
    for episode in episodes.EPISODE_ORDER:
        assert episode in index
        record = (review.REVIEW_DIR / "episodes" / f"{episode}.md")
        assert record.is_file()


def _pending_items(record: Path) -> int:
    """记录里「优先修改」中**还没改掉**的条数。

    一条算「已改」有两个标记：`已改`（改完了，成片还没重出）与
    `已合入`（改完、重出片、复审通过）。没写状态的算「待改」。
    """
    text = record.read_text(encoding="utf-8")
    section = text.split("## 优先修改", 1)[1].split("\n## ", 1)[0]
    lines = section.splitlines()
    pending = 0
    index = 0
    while index < len(lines):
        if not re.match(r"^\d+\.\s+位置：", lines[index]):
            index += 1
            continue
        # 这一条的其余行（到下一条为止）里有没有「已改 / 已合入」
        done = False
        probe = index + 1
        while probe < len(lines) and not re.match(r"^\d+\.\s+位置：", lines[probe]):
            if re.match(r"^\s+- 状态：(已改|已合入)", lines[probe]):
                done = True
            probe += 1
        if not done:
            pending += 1
        index = probe
    return pending


def test_the_index_pending_count_matches_the_records():
    """进度表的「待确认项」一列 == 记录里还没改掉的条数。

    **两处维护必然不一致**：改了记录忘了改表，或者改了表忘了改记录。
    索引一旦是噪声，就没人再看它——所以由测试钉住。

    「待确认项」记的是**还没改掉**的条数，不是「优先修改」的总条数：
    已改的条目仍然留在记录里（它是改动的依据），但不再欠着。
    """
    index = (review.REVIEW_DIR / "INDEX.md").read_text(encoding="utf-8")
    for episode in episodes.EPISODE_ORDER:
        row = next(line for line in index.splitlines()
                   if line.strip().startswith("|")
                   and [c.strip() for c in line.strip("|").split("|")][1:2]
                   == [episode])
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[-2].isdigit(), f"{episode} 的「待确认项」列不是数字：{cells[-2]}"
        pending = _pending_items(
            review.REVIEW_DIR / "episodes" / f"{episode}.md")
        assert int(cells[-2]) == pending, (
            f"{episode}：进度表写着 {cells[-2]} 条待确认，"
            f"记录里没改掉的是 {pending} 条——对一下"
        )


def test_review_records_are_not_published():
    """`aiv/review/` 只记录审核过程，不是对外发布内容。

    发布白名单里不能有它——`sync_publish_docs.py` 是「哪些文档要发布」的
    唯一真相，审核记录进去了就变成线上文章。
    """
    sync = (review.AIV_ROOT / "scripts" / "sync_publish_docs.py")
    source = sync.read_text(encoding="utf-8")
    assert "review/" not in source


def test_the_six_episode_records_exist_with_a_status_line():
    """每条记录都带状态行——状态是进度表的依据。"""
    records = review.REVIEW_DIR / "episodes"
    for episode in episodes.EPISODE_ORDER:
        text = (records / f"{episode}.md").read_text(encoding="utf-8")
        assert re.search(r"^- 状态：", text, re.MULTILINE), episode
