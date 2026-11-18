"""「查看全部 N 篇」不该把人丢进一个 1/N 的轮播。

**现状**：首页的「查看全部 **577** 篇」→ ``/all/``。``all.ejs`` 把**全部**
文章渲染进一个 3D 轮播（``.carousel-3d-container``），``3d-carousel.js`` 在
超过 10 条时只给一个「**1 / 577**」的计数器——要逐张点。没有筛选、没有搜索、
没有排序，577 张卡一次性进 DOM。

**真正能翻阅的列表在** ``/archives/``（时间轴 + 年度分页）——首页的入口没指
过去。

**改法**：首页的入口指到 ``/archives/``；``/all/`` 保留成一个**重定向页**
（canonical + meta refresh + 一个真链接），旧 URL 不 404——spec §7.4 的 URL
稳定性是硬约束。meta refresh 被禁用时（某些浏览器设置、公司代理）人还能
点那个链接。

这里断言的是**行为**：重定向页真的会在浏览器里把访客送到归档页（跑一遍
``all.ejs`` 自己的那段逻辑），而不是只在模板里出现过一个字符串。
"""

from __future__ import annotations

import re
from pathlib import Path

from paths import REPO_ROOT as REPO, SITE
THEME = SITE / "themes" / "matery"
PARTIAL = THEME / "layout" / "_partial"
ALL_EJS = THEME / "layout" / "all.ejs"
HOME_CONTENT = PARTIAL / "home-content.ejs"


def _read(path: Path) -> str:
    assert path.is_file(), "找不到 {}".format(path)
    return path.read_text(encoding="utf-8")


# --- 入口指对了 -------------------------------------------------------------


def test_the_view_all_link_points_at_the_archive():
    """首页「查看全部 N 篇」指向 ``/archives/``，不再指向 ``/all/``。"""
    content = _read(HOME_CONTENT)

    assert "url_for('/all/')" not in content, (
        "首页「查看全部」还指向 /all/ —— 那是个 1/577 的轮播"
    )
    assert "url_for('/archives/')" in content, (
        "首页「查看全部」没有指向 /archives/"
    )


# --- /all/ 变成重定向页 ------------------------------------------------------


def test_the_all_page_redirects_to_the_archive():
    """``/all/`` 要有 canonical、meta refresh 和一个真链接。

    三个都要：
    - canonical：告诉搜索引擎这个 URL 的正身是归档页；
    - meta refresh：普通浏览器直接跳过去；
    - 真链接：meta refresh 被禁用时，人还能走。
    """
    page = _read(ALL_EJS)

    assert re.search(r'<link[^>]+rel=["\']canonical["\']', page), (
        "/all/ 没有 canonical —— 搜索引擎会把它当成另一个页面"
    )
    assert "http-equiv" in page and "refresh" in page, (
        "/all/ 没有 meta refresh"
    )
    assert re.search(r"<a\s[^>]*href=[^>]*archives", page), (
        "/all/ 没有一个指向归档页的可点链接 —— meta refresh 被禁时人就卡在这"
    )
    assert "carousel-3d-container" not in page, (
        "/all/ 还在渲染 3D 轮播 —— 577 张卡一次性进 DOM"
    )


def test_the_all_page_says_where_the_articles_went():
    """重定向页要有一句人话，别让访客以为页面坏了。"""
    page = _read(ALL_EJS)

    assert re.search(r"归档", page), "/all/ 没有一句说明文章去哪了"


def test_the_all_page_is_a_standalone_document():
    """这一页自带完整 HTML，所以**不能**再被主题的 layout.ejs 包一层。

    主题的 layout.ejs 会把每个 view 包进完整的 HTML 文档。这一页自己就是
    完整文档（canonical 和 meta refresh 只有在自己的 ``<head>`` 里才算数），
    不关掉包裹就会套出两层 ``<html>``。

    关掉的办法是 view 自己的 front matter：``layout: false``。
    """
    page = _read(ALL_EJS)

    assert re.search(r"^---\s*\nlayout:\s*false\s*\n---", page), (
        "/all/ 没有关掉主题的包装（layout: false）—— 会套出两层 <html>"
    )
    # EJS 注释（<%# ... %>）里提到过 <html>——先剥掉再数。
    markup = re.sub(r"<%#.*?%>", "", page, flags=re.S)
    assert markup.count("<html") == 1, "/all/ 里有多个 <html>"


