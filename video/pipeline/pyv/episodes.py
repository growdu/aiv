"""期定位：一期 = 一个档位目录。

**坐标就是接口。** 期根是 `video/episodes/`，往下四层：

```
video/episodes/<系列>/<合集>/<文档>/<档位>/
                 一级   二级   三级   四级
```

| 层 | 是什么 | 例子 |
| --- | --- | --- |
| 一级 | **系列**——一条主线 | `<系列>` |
| 二级 | **合集**——主线下的一块 | `<合集>` |
| 三级 | **文档**——一篇母稿 | `<文档>` |
| 四级 | **档位**——这篇文档的三条片子 | `short` / `mid` / `full` |

**一期 = 一个档位目录**。同一篇文档的三档是三期，各有自己的口播稿、
契约、旁白；它们共享的是那一篇文档的骨架（`skeleton.yaml`，放在文档目录里）。

期身份 = **期目录相对期根的路径**，例如
`<系列>/<合集>/<文档>/short`。
**成片**用期路径原样（`out/<系列>/<合集>/<文档>/<档位>.mp4`），
**片段目录**用压平后的 `ep_id()`（`build/<系列>-<合集>-<文档>-<档位>/`）。

**两个名字，别混**：

| | 是什么 | 落在哪 |
| --- | --- | --- |
| **文档路径** | `系列/合集/文档`——母稿的身份 | 口播稿 front matter `episode`（**契约**的 `episode` 记的是四层**期路径**） |
| **期号** | 播放顺序（`ep01`） | 口播稿 front matter `episode_number` |
| **档位** | 三档里的哪一档 | 口播稿 front matter `tier`，也是目录名 |

**没有登记表。** 目录就是登记表：建目录、放文件，就是新的一期。
以前这里有一张 Python 侧的登记表，Makefile 里还有一份 shell 侧的副本，
两份靠一个测试盯着别漂移。现在没有登记表可漂了。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# video/ 是 pipeline/ 的上一级：pyv/episodes.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]

#: 期根。坐标从这儿往下数。
EPISODES_DIR = AIV_ROOT / "episodes"

#: 档位。一篇文档的三档，目录名固定。
TIERS = ("short", "mid", "full")

#: 坐标的层数：系列 / 合集 / 文档 / 档位
DEPTH = 4

SCRIPT_NAME = "口播稿.md"
CONTRACT_NAME = "contract.json"
PUBLISH_NAME = "publish.json"
NARRATION_NAME = "narration.mp3"
STORYBOARD_NAME = "storyboard.json"
REVIEW_NAME = "review.md"
FRAMES_NAME = "frames.md"

#: 抽出来的帧（媒体产物）。清单在期目录里，帧在这个子目录里。
FRAMES_SUBDIR = "frames"

#: 文档目录里放的**讲稿骨架**——一篇母稿解析出来的中间物，三档共用。
SKELETON_NAME = "skeleton.yaml"


@dataclass(frozen=True)
class Episode:
    """一期。`ep` 是期身份（期目录相对期根的路径），`root` 是这一期的目录。"""

    ep: str
    root: Path

    @property
    def doc(self) -> str:
        """文档路径（`系列/合集/文档`）——这一期属于哪篇文档。"""
        return "/".join(self.ep.split("/")[:-1])

    @property
    def tier(self) -> str:
        """档位：`short` / `mid` / `full`。"""
        return self.ep.rsplit("/", 1)[-1]

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


def episode_root(ep: str) -> Path:
    """这一期的目录。`ep` 是期路径（相对期根）。"""
    return EPISODES_DIR / ep


def episode(ep: str) -> Episode:
    return Episode(ep=ep, root=episode_root(ep))


def episode_at(root: str | Path, ep: str) -> Episode:
    """指定目录下的期。

    测试夹具与外部调用走这条：期目录不在默认根下时，
    路径照样由目录说了算。
    """
    return Episode(ep=ep, root=Path(root))


def doc_root(doc: str) -> Path:
    """文档目录（三层：系列/合集/文档）。"""
    return EPISODES_DIR / doc


def ep_id(ep: str) -> str:
    """期路径压平成一个文件名片段（斜杠 → 连字符）。"""
    return ep.replace("/", "-")


def cut_path(ep: str) -> Path:
    """成片的路径：out/<系列>/<合集>/<文档>/<档位>.mp4。

    **一处算，两处用**——``pyv/cli.py`` 的 preflight 与 ``pyv/review.py``
    的成片层**原来**各算一遍（两处都写着 ``episodes.ep_id(...)``），
    改的时候漏一处就找不到成片了。现在两处都调它。
    """
    return AIV_ROOT / "out" / f"{ep}.mp4"


def known_eps_at(root: str | Path) -> list[str]:
    """指定根下有的期（相对路径），按期路径排序。

    **认的是坐标**：期 = 深度 4 且末段是档位名的目录。
    """
    base = Path(root)
    if not base.is_dir():
        return []
    found: list[str] = []
    for path in base.rglob("*"):
        if not path.is_dir() or path.name.startswith("."):
            continue
        relative = path.relative_to(base)
        if len(relative.parts) != DEPTH or relative.parts[-1] not in TIERS:
            continue
        found.append(relative.as_posix())
    return sorted(found)


def known_eps() -> list[str]:
    """磁盘上有的期（期路径），按期路径排序。

    **没有登记表**：目录就是登记表。
    """
    return known_eps_at(EPISODES_DIR)


def known_docs_at(root: str | Path) -> list[str]:
    """指定根下有的文档（相对路径，三层），按文档路径排序。"""
    base = Path(root)
    if not base.is_dir():
        return []
    found: list[str] = []
    for path in base.rglob("*"):
        if not path.is_dir() or path.name.startswith("."):
            continue
        relative = path.relative_to(base)
        if len(relative.parts) != DEPTH - 1:
            continue
        if any(child.is_dir() and child.name in TIERS for child in path.iterdir()):
            found.append(relative.as_posix())
    return sorted(found)


def known_docs() -> list[str]:
    """磁盘上有的文档（文档路径）。"""
    return known_docs_at(EPISODES_DIR)


def script_path(ep: str) -> Path:
    return episode(ep).script


def contract_path(ep: str) -> Path:
    return episode(ep).contract


def publish_path(ep: str) -> Path:
    return episode(ep).publish


def narration_path(ep: str) -> Path:
    return episode(ep).narration


def storyboard_path(ep: str) -> Path:
    return episode(ep).storyboard


def review_path(ep: str) -> Path:
    return episode(ep).review


def frames_dir(ep: str) -> Path:
    return episode(ep).frames_dir


def frames_manifest_path(ep: str) -> Path:
    return episode(ep).frames_manifest


def skeleton_path(doc: str) -> Path:
    """讲稿骨架（文档级，三档共用）。"""
    return doc_root(doc) / SKELETON_NAME


def _front_matter(path: Path) -> dict[str, str]:
    """读 front matter 里的顶层标量键值对。

    只取顶层、只取标量——口播稿的 front matter 就是 `title` / `episode`
    / `tier` / `episode_number` 这样的单行键值对。嵌套结构读不了也不需要，
    读不到就当没有。
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


def ep_number(ep: str) -> str:
    """这一期的期号标签（`ep01` 这样的），取自口播稿的 front matter。

    取不到就返回空串：期号是编辑事实，没有就不该编一个。

    **front matter 里有两个名字，别混**：
    `episode` 是**文档路径**（这篇属于哪篇文档），`episode_number` 才是期号。
    """
    return _front_matter(script_path(ep)).get("episode_number", "")


def ep_doc(ep: str) -> str:
    """这一期 front matter 里记的文档路径（没有就空串）。"""
    return _front_matter(script_path(ep)).get("episode", "")


def ep_tier(ep: str) -> str:
    """这一期 front matter 里记的档位（没有就空串）。"""
    return _front_matter(script_path(ep)).get("tier", "")
