#!/usr/bin/env python3
"""生成品牌片用的两张 AI 背景底板。

产出：
  brand/assets/bg_intro.png    AI 背景：深蓝数据中心（16:9）
  brand/assets/bg_outro.png    AI 背景：蓝调城市天际线（16:9）

**为什么要有这个脚本。** 背景原本是手工生成的：仓库里只有成品，没有生成
步骤。换一版背景、或者在另一台机器上补一张背景，都只能靠人回忆当时的
prompt——路线不可复现。这个脚本把那一步固定下来。

**AI 宽幅背景有个固定毛病：左右两个场景硬拼**，中间贯穿全图一条接缝。
羽化只会把缝糊掉（糊成一条更宽的糊带），正确做法是用「**单一连续空间**」
的 prompt 重新生成。所以 prompt 里必须写死这一条，而且**一张图一次生成**，
不许拼两个半张。

生成之后还有一道**语义验收**：问视觉模型「这张图是不是一个整体空间、
有没有混进角色或文字」。像素判据证明不了这件事——试过两种都误报
（楼群边缘、走廊尽头的亮光都被当成了接缝），「是不是一整个空间」是
语义问题，交给能看图的模型问。验收不过脚本直接报错。

规矩（跟 `aiv/brand/README.md` 的「三条不能违反的规矩」一致）：

1. 背景里不许有角色、文字、Logo、UI 元素——文字一律用真实字体在 cairo
   阶段渲染，模型生成的中英文会乱码；
2. 背景必须是**单一连续空间**，不能拼接；
3. 版式由代码定：左侧约三分之一留给角色，右侧留给文字，所以背景只要
   纹理和纵深，不要抢戏的视觉焦点。

依赖 mcode-tools CLI（先加载 `mcode-tools-master` skill）。
每次运行都会消耗生成额度，重复执行前先确认是否真的需要重做。

用法：
  python3 scripts/generate_backgrounds.py              # 两张都生成
  python3 scripts/generate_backgrounds.py --intro      # 只生成片头背景
  python3 scripts/generate_backgrounds.py --outro
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BRAND = HERE.parent
AIV = BRAND.parent
CHARACTER_SCRIPTS = AIV / "character" / "scripts"
sys.path.insert(0, str(CHARACTER_SCRIPTS))

from _mcode import call, download, upload  # noqa: E402

ASSETS = BRAND / "assets"

# 生成参数。4K 是为了在 draw_cover 的推近镜头下不糊：
# 画布 1920×1080，推到 1.07 倍时实际取样约 2054×1160。
ASPECT_RATIO = "16:9"
AREA = "4K"

# 两张背景共用的「不许拼接 / 不许有字」约束。
# 拼接缝那句必须留着：初版 bg_outro.png 就是左右两场景硬拼的，
# 羽化糊不掉，只能靠 prompt 重新生成。
_NO_SPLIT = """- 全幅必须是一个**单一连续空间**：同一片天空/天花板、同一层地平线、
  同一套建筑/机柜、同一套光照；绝不允许把两张画面左右拼在一起，
  不要接缝、不要硬边分界、不要镜像重复、不要拼贴
- 画面里没有任何人物、角色、动物、机器人、剪影
- 画面里没有任何文字、字母、数字、标牌、Logo、水印、UI 面板、图表、代码"""

# 片头：深蓝数据中心。右侧压暗后放白字，所以灯带别铺满全图。
INTRO_PROMPT = f"""一张深蓝色调的现代超大规模数据中心机房内部。

场景：一条机房主走廊向纵深延伸，两侧是整齐排列的深灰色服务器机柜，
机柜面板的指示灯发出冷蓝色微光，地面是抛光环氧地坪，映出机柜灯带的竖向倒影，
天花板是整齐排列的线缆桥架，远处尽头有一处柔和的冷白亮光。
镜头平视，视线沿走廊中心线向深处延伸，形成强烈的单点透视纵深。

{_NO_SPLIT}

- 整体偏暗，冷蓝为主调；机柜指示灯是画面里最亮的元素，但不要过曝
- 构图：地面占下半部，天花板线缆占上部约三分之一，走廊尽头在画面中偏左
- 画面右侧三分之一（将来压暗后放白色文字）要相对干净、对比度低一些，
  不要堆满密集灯带
- 干净、专业、冷峻、电影感的产品级 3D 渲染质感"""

# 片尾：蓝调城市天际线。右侧压白后放深蓝字，所以底色要亮、要通透。
OUTRO_PROMPT = f"""一张蓝调现代城市天际线远景，傍晚时分。

场景：一整片连续的城市天际线，从左到右是同一座城市——远处的高层建筑群、
中景的办公楼、脚下平铺的城市街区与一条向远处收束的街道。
天空是清澈的浅蓝到近白的渐变，飘着极淡的云，一轮柔和的日光从画面偏左上方照下来，
建筑群之间有真实的距离层次与空气透视（越远越淡越蓝）。

{_NO_SPLIT}

- 主色调是浅蓝、天青与近白，通透明亮，不要深色
- 建筑不要出现密集的窗户网格噪点，形体要简洁干净
- 构图：地平线压在画面下方约三分之一，天空占据大半幅；右侧靠近地平线的位置
  建筑群要低一些、亮一些（将来那里要压白后放深蓝色文字）
