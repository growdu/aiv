"""铺底循环：曲子不够长时接回自己，接缝落在最安静处。

**为什么要有这一层**
------------------
`duck_bgm` 原来取 `min(曲子长度, 旁白长度)`——曲子不够长时铺底直接断掉。
实测 300 s 旁白只铺出 209.23 s：12 分钟的片子会有 8 分多钟没有音乐。

**这条守卫分三层**（2026-11-15 评审补记）：
原计划里的两条接缝守卫是**恒真断言**——
`seam_jump <= jumps.max() * 1.001` 左边是**子集**最大值、右边是全集最大值；
`seam_energy < whole_energy` 的测量窗整个落在淡化斜坡内，幅度被 ramp 压到约
0.026 倍，天然远低于整首均值，**与接缝落在哪无关**。注入缺陷后它们仍全绿。

所以拆开：

- **单元级**：`_quiet_seam` 返回的就是全曲 2×fade 窗口能量的**最小值**；
- **集成级**：**淡化前**的接缝素材能量低于整曲均值；
- **click 级**：接缝跳变与**典型**跳变比（99.9 分位 × 1.5），不是与最大值比。

跑法::

    cd video/pipeline && python3 -m pytest tests/test_bgm_loop.py -q
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from pyv import bgm

SAMPLE_RATE = 48000


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _make_bgm(path: Path, seconds: float, sample_rate: int = SAMPLE_RATE) -> Path:
    """造一条测试用曲子：正弦 + 中间一段安静。"""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    quiet = np.zeros_like(tone)
    middle = slice(len(tone) // 3, len(tone) // 3 + len(tone) // 10)
    tone[middle] = 0.0
    stereo = np.stack([tone, tone], axis=1).astype(np.float32)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ac", "2",
         "-ar", str(sample_rate), "-i", "-", str(path)],
        input=stereo.tobytes(), check=True,
    )
    return path


def _make_two_level_bgm(path: Path, seconds: float,
                         sample_rate: int = SAMPLE_RATE) -> Path:
    """造一条**开头响、后面安静**的曲子（响度差 20 dB）。

    为什么需要它：循环铺底会把曲子**旋转**（接缝落在最安静处），
    于是「循环后的铺底」与「原曲」在时间轴上就**不是同一段素材**了。
    拿原曲当对照去量 duck 深度，量到的是两段不同素材的 RMS 差。

    ⚠️ **响段必须在开头，而且不能占一半**：
    响段占一半时，接缝落在中点，旋转后的素材与原曲关于中点对称——
    「原曲的响段」和「铺底的响段」正好错开，两边的 RMS 差**互相抵消**，
    拿错对照也量出 7 dB（实测：6.95 vs 6.99）。
    响段缩到开头 1 秒，对照错掉时立刻偏到 20 dB。
    """
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    tone[: int(1.0 * sample_rate)] *= 1.0    # 开头 1 秒：响
    tone[int(1.0 * sample_rate):] *= 0.1    # 其余：安静（接缝落在这里 → 曲子被旋转）
    stereo = np.stack([tone, tone], axis=1).astype(np.float32)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ac", "2",
         "-ar", str(sample_rate), "-i", "-", str(path)],
        input=stereo.tobytes(), check=True,
    )
    return path


def _make_narration(path: Path, seconds: float, sample_rate: int = SAMPLE_RATE,
                    speech_every_s: float = 3.0,
                    speech_s: float = 1.5) -> Path:
    """造一段旁白：每 ``speech_every_s`` 秒说 ``speech_s`` 秒。

    ⚠️ **说话段必须够长**：包络的上升时间常数是 120 ms，
    爬到 `SATURATED_ENVELOPE`（0.99）要 560 ms——
    0.6 s 的短句根本到不了平台期，「饱和帧」是空的，量不出压深。
    """
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    voice = np.zeros_like(t)
    step = int(speech_every_s * sample_rate)
    span = int(speech_s * sample_rate)
    for start in range(0, len(voice) - span, step):
        voice[start:start + span] = 0.2
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ac", "1",
         "-ar", str(sample_rate), "-i", "-", str(path)],
        input=voice.astype(np.float32).tobytes(), check=True,
    )
    return path


def _window_samples() -> int:
    return max(1, int(round(bgm.LOOP_FADE_S * SAMPLE_RATE)))


# ── 单元级：接缝点选得对不对 ───────────────────────────────


def test_quiet_seam_picks_the_minimum_energy_window(tmp_path):
    """`_quiet_seam` 必须返回**全曲 2×fade 窗口能量的最小值**那个窗口的中心。

    这是「接缝落在最安静处」这句话的**可判定形式**——
    原来那条集成断言测不到它（测量窗整个落在淡化斜坡内，与接缝位置无关）。
    """
    src = _make_bgm(tmp_path / "bgm.wav", 10.0)
    song = bgm._decode_stereo(src, SAMPLE_RATE)
    window = _window_samples()
    seam = bgm._quiet_seam(song, window)

    power = (song ** 2).mean(axis=1)          # 逐声道功率（不是带符号均值）
    cumulative = np.concatenate([[0.0], np.cumsum(power)])
    energies = cumulative[2 * window:] - cumulative[:-2 * window]
    best = int(np.argmin(energies)) + window
    assert seam == best


def test_quiet_seam_uses_per_channel_power():
    """左右反相的立体声，用带符号的单声道均值会选错位置。

    带符号均值可以很小而实际很响——接缝会选到响处。
    """
    sample_rate = 1000
    # 左正右负：带符号均值恒为 0，逐声道功率却是满的
    t = np.arange(sample_rate) / sample_rate
    left = 0.5 * np.sin(2 * np.pi * 100 * t)
    song = np.stack([left, -left], axis=1)
    window = 10
    seam = bgm._quiet_seam(song, window)
    # 真的按逐声道功率算：每一处窗口能量都一样，取第一个最小值
    power = (song ** 2).mean(axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(power)])
    energies = cumulative[2 * window:] - cumulative[:-2 * window]
    assert seam == int(np.argmin(energies)) + window


# ── 集成级：循环出来的铺底 ─────────────────────────────────


def test_loop_bgm_covers_the_requested_duration(tmp_path):
    """循环后的铺底长度必须盖住请求的时长。"""
    src = _make_bgm(tmp_path / "bgm.wav", 10.0)
    out = bgm.loop_bgm(src, duration_s=35.0, sample_rate=SAMPLE_RATE)
    assert out.shape == (35 * SAMPLE_RATE, 2)


def test_loop_bgm_returns_the_track_unchanged_when_it_is_long_enough(tmp_path):
    """曲子本来就够长时，输出应当就是曲子本身（不改变已有成片）。"""
    src = _make_bgm(tmp_path / "bgm.wav", 30.0)
    out = bgm.loop_bgm(src, duration_s=10.0, sample_rate=SAMPLE_RATE)
    assert out.shape == (10 * SAMPLE_RATE, 2)
    decoded = bgm._decode_stereo(src, SAMPLE_RATE)
    assert np.allclose(out[: decoded.shape[0]], decoded[: out.shape[0]], atol=1e-6)


def test_the_seam_material_is_quiet_before_the_fade(tmp_path):
    """**淡化前**的接缝素材必须比整曲安静——否则循环处会「咔」一下。

    这里量的是**素材本身**（曲子在接缝处的那一段），
    不是循环输出里被 ramp 压过的那一段——
    压过之后就恒低于均值了，跟接缝选得对不对无关。
    """
    src = _make_bgm(tmp_path / "bgm.wav", 10.0)
    song = bgm._decode_stereo(src, SAMPLE_RATE)
    window = _window_samples()
    seam = bgm._quiet_seam(song, window)
    material = song[seam - window: seam + window]
    assert float(np.mean(material ** 2)) < float(np.mean(song ** 2))


def test_loop_bgm_does_not_click_at_the_seam(tmp_path):
    """接缝处不许有咔哒：跳变不得比**典型**跳变大太多。

    与**最大值**比是恒真的（最大值必然在全集里），
    所以这里跟 99.9 分位比。
    """
    src = _make_bgm(tmp_path / "bgm.wav", 10.0)
    out = bgm.loop_bgm(src, duration_s=25.0, sample_rate=SAMPLE_RATE)
    period = 10 * SAMPLE_RATE
    jumps = np.abs(np.diff(out, axis=0)).max(axis=1)
    seam_jump = float(jumps[period - 600: period + 600].max())
    typical = float(np.percentile(jumps, 99.9))
    assert seam_jump <= typical * 1.5, (
        f"接缝处跳变 {seam_jump:.6f} 超过典型跳变 {typical:.6f} 的 1.5 倍——会咔哒"
    )


# ── 核心：铺底要盖住整段正文 ───────────────────────────────


def test_duck_bgm_covers_the_whole_narration(tmp_path):
    """铺底必须盖住整段旁白——这条是本次修的核心。

    曲子 10 s、旁白 300 s：旧行为只铺出 10 s。
    """
    narration = _make_narration(tmp_path / "narration.wav", 300.0)
    src = _make_bgm(tmp_path / "bgm.wav", 10.0)
    out = bgm.duck_bgm(src, narration, tmp_path / "ducked.wav")
    assert _wav_seconds(out) >= 300.0 - 0.5


def test_duck_bgm_still_respects_the_duck_depth(tmp_path):
    """循环之后 duck 深度仍然精确（不许因为循环把包络搞坏）。"""
    seconds = 20.0
    narration = _make_narration(tmp_path / "narration.wav", seconds)
    src = _make_bgm(tmp_path / "bgm.wav", 8.0)
    out = bgm.duck_bgm(src, narration, tmp_path / "ducked.wav", duration_s=seconds)

    # 对照的是**同一份循环铺底**，不是原曲——循环后开头已经不是原曲开头了。
    # 只在**饱和帧**上量：词间空隙处包络在回落，增益本来就在回升，
    # 拿它一起算会把压深算浅（这正是 `saturated_mask` 存在的理由）。
    bed = bgm.loop_bgm(src, duration_s=seconds, sample_rate=SAMPLE_RATE)
    ducked = bgm._decode_stereo(out, SAMPLE_RATE)
    narration_samples = bgm.decode_mono(narration, SAMPLE_RATE)
    mask = bgm.saturated_mask(narration_samples, SAMPLE_RATE)
    length = min(bed.shape[0], ducked.shape[0], mask.size)
    saturated = mask[:length]
    assert saturated.any(), "没有饱和帧——夹具的说话段太短，包络爬不到平台期"
    gain_db = (bgm._rms_db(ducked[:length].mean(axis=1)[saturated])
               - bgm._rms_db(bed[:length].mean(axis=1)[saturated]))
    assert gain_db == pytest.approx(bgm.DUCK_DEPTH_DB, abs=0.5)


def test_measure_duck_depth_uses_the_looped_bed_as_its_reference(tmp_path):
    """成片级判据的对照物必须是**同一份循环铺底**。

    拿原母带当对照，量到的不是 duck 深度，而是「两段不同素材的 RMS 差」——
    实测能偏到 20 dB（设定 7 dB）。

    这条曲子**前后两段差 10 倍**：循环铺底会把它旋转（接缝落在最安静处），
    于是「循环后的铺底」与「原曲」已经不是同一段素材——
    对照物一错，量出来的压深立刻离谱。
    """
    src = _make_two_level_bgm(tmp_path / "bgm.wav", 6.0)
    narration = _make_narration(tmp_path / "narration.wav", 30.0)
    measured = bgm.measure_duck_depth(src, narration)
    assert measured == pytest.approx(abs(bgm.DUCK_DEPTH_DB), abs=0.5)
