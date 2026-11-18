"""分类树的守卫：**目录即接口**，四条不变量。

**背景**
------
`docs/` 的目录结构就是站点与视频线的**接口**
（见 ``review/specs/2026-11-18-目录即接口与分类增设.md``）：

    一级目录 = 一个分类
    二级目录 = 一块二级内容
    一篇文档 = 一期

方向与系列**目录派生**，不写进 front matter；但分类的**中文名**要写在
``_index.md`` 里——``title:`` 与 ``cascade.categories`` 这两个字段是分类链
在站点上**唯一的显示来源**（``sync-hexo.py`` 的 ``read_section_categories()``
与 ``read_cascade_categories()`` 只读它们）。

它们各有各的失败方式，而且**全都静默**：

1. 顶层目录没有 ``title:`` → 分类名退化成英文目录名 → **URL 变了**，
   老链接集体失效。
2. 分类目录没有 ``cascade.categories`` → 二三级分类**整条消失**，
   文章全挂到一级赛道——**没有一个已有的测试会报错**。
3. ``title:`` 与 ``cascade.categories`` 各说各的 → 页面标题一个名、
   分类链另一个名，读者点进去发现对不上。
4. 源码方向的**阶段 ↔ 系列目录**不是 1:1 → 学习路径的顺序跟目录的顺序脱钩，
   「循序渐进」这条线就断了。

这个测试**不需要构建产物**：分类树直接读 ``docs/``，
赛道与阶段读 ``data/learning-path.json``。

放在 ``platforms/blog/site/tests/``，随 ``site-guard.yml`` 进 CI。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from paths import REPO_ROOT, SITE_DATA

DOCS = REPO_ROOT / "docs"
RULES_FILE = SITE_DATA / "learning-path.json"

#: 顶层分类目录（``docs/`` 下的直接子目录）。
SECTIONS = sorted(
    p.name for p in DOCS.iterdir() if p.is_dir() and not p.name.startswith(".")
)

#: **豁免名单要窄**：口子一宽，守卫就退化成「报告」。
#: 今天只有一个目录豁免——``docs/life/`` 的文章都在它的子目录下，
#: 顶层这一层不直接挂文章，所以它不需要自己的 ``cascade.categories``。
#: 加新豁免要在这里写清理由。
EXEMPT_NO_CASCADE = {"life"}

#: 源码方向的分类（``docs/source-tracks/``）下的**系列目录**。
SOURCE_TRACKS = "source-tracks"

_TITLE_RE = re.compile(r'^title:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
_CASCADE_RE = re.compile(
    r"cascade:\s*\n\s*categories:\s*\n((?:\s*-\s*.+\n)+)", re.MULTILINE
)


def _index_files() -> list[Path]:
    """所有分类目录的 ``_index.md``（按路径排序）。"""
    out = []
    for path in sorted(DOCS.rglob("_index.md")):
        if any(part.startswith(".") for part in path.relative_to(DOCS).parts):
            continue
        out.append(path)
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _title(text: str) -> str | None:
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else None


def _cascade(text: str) -> list[str]:
    m = _CASCADE_RE.search(text)
    if not m:
        return []
    items = []
    for line in m.group(1).split("\n"):
        item = re.match(r"\s*-\s*(.+)", line)
        if item:
            items.append(item.group(1).strip())
    return items


@pytest.fixture(scope="module")
def rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------- CAT-01


def test_every_section_has_a_chinese_name():
    """每个顶层分类目录都得有 ``_index.md`` 且带 ``title:``。

    没有 ``title:`` 时，``sync-hexo.py`` 会退回到**目录名**——
    分类名就成了英文的 ``source-tracks``，而分类名决定 URL。
    这一条红了意味着**一批链接要改**。
    """
    missing = []
    for name in SECTIONS:
        idx = DOCS / name / "_index.md"
        if not idx.is_file():
            missing.append("{}：没有 _index.md".format(name))
            continue
        if _title(_read(idx)) is None:
            missing.append("{}：_index.md 没有 title:".format(name))
    assert not missing, "\n".join(missing)


# --------------------------------------------------------------- CAT-02


def test_every_category_declares_its_name():
    """每个分类目录都要声明自己的分类名（``cascade.categories``）。

    这是**静默消失**那条路的门：没有它，这个目录下的文章在站点上
    只剩一级分类，二三级分类整条链不见了——而没有别的测试会响。
    """
    missing = []
    for idx in _index_files():
        rel = str(idx.parent.relative_to(DOCS)).replace("\\", "/")
        if rel in EXEMPT_NO_CASCADE:
            continue
        if not _cascade(_read(idx)):
            missing.append(rel)
    assert not missing, (
        "这些分类目录没有 cascade.categories（二三级分类会静默消失）：\n"
        "{}".format("\n".join("  " + m for m in missing))
    )


# --------------------------------------------------------------- CAT-03


def test_category_name_matches_page_title():
    """``title:`` 与 ``cascade.categories`` 说的是同一件事，就得写同一个名字。

    页面标题一个名、分类链另一个名，读者点进去会发现对不上。
    """
    mismatch = []
    for idx in _index_files():
        rel = str(idx.parent.relative_to(DOCS)).replace("\\", "/")
        if rel in EXEMPT_NO_CASCADE:
            continue
        text = _read(idx)
        title = _title(text)
        cascade = _cascade(text)
        if title and cascade and cascade[0] != title:
            mismatch.append("{}：title={!r} cascade={!r}".format(rel, title, cascade))
    assert not mismatch, "\n".join(mismatch)


# --------------------------------------------------------------- CAT-04


def _source_track_series(rules: dict) -> dict[str, list[str]]:
    """源码方向的赛道 → 它的阶段前缀（``source-tracks/<系列>/<块>/``）。

    赛道与系列的对应是**派生**出来的，不另设一张表：
    一个赛道的所有阶段都带 ``path_prefix``，且这些前缀全在同一个
    ``source-tracks/<系列>/`` 底下——它就是源码方向的赛道。
    """
    series: dict[str, list[str]] = {}
    for track in rules["tracks"]:
        prefixes = []
        for stage in track["stages"]:
            for m in stage["match"]:
                if "path_prefix" in m:
                    prefixes.append(m["path_prefix"])
        series_dirs = {
            p.rstrip("/").split("/")[1]
            for p in prefixes
            if p.startswith(SOURCE_TRACKS + "/")
        }
        # 只有「每条阶段的前缀都在同一个系列下」的赛道才算源码方向。
        if len(series_dirs) != 1:
            continue
        name = series_dirs.pop()
        own = [p for p in prefixes if p.startswith("{}/{}/".format(SOURCE_TRACKS, name))]
        if len(own) != len(track["stages"]):
            # 有阶段没有自己的前缀 —— 不是 1:1，交给下一条断言报。
            series.setdefault(name, []).extend(own)
            continue
        series[name] = own
    return series


def test_source_track_stages_match_series_dirs(rules):
    """源码方向：**阶段 ↔ 系列目录 1:1**。

    教学顺序与系列划分天生一致——「循序渐进」不需要另维护，
    它就是目录的顺序（见《层间接口与内容坐标系》§2.4）。

    只对源码方向成立：``engineering``（6 目录 / 4 阶段）、
    ``distributed``（6 / 4）当场就是红的，所以这条**不能**写成全站通则。
    """
    problems = []
    for series, prefixes in _source_track_series(rules).items():
        series_root = DOCS / SOURCE_TRACKS / series
        if not series_root.is_dir():
            problems.append("系列目录不存在：{}/{}".format(SOURCE_TRACKS, series))
            continue
        on_disk = {
            p.name for p in series_root.iterdir() if p.is_dir() and not p.name.startswith(".")
        }
        in_rules = {p.rstrip("/").split("/")[-1] for p in prefixes}
        for missing in sorted(on_disk - in_rules):
            problems.append(
                "{}/{} 没有对应的阶段（目录有文章但学习路径里没有这一站）".format(
                    SOURCE_TRACKS, missing
                )
            )
        for missing in sorted(in_rules - on_disk):
            problems.append(
                "阶段 {}/{} 没有对应的目录".format(SOURCE_TRACKS, missing)
            )
        stages = sum(
            1
            for track in rules["tracks"]
            for stage in track["stages"]
            if any(
                m.get("path_prefix", "").startswith(
                    "{}/{}/".format(SOURCE_TRACKS, series)
                )
                for m in stage["match"]
            )
        )
        if stages != len(on_disk):
            problems.append(
                "{}/{}：阶段 {} 个，目录 {} 个 —— 不是 1:1".format(
                    SOURCE_TRACKS, series, stages, len(on_disk)
                )
            )
    assert not problems, "\n".join(problems)
