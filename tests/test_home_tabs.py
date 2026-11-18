"""首页文章区 tab 的守卫测试。

**背景**：首页的三个 tab（最新发布 / 编辑推荐 / 近期热门）此前是**假控件**。

Materialize 自带 Tabs 组件，但本主题从来没调用过 ``.tabs()``——三个面板
于是依次平铺渲染，访客点「编辑推荐」看起来像切了，其实什么都没发生。
而 DOM 里有三组共 18 张卡片，页面被撑得很长。

修法是让 ``matery.js`` 调用 ``.tabs()``，另加一条 CSS 兜底（默认只显示
第一个面板），这样即使 JS 没跑起来，首页也不会一次铺开 18 张卡片。

这里断言的是**行为契约**，不是「某段代码存在」：

1. 三个面板各有一个 tab 标签，href 与面板 id 一一对应（对不上 = 点不动）。
2. 默认激活的是「最新发布」，且它是 DOM 里第一个面板。
3. CSS 有「默认只显示一个面板」的兜底规则。
4. ``matery.js`` 真的初始化了 tabs。

**为什么第 1 条要这么写**：只断言「有 ``.tabs()`` 调用」是自证的——
把那行代码删掉，测试照样绿（只要字符串还在别处）。真正会坏的是
**href 与 id 对不上**，或者**面板的 class 漏了**，那时候 ``.tabs()``
调了也没用。所以这里把「标签 ↔ 面板」的对应关系当成契约来钉。

放在根级 ``tests/``，随 ``site-guard.yml`` 进 CI。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "platforms" / "blog" / "site"
THEME = SITE / "themes" / "matery"
HOME_CONTENT = THEME / "layout" / "_partial" / "home-content.ejs"
MATERY_JS = THEME / "source" / "js" / "matery.js"
MY_CSS = THEME / "source" / "css" / "my.css"
PATCH_THEME = SITE / "tools" / "patch-theme.py"
CHECKER = SITE / "tools" / "check-home-tabs.py"
WORKFLOW = REPO / ".github" / "workflows" / "hexo.yml"

# tab 标签与面板的 id。三个面板各对应一个 tab。
TAB_IDS = ["home-tab-latest", "home-tab-featured", "home-tab-hot"]


def load_tool(name):
    """Import one of the tools as a module."""
    spec = importlib.util.spec_from_file_location(
        "tool_under_test_{}".format(name.replace("-", "_")), CHECKER.parent / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


home_tabs_checker = load_tool("check-home-tabs")


def _home_content() -> str:
    return HOME_CONTENT.read_text(encoding="utf-8")


def _good_page() -> str:
    """一个结构正确的首页片段（检查器的输入）。"""
    return (
        '<ul class="tabs" role="tablist">'
        '<li class="tab col s4"><a class="active" href="#home-tab-latest">最新发布</a></li>'
        '<li class="tab col s4"><a href="#home-tab-featured">编辑推荐</a></li>'
        '<li class="tab col s4"><a href="#home-tab-hot">近期热门</a></li>'
        "</ul>"
        '<div id="home-tab-latest" class="col s12 home-tab-panel active">A</div>'
        '<div id="home-tab-featured" class="col s12 home-tab-panel">B</div>'
        '<div id="home-tab-hot" class="col s12 home-tab-panel">C</div>'
    )


# --- 1. 标签 ↔ 面板的对应关系 ---------------------------------------------


def test_every_tab_label_points_at_a_panel_that_exists():
    """标签的 href 必须能找到一个同 id 的面板。

    Materialize 按 href 找面板。href 写错或面板漏了，``.tabs()`` 调用了
    也切不动——而「有 ``.tabs()`` 调用」这个断言照样是绿的。
    """
    text = _home_content()

    hrefs = re.findall(r'<li class="tab[^"]*"><a[^>]*href="#([^"]+)"', text)
    assert hrefs == TAB_IDS, "tab 标签的 href 应当正好是三个面板 id，实际：{}".format(hrefs)

    panel_ids = re.findall(r'<div id="(home-tab-[^"]+)"', text)
    assert panel_ids == TAB_IDS, "面板 id 应当与 tab 标签一一对应，实际：{}".format(panel_ids)


def test_every_panel_carries_the_shared_class():
    """三个面板都要带 ``home-tab-panel``。

    CSS 兜底规则（默认只显示一个面板）靠这个类名生效；漏了哪个面板，
    那个面板就会在 JS 没跑起来时铺开。
    """
    text = _home_content()

    for panel_id in TAB_IDS:
        match = re.search(
            r'<div id="{}"[^>]*>'.format(re.escape(panel_id)), text
        )
        assert match is not None, "找不到面板 {}".format(panel_id)
        assert "home-tab-panel" in match.group(0), (
            "面板 {} 缺少 home-tab-panel 类名，CSS 兜底对它不生效".format(panel_id)
        )


# --- 2. 默认激活的是「最新发布」 -------------------------------------------


def test_the_latest_panel_is_the_default_and_comes_first():
    """默认激活「最新发布」，且它是 DOM 里的第一个面板。

    「新文章上线即可见」是这个 tab 存在的理由，所以它必须是默认项，
    也必须排在最前面——否则 Materialize 初始化时激活的是别的面板。
    """
    text = _home_content()

    active_tabs = re.findall(r'<li class="tab[^"]*"><a class="active" href="#([^"]+)"', text)
    assert active_tabs == ["home-tab-latest"], (
        "默认激活的应当只有「最新发布」，实际：{}".format(active_tabs)
    )

    first_panel = re.search(r'<div id="(home-tab-[^"]+)"[^>]*class="[^"]*active', text)
    assert first_panel is not None, "第一个面板应当带 active 类"
    assert first_panel.group(1) == "home-tab-latest", (
        "带 active 的应当是第一个面板「最新发布」，实际：{}".format(first_panel.group(1))
    )


# --- 3. CSS 兜底 ------------------------------------------------------------


def test_the_css_hides_the_other_panels_by_default():
    """没有 JS 时也要只显示一个面板。

    Materialize 用**内联** ``display`` 切换显隐，而内联样式要等它初始化
    才写上。在那之前三个面板会一起铺开——首页一次出现 18 张卡片。
    CSS 兜底把这件事挡掉。
    """
    css = MY_CSS.read_text(encoding="utf-8")

    assert "/* HOME-TABS */" in css, "缺少 HOME-TABS 标记段"
    assert ".home-tabs .home-tab-panel" in css
    # 默认隐藏，激活的显示
    assert re.search(
        r"\.home-tabs \.home-tab-panel\s*\{[^}]*display:\s*none", css
    ), "缺少「默认隐藏面板」的规则"
    assert re.search(
        r"\.home-tabs \.home-tab-panel\.active\s*\{[^}]*display:\s*block", css
    ), "缺少「激活面板显示」的规则"


def test_the_patch_theme_owns_the_home_tabs_css():
    """CSS 注入段在 ``patch-theme.py`` 里，幂等。

    样式只写在 ``my.css`` 里而不进注入段，下次有人重跑
    ``patch-theme.py``（CI 每次构建都跑）就会把它冲掉。

    这里断言的是「marker 与 CSS 正文都在」——只断言 marker 名字的话，
    把它换个名字（``home_tabs_marker = "/* HOME-TABS-REMOVED */"``）
    而正文照旧，测试是绿的，注入段却已经对不上 my.css 了。
    """
    text = PATCH_THEME.read_text(encoding="utf-8")

    assert "/* HOME-TABS */" in text, "注入段里缺少 HOME-TABS 标记"
    assert "home_tabs_marker" in text, "缺少幂等标记变量"
    # 注入的 CSS 正文要包含兜底规则本身
    assert ".home-tabs .home-tab-panel" in text, "注入段里缺少 home-tab-panel 规则"
    assert "display: none" in text and "display: block" in text
    # marker 与正文必须**同源**：正文由 marker 拼出来。
    # 写成两个独立常量的话，改了其中一个就会对不上——而后果是
    # patch-theme 认为这段 CSS 已注入过（marker 在 my.css 里），
    # 于是永远不写正文，兜底规则静默失效。
    marker_match = re.search(r'home_tabs_marker\s*=\s*"([^"]+)"', text)
    assert marker_match is not None, "找不到 marker 的赋值"
    marker = marker_match.group(1)
    assert marker == "/* HOME-TABS */", (
        "marker 应当是 /* HOME-TABS */，实际：{}".format(marker)
    )
    assert re.search(
        r'ht_css\s*=\s*home_tabs_marker\s*\+', text
    ), "CSS 正文应当由 marker 拼出来（保证两者永远一致）"


# --- 4. 真的初始化了 tabs ---------------------------------------------------


def test_the_theme_js_initializes_the_tabs():
    """``matery.js`` 要真的调用 ``.tabs()``。

    这里只断言「调用了」——真正保证「切得动」的是上面第 1 条
    （href ↔ id 对应）与第 3 条（CSS 兜底），三条合起来才是行为契约。

    **用正则匹配代码会漏**：``.tabs()`` 这几个字在注释里也出现过
    （那段注释正好在讲这件事），把真正的调用删掉，字符串还在，断言照样绿。
    所以这里剥掉注释与字符串字面量，只看**真正执行的代码**。
    """
    js = MATERY_JS.read_text(encoding="utf-8")
    code = _strip_comments_and_strings(js)

    # 1. 选择器限定在 .home-tabs 内（只看代码，不看注释）
    selectors = re.findall(r"\$\(\s*'([^']*)'\s*\)", code)
    home_selectors = [s for s in selectors if ".home-tabs" in s]
    assert home_selectors, "找不到针对 .home-tabs 的选择器"

    # 2. 那个选择器取到的对象上确实调了 .tabs()
    assert re.search(r"\.tabs\s*\(\s*\)", code), "代码里没有对 tabs 的初始化调用"

    # 3. 调用点与选择器在同一个变量上——不能是两处无关的代码
    #    （选择器存在、但调用的是别的东西，同样是坏的）。
    var_names = set()
    for match in re.finditer(
        r"(?:let|var|const)\s+([A-Za-z_$][\w$]*)\s*=\s*\$\(\s*'([^']*\.home-tabs[^']*)'",
        code,
    ):
        var_names.add(match.group(1))
    assert var_names, "找不到持有 .home-tabs 选择器的变量"
    called = any(
        re.search(r"\b{}\s*\.tabs\s*\(\s*\)".format(re.escape(name)), code)
        for name in var_names
    )
    assert called, (
        "持有 .home-tabs 选择器的变量 {} 上没有调用 .tabs()".format(sorted(var_names))
    )


def _strip_comments_and_strings(source: str) -> str:
    """去掉 JS 注释，只保留代码与字符串字面量的内容。

    目的是让「代码里有这段字」和「注释里提到这段字」不再混为一谈——
    前者是行为，后者只是说明。

    **字符串字面量的内容要留下**：选择器 ``'.home-tabs .tabs'`` 本身就是
    行为的一部分，剥成空串就等于把「选择器写错了」这个缺陷藏起来了。
    """
    out = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            out.append(ch)
            while i < n and source[i] != quote:
                if source[i] == "\\" and i + 1 < n:
                    out.append(source[i])
                    out.append(source[i + 1])
                    i += 2
                    continue
                out.append(source[i])
                i += 1
            out.append(quote)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def test_the_materalize_tabs_component_is_actually_available():
    """Materialize 必须真的带 Tabs 组件。

    主题依赖的是本地 vendored 的 ``materialize.min.js``。如果哪天
    换了版本而那个版本没有 Tabs，``.tabs()`` 就不存在——那时候
    「代码里有调用」这个断言是绿的，页面却仍然是个假控件。
    """
    vendored = SITE / "themes" / "matery" / "source" / "libs" / "materialize" / "materialize.min.js"
    assert vendored.is_file(), "找不到 vendored 的 materialize.min.js"

    source = vendored.read_text(encoding="utf-8", errors="replace")
    assert "M.Tabs" in source, "vendored 的 materialize 里没有 Tabs 组件"
    # jQuery 包装：``$('.x').tabs()`` 依赖 initializeJqueryWrapper 注册的
    # jQuery 插件（jQuery 必须在 materialize 之前加载，head.ejs 里已保证）。
    assert "initializeJqueryWrapper" in source
    assert "tabs" in source


# --- 5. 渲染产物检查器 ------------------------------------------------------


def _write_page(tmp_path, html):
    public = tmp_path / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / "index.html").write_text(html, encoding="utf-8")
    return str(public)


def test_the_checker_passes_on_a_correct_homepage(tmp_path):
    assert home_tabs_checker.check(_write_page(tmp_path, _good_page())) == []


def test_the_checker_catches_a_href_that_points_nowhere(tmp_path):
    """标签 href 与面板 id 对不上——点了切不动。"""
    html = _good_page().replace('href="#home-tab-featured"', 'href="#nope"')
    problems = home_tabs_checker.check(_write_page(tmp_path, html))

    assert problems, "检查器应当报出问题"
    assert any("href" in p for p in problems), problems


def test_the_checker_catches_a_panel_without_the_shared_class(tmp_path):
    """面板漏了 home-tab-panel——CSS 兜底对它不生效。"""
    html = _good_page().replace(
        '<div id="home-tab-hot" class="col s12 home-tab-panel">',
        '<div id="home-tab-hot" class="col s12">',
    )
    problems = home_tabs_checker.check(_write_page(tmp_path, html))

    assert any("home-tab-panel" in p for p in problems), problems


def test_the_checker_catches_a_duplicated_panel_id(tmp_path):
    """面板 id 重复——标签只能指到第一个。"""
    html = _good_page().replace(
        '<div id="home-tab-hot" class="col s12 home-tab-panel">',
        '<div id="home-tab-featured" class="col s12 home-tab-panel">',
    )
    problems = home_tabs_checker.check(_write_page(tmp_path, html))

    assert any("重复" in p for p in problems), problems


def test_the_checker_catches_a_missing_rendered_page(tmp_path):
    """构建产物没出来时要说人话，而不是抛异常。"""
    problems = home_tabs_checker.check(str(tmp_path / "nonexistent"))

    assert problems
    assert "找不到渲染产物" in problems[0]


def test_the_ci_runs_the_home_tabs_checker_in_both_builds():
    """两个 build job 都要跑——少一个就有一处不设防。"""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("python3 platforms/blog/site/tools/check-home-tabs.py") == 2
    # 必须在 hexo generate 之后——检查的是渲染产物
    for build in workflow.split("- name: Build with Hexo")[1:]:
        segment = build.split("- name: Subset Font Awesome fonts")[0]
        assert "platforms/blog/site/tools/check-home-tabs.py" in segment
