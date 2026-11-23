"""讲稿骨架：一份母稿的讲法，三档共用。

**骨架记的是「这篇文档讲什么」**，而那是 short / mid / full 共享的东西。
所以骨架住在**文档目录**里（`video/episodes/<系列>/<合集>/<文档>/skeleton.yaml`），
三档共用一份；档位不在骨架里——档位在期目录那一层。

形状见《长视频三档》§5.1，裁剪口径见 §5.2。

**裁剪是机械的，删段凑字数是禁止的。**

一段进哪几档，只看它的 `role`：

| role | 含义 | short | mid | full |
| --- | --- | :---: | :---: | :---: |
| `hook` | 身份 + 钩子 | ✅ | ✅ | ✅ |
| `mechanism` | 机制本体 | | ✅ | ✅ |
| `evidence` | 证据 / 数据 / 复现 | | ✅ | ✅ |
| `conclusion` | 收束 + 落版 | ✅ | ✅ | ✅ |
| `aside` | 支线 / 延伸 / 番外 | | | ✅ |

**`ROLE_TIERS` 是那张表的逐格照抄**——那张表是判据（《长视频三档》§5.2），
改它得先改规格。测试 `test_the_role_table_matches_the_spec` 盯着。

**不做自动裁剪。** 段数或字数落不进区间 → 守卫报红 → 改 `role` 标记。
这里**没有任何按字数截断的逻辑**：悄悄截断出来的片子看着像那么回事，
实际上内容没了，而且没人知道少的是哪一段。

**不认识的 role 报错，不当它没有。** role 拼错（`mechanim`）的段在
「按 role 过滤」的口径下会从**三档里同时消失**——而页面上看不出少了东西。
所以这里宁可炸掉，也不让它安静地消失。
"""
from __future__ import annotations

from pathlib import Path

import yaml

#: 档位。从短到长。
TIERS: tuple[str, ...] = ("short", "mid", "full")

#: role → 包含它的档位集合。
#:
#: **逐格照抄《长视频三档》§5.2 的表**，一格不许自己发挥。
ROLE_TIERS: dict[str, tuple[str, ...]] = {
    # 身份 + 钩子：三档都讲。
    "hook": ("short", "mid", "full"),
    # 机制本体：short 讲不动，进阶版起讲。
    "mechanism": ("mid", "full"),
    # 证据 / 数据 / 复现：同上。
    "evidence": ("mid", "full"),
    # 收束 + 落版：三档都要有个落点。
    "conclusion": ("short", "mid", "full"),
    # 支线 / 延伸 / 番外：进阶版放不下，只在完整版讲。
    "aside": ("full",),
}


class SkeletonError(ValueError):
    """骨架本身坏了：读不了、形状不对、role 不认识。"""


class TierError(ValueError):
    """档位不认识。"""


def parse_skeleton(text: str) -> dict:
    """解析骨架 YAML。

    只做**解析**：形状对不对、role 认不认识，留给 `select_segments`，
    因为那才是真正用骨架的地方（在这里查一遍，等于查两遍）。
    """
    data = yaml.safe_load(text)
    if data is None:
        raise SkeletonError("骨架是空的")
    if not isinstance(data, dict):
        raise SkeletonError(f"骨架不是一个对象，是 {type(data).__name__}")
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise SkeletonError("骨架里没有 segments 列表")
    return data


def load_skeleton(path: str | Path) -> dict:
    """读骨架文件。"""
    file = Path(path)
    if not file.is_file():
        raise SkeletonError(f"骨架不存在：{file}")
    return parse_skeleton(file.read_text(encoding="utf-8"))


def select_segments(skeleton: dict, tier: str) -> list[dict]:
    """按 role 选出这一档要的段。**段序保持骨架里的原样**（不重排）。

    `tier` 不认识 → 抛 `TierError`：档位是坐标的一部分，
    拼错了就是拼错了，不能当成「什么都不讲」——那样会出一支空片子，
    而且命令还报「成功」。

    段上的 `role` 不认识 → 抛 `SkeletonError`：见模块开头的说明。
    """
    if tier not in TIERS:
        raise TierError(f"档位不认识：{tier!r}（只认 {'、'.join(TIERS)}）")

    segments = skeleton.get("segments") or []
    picked = []
    for segment in segments:
        role = segment.get("role")
        if role not in ROLE_TIERS:
            raise SkeletonError(
                f"段 {segment.get('id', '?')} 的 role 是 {role!r}，"
                f"不认识（只认 {'、'.join(ROLE_TIERS)}）"
            )
        if tier in ROLE_TIERS[role]:
            picked.append(segment)
    return picked


def render_narration(segments: list[dict]) -> str:
    """把选中的段拼成口播稿文本：**一句一行**。

    这是 `align.parse_script` 与 `persona.extract_sentences` 认的那种形状
    （口播稿小节里的代码块，每行一句）。

    **不重排、不截断、不改字。** 段序是骨架的原序，句子是段里的原句。
    """
    lines: list[str] = []
    for segment in segments:
        narration = segment.get("narration") or []
        if isinstance(narration, str):
            narration = [narration]
        for sentence in narration:
            text = str(sentence).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)
