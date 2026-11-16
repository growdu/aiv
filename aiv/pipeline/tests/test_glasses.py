"""眼镜相关测试。

两条线：

1. **规格与生成脚本同步**——规范里写的眼镜（深藏蓝 #2B4C7E 方形细边框、
   镜片透明），生成脚本的 prompt 里必须写的是同一件事。规范和 prompt
   漂移了，下一次重生成就会得到一只没戴眼镜或戴错色的小象。

2. **本机素材确实戴了眼镜**——不是看 prompt，是看像素：脸的区域里得有
   深藏蓝的方框眼镜。
"""
import importlib.util
import sys

import numpy as np
import pytest

from pyv import character


def _load(name: str, relative: str):
    """加载 character/scripts/ 下的脚本（不在 pipeline 包内，按路径载入）。"""
    path = character.AIV_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules：模块里有 dataclass，dataclass 机制要回查
    # sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _add_glasses():
    return _load("add_glasses", "character/scripts/add_glasses.py")


def _generate_character():
    return _load("generate_character", "character/scripts/generate_character.py")


# ---------------------------------------------------------------- 规格同步

def test_spec_declares_the_glasses():
    """规范 §1.1 必须把眼镜写进配饰。"""
    spec = (character.AIV_ROOT / "形象与音色规范.md").read_text(encoding="utf-8")
    assert "眼镜" in spec
    assert "2B4C7E" in spec
    # 方形 + 镜片透明，两个要点都要在
    assert "方形" in spec
    assert "透明" in spec


def test_generation_prompt_uses_the_specified_glasses():
    """生成 prompt 里的眼镜，必须和规范是同一副（颜色码 + 方形 + 透明）。"""
    glasses = _add_glasses()
    prompt = glasses.build_prompt()
    assert glasses.GLASSES_COLOR in prompt
    assert "方形" in prompt
    assert "透明" in prompt
    # 不许在镜框镜腿上贴白牌——模型的老毛病
    assert "不要出现任何白色标签" in prompt


def test_character_generation_prompt_uses_the_specified_glasses():
    """从原型全量重生成的 prompt，也得戴上同一副眼镜。"""
    glasses = _add_glasses()
    generator = _generate_character()
    for prompt in (generator.CHARACTER_PROMPT, generator.POSE_PROMPT):
        assert glasses.GLASSES_COLOR in prompt
        assert "眼镜" in prompt


def test_cleanup_prompt_targets_the_glasses_nameplate():
    """擦镜框杂物的 prompt 得说清楚擦什么。"""
    glasses = _add_glasses()
    assert "白色小铭牌" in glasses.CLEANUP_PROMPT
    assert "白色小铭牌" in glasses.CLEANUP_SHEET_PROMPT


# ---------------------------------------------------------------- 像素验收

# 镜框色 #2B4C7E = (43, 76, 126)。
# 判据要卡得够死：小象的**虹膜也是蓝色**（约 #4A8FC0）、耳朵内壁与阴影是
# 蓝灰色。只按「暗 + 偏蓝」去筛，虹膜和阴影会混进来，测不出眼镜。
# 所以用「够暗 + 蓝红差够大」：虹膜亮、蓝红差也没这么大；阴影则是灰的，
# 蓝红差不够。
NAVY_MAX_RED = 95           # 镜框最亮处也不超过这个红通道
NAVY_MIN_BLUE_GAP = 70      # 蓝通道要比红通道高这么多，才算深藏蓝而不是灰

# 眼镜判据的两个数（**实测标定**，不是拍脑袋）：
#
# · **列跨度**：脸区里深藏蓝像素的最左列到最右列，占主体宽的比例。
#   实测三张素材：主形象 61.0%、点赞姿态 56.8%、挥手姿态 54.0%。
#   40% 是安全门槛——没有眼镜时脸区里根本没有深藏蓝（眉毛是深棕，
#   不是深藏蓝；耳机是纯黑，蓝红差为 0），跨度会塌到 0。
#
# · **像素占比**：脸区里深藏蓝像素占脸区面积的比。实测 0.96% ~ 2.3%，
#   0.5% 是安全门槛——它保证镜框**有厚度**，不是一根线。
MIN_NAVY_SPAN_RATIO = 0.40
MIN_NAVY_AREA_RATIO = 0.005


def _subject_box(rgb: np.ndarray, alpha: np.ndarray | None):
    """主体包围盒（透明底按 alpha；白底按「不是白」）。"""
    if alpha is not None and alpha.min() < 250:
        mask = alpha > 8
    else:
        mask = ~((rgb[..., 0] > 245) & (rgb[..., 1] > 245) & (rgb[..., 2] > 245))
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _navy(rgb: np.ndarray) -> np.ndarray:
    """深藏蓝镜框的像素。"""
    r = rgb[..., 0].astype(int)
    b = rgb[..., 2].astype(int)
    return (r < NAVY_MAX_RED) & ((b - r) >= NAVY_MIN_BLUE_GAP)


