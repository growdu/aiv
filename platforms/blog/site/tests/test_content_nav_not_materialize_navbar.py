"""内容模板里不许用 ``<nav>``。

**为什么**
--------
Materialize 按**元素名**给 ``nav`` 上样式::

    nav{height:64px;line-height:64px;background-color:#ee6e73}

那一块会被压成一条 64px 高的**红条**，横在正文中间。文章页、学习流页、
目录页里任何一个 ``<nav>``（面包屑、分页、上下篇导航）都会这样——
它不是「导航条该有的样子」，是样式表里的一条遗留规则。

站点自己的顶栏（``_partial/header.ejs``）用 ``<nav id="headNav">``，
那是**故意**的：Materialize 认它，主题的 CSS 也照着它写。面包屑这类
内容里的导航一律用 ``<div>``。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

from paths import SITE

SITE_ROOT = SITE
THEME = SITE_ROOT / "themes" / "matery"
LAYOUT = THEME / "layout"

#: 允许用 ``<nav>`` 的模板：站点自己的顶栏。
ALLOWED = {"_partial/header.ejs"}

#: EJS 注释：``<%# ... %>``（单行）与 ``<%/* ... */%>``（块）。
EJS_COMMENT_RE = re.compile(r"<%#.*?%>|<%/\*.*?\*/%>", re.S)

NAV_RE = re.compile(r"<nav\b", re.I)


def _strip_ejs_comments(text: str) -> str:
    """把 EJS 注释去掉——注释里提到 ``<nav>`` 是说明，不是标签。"""
    return EJS_COMMENT_RE.sub("", text)


def test_no_content_template_uses_a_nav_element():
    offenders = []
    for path in sorted(LAYOUT.rglob("*.ejs")):
        rel = path.relative_to(LAYOUT).as_posix()
        if rel in ALLOWED:
            continue
        text = _strip_ejs_comments(path.read_text(encoding="utf-8"))
        if NAV_RE.search(text):
            offenders.append(rel)
    assert not offenders, (
        "内容模板里用了 <nav>（Materialize 会把它压成一条 64px 的红条）："
        + "、".join(offenders)
    )
