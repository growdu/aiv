"""母稿与草稿的 front matter。

**只解析**——不判断一份稿子「过没过审」（那是 `review.py` 的事），
也不改它。改稿是编辑器的事（那是 `drafts.py` 的事）。
"""
from __future__ import annotations


def parse(text: str) -> dict:
    """读一份 markdown 的 front matter，返回「键 → 值」的映射。

    - 没有 front matter → 空 dict。
    - 不是 `key: value` 的行 → 跳过。
    - 值原样保留（不剥引号、不转类型）——**这一层不做解释**。
    """
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line or line.startswith(("#", " ", "\t")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def title(text: str, fallback: str = "") -> str:
    """读 front matter 里的 `title:`。读不到就用 `fallback`。"""
    value = parse(text).get("title", "")
    return value or fallback
