"""共享术语规则（根工具层的读取器）。

**规则只有一份**：仓库根的 `rules/terminology.json`。这个模块是它的**读取器**——
根 `tools/` 里的审校检查器从这里取词表，不把词写死在代码里。

⚠️ **方向**：`publish/publishkit/` **不许** import 本模块，本模块也**不许**
import `publish/publishkit/`。两层之间的接缝是**文件**（那份 JSON），
不是 import——共享规则是数据，不是代码。

**为什么叫 `terminology_rules` 而不是 `rules`**：仓库根有个 `rules/` **目录**
（规则文件自己住那儿）。模块名跟目录同名，谁在 `sys.path` 上靠前谁赢——
那是隐式依赖。换个名字就没有这个雷（与 `url_rules` 同一条理由）。

判据在 `review/specs/2026-11-24-术语纪律与反造词.md`；本模块只管**读**。

用法（根 `tools/` 已经在 `sys.path` 上的前提下）::

    from terminology_rules import load_terminology
    load_terminology()["banned"]        # {'管线': '改成「流程」……', ...}
"""

from __future__ import annotations

import json
from pathlib import Path

# tools/terminology_rules.py → parents[0]=tools, [1]=仓库根
REPO_ROOT = Path(__file__).resolve().parents[1]

#: 规则文件在仓库根的那一个文件。
RULES_FILE = REPO_ROOT / "rules" / "terminology.json"

#: 规则里**必须**有的键。少一个就是规则文件坏了——宁可让检查器报错，
#: 也不要拿着半张词表出信号（那样会漏判，还让人以为「查过了」）。
REQUIRED_KEYS = ("version", "banned", "soft", "bad_names", "title_words",
                 "title_words_soft")

#: 五张表都得是「词 → 替换说明」的映射。说明可以空串（不许不是字符串）。
WORD_TABLES = ("banned", "soft", "bad_names", "title_words", "title_words_soft")


def rules_path() -> Path:
    """规则文件的路径。"""
    return RULES_FILE


def load_terminology(path: str | Path | None = None) -> dict:
    """读规则文件，返回它的内容。

    读不到文件、JSON 不合法、少必需键、表不是「词 → 说明」的映射，
    都抛 `ValueError`（消息里写清是哪个路径、缺哪一块）——
    规则文件坏了要立刻知道，而不是拿着半张词表悄悄出信号。
    """
    target = Path(path) if path is not None else rules_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"读不到规则文件：{target}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"规则文件不是合法的 JSON：{target}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ValueError(f"规则文件不是一个对象：{target}")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"规则文件缺键：{', '.join(missing)}（{target}）")
    for table in WORD_TABLES:
        words = data[table]
        if not isinstance(words, dict):
            raise ValueError(f"规则文件的 {table} 不是一个对象：{target}")
        for word, advice in words.items():
            if not isinstance(word, str) or not word:
                raise ValueError(f"规则文件的 {table} 里有空词或非字符串词：{target}")
            if not isinstance(advice, str):
                raise ValueError(
                    f"规则文件的 {table} 里「{word}」的替换说明不是字符串：{target}")
    return data
