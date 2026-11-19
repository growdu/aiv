"""文章页两栏的守卫：左边目录树，右边文章大纲。

**背景**
------
顶层设计里，所有文档是一棵目录树（目录即分类）。站点的文章页于是
固定两栏：左栏是 docs/ 的真实目录树，右栏是这一篇的小标题大纲。
学习流不单独占栏——阶段本来就是目录，它折在树的节点上。

这个测试把这两条钉住：

1. 有目录树的页面就得有大纲，有大纲的页面就得有目录树（不许只剩一栏）。
2. 目录树里必须出现**每个**内容单元的地址——
   树就是 docs/ 的结构，少一篇就说明树跟 docs 对不上。

**跑法**（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE

DIST = SITE / "dist"

TREE = re.compile(r'<nav class="tree"')
OUTLINE = re.compile(r'<aside class="side side-outline"')
HREF = re.compile(r'href="(/[^"#?]*)"')


def _unit_urls() -> set[str]:
    """每个内容单元在站上的地址。"""
    urls: set[str] = set()
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        unit_id = rel.removesuffix(".md")
        if unit_id == "_index" or unit_id.endswith("/_index"):
            urls.add("/docs/" + unit_id.removesuffix("/_index").removeprefix("_index") + "/")
        elif unit_id.startswith("video/"):
            urls.add("/videos/" + unit_id.removeprefix("video/") + "/")
        else:
            urls.add(f"/docs/{unit_id}/")
    return urls


def _tree_urls(html: str) -> set[str]:
    """页面里目录树那一段的站内链接。"""
    start = html.find('<nav class="tree"')
    if start < 0:
        return set()
    end = html.find("</nav>", start)
    if end < 0:
        return set()
    return set(HREF.findall(html[start:end]))


@pytest.fixture(scope="module")
def dist_pages() -> list[Path]:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return sorted(DIST.rglob("*.html"))


def test_article_pages_have_tree_and_outline(dist_pages):
    """目录树与大纲成对出现——不许只剩一栏。"""
    broken = []
    for page in dist_pages:
        html = page.read_text(encoding="utf-8", errors="ignore")
        has_tree = bool(TREE.search(html))
        has_outline = bool(OUTLINE.search(html))
        if has_tree != has_outline:
            broken.append(
                f"{page.relative_to(DIST)}：tree={has_tree} outline={has_outline}"
            )
    assert not broken, "文章页的两栏不成对：\n" + "\n".join(broken)


def test_tree_covers_every_unit(dist_pages):
    """树 = docs/ 的结构：每个内容单元都要在树里露个面。"""
    wanted = _unit_urls()
    trees = [
        _tree_urls(page.read_text(encoding="utf-8", errors="ignore"))
        for page in dist_pages
    ]
    trees = [t for t in trees if t]
    assert trees, "构建产物里一个目录树都没有"

    missing = sorted(url for url in wanted if not any(url in t for t in trees))
    assert not missing, "这些内容单元没出现在目录树里：\n" + "\n".join(missing)
