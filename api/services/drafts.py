"""草稿箱的读写。

**保存只写草稿箱**（全局约束 4）：这里的每个函数都只往 `drafts/` 里写，
**不碰 `docs/`，也不碰 `video/`**。往母稿层搬东西是另一件事
（`promote_unit`，见下）——那是**复制**，而且要人点确认。
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import (
    CONTRACT_NAME,
    DRAFTS_DIR,
    EPISODE_FACT_FILES,
    PUBLISH_NAME,
    SCRIPT_NAME,
    SKELETON_NAME,
    TIERS,
    VIDEO_DRAFT_PREFIX,
    DraftUnit,
    list_draft_units,
)


class DraftNotFound(LookupError):
    """草稿箱里没有这一号。"""


class DraftExists(ValueError):
    """这一号已经在草稿箱里了。"""


def _safe_child(unit_path: Path, name: str) -> Path:
    """把单元内的文件名解析成路径，并挡住「写出单元之外」的名字。"""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"文件名不合法：{name!r}")
    base = Path(unit_path).resolve()
    target = (base / name).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"文件名会写到单元之外：{name!r}")
    return target


def read_unit(unit: DraftUnit) -> dict[str, str]:
    """读一个单元：返回「文件名 → 内容」。

    **只读单元内的文件**，不递归（bundle 的素材在单元目录里，是一层的）。
    """
    out: dict[str, str] = {}
    for name in unit.files:
        path = unit.path / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8")
    return out


def write_unit(unit: DraftUnit, files: dict[str, str]) -> None:
    """写一个单元：**只写 body 里给的键**。

    body 里没给的键**原样不动**（不删）。文件名会写出单元之外的 → `ValueError`。
    """
    for name, content in files.items():
        target = _safe_child(unit.path, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def find_unit(draft_id: str, root: Path = DRAFTS_DIR) -> DraftUnit:
    """按 `draft_id` 找单元。找不到 → `DraftNotFound`。"""
    for unit in list_draft_units(root):
        if unit.draft_id == draft_id.strip("/"):
            return unit
    raise DraftNotFound(f"草稿箱里没有 {draft_id!r}")


def create_unit(kind: str, *, draft_id: str, title: str = "",
                root: Path = DRAFTS_DIR) -> DraftUnit:
    """在草稿箱里新建一个单元。

    - `document` → `<draft_id>.md`，带一个最小 front matter。
    - `episode` → 一个档位目录，放**三个入库事实**（口播稿 / 契约 / 发布元数据）。
    - `skeleton` → 一个文档级目录，放 `skeleton.yaml`。

    已经在 → `DraftExists`。
    """
    root = Path(root)
    draft_id = draft_id.strip("/")

    if kind == "document":
        path = root / f"{draft_id}.md"
        if path.exists():
            raise DraftExists(f"{draft_id} 已经在草稿箱里了")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            f"title: {title or path.stem}\n"
            'topic: ""\n'
            "---\n\n",
            encoding="utf-8",
        )
        return DraftUnit(kind="document", draft_id=draft_id,
                         path=path.parent, files=(path.name,))

    if kind == "episode":
        path = root / draft_id
        if path.exists():
            raise DraftExists(f"{draft_id} 已经在草稿箱里了")
        parts = draft_id.split("/")
        episode = "/".join(p for p in parts if p != VIDEO_DRAFT_PREFIX)
        doc_path = "/".join(episode.split("/")[:-1])   # 三层：文档路径
        tier = episode.split("/")[-1]
        if tier not in TIERS:
            raise ValueError(f"档位必须是 {TIERS} 之一：{tier!r}")
        path.mkdir(parents=True, exist_ok=True)
        (path / SCRIPT_NAME).write_text(
            "---\n"
            f"title: {title or path.name}\n"
            f"episode: {doc_path}\n"
            f"tier: {tier}\n"
            "# 期号（每个系列一个，形如 ep01）由人填——编视频内容单元要用它当文件名。\n"
            "# episode_number: ep01\n"
            "---\n\n",
            encoding="utf-8",
        )
        (path / CONTRACT_NAME).write_text(
            json.dumps({"version": 1, "episode": episode, "title": title,
                        "segments": []}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (path / PUBLISH_NAME).write_text(
            json.dumps({"episode": episode, "title": title},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return DraftUnit(kind="episode", draft_id=draft_id, path=path,
                         files=tuple(sorted(EPISODE_FACT_FILES)))

    if kind == "skeleton":
        path = root / draft_id
        if path.exists():
            raise DraftExists(f"{draft_id} 已经在草稿箱里了")
        path.mkdir(parents=True, exist_ok=True)
        (path / SKELETON_NAME).write_text(
            "# 骨架：这一份文档的公共结构（三档共用）\n"
            "scenes: []\n",
            encoding="utf-8",
        )
        return DraftUnit(kind="skeleton", draft_id=draft_id, path=path,
                         files=(SKELETON_NAME,))

    raise ValueError(f"不认识的单元种类：{kind!r}")
