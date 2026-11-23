"""混音阶段不许再编码视频：成片的视频流必须与 silent.mp4 逐帧一致。

**为什么**
----------
成片原来把视频编码了三遍：分段渲染一遍 → concat 拼一遍 → 混音又一遍。
第三遍纯属浪费——`silent.mp4` 已经是 libx264 / yuv420p / 时间基 24000，
`-c:v copy` 就能直接贴上去。12 分钟的片子能省掉十几分钟。

**这两条断言分两层**
--------------------
- **命令层**：混音命令里必须出现 `-c:v copy`，且不许出现 `libx264`；
- **成片层**：真出一遍，比对成片与 `silent.mp4` 的**视频帧校验和**——
  只比命令不够，命令对了而实际仍重编码的情况也要能抓到。

跑法::

    cd video/pipeline && python3 -m pytest tests/test_compose_no_reencode.py -q
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pyv import compose
from pyv.timeline import Audio, Scene, Storyboard, SubtitleStyle, Video


def _storyboard() -> Storyboard:
    """一个最小的 storyboard——**不依赖入库产物**。

    `storyboard*.json` 是产物、不入库（见 `video/pipeline/.gitignore`），
    测试读不到它，所以这里现造一个。
    """
    return Storyboard(
        version=1,
        video=Video(width=320, height=180, fps=24, duration=2.0),
        audio=Audio(narration=""),
        subtitle_style=SubtitleStyle(primary="#1B2A47", outline="#FFFFFF"),
        scenes=[Scene(id="s01", start=0.0, end=2.0, type="code",
                      subtitle="", renderer="pyv.scenes.s01_intro")],
        subtitles=[],
    )


def _tone(path: Path, seconds: float = 2.0) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}", str(path)],
        check=True,
    )
    return path


def _video_md5(path: Path) -> str:
    """视频流的帧校验和——比逐字节比文件更贴近「画面没被重新编码」。"""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
         "-f", "framemd5", "-"],
        capture_output=True, text=True,
    )
    return proc.stdout


def _bitstream_md5(path: Path) -> str:
    """**码流**（压缩包）的指纹——比帧校验和更严。

    帧校验和只比「解码出来的画面」；码流指纹比「压缩后的字节」。
    重编码必改码流，copy 必不改。
    """
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
         "-c", "copy", "-f", "md5", "-"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip()


def test_mux_command_copies_the_video_stream(tmp_path):
    """混音命令里必须是 -c:v copy，不许再出现 libx264。"""
    storyboard = _storyboard()
    tone = _tone(tmp_path / "tone.wav")
    cmd = compose._mux_cmd(
        tmp_path / "silent.mp4", tmp_path / "out.mp4", storyboard,
        [(tone, 0.0, compose.VOICE_CHAIN)],
    )
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "libx264" not in cmd


def test_the_final_video_has_the_same_frames_as_the_silent_one(tmp_path):
    """真出一遍：成片的视频帧校验和必须与 silent.mp4 一致。

    ⚠️ **夹具不能用纯色**（`color=c=blue` 之类）：
    纯色画面重编码之后**逐帧一模一样**，帧校验和根本不变——
    这条断言会**恒真**，重编码也照样全绿（实测过）。
    这里用 `testsrc2`（自带渐变与噪声），重编码必改帧。
    """
    storyboard = _storyboard()

    clips = []
    for index in range(2):
        out = tmp_path / f"clip{index}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", f"testsrc2=s={storyboard.video.width}x{storyboard.video.height}"
             f":d=1:r={storyboard.video.fps}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-video_track_timescale", str(storyboard.video.fps * 1000),
             str(out)],
            check=True,
        )
        clips.append(out)

    concat = tmp_path / "concat.txt"
    concat.write_text(
        "".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8"
    )
    silent = tmp_path / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat), *compose.concat_encode_args(), "-an", str(silent)],
        check=True,
    )

    final = tmp_path / "final.mp4"
    tone = _tone(tmp_path / "tone.wav")
    cmd = compose._mux_cmd(silent, final, storyboard,
                           [(tone, 0.0, compose.VOICE_CHAIN)])
    subprocess.run(cmd, check=True)

    assert _video_md5(final) == _video_md5(silent)
    # 码流也要一模一样——帧一样但码流不同，说明画面被重新压缩过
    assert _bitstream_md5(final) == _bitstream_md5(silent)
