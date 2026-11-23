"""产物取用：白名单根 + 期目录下的那几样。

**不接受用户传的路径**（规格 §6.1）。合格的路只有三条：

1. 成片根 `video/out/`；
2. 片段根 `video/build/`；
3. 某一期目录下的那几样产物（旁白、时间轴、抽帧）。

其余一律**不合格**——路由拿到 `None` 就 404，**不 403**
（403 等于告诉调用者「这个路径存在」）。

**产物不是入库事实**：它们不入库、不跟着过审走（`promote_unit` 只复制
`EPISODE_FACT_FILES`），所以这里读的都是磁盘上的现状。
"""
from __future__ import annotations

from pathlib import Path

from .paths import REPO_ROOT

#: 产物的两个根（相对仓库根）。
ARTIFACT_ROOTS = ("video/out", "video/build")

#: 某一期目录下的产物文件名（相对期目录）。
EPISODE_ARTIFACT_FILES = (
    "narration.mp3",
    "storyboard.json",
    "storyboard__nobrand.json",
    "storyboard__vertical.json",
    "storyboard__vertical_aligned.json",
    "frames.md",
)

#: 某一期目录下的产物目录（相对期目录）。
EPISODE_ARTIFACT_DIRS = ("frames",)


def _under(path: Path, base: Path) -> bool:
    """`path` 在 `base` 之下吗（`base` 本身也算）。"""
    return path == base or base in path.parents


def artifact_id(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    """产物路径 → `artifact_id`（仓库根下的相对 posix 路径）。"""
    root = Path(repo_root).resolve()
    return Path(path).resolve().relative_to(root).as_posix()


def _episode_artifact(resolved: Path, root: Path) -> bool:
    """这个文件是不是某一期目录下的产物。"""
    episodes_root = (root / "video" / "episodes").resolve()
    if not _under(resolved, episodes_root) or resolved == episodes_root:
        return False
    parts = resolved.relative_to(episodes_root).parts
    # 期路径四层（系列/合集/文档/档位）+ 文件名
    if len(parts) == 5 and parts[4] in EPISODE_ARTIFACT_FILES:
        return True
    # 期路径四层 + 产物目录 + 文件
    if len(parts) >= 6 and parts[4] in EPISODE_ARTIFACT_DIRS:
        return True
    return False


def resolve_artifact(artifact_id: str, *, repo_root: Path = REPO_ROOT) -> Path | None:
    """把 `artifact_id` 变成一个**可以给出去**的文件路径。不合格 → `None`。

    判定顺序：

    1. id 为空、含 `\\`、以 `/` 开头、或任一段是 `..` → 不合格；
    2. 解析后的路径必须**在仓库根之内** → 否则不合格；
    3. 必须在两个产物根之下，**或者**是某一期目录下的产物 → 否则不合格；
    4. 必须是**已存在的文件**（不是目录）→ 否则不合格。
    """
    if not artifact_id or "\\" in artifact_id or artifact_id.startswith("/"):
        return None
    parts = [p for p in artifact_id.split("/") if p]
    if not parts or any(p == ".." for p in parts):
        return None

    root = Path(repo_root).resolve()
    resolved = (root / Path(*parts)).resolve()
    if not _under(resolved, root) or resolved == root:
        return None

    in_root = any(_under(resolved, (root / rel).resolve())
                   for rel in ARTIFACT_ROOTS)
    if not in_root and not _episode_artifact(resolved, root):
        return None

    if not resolved.is_file():
        return None
    return resolved


def _item(path: Path, kind: str, *, repo_root: Path) -> dict:
    """产物清单里的一项。"""
    return {
        "artifact_id": artifact_id(path, repo_root=repo_root),
        "name": path.name,
        "kind": kind,
        "bytes": path.stat().st_size,
    }


def episode_artifacts(episode: str, *, repo_root: Path = REPO_ROOT) -> list[dict]:
    """一期的产物清单：成片、旁白、时间轴、抽帧、片段。

    **成片按期分目录**（`out/<期路径>.mp4`），**片段压平成连字符**
    （`build/<期路径压平>/`）——这两条是 `video/pipeline/Makefile` 的
    `OUT` 与 `BUILD` 定的。
    """
    root = Path(repo_root).resolve()
    episode = episode.strip("/")
    items: list[dict] = []

    def add(path: Path, kind: str) -> None:
        if path.is_file():
            items.append(_item(path, kind, repo_root=root))

    # 成片：正片、无品牌导流版、竖版
    out = root / "video" / "out"
    add(out / f"{episode}.mp4", "cut")
    add(out / f"{episode}__nobrand.mp4", "cut")
    add(out / f"{episode}__vertical.mp4", "cut")

    # 某一期目录下的东西
    tier = root / "video" / "episodes" / episode
    add(tier / "narration.mp3", "narration")
    for name in EPISODE_ARTIFACT_FILES:
        if name.endswith(".json"):
            add(tier / name, "timeline")
    frames = tier / "frames"
    if frames.is_dir():
        for png in sorted(frames.glob("*.png")):
            add(png, "frame")

    # 片段：目录名是期路径压平成连字符
    flat = episode.replace("/", "-")
    build = root / "video" / "build"
    for name in (flat, f"{flat}__nobrand", f"{flat}__vertical"):
        directory = build / name
        if not directory.is_dir():
            continue
        for segment in sorted(directory.iterdir()):
            if segment.is_file():
                add(segment, "frame")

    return items
