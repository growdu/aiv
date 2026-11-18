"""首页是单页设计，不该再分页。

首页的内容（统计条 / 学习路径 / 三个 Tab 的卡片）全都渲染在
``platforms/blog/site/themes/matery/layout/_partial/home-content.ejs`` 里，而那个 partial
**只在第一页渲染**::

    <% if (is_home() && page.current === 1) { %>

所以 ``_config.yml`` 的 ``index_generator.per_page`` 要是还留着 10，
hexo-generator-index 就会按 10 篇一页把文章切开，生成
``/page/2/`` … ``/page/57/`` —— 57 个**零内容页**：既没有封面也没有列表，
站内没有任何入口链到它们。

它们不是「待优化项」，是 57 个既没有内容、又占着 URL 的空壳。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "platforms" / "blog" / "site"
CONFIG = SITE / "_config.yml"
HOME_CONTENT = (
    SITE / "themes" / "matery" / "layout" / "_partial" / "home-content.ejs"
)


def read_index_generator_per_page() -> int:
    """读 ``_config.yml`` 里 ``index_generator.per_page`` 的值。

    不引 PyYAML：仓库的依赖里没有它（``sync-hexo.py`` 干脆自己写了一个
    YAML 解析器）。这里只需要一个整数，按行扫就够了。
    """
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    in_block = False
    for line in lines:
        if re.match(r"^index_generator:\s*$", line):
            in_block = True
            continue
        if in_block:
            if line and not line.startswith((" ", "\t", "#")):
                break  # 出了这个块
            m = re.match(r"^\s+per_page:\s*(\d+)\s*$", line)
            if m:
                return int(m.group(1))
    raise AssertionError("_config.yml 里找不到 index_generator.per_page")


def test_the_home_paginator_produces_a_single_page():
    """``per_page`` 必须是 0——hexo-pagination 在 perPage 为 0 时只出一页。

    顺带说明为什么首页内容一个字都不会变：``home-content.ejs`` 渲染的是
    ``site.posts``（全部文章），不是 ``page.posts``，所以分不分页都一样。
    """
    assert read_index_generator_per_page() == 0


def test_the_home_content_is_still_a_single_page_design():
    """单页设计的前提还在：内容只在第一页渲染。

    这条是给「以后有人要把首页改成分页列表」的人留的提醒：真要改，
    得先把这行判断拆掉，再把 ``per_page`` 调回去——反过来就会重演
    「有一堆零内容页」这一出。
    """
    text = HOME_CONTENT.read_text(encoding="utf-8")

    assert "page.current === 1" in text, text[:400]


def test_nothing_links_to_the_pagination_pages():
    """站内不许有入口链到 ``/page/N/``。

    现在没有，但这是「零内容页」能悄悄攒到 57 个的原因之一：没有入口，
    搜索引擎却照样能顺着 sitemap 爬进去。分页一旦关掉，这些 URL 就该
    从来没被引用过。
    """
    offenders = []
    for path in (
        *sorted((SITE / "themes" / "matery" / "layout").rglob("*.ejs")),
        SITE / "tools" / "patch-theme.py",
    ):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if "/page/" in line and not line.strip().startswith(("//", "*", "#")):
                # 注释里提到 /page/N/ 是说明，不是链接
                if "/page/2/" in line and "pseudo-pages" in line:
                    continue
                offenders.append("{}:{}: {}".format(path, number, line.strip()))

    assert offenders == [], offenders
