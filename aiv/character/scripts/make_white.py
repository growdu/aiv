#!/usr/bin/env python3
"""从透明底主形象合成一份白底主形象。

**为什么要这一份。** `brand/scripts/generate_poses.py` 用主形象当参考图去
生成姿态图，模型在「图生图」时会连着参考图的**背景**一起学——参考图是
白底，生成出来的小象才是白底；参考图是透明底，模型很可能给出一张透明底
或者脏背景的图，姿态素材的抠底就白做了。

所以姿态生成需要一张**白底**的主形象当参考图。

**为什么不重新生成一张。** 重新生成会让吉祥物形象漂移：皮肤色、马甲色、
数据库图标、耳机、眼镜全都要重新赌一次，赌出来的小象跟已经入库的
`growdu_character_2k_nobg.png` 不是同一只，品牌的视觉一致性就断了。
合成是**无损**的：像素照抄，只把透明的地方填成白。

产物：
  character/growdu_character_2k.png    白底主形象（2048²，alpha 全 255）

用法：
    python3 scripts/make_white.py                  # 产出默认素材
    python3 scripts/make_white.py <src.png> [dst.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
AIV = HERE.parent.parent                     # aiv
CHAR_DIR = AIV / "character"

# 输入：透明底主形象（入库的那份）。输出：白底主形象。
SOURCE_NAME = "growdu_character_2k_nobg.png"
OUTPUT_NAME = "growdu_character_2k.png"


def make_white(source: str | Path, output: str | Path | None = None) -> Path:
    """把透明底素材铺成白底，写到 output。

    铺法是标准 alpha 合成：``out = src * alpha + white * (1 - alpha)``。
    边缘的半透明像素会得到正确的抗锯齿过渡，不会出现一圈灰边。
    """
    source = Path(source)
    if not source.exists():
        print(f"  - {source.name}：文件不存在，跳过", file=sys.stderr)
        raise FileNotFoundError(source)

    image = Image.open(source).convert("RGBA")
    white = Image.new("RGBA", image.size, (255, 255, 255, 255))
    white.alpha_composite(image)

    out = Path(output) if output else source.with_name(OUTPUT_NAME)
    # 存成 RGBA：alpha 恒为 255，但通道模式与素材库里其它图一致，
    # 下游不必分支处理 RGB / RGBA。
    white.save(out)
    print(f"  → {out.name}（{white.width}×{white.height}，白底）")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = Path(argv[0]) if argv else CHAR_DIR / SOURCE_NAME
    output = Path(argv[1]) if len(argv) > 1 else None
    make_white(source, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
