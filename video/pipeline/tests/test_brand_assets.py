"""品牌片成片链路的守卫。

盯的是「品牌片素材 → 成片」这条链上最容易**静默**出错的三件事：

1. **成片里的字标用的是入库的真粗体**，不是后端合成出来的那一份；
2. **入库的品牌片符合渲染脚本定的规格**（帧数 / 时长 / 时间基）；
3. **生成脚本的结构性约束**：背景一次生成一个连续空间、姿态要补镜框修补。

**为什么第 1 条要在成片上看**：合成粗体是**各后端自己的做法**，两个平台
合成出来的不一样（实测轮廓差 3.14px）。品牌片是**入库的产物**——成片里
用的到底是哪一面粗体，源码说了不算，得在像素上看。

形象素材那一侧（白底派生、铭牌定位）见 `test_character_assets.py`。
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import numpy as np
import pytest

from pyv import fonts

AIV_ROOT = Path(__file__).resolve().parents[2]
BRAND = AIV_ROOT / "brand"
BRAND_SCRIPTS = BRAND / "scripts"
INTRO_CLIP = BRAND / "clips" / "growdu_intro_3s_1080p.mp4"
OUTRO_CLIP = BRAND / "clips" / "growdu_outro_3s_1080p.mp4"

#: 入库的品牌片规格（与 `render_brand.py` 顶部的常量对得上）。
#:
#: 这里**写死字面量**而不是从渲染脚本 import——import 了就等于自证：
#: 脚本改了，常量跟着改，守卫永远绿。
EXPECTED_FRAMES = 68
EXPECTED_FPS = 24
EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080
EXPECTED_TIMEBASE = "1/24000"
MAX_SECONDS = 3.0

#: 片头字标的墨迹宽度判据。
#:
#: 探针实测（同一份内置字体，@142px）：真粗体 539px、细体 507px，**差 32px**。
#: 成片是 h264 压过的，边缘会有 1~2px 的振铃，所以容差取 4px。
#:
#: 两条都要成立：与真粗体对得上（差 ≤4px），且明显不是细体（差 ≥20px）。
#: 只写第一条的话，「用细体渲染」会红、「用别的字体渲染」会红，
#: 但「恰好用了一个宽度相近的字体」会绿——所以要加上第二条。
BOLD_INK_WIDTH = 539
REGULAR_INK_WIDTH = 507
INK_TOLERANCE = 4
MIN_BOLD_EXCESS = 20

#: 片头字标在成片里的位置（1920×1080 画布上的像素）。
#:
#: 基线在 `H*0.355 = 383`，字号 142，标语在 447 之下，所以行带取
#: 240~400。x 从 900 起：走廊尽头那道亮门在 600~771，不在字标上。
WORDMARK_BAND = (240, 400, 900, 1920)
WORDMARK_BRIGHT = 220


def _probe_ink_width(text: str, size: float, *, bold: bool) -> int:
    """探针：把同一段字画到空画布上，量它的墨迹宽度。"""
    cairo = pytest.importorskip("cairo")

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1400, 300)
    ctx = cairo.Context(surface)
    fonts.select_font(ctx, fonts.font_family(), bold=bold)
    ctx.set_font_size(size)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.move_to(40, 200)
    ctx.show_text(text)
    surface.flush()
    data = np.frombuffer(bytes(surface.get_data()), dtype=np.uint8)
    mask = data.reshape(300, surface.get_stride() // 4, 4)[..., 3] > 40
    columns = np.flatnonzero(mask.any(axis=0))
    return int(columns[-1] - columns[0] + 1) if columns.size else 0


def _extract_frame(path: Path, frame: int, out: Path) -> "np.ndarray":
    """从成片里抽一帧，返回 RGB 数组。"""
    from PIL import Image

    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path),
         "-vf", f"select=eq(n\\,{frame})", "-vframes", "1",
         "-f", "image2", str(out)],
        check=True, capture_output=True,
    )
    return np.array(Image.open(out).convert("RGB"))


# ---------------------------------------------------------------- 成片规格


@pytest.mark.parametrize("name,path", [
    ("片头", INTRO_CLIP),
    ("片尾", OUTRO_CLIP),
])
def test_the_committed_brand_clips_match_the_render_spec(name, path):
    """入库的品牌片必须符合渲染脚本定的规格。

    帧数不对，concat 之后的总时长就会漂；时间基不一致，concat 时长
    也会漂。这两条都在成片上看，不在源码上看。
    """
    if not path.exists():
        pytest.skip(f"{name}不在仓库里，跳过")

    import json

    info = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames",
         "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,time_base,nb_read_frames:"
         "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout

    data = json.loads(info)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = [s for s in data["streams"] if s["codec_type"] == "audio"]

    assert video["width"] == EXPECTED_WIDTH
    assert video["height"] == EXPECTED_HEIGHT
    assert video["r_frame_rate"] == f"{EXPECTED_FPS}/1"
    assert video["time_base"] == EXPECTED_TIMEBASE
    assert int(video["nb_read_frames"]) == EXPECTED_FRAMES, \
        f"{name}帧数不对：{video['nb_read_frames']} != {EXPECTED_FRAMES}"
    assert float(data["format"]["duration"]) <= MAX_SECONDS, \
        f"{name}超过 {MAX_SECONDS} 秒"
    assert audio, f"{name}没有音轨——品牌片自带人声 + 配乐"


# ---------------------------------------------------------------- 真粗体


def test_the_committed_intro_uses_the_real_bold_face(tmp_path):
    """入库的片头里，字标用的是**入库的真粗体**。

    判据是**墨迹宽度**：同一份内置字体，真粗体 539px、细体 507px，
    差得开。合成粗体是后端自己的做法，宽度跟真粗体对不上——所以这条
    判据同时挡住「用了细体」「用了别的字体」「用了合成粗体」。

    **在成片上看**：品牌片是入库的产物，源码说了不算。

    **注入验证**（2026-11-16）：把字标强制改成细体重渲一帧，墨迹宽从
    537px 掉到 506px——与真粗体探针差 33px（>容差 4px）、与细体探针只差
    1px（<下限 20px），两条断言都会红。
    """
    if not INTRO_CLIP.exists():
        pytest.skip("片头不在仓库里，跳过")
    if fonts.font_family() != fonts.BUNDLED_FAMILY:
        pytest.skip("这台机器用的不是仓库内置字体，判据不成立")
    if not fonts.bold_face_resolves():
        pytest.skip("这台机器认不出真的粗体字面，判据不成立")

    frame = _extract_frame(INTRO_CLIP, 50, tmp_path / "intro.png")

    top, bottom, left, right = WORDMARK_BAND
    band = frame[top:bottom, left:right]
    bright = ((band[..., 0] >= WORDMARK_BRIGHT)
              & (band[..., 1] >= WORDMARK_BRIGHT)
              & (band[..., 2] >= WORDMARK_BRIGHT))
    columns = np.flatnonzero(bright.any(axis=0))
    assert columns.size, "没在片头里找到字标——判据失效"
    measured = int(columns[-1] - columns[0] + 1)

    bold = _probe_ink_width("Growdu", 142, bold=True)
    regular = _probe_ink_width("Growdu", 142, bold=False)

    assert abs(measured - bold) <= INK_TOLERANCE, (
        f"成片里字标的墨迹宽 {measured}px，真粗体探针 {bold}px——"
        f"对不上，成片用的不是入库的真粗体"
    )
    assert measured - regular >= MIN_BOLD_EXCESS, (
        f"成片里字标的墨迹宽 {measured}px，细体探针 {regular}px——"
        f"差不到 {MIN_BOLD_EXCESS}px，不像粗体"
    )
    assert abs(bold - BOLD_INK_WIDTH) <= INK_TOLERANCE, \
        f"真粗体探针量出 {bold}px，与写死的 {BOLD_INK_WIDTH}px 对不上"
    assert abs(regular - REGULAR_INK_WIDTH) <= INK_TOLERANCE, \
        f"细体探针量出 {regular}px，与写死的 {REGULAR_INK_WIDTH}px 对不上"


# ---------------------------------------------------------------- 脚本结构


def test_the_pose_script_repairs_the_glasses_badge():
    """姿态素材必须走一次镜框局部修补。

    模型戴上方形眼镜后有个固定毛病：会在镜框或镜腿上贴一小块白色小
    铭牌（实测写着 growdu）。prompt 里禁了也不听，所以图生图之后必须
    再补一次局部修补。
    """
    tree = ast.parse(
        (BRAND_SCRIPTS / "generate_poses.py").read_text(encoding="utf-8"))
    imported = any(
        isinstance(node, ast.ImportFrom) and node.module == "add_glasses"
        and any(alias.name == "cleanup_glasses" for alias in node.names)
        for node in ast.walk(tree)
    )
    called = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "cleanup_glasses"
        for node in ast.walk(tree)
    )
    assert imported and called, (
        "generate_poses.py 没有走 cleanup_glasses——镜框上的白色小铭牌"
        "会留在素材上"
    )


def test_the_background_script_makes_one_continuous_space():
    """背景必须**一次生成一个连续空间**，不许拼两个半张。

    AI 宽幅背景的固定毛病就是左右两个场景硬拼。羽化糊不掉缝，正解是
    用「单一连续空间」的 prompt 重新生成——所以 prompt 里必须写死这一
    条，而且不许把两张图拼起来。
    """
    source = (BRAND_SCRIPTS / "generate_backgrounds.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = getattr(node.func, "id", "")
        if name in {"hstack", "vstack", "concat", "paste", "tile"}:
            offenders.append(f"{name}（第 {node.lineno} 行）")
    assert offenders == [], (
        f"背景脚本里有把图拼起来的调用：{offenders}——"
        f"拼出来的接缝羽化糊不掉"
    )

    assert "单一连续空间" in source, "prompt 里必须写死「单一连续空间」"
    assert "不要接缝" in source, "prompt 里必须写死「不要接缝」"


def test_the_background_script_verifies_its_own_output():
    """背景生成完必须过**语义验收**，不许直接出货。

    像素判据证明不了「这是不是一整个空间」——试过两种都误报（楼群边缘、
    走廊尽头的亮光都被当成了接缝）。这条交给能看图的模型问。
    """
    source = (BRAND_SCRIPTS / "generate_backgrounds.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    called = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "verify_continuous_space"
        for node in ast.walk(tree)
    )
    assert called, "背景脚本没有做语义验收——拼缝的背景会直接出货"
