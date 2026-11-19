"""形象素材链路的守卫：白底派生 + 铭牌定位。

盯两件最容易**静默**出错的事：

1. **白底主形象是从入库的透明底主形象无损合成出来的**——姿态生成拿它当
   参考图；重新生成主形象会让吉祥物形象漂移，跟已入库的素材对不上。
2. **铭牌定位不会被铭牌自己的描边挡住**——4px 宽的「马甲占比」环整个
   落在铭牌自带的深色描边上，真实铭牌反而被判成「没找到铭牌」，字盖不上。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from pyv.config import load as load_config

_CONFIG = load_config()

AIV_ROOT = Path(__file__).resolve().parents[2]
CHARACTER_SCRIPTS = AIV_ROOT / "character" / "scripts"
# 素材的文件名带角色 slug（见 `character/scripts/*.py`）
_SLUG = _CONFIG.character_slug


def _load(name: str, path: Path):
    """按路径载入脚本（不在 pipeline 包内）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules：模块里的 dataclass 机制要回查
    # sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- 白底主形象


def test_make_white_keeps_the_subject_pixels_untouched(tmp_path):
    """白底合成是**无损**的：主体的每一个像素照抄，只把背景填成白。

    姿态生成拿白底主形象当参考图；合成一旦动了主体的像素，姿态素材里
    就会带着改动过的吉祥物，品牌一致性就断了。
    """
    from PIL import Image

    source = AIV_ROOT / "character" / f"{_SLUG}_character_2k_nobg.png"
    if not source.exists():
        pytest.skip("主形象不在本机，跳过")
    module = _load("make_white", CHARACTER_SCRIPTS / "make_white.py")

    out = tmp_path / "white.png"
    module.make_white(source, out)

    white = np.array(Image.open(out).convert("RGBA"))
    original = np.array(Image.open(source).convert("RGBA"))

    opaque = original[..., 3] == 255
    assert opaque.sum() > 0, "主形象里没有不透明像素"
    assert np.array_equal(white[opaque][:, :3], original[opaque][:, :3]), \
        "白底合成动了主体的像素"

    assert white[..., 3].min() == 255, "白底版的 alpha 应当恒为 255"
    empty = original[..., 3] == 0
    assert np.array_equal(
        white[empty][:, :3],
        np.full((int(empty.sum()), 3), 255, dtype=np.uint8),
    ), "透明的地方应当被填成纯白"


def test_make_white_is_reproducible(tmp_path):
    """同一份素材合成两次，结果逐字节相同——路线要可复现。"""
    source = AIV_ROOT / "character" / f"{_SLUG}_character_2k_nobg.png"
    if not source.exists():
        pytest.skip("主形象不在本机，跳过")
    module = _load("make_white", CHARACTER_SCRIPTS / "make_white.py")

    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    module.make_white(source, first)
    module.make_white(source, second)
    assert first.read_bytes() == second.read_bytes()


# ---------------------------------------------------------------- 铭牌定位


def _synthetic_vest_with_rimmed_badge():
    """造一张「深藏蓝马甲 + 带深色描边的白铭牌」的图。

    描边 6px——实测真实素材上那圈描边就是这么宽（点赞姿态的 4px 环
    量到的马甲占比是 0.016、6px 环是 0.053、8px 环才 0.165）。
    """
    from PIL import Image

    width = height = 600
    image = Image.new("RGBA", (width, height), (10, 10, 10, 255))
    pixels = np.array(image)
    pixels[150:450, 120:480] = (43, 76, 126, 255)      # 马甲 #2B4C7E
    pixels[296:326, 266:334] = (10, 10, 10, 255)       # 铭牌自带的深色描边
    pixels[302:320, 272:328] = (255, 255, 255, 255)    # 铭牌的白色牌面
    return Image.fromarray(pixels, "RGBA")


def test_a_badge_with_its_own_rim_is_still_found():
    """真实铭牌带深色描边，定位不能被这圈描边挡住。

    「马甲占比」那一圈只有 4px 宽时，整个环都落在描边上，量到的占比
    近乎为零——真实铭牌被判成「没找到铭牌」，字就盖不上（实测点赞
    姿态：4px 环 0.016、10px 环 0.268）。
    """
    stamp = _load("stamp_badge", CHARACTER_SCRIPTS / "stamp_badge.py")
    box = stamp.find_badge(_synthetic_vest_with_rimmed_badge())
    assert box is not None, "带描边的铭牌没被找到——盖不上字"
    assert box[2] - box[0] == 56, f"框宽不对：{box}"


def test_a_narrow_ring_would_miss_the_plate_rim(monkeypatch):
    """注入验证：把环宽改回 4px，上面那张图就找不到了。

    说明这条守卫**有牙齿**——它守的不是「环宽这个数字」，而是
    「带描边的铭牌也要找得到」这件事。
    """
    stamp = _load("stamp_badge", CHARACTER_SCRIPTS / "stamp_badge.py")
    monkeypatch.setattr(stamp, "VEST_RING_WIDTH", 4)
    assert stamp.find_badge(_synthetic_vest_with_rimmed_badge()) is None, \
        "环宽 4px 竟然找到了带描边的铭牌——注入没生效，守卫可能是瞎的"


@pytest.mark.parametrize("relative", [
    f"character/{_SLUG}_character_2k_nobg.png",
    f"brand/assets/{_SLUG}_pose_thumbsup_nobg.png",
    f"brand/assets/{_SLUG}_pose_wave_nobg.png",
])
def test_the_real_assets_still_have_a_findable_badge(relative):
    """本机素材的铭牌必须找得到——找得到才盖得上字。"""
    from PIL import Image

    path = AIV_ROOT / relative
    if not path.exists():
        pytest.skip("素材不在本机，跳过")
    stamp = _load("stamp_badge", CHARACTER_SCRIPTS / "stamp_badge.py")
    assert stamp.find_badge(Image.open(path).convert("RGBA")) is not None, \
        f"{relative}：找不到铭牌，字盖不上"