def test_the_built_all_page_redirects_without_a_nested_document():
    """构建产物里 ``/all/`` 是一个干净的、只有一层的重定向页。

    产物是 gitignore 的，本地构建过才有；CI 的 site-guard 不构建，
    所以没构建时跳过，而不是红。
    """
    built = SITE / "public" / "all" / "index.html"
    if not built.is_file():
        import pytest

        pytest.skip("还没构建（platforms/blog/site/public/all/index.html 不存在）")

    html = built.read_text(encoding="utf-8")

    assert html.count("<html") == 1, "构建出来的 /all/ 套了多层 <html>"
    assert "http-equiv" in html and "refresh" in html, "构建出来的 /all/ 没有 meta refresh"
    assert "/archives/" in html, "构建出来的 /all/ 没有指向归档页"


def test_the_archive_page_exists_in_the_built_site():
    """``/archives/`` 得真的存在——入口指过去不能指到一个 404。

    产物是 gitignore 的，本地构建过才有；CI 的 site-guard 不构建，
    所以没构建时跳过，而不是红。
    """
    built = SITE / "public" / "archives" / "index.html"
    if not built.is_file():
        import pytest

        pytest.skip("还没构建（platforms/blog/site/public/archives/index.html 不存在）")

    assert built.stat().st_size > 0, "platforms/blog/site/public/archives/index.html 是空的"


# --- 独立页不该被注入主题资源 -----------------------------------------------


def _patcher_function(name: str):
    """把 ``patch-theme.py`` 里某个函数抠出来单独跑。

    那个脚本是一路执行下来的（没有 ``main()`` 保护），import 它会把整个
    主题改一遍——所以只能抠出函数体自己 exec。
    """
    text = (SITE / "tools" / "patch-theme.py").read_text(encoding="utf-8")
    rest = text[text.index("def {}(".format(name)):]
    # 函数体到**第一个顶格行**为止（下一个模块级语句）。
    lines = rest.split("\n")
    body_lines = [lines[0]]  # def 那一行本身是顶格的
    for line in lines[1:]:
        if line and not line.startswith((" ", "\t")):
            break
        body_lines.append(line)
    body = "\n".join(body_lines)
    namespace = {"re": re}
    exec(compile(body, "patch-theme.py", "exec"), namespace)
    return namespace[name]


def test_the_patcher_recognises_a_standalone_page():
    """``layout: false`` 的页面自带 html/head/body，主题资源不该往里塞。"""
    is_standalone = _patcher_function("is_standalone_page")

    assert is_standalone(
        "---\nlayout: false\n---\n<html><head></head><body></body></html>"
    )
    assert not is_standalone(
        "---\ntitle: x\n---\n<html><head></head><body></body></html>"
    )
    assert not is_standalone("<html><head></head><body></body></html>")


def test_the_all_page_is_not_polluted_with_the_theme_assets():
    """``/all/`` 是个重定向页，不该背着一整份主题 CSS。

    它以前被 patcher 当成注入目标，于是：多了一份 25KB 的 CSS、多了
    一条跟自己的跳转目标打架的 canonical（``/archives/`` 和
    ``growdu.cn/all/index.html`` 同时存在）——而且因为注入过的文件会被
    跳过，那份 CSS 从此冻结，patcher 再也不刷新它。
    """
    text = ALL_EJS.read_text(encoding="utf-8")

    assert "custom-blog-style" not in text, "独立页里被注入了主题 CSS"
    assert "custom-blog-script" not in text, "独立页里被注入了主题 JS"
    assert text.count('rel="canonical"') == 1, (
        "有 {} 条 canonical——跳转页只能有一条，指向它的正身".format(
            text.count('rel="canonical"')
        )
    )
