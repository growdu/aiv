"""母稿里的相对链接必须变成站上的地址。

**背景**
------
母稿里的链接是**仓库里的相对路径**（`./子目录/_index.md`），
站上的地址是另一套（文档前缀 + 单元 id）。
这层翻译由 `tools/rewrite-links.mjs` 在渲染前做。

**它曾经漏掉目录导航页**：重写器只遍历 `source/_posts/`，
而目录导航页住在 `source/docs/<目录>/index.md`。
于是目录页上那些「进子目录」的入口在站点上是死链——
而且**构建不报错**，点下去只是 404，站点照常构建出来。

所以这里守着两件事：

1. 产物里没有残留的相对 markdown 链接（`href="./某篇.md"`）；
2. 目录导航页的标题还在——正文开头那个 H1 不能被摘掉：
   目录页的版面（`docs-index.ejs`）只渲染正文，标题就是正文里那个 H1。

**为什么死链守卫 `test_pages.py` 抓不到这种**：那条只查以 `/` 开头的
站内地址；没被翻译的相对链接连 `/` 都不带，就从它眼皮底下过去了。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE
from url_shape import is_category_id

DIST = SITE / "dist"

#: 产物里取地址的地方。
LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')

#: 母稿里的链接长这样：相对路径 + `.md`。
MARKDOWN_LINK_RE = re.compile(r'href="([^"]*\.md)"')


@pytest.fixture(scope="module")
def dist() -> Path:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return DIST


def _is_relative(url: str) -> bool:
    """站内绝对地址（`/docs/…`）与站外地址（`https://…`）都不算相对链接。"""
    if url.startswith("/") or url.startswith("#"):
        return False
    return "://" not in url


def test_no_relative_markdown_links_survive(dist):
    """产物里不该还有指向 `.md` 的相对链接。"""
    leftover: list[str] = []
    for html in sorted(dist.rglob("*.html")):
        text = html.read_text(encoding="utf-8", errors="ignore")
        for match in MARKDOWN_LINK_RE.finditer(text):
            url = match.group(1)
            if not _is_relative(url):
                continue
            leftover.append(f"{html.relative_to(dist)} → {url}")

    assert not leftover, "没翻译的相对链接：\n  " + "\n  ".join(sorted(set(leftover)))


def test_category_pages_keep_their_title(dist):
    """目录导航页的标题是正文里那个 H1——摘掉就成无名页了。"""
    missing: list[str] = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        unit_id = path.relative_to(CONTENT_UNITS).as_posix().removesuffix(".md")
        if not is_category_id(unit_id):
            continue
        directory = unit_id[: -len("_index")] if unit_id.endswith("_index") else unit_id
        page = dist / "docs" / directory / "index.html"
        if not page.exists():
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "<h1" not in text:
            missing.append(unit_id)

    assert not missing, f"这些目录页没有标题：{missing}"


def test_category_pages_link_to_their_children_as_site_urls(dist):
    """目录页上的「进子目录」入口得是站上真地址，不是仓库里的相对路径。"""
    broken: list[str] = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        unit_id = path.relative_to(CONTENT_UNITS).as_posix().removesuffix(".md")
        if not is_category_id(unit_id):
            continue
        directory = unit_id[: -len("_index")] if unit_id.endswith("_index") else unit_id
        page = dist / "docs" / directory / "index.html"
        if not page.exists():
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        for match in LINK_RE.finditer(text):
            url = match.group(1)
            if "_index" not in url and not url.endswith(".md"):
                continue
            if url.endswith(".md"):
                broken.append(f"{unit_id} → {url}")
    assert not broken, "目录页里没翻译的入口：\n  " + "\n  ".join(sorted(set(broken)))
