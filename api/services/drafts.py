"""草稿箱的读写。

**保存只写草稿箱**（全局约束 4）：这里的每个函数都只往 `drafts/` 里写，
**不碰 `docs/`，也不碰 `video/`**。往母稿层搬东西是另一件事
（`promote_unit`，见下）——那是**复制**，而且要人点确认。
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .paths import (
    CONTRACT_NAME,
    DRAFTS_DIR,
    EPISODE_FACT_FILES,
    PUBLISH_NAME,
    REPO_ROOT,
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


class PromoteError(ValueError):
    """这一稿不能过审（形状不对，或没到能过审的时候）。"""


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


# ── 过审 = 只复制 ───────────────────────────────────────────────────────

#: 复制之后**还要人手工做的三步**。门面不做，也不许假装做了。
MANUAL_STEPS = (
    "建/更新审校记录（review/<镜像路径>.md 或期目录下的 review.md）",
    "补 review/INDEX.md 与 video/review/INDEX.md 的行（两个守卫要求与磁盘集合相等）",
    "提交（文档流的守卫 G-01 要求 docs/ 里每一篇都有 status: 已合入 的记录）",
)


@dataclass(frozen=True)
class PromoteResult:
    """过审的结果：复制了哪些文件，还欠人做哪几步。"""

    kind: str
    targets: tuple[str, ...]
    overwritten: tuple[str, ...]
    manual_steps: tuple[str, ...]


def _copy_fact(source: Path, target: Path, repo_root: Path) -> tuple[str, bool]:
    """复制一个入库事实。

    返回 `(相对仓库根的 posix 路径, 是不是覆盖了不同的旧内容)`。
    """
    existed = target.exists()
    differs = existed and target.read_bytes() != source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target.relative_to(repo_root).as_posix(), differs


def promote_unit(unit: DraftUnit, *, repo_root: Path = REPO_ROOT) -> PromoteResult:
    """把草稿**复制**进母稿层。

    **只复制入库事实**（全局约束 5）：

    - `document` → `docs/<draft_id>.md`
    - `skeleton` → `video/episodes/<文档路径>/skeleton.yaml`
    - `episode` → `video/episodes/<期路径>/{口播稿.md,contract.json,publish.json}`

    **不复制**旁白、时间轴、渲染帧——它们是产物，跟过去会撞
    `EPISODE_PRODUCT_PATTERNS` 守卫。

    **复制不是移动**：草稿留在原地。**不写审校记录、不补 INDEX、不 commit**
    ——那三步由人做（`MANUAL_STEPS`）。

    `index` / `bundle` / `unknown` / `readme` → `PromoteError`：
    索引页照抄会造站内死链，bundle 稿要引用解析器，形状对不上就没法过。
    """
    repo_root = Path(repo_root)
    targets: list[str] = []
    overwritten: list[str] = []

    def copy_one(source: Path, target: Path) -> None:
        rel, differs = _copy_fact(source, target, repo_root)
        targets.append(rel)
        if differs:
            overwritten.append(rel)

    if unit.kind == "document":
        names = [n for n in unit.files if n.endswith(".md")]
        if not names:
            raise PromoteError(f"{unit.draft_id} 里没有 .md 文件，没什么可复制的")
        for name in names:
            source = unit.path / name
            if not source.is_file():
                continue
            copy_one(source, repo_root / "docs" / f"{unit.draft_id}.md")

    elif unit.kind == "skeleton":
        source = unit.path / SKELETON_NAME
        if not source.is_file():
            raise PromoteError(f"{unit.draft_id} 里没有 {SKELETON_NAME}")
        doc_path = unit.draft_id
        if doc_path.startswith(f"{VIDEO_DRAFT_PREFIX}/"):
            doc_path = doc_path[len(VIDEO_DRAFT_PREFIX) + 1:]
        copy_one(source, repo_root / "video" / "episodes" / doc_path / SKELETON_NAME)

    elif unit.kind == "episode":
        episode = unit.draft_id
        if episode.startswith(f"{VIDEO_DRAFT_PREFIX}/"):
            episode = episode[len(VIDEO_DRAFT_PREFIX) + 1:]
        for name in EPISODE_FACT_FILES:
            source = unit.path / name
            if not source.is_file():
                continue
            copy_one(source, repo_root / "video" / "episodes" / episode / name)
        if not targets:
            raise PromoteError(f"{unit.draft_id} 里没有入库事实（{EPISODE_FACT_FILES}）")

    else:
        raise PromoteError(
            f"{unit.kind} 形态的稿子这一版不能过审："
            "索引页照抄会造站内死链，bundle 稿要引用解析器，"
            "形状对不上的东西就没法进母稿层"
        )

    return PromoteResult(kind=unit.kind, targets=tuple(targets),
                         overwritten=tuple(overwritten),
                         manual_steps=MANUAL_STEPS)
