"""期号定位：一期 = 一个目录。

**这里没有登记表。** 一期在磁盘上是什么，路径说了算：

    video/episodes/<slug>/口播稿.md        母稿：口播 + 字幕表
    video/episodes/<slug>/contract.json    视觉分镜契约
    video/episodes/<slug>/publish.json     发布元数据
    video/episodes/<slug>/narration.mp3    旁白（媒体产物）
    video/episodes/<slug>/storyboard.json  时间轴（媒体产物）
    video/episodes/<slug>/review.md        审校记录
    video/episodes/<slug>/frames.md        抽帧清单

**slug 是身份，期号（ep01…）是播放顺序**，两回事：
slug 进路径（改标题不改路径），期号是编辑事实——落在口播稿的 front matter
（`episode_number: ep01`）与《选题库》的 `id` 上，两边对得上才算数。
front matter 里 `episode` 记的也是 slug（跟期目录名一样），不是期号。

新一期不用改代码：建目录、放文件、跑流水线。
以前这里有一张 Python 侧的登记表，Makefile 里还有一份 shell 侧的副本，
两份靠一个测试盯着别漂移。现在没有登记表可漂了。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# video/ 是 pipeline/ 的上一级：pyv/episodes.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]

#: 一期的根目录。每个子目录就是一期。
EPISODES_DIR = AIV_ROOT / "episodes"

SCRIPT_NAME = "口播稿.md"
CONTRACT_NAME = "contract.json"
PUBLISH_NAME = "publish.json"
NARRATION_NAME = "narration.mp3"
STORYBOARD_NAME = "storyboard.json"
REVIEW_NAME = "review.md"
FRAMES_NAME = "frames.md"

#: 抽出来的帧（媒体产物）。清单在期目录里，帧在这个子目录里。
FRAMES_SUBDIR = "frames"


@dataclass(frozen=True)
class Episode:
    """一期。`slug` 是身份，`root` 是这一期的目录。"""

    slug: str
    root: Path

    @property
    def script(self) -> Path:
        return self.root / SCRIPT_NAME

    @property
    def contract(self) -> Path:
        return self.root / CONTRACT_NAME

    @property
    def publish(self) -> Path:
        return self.root / PUBLISH_NAME

    @property
    def narration(self) -> Path:
        return self.root / NARRATION_NAME

    @property
    def storyboard(self) -> Path:
        return self.root / STORYBOARD_NAME

    @property
    def review(self) -> Path:
        return self.root / REVIEW_NAME

    @property
    def frames_dir(self) -> Path:
        return self.root / FRAMES_SUBDIR

    @property
    def frames_manifest(self) -> Path:
        return self.root / FRAMES_NAME


def episode_root(slug: str) -> Path:
    """这一期的目录。"""
    return EPISODES_DIR / slug


def episode(slug: str) -> Episode:
    return Episode(slug=slug, root=episode_root(slug))


def episode_at(root: str | Path, slug: str) -> Episode:
    """指定目录下的期。

    测试夹具与外部调用走这条：期目录不在默认根下时，
    路径照样由目录说了算。
    """
    return Episode(slug=slug, root=Path(root))


def known_eps_at(root: str | Path) -> list[str]:
    """指定目录下有的期（目录名），按 slug 排序。"""
    base = Path(root)
    if not base.is_dir():
        return []
    return sorted(
        path.name
        for path in base.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def known_eps() -> list[str]:
    """磁盘上有的期（目录名），按 slug 排序。

    **没有登记表**：目录就是登记表。
    """
    if not EPISODES_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in EPISODES_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def script_path(slug: str) -> Path:
    return episode(slug).script


def contract_path(slug: str) -> Path:
    return episode(slug).contract


def publish_path(slug: str) -> Path:
    return episode(slug).publish


def narration_path(slug: str) -> Path:
    return episode(slug).narration


def storyboard_path(slug: str) -> Path:
    return episode(slug).storyboard


def review_path(slug: str) -> Path:
    return episode(slug).review


def frames_dir(slug: str) -> Path:
    return episode(slug).frames_dir


def frames_manifest_path(slug: str) -> Path:
    return episode(slug).frames_manifest


def _front_matter(path: Path) -> dict[str, str]:
    """读 front matter 里的顶层标量键值对。

    只取顶层、只取标量——口播稿的 front matter 就是 `title` / `episode`
    / `episode_number` 这样的单行键值对。嵌套结构读不了也不需要，读不到就当没有。
    """
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def ep_number(slug: str) -> str:
    """这一期的期号标签（`ep01` 这样的），取自口播稿的 front matter。

    取不到就返回空串：期号是编辑事实，没有就不该编一个。

    **front matter 里有两个名字，别混**：
    `episode` 是 slug（身份，跟期目录名一致），`episode_number` 才是期号。
    """
    return _front_matter(script_path(slug)).get("episode_number", "")
