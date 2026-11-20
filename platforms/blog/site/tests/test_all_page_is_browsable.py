"""``/all/`` 那一页：跳到 ``/archives/``，但仍然是**能看**的一页。

**背景**
--------
``/all/`` 以前把全部文章渲染进一个 3D 轮播（几百张卡一次性进 DOM）。
现在归档页（``/archives/``）按时间轴 + 年度分页把同样的内容排好了，
首页的「查看全部」直接指向归档页。

但旧 URL 不能 404：发布出去很久的书签、搜索引擎的索引、别人的博客都还链着
（URL 稳定性是硬约束）。所以 ``/all/`` 留一个跳转页，三件事一起做：

1. **canonical** —— 告诉搜索引擎这个 URL 的正身在 ``/archives/``；
2. **meta refresh** —— 普通浏览器直接跳过去；
3. **一个真链接** —— meta refresh 被禁用时（浏览器设置、公司代理）人还能走。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from paths import SITE

SITE_ROOT = SITE
DIST = SITE_ROOT / "dist"
ALL_PAGE = DIST / "all" / "index.html"


@pytest.fixture(scope="module")
def page() -> str:
    if not ALL_PAGE.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return ALL_PAGE.read_text(encoding="utf-8")


def test_the_page_points_at_the_archives(page):
    assert "/archives/" in page, "跳转页没有指向归档页"


def test_it_has_a_canonical(page):
    assert re.search(r'<link[^>]+rel="canonical"[^>]+href="[^"]*/archives/"', page), (
        "跳转页没有 canonical（或它指的不是归档页）"
    )


def test_it_is_not_indexed(page):
    """跳转页不该被搜索引擎当成内容页收进索引。"""
    assert re.search(r'<meta[^>]+name="robots"[^>]+noindex', page), (
        "跳转页没有 noindex"
    )


def test_it_has_a_meta_refresh(page):
    assert re.search(r'<meta[^>]+http-equiv="refresh"', page), "跳转页没有 meta refresh"


def test_it_has_a_real_link(page):
    """meta refresh 被禁用时，人还得能走。"""
    assert re.search(r'<a[^>]+href="[^"]*/archives/"', page), "跳转页里没有真链接"


def test_it_is_a_whole_document(page):
    """这一页自己是完整的 HTML 文档——套一层就会套出两层 <html>。"""
    assert page.count("<html") == 1, "跳转页被套了多层 <html>"
    assert page.count("<body") == 1, "跳转页被套了多层 <body>"
