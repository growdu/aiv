"""分类 / 标签这套页面退休的守卫。

**为什么整套退休**
------------------
分类与标签是 hexo 的两个**检索维度**，跟站点的「学习路径」那套**导航维度**
是同一件事的两个入口。blog-bak 那次已经整套退休了（页面、菜单、chip 全清），
这一版是它的翻版，就也不搬。

文章 front matter 里的 ``categories`` / ``tags`` 字段**留着**——
学习流的归类规则、检索索引的字段都在用它们——只是不再往访客面前摆，
也不再为它们生成页面。

**这一份守的是「别让它复活」**：模板、工具、菜单、产物，四处都得干净。
只删一处的话，CI 构建一次就把页面带回来了——本地看着删干净了，线上又长出来。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from paths import SITE

SITE_ROOT = SITE
DIST = SITE_ROOT / "dist"
THEME = SITE_ROOT / "themes" / "matery"
IDENTITY_FILE = SITE_ROOT / "data" / "site.json"

#: 分类页与标签页在站上的地址。
TAXONOMY_PREFIXES = ("/categories/", "/tags/", "/category/", "/tag/")

#: EJS 注释：``<%# ... %>``（单行）与 ``<%/* ... */%>``（块）。
EJS_COMMENT_RE = re.compile(r"<%#.*?%>|<%/\*.*?\*/%>", re.S)


def _strip_ejs_comments(text: str) -> str:
    """把 EJS 注释去掉。

    模板的注释里会提到「那套页面已经删了」——提到路径是说明，不是链接。
    """
    return EJS_COMMENT_RE.sub("", text)


def _layout_files() -> list[Path]:
    return sorted((THEME / "layout").rglob("*.ejs"))


# ── 产物里没有分类页与标签页 ───────────────────────────────


@pytest.mark.skipif(not DIST.exists(), reason="还没构建（先跑 npm run build）")
def test_no_taxonomy_pages_in_the_build():
    for prefix in ("categories", "tags"):
        assert not (DIST / prefix).exists(), f"产物里又长出了 {prefix}/"


@pytest.mark.skipif(not DIST.exists(), reason="还没构建（先跑 npm run build）")
def test_no_page_links_to_a_taxonomy_page():
    for html in sorted(DIST.rglob("*.html")):
        text = html.read_text(encoding="utf-8", errors="ignore")
        for url in re.findall(r'href="([^"]+)"', text):
            if url.startswith(TAXONOMY_PREFIXES):
                raise AssertionError(
                    f"{html.relative_to(DIST)} 链到了分类/标签页：{url}"
                )


# ── 菜单里没有它们 ─────────────────────────────────────────


def test_the_menu_has_no_taxonomy_entries():
    identity = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
    for item in identity.get("nav") or []:
        href = str(item.get("href") or "")
        assert not href.startswith(TAXONOMY_PREFIXES), f"菜单里有分类/标签：{item}"


# ── 模板里不再渲染它们 ─────────────────────────────────────


def test_the_templates_do_not_link_to_taxonomy_pages():
    for path in _layout_files():
        text = _strip_ejs_comments(path.read_text(encoding="utf-8"))
        for prefix in TAXONOMY_PREFIXES:
            assert prefix not in text, (
                f"{path.relative_to(SITE_ROOT)} 里还有指向 {prefix} 的链接"
            )


def test_article_pages_have_no_category_or_tag_chips():
    """文章页顶部的分类名与标签 chip 退休了——文章页再链过去就是死链。"""
    for name in ("post-detail.ejs", "post.ejs"):
        path = THEME / "layout" / "_partial" / name
        if not path.exists():
            continue
        text = _strip_ejs_comments(path.read_text(encoding="utf-8"))
        for word in ("page.categories", "page.tags", "category", "tag-chip"):
            assert word not in text, f"{name} 里还在渲染「{word}」"
