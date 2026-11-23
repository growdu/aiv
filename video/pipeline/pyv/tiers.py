"""三档的档位阈值与判据：字数、时长、压缩比。

**阈值是字面量**——不从别的模块 import 常量过来。
一致性由 ``tests/test_tiers.py`` 里的**两份独立取值**钉住：
一份抄在测试里，一份直接**解析规格文档的表**
（``publish/spec/09-长视频三档.md`` §三）。
生产代码改了阈值而规格没改 → 那条测试会红；
规格改了而生产代码没改 → 同样会红。

**坐标口径**：``check_episode`` 收的是**文档路径**（`系列/合集/文档`），
不是期号——档位在路径里（`系列/合集/文档/short` 才是期路径）。
母稿路径不在登记表里：**从骨架的 `source:` 字段读**
（新坐标没有登记表，目录就是登记表）。

**豁免是临时的**：产出过的档位不许再豁免，
否则豁免会变成「一律豁免」的后门。
"""
from __future__ import annotations

import re
from pathlib import Path

from pyv import derive
from pyv import episodes
from pyv import motherdoc
from pyv import skeleton

# video/ 是 pipeline/ 的上一级：pyv/tiers.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AIV_ROOT.parent

#: 档位名。**从 skeleton 拿**，不在这里另抄一份——抄两份就会漂。
TIER_NAMES = skeleton.TIERS

#: 每一档的阈值。``None`` 表示这一侧不限。
TIER_LIMITS: dict[str, dict] = {
    "short": {
        "min_seconds": None,
        "max_seconds": 60.0,
        "min_chars": None,
        "max_chars": 431,
        "max_ratio": 100.0,
    },
    "mid": {
        "min_seconds": 300.0,
        "max_seconds": 600.0,
        "min_chars": 2157,
        "max_chars": 4314,
        "max_ratio": 12.0,
    },
    "full": {
        "min_seconds": 600.0,
        "max_seconds": None,
        "min_chars": 4314,
        "max_chars": None,
        "max_ratio": 1.5,
    },
}

#: 语速（去空格的字符数 ÷ 秒）。与证据密度规格 EV-05 同源。
SPEECH_RATE = 7.19

#: 文档路径 → 豁免的档位与理由。**临时**的：产出过就移走。
#:
#: 现在是空的——那六期 2026-11-18 已清空，仓库里一篇文档都没有。
#: 机制留着：将来某篇文档只出了精简版，就在进阶版上写清理由。
TIER_EXEMPT: dict[str, dict[str, str]] = {}


def count_chars(texts) -> int:
    """去空格的字符数。"""
    return sum(len(re.sub(r"\s+", "", t)) for t in texts)


def check_numbers(tier: str, seconds: float, chars: int, ratio: float) -> list[str]:
    """核对一档的三个数。返回问题清单，空列表 = 通过。"""
    limits = TIER_LIMITS.get(tier)
    if limits is None:
        raise ValueError(f"未知档位 {tier!r}，合法值只有 {TIER_NAMES}")
    problems: list[str] = []

    low = limits["min_seconds"]
    high = limits["max_seconds"]
    if low is not None and seconds < low:
        problems.append(f"时长 {seconds:.1f} s 低于下限 {low:.0f} s")
    if high is not None and seconds > high:
        problems.append(f"时长 {seconds:.1f} s 超过上限 {high:.0f} s")

    low = limits["min_chars"]
    high = limits["max_chars"]
    if low is not None and chars < low:
        problems.append(f"口播字数 {chars} 低于下限 {low}")
    if high is not None and chars > high:
        problems.append(f"口播字数 {chars} 超过上限 {high}")

    ratio_limit = limits["max_ratio"]
    if ratio > ratio_limit:
        problems.append(f"压缩比 {ratio:.1f}:1 超过上限 {ratio_limit:.1f}:1")

    return problems


def _motherdoc_path(source: str) -> Path:
    """母稿路径：绝对路径原样，相对路径相对仓库根。"""
    path = Path(source)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def check_episode(
    doc: str, tier: str, root: str | Path | None = None
) -> list[str]:
    """核对某一篇文档的某一档。返回问题清单；豁免返回一行说明。

    `doc` 是**文档路径**（`系列/合集/文档`），`tier` 是档位。
    `root` 是期根——默认 `video/episodes/`，测试夹具另指。

    **不抛异常**：不合规是问题清单，坏文件也是问题清单。
    调用方决定怎么报。
    """
    if tier in TIER_EXEMPT.get(doc, {}):
        return [f"豁免：{TIER_EXEMPT[doc][tier]}"]

    base = Path(root) if root is not None else episodes.EPISODES_DIR
    path = episodes.skeleton_path_at(base, doc)
    if not path.is_file():
        return [f"没有骨架文件：{path}"]

    try:
        loaded = skeleton.load_skeleton(path)
        result = derive.derive(loaded, tier)
    except (ValueError, OSError, LookupError) as exc:
        # 骨架坏了 / 档位不认识 / 母稿引用断了——都算「这一档有问题」。
        return [f"派生失败：{exc}"]

    chars = count_chars(result.narration)
    if chars == 0:
        problems = ["这一档一段口播都没有"]
        problems.extend(check_numbers(tier, 0.0, 0, 0.0))
        return problems

    seconds = chars / SPEECH_RATE

    source = str(loaded.get("source") or "").strip()
    if not source:
        return ["骨架没有 source——不知道母稿是哪一篇"]
    mother_path = _motherdoc_path(source)
    if not mother_path.is_file():
        return [f"母稿不存在：{source}"]

    mother = motherdoc.load_motherdoc(mother_path)
    ratio = mother.prose_chars / chars

    return check_numbers(tier, seconds, chars, ratio)