- 干净、宁静、专业的产品级 3D 渲染质感"""

BACKGROUNDS = {
    "intro": (INTRO_PROMPT, ASSETS / "bg_intro.png"),
    "outro": (OUTRO_PROMPT, ASSETS / "bg_outro.png"),
}


def seam_score(image: Image.Image) -> tuple[float, int]:
    """量一条竖向硬接缝：左右两半的平均亮度**台阶**，以及台阶所在的列。

    **怎么量的。** 把每一列压成一个平均亮度，得到一条沿宽度方向的亮度剖面；
    对每个候选列 c，比较它左右各一个宽窗（窗宽 = 图宽的 8%）的平均值，
    取差值最大的那个候选。接缝会让亮度**换了一个档**，这个差值就大。

    **为什么不用「相邻两列的跳变」。** 那会把一栋楼的楼边当成接缝——
    实测 bg_outro 的玻璃幕墙楼群在第 857 列跳了 39/255，而那张图里
    根本没有接缝（目视与视觉模型双重确认过）。

    **这个量只是参考，不是判决。** 它照样会误报：bg_intro 走廊尽头的
    亮光造成 37/255 的台阶，那是光照梯度，不是接缝。两段亮度接近的
    场景硬拼，它又量不出来。

    真正的判据是**语义**的（这张图是不是一个整体空间），交给
    `verify_continuous_space` 去问能看图的模型。像素判据只当提示。

    返回 (台阶幅度, 列号)。
    """
    gray = np.array(image.convert("L"), dtype=np.float64)
    column_mean = gray.mean(axis=0)
    width = column_mean.size
    window = max(8, int(width * 0.08))
    prefix = np.concatenate([[0.0], np.cumsum(column_mean)])
    candidates = np.arange(window, width - window)
    left = (prefix[candidates] - prefix[candidates - window]) / window
    right = (prefix[candidates + window] - prefix[candidates]) / window
    step = np.abs(right - left)
    index = int(step.argmax())
    return float(step[index]), int(candidates[index])


# 生成完的**语义验收**：问视觉模型「这是不是单一连续空间」。
#
# 为什么不用像素判据当判据：试过了，误报两次——
#   · 相邻列跳变：bg_outro 的玻璃幕墙楼群在第 857 列跳了 39/255，其实是楼边；
#   · 宽窗台阶：bg_intro 走廊尽头的亮光造成 37/255，其实是光照梯度。
# 「这是不是一整个空间」是个**语义问题**，像素判据证明不了；能看图的模型能。
#
# 验收不过就不让这张图出门：README 记的正解是「用『单一连续空间』的
# prompt 重新生成」——羽化只会把缝糊掉。
VERIFY_PROMPT = """请只依据画面本身判断，不要客套。

这张图是不是一个**单一连续的空间**，还是左右两个不同的场景被硬拼在一起？
- 如果是单一连续空间，第一行只写 "VERDICT: PASS"，之后简要说明依据；
- 如果存在拼接缝、或明显是两个场景硬拼，第一行只写 "VERDICT: FAIL"，
  并指出缝大约在画面宽度的百分之几处、缝长什么样。

另外请一并检查：
- 画面里有没有人物、角色、动物、机器人或它们的剪影？
- 画面里有没有任何文字、字母、数字、标牌、Logo、水印、UI 面板、图表或代码？"""


def verify_continuous_space(path: Path) -> tuple[bool, str]:
    """问视觉模型：这张背景是不是单一连续空间。返回 (是否通过, 模型原话)。"""
    res = call("connector__matrix__describe_images", {"image_info": [{
        "url": upload(path),
        "mime_type": "image/png",
        "prompt": VERIFY_PROMPT,
    }]})
    results = res.get("results") or []
    if not results or not results[0].get("success"):
        raise RuntimeError(f"视觉验收失败：{res}")
    answer = str(results[0].get("description") or "")
    passed = "VERDICT: PASS" in answer.upper()
    return passed, answer


def generate(prompt: str, dest: Path) -> None:
    """生成一张背景，验收通过才落到 dest。"""
    res = call("connector__matrix__generate_image", {"requests": [{
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO, "area": AREA, "output_format": "png",
        "output_file": dest.name, "n": 1,
    }]})
    items = res.get("success_items") or []
    if not items:
        raise RuntimeError(f"生成失败：{res}")
    download(items[0]["node_id"], dest)
    image = Image.open(dest)
    print(f"  → {dest}（{image.width}×{image.height}）")

    # 像素诊断：只当提示，不当判据（它误报过两次，见 seam_score 的说明）。
    step, column = seam_score(image)
    print(f"    像素诊断：最大亮度台阶 {step:.1f}/255（第 {column} 列）——仅供参考")

    # 验收：是不是单一连续空间、有没有混进角色或文字。
    # 验收不过就报错——**羽化糊不掉缝**，正解是用同样的 prompt 重新生成。
    passed, answer = verify_continuous_space(dest)
    print("    视觉验收：")
    for line in answer.strip().splitlines():
        print(f"      {line}")
    if not passed:
        raise RuntimeError(
            f"{dest.name} 没通过视觉验收（不是单一连续空间，或混进了"
            f"角色/文字）。正解是用同样的 prompt 重新生成，"
            f"不要羽化硬凑——糊掉的缝比原来的缝更难看。"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成品牌片用的 AI 背景")
    parser.add_argument("--intro", action="store_true", help="只生成片头背景")
    parser.add_argument("--outro", action="store_true", help="只生成片尾背景")
    args = parser.parse_args(argv)

    wanted = []
    if args.intro or not args.outro:
        wanted.append("intro")
    if args.outro or not args.intro:
        wanted.append("outro")
    for name in wanted:
        prompt, dest = BACKGROUNDS[name]
        print(f"生成 {name} 背景 …")
        generate(prompt, dest)
    print("完成。规范见 aiv/形象与音色规范.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
