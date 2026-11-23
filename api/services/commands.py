"""作业调的命令与 cwd 表。

**这张表是门面与流水线之间唯一的接点。** 门面的作业调的就是这几条命令，
与手敲命令行**逐字等价**——流水线的行为一个字都不改（反目标 A3）。

**cwd 那一列最容易搞错**，所以逐条对着源码核过：

| 干什么 | cwd | 为什么 |
| --- | --- | --- |
| 文档审校 / 编译器 | 仓库根 | `tools/` 里的脚本按相对路径找仓库 |
| `make EP=…` | `video/pipeline/` | Makefile 的 `ROOT := ..` 是相对它自己的目录 |
| 平台出包 | `platforms/` | 平台包是靠 cwd 在 `sys.path` 里找到的 |
| 站点构建 | `platforms/blog/site/` | `npm run build` 要在有 package.json 的目录里跑 |

**argv 必须逐个传参，绝不拼 shell 字符串**：期路径含中文与空格
（`postgresql/getting-started/postgresql基操/short`），拼了会被拆词。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import PIPELINE_DIR, PLATFORMS_DIR, REPO_ROOT, SITE_DIR

__all__ = [
    "Command",
    "REPO_ROOT",
    "PIPELINE_DIR",
    "PLATFORMS_DIR",
    "SITE_DIR",
    "document_review",
    "document_units_rebuild",
    "video_units_rebuild",
    "site_build",
    "video_review_text",
    "video_review_video",
    "video_align",
    "video_build",
    "video_vertical",
    "platform_package",
]


@dataclass(frozen=True)
class Command:
    """一条要跑的作业命令。"""

    argv: list[str] = field(default_factory=list)
    cwd: Path = REPO_ROOT
    key: str = ""


def document_review(doc_path: str) -> Command:
    """文档流的审校信号。"""
    return Command(
        argv=["python3", "tools/review-check.py", str(doc_path),
              "--json", "--docs-root=docs/"],
        cwd=REPO_ROOT,
        key=f"document-review:{doc_path}",
    )


def document_units_rebuild() -> Command:
    """编译文档内容单元（`docs/` → `content/units/`）。"""
    return Command(argv=["python3", "tools/build-content-units.py"],
                   cwd=REPO_ROOT, key="rebuild:documents")


def video_units_rebuild() -> Command:
    """编译视频内容单元（`video/` → `content/units/video/`）。"""
    return Command(argv=["python3", "tools/build-video-pages.py"],
                   cwd=REPO_ROOT, key="rebuild:videos")


def site_build() -> Command:
    """构建站点。"""
    return Command(argv=["npm", "run", "build"], cwd=SITE_DIR, key="rebuild:site")


def video_review_text(episode: str) -> Command:
    """视频线的文本层审校。"""
    return Command(
        argv=["python3", "-m", "pyv.cli", "review", "text",
              "--episode", episode, "--json"],
        cwd=PIPELINE_DIR,
        key=f"review-text:{episode}",
    )


def video_review_video(episode: str) -> Command:
    """视频线的成片层审校。"""
    return Command(
        argv=["python3", "-m", "pyv.cli", "review", "video",
              "--episode", episode, "--json"],
        cwd=PIPELINE_DIR,
        key=f"review-video:{episode}",
    )


def video_align(episode: str) -> Command:
    """按旁白重算时间轴。

    **路径用相对形式**——与 Makefile 的 `NARRATION` / `SCRIPT` / `CONTRACT` /
    `STORYBOARD` 四个变量逐字一致（Makefile:56-59）。
    """
    base = f"../episodes/{episode}"
    return Command(
        argv=["python3", "-m", "pyv.cli", "align",
              "--audio", f"{base}/narration.mp3",
              "--script", f"{base}/口播稿.md",
              "--scenes", f"{base}/contract.json",
              "--out", f"{base}/storyboard.json"],
        cwd=PIPELINE_DIR,
        key=f"align:{episode}",
    )


def video_build(episode: str) -> Command:
    """出片（`make EP=… all` = validate → brand → render → compose）。

    **注意 `all` 不含 `align`**——时间轴要先单独对齐（见 `video_align`）。
    """
    return Command(argv=["make", f"EP={episode}", "all"], cwd=PIPELINE_DIR,
                   key=f"build:{episode}")


def video_vertical(episode: str) -> Command:
    """竖版 9:16（抖音那一档）。"""
    return Command(argv=["make", f"EP={episode}", "vertical"], cwd=PIPELINE_DIR,
                   key=f"vertical:{episode}")


def platform_package(platform: str, episode: str) -> Command:
    """给一个平台出包。

    **平台 id 由调用方给**——调用方是扫 `platforms/*/capability.toml` 得到的，
    这里不写死任何一个平台名。
    """
    return Command(argv=["python3", "-m", f"{platform}.cli", "package", episode],
                   cwd=PLATFORMS_DIR, key=f"package:{platform}:{episode}")