def _face_band(box, height: int):
    """脸所在的那一段行：主体上部 18% ~ 42%。

    眼镜在眼睛上；这个区间的上方是头顶呆毛，下方是耳机与马甲。
    """
    x0, y0, x1, y1 = box
    subject_h = y1 - y0
    return int(y0 + subject_h * 0.18), int(y0 + subject_h * 0.42)


def _glasses_measure(rgb: np.ndarray, alpha: np.ndarray | None):
    """量脸区里的深藏蓝：返回 (列跨度, 像素数, 脸区面积, 主体宽)。

    **为什么用「列跨度」而不是「最长水平段」。** 早先的判据是「镜框是
    横着走的长条」，量的是**最长水平连续段**。那只在头是正的时候成立：
    点赞姿态的小象头是歪的，镜框上沿是**斜线**，任何一行都截不出长段
    （实测只有主体宽的 2.8%，远低于门槛 6%）——可那张图的眼镜明明在。

    那是**判据的局限，不是素材的毛病**。列跨度对倾斜免疫：镜框横跨两只
    眼睛，不管上沿是平是斜，占的列都是同一段。
    """
    box = _subject_box(rgb, alpha)
    if box is None:
        return 0, 0, 0, 0
    x0, y0, x1, y1 = box
    subject_h = y1 - y0
    subject_w = x1 - x0
    top, bottom = _face_band(box, subject_h)
    band = _navy(rgb)[top:bottom]
    columns = np.flatnonzero(band.any(axis=0))
    span = int(columns[-1] - columns[0] + 1) if columns.size else 0
    return span, int(band.sum()), int(band.size), subject_w


@pytest.mark.parametrize("relative", [
    "character/growdu_character_2k_nobg.png",
    "brand/assets/growdu_pose_thumbsup_nobg.png",
    "brand/assets/growdu_pose_wave_nobg.png",
])
def test_real_assets_wear_navy_square_glasses(relative):
    """本机素材：小象脸上得有深藏蓝的方框眼镜。

    判据是脸区里的**深藏蓝掩膜**：
    - **列跨度**要够宽——镜框横跨两只眼睛（实测 54%~61% 主体宽）；
    - **像素占比**要够多——镜框有厚度，不是一根线。

    眉毛不进这道掩膜（深棕，蓝红差不够），耳机也不进（纯黑，蓝红差为 0），
    所以脸区里的深藏蓝就是镜框本身。
    """
    from PIL import Image

    path = character.AIV_ROOT / relative
    if not path.exists():
        pytest.skip("素材不在本机，跳过")

    image = Image.open(path).convert("RGBA")
    arr = np.array(image)
    span, pixels, area, subject_w = _glasses_measure(arr[..., :3], arr[..., 3])

    assert span > 0, f"{relative}：脸区里没有深藏蓝像素，眼镜没戴上"
    assert span >= subject_w * MIN_NAVY_SPAN_RATIO, (
        f"{relative}：脸区的深藏蓝只横跨 {span}px（主体宽 {subject_w}px，"
        f"不到 {MIN_NAVY_SPAN_RATIO:.0%}）——不像横跨两只眼睛的镜框"
    )
    assert pixels >= area * MIN_NAVY_AREA_RATIO, (
        f"{relative}：脸区深藏蓝只有 {pixels}px（占脸区 {pixels / area:.2%}），"
        f"不像有厚度的镜框"
    )


def test_the_glasses_judgement_fails_when_the_frames_are_removed():
    """注入验证：把镜框抹掉，判据必须塌下来。

    说明它量的是**眼镜**，不是脸区里别的东西——判据有效性自己也要被验。
    """
    from PIL import Image

    path = character.AIV_ROOT / "character/growdu_character_2k_nobg.png"
    if not path.exists():
        pytest.skip("主形象不在本机，跳过")

    arr = np.array(Image.open(path).convert("RGBA"))
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    span, pixels, area, subject_w = _glasses_measure(rgb, alpha)
    assert span >= subject_w * MIN_NAVY_SPAN_RATIO, "原图就没通过，注入没意义"

    # 把镜框连同它的抗锯齿边缘一起抹成皮肤色
    from scipy import ndimage

    box = _subject_box(rgb, alpha)
    top, bottom = _face_band(box, box[3] - box[1])
    frame = np.zeros(rgb.shape[:2], dtype=bool)
    frame[top:bottom] = _navy(rgb)[top:bottom]
    frame = ndimage.binary_dilation(frame, np.ones((7, 7)))
    stripped = rgb.copy()
    stripped[frame] = (176, 196, 210)      # 小象皮肤的浅蓝灰

    new_span, new_pixels, _, _ = _glasses_measure(stripped, alpha)
    assert new_span < subject_w * MIN_NAVY_SPAN_RATIO, (
        f"抹掉镜框后判据仍然通过（跨度 {new_span}px）——它量的不是眼镜"
    )

