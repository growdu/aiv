"""仓库坐标与草稿单元分类。

**这一层只认路径形状，不认登记表。** 目录即接口——
一期视频就是一个四层目录，一篇文档就是一个 markdown 文件。

**身份不在这里。** 站名、品牌名、平台名全在使用者一侧（site.json /
config.toml / capability.toml），这一层只读。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ── 坐标 ────────────────────────────────────────────────────────────────
# 仓库根 = api/services/paths.py 的上上级。
REPO_ROOT = Path(__file__).resolve().parents[2]

DRAFTS_DIR = REPO_ROOT / "drafts"
DOCS_DIR = REPO_ROOT / "docs"

# 视频线
EPISODES_DIR = REPO_ROOT / "video" / "episodes"
OUT_DIR = REPO_ROOT / "video" / "out"
BUILD_DIR = REPO_ROOT / "video" / "build"
PIPELINE_DIR = REPO_ROOT / "video" / "pipeline"
VOICE_DIR = REPO_ROOT / "video" / "voice"

# 平台层
PLATFORMS_DIR = REPO_ROOT / "platforms"
SITE_DIR = PLATFORMS_DIR / "blog" / "site"

# ── 形状 ────────────────────────────────────────────────────────────────
# 视频线的草稿在 `drafts/_video/` 下。`_` 是保留前缀：
# 它**不是分类**——不生成 URL、不进 docs/、不登记学习流。
VIDEO_DRAFT_PREFIX = "_video"

# 三档。顺序与 video/pipeline/pyv/episodes.py 的 TIERS 一致。
TIERS = ("short", "mid", "full")

# 一期视频的入库事实（只这三个文件进母稿层）。
SCRIPT_NAME = "口播稿.md"
CONTRACT_NAME = "contract.json"
PUBLISH_NAME = "publish.json"
EPISODE_FACT_FILES = (SCRIPT_NAME, CONTRACT_NAME, PUBLISH_NAME)

# 骨架在**文档级**（三档共用），不在档位目录里。
SKELETON_NAME = "skeleton.yaml"

# 产物（不是入库事实，跟着走会撞 EPISODE_PRODUCT_PATTERNS 守卫）。
NARRATION_NAME = "narration.mp3"
STORYBOARD_NAME = "storyboard.json"


@dataclass(frozen=True)
class DraftUnit:
    """草稿箱里的一个可编辑单元。

    `path` 是**单元所在的目录**，`files` 是单元内文件名（相对该目录）。
    """

    kind: str
    draft_id: str
    path: Path
    files: tuple[str, ...]


def classify_draft(rel: str) -> str:
    """按路径形状判定草稿单元的种类。

    返回值：`document` / `index` / `bundle` / `skeleton` / `episode` /
    `readme` / `unknown`。

    - `rel` 是相对 `drafts/` 的 posix 路径。
    - 视频线以 `_video/` 开头：去掉前缀后，**四段**且末段是
      `skeleton.yaml` → 骨架；**四段**且末段 ∈ `TIERS` → 一期。
    - 文档线：末段是 `README.md` → 说明文件（**不是可编辑单元**）；
      末段是 `_index.md` → 索引页；末段是 `index.md` 且四段 → bundle 稿
      （目录里带素材的那种）；**三级以上**且末段是别的 `.md` → 扁平稿
      （**深度不写死**：源向线比扁平稿深两级）。
    """
    parts = [p for p in rel.strip("/").split("/") if p]
    if not parts:
        return "unknown"

    if parts[0] == VIDEO_DRAFT_PREFIX:
        rest = parts[1:]
        if len(rest) == 4 and rest[3] == SKELETON_NAME:
            return "skeleton"
        if len(rest) == 4 and rest[3] in TIERS:
            return "episode"
        return "unknown"

    if parts[-1] == "README.md":
        return "readme"
    if parts[-1] == "_index.md":
        return "index"
    if len(parts) == 4 and parts[-1] == "index.md":
        return "bundle"
    # 扁平稿：**至少三级目录**（分类 / 二级内容 / 期号）。
    # **深度不写死**——源向线多两级（方向 / 系列），那也是一篇文档。
    # （`index.md` 是 bundle 的标记，不算扁平稿。）
    if len(parts) >= 3 and parts[-1].endswith(".md") and parts[-1] != "index.md":
        return "document"
    return "unknown"


def _visible(names) -> tuple[str, ...]:
    """单元里的文件：不含点开头的（编辑器临时文件之类）。"""
    return tuple(sorted(n for n in names if not n.startswith(".")))


def list_draft_units(root: Path = DRAFTS_DIR) -> list[DraftUnit]:
    """列出草稿箱里的全部单元，按 `draft_id` 排序。

    **说明文件（README.md）与形状对不上的东西不列**——
    它们不是可编辑单元，列出来也点不动。
    """
    root = Path(root)
    if not root.is_dir():
        return []

    units: dict[str, DraftUnit] = {}

    # 第一遍：目录形态的单元（一期 = 一个档位目录）。
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            continue
        if classify_draft(rel_dir) == "episode":
            units[rel_dir] = DraftUnit(
                kind="episode",
                draft_id=rel_dir,
                path=Path(dirpath),
                files=_visible(filenames),
            )

    # 第二遍：文件形态的单元（扁平稿 / 索引页 / bundle / 骨架）。
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}" if rel_dir != "." else name
            kind = classify_draft(rel)
            if kind in {"readme", "unknown"}:
                continue
            if kind == "bundle":
                draft_id = rel[: -len("/index.md")]
                files = _visible(filenames)
            elif kind == "skeleton":
                draft_id = rel[: -len(f"/{SKELETON_NAME}")]
                files = (name,)
            else:  # document / index
                draft_id = rel[: -len(".md")]
                files = (name,)
            units[draft_id] = DraftUnit(
                kind=kind,
                draft_id=draft_id,
                path=Path(dirpath),
                files=files,
            )

    return sorted(units.values(), key=lambda u: u.draft_id)


def episode_to_draft(episode: str) -> str:
    """期坐标 → 草稿坐标。`系列/合集/文档/short` → `_video/系列/合集/文档/short`。"""
    return f"{VIDEO_DRAFT_PREFIX}/{episode.strip('/')}"


def episode_to_skeleton_draft(episode: str) -> str:
    """期坐标 → 骨架的草稿坐标（骨架在文档级，三档共用）。"""
    parts = episode.strip("/").split("/")
    if len(parts) >= 2:
        parts = parts[:-1]
    return f"{VIDEO_DRAFT_PREFIX}/" + "/".join(parts)


def draft_to_episode(draft_id: str) -> str | None:
    """草稿坐标 → 期坐标。不是视频线的草稿 → `None`。"""
    draft_id = draft_id.strip("/")
    prefix = f"{VIDEO_DRAFT_PREFIX}/"
    if not draft_id.startswith(prefix):
        return None
    return draft_id[len(prefix):]


def draft_to_document(draft_id: str) -> str:
    """草稿坐标 → 母稿层的文档路径（相对仓库根）。"""
    return f"docs/{draft_id.strip('/')}.md"
