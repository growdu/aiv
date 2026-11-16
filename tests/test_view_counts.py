"""侧栏的🔥阅读量是真的吗？——从「字数除以 50」到 GoatCounter 的真实 PV。

**背景**：阶段 1 的 Task 6。

线上侧栏「最热文章」那一栏的🔥数字，是 ``patch-theme.py`` 里的一句
``Math.max(5, Math.floor(字数 / 50))``——**它是文章的字数除以 50**。
一篇十万字的文章显示「🔥 2000」，读者以为有两千人读过它。

真实的两套统计是有的：GoatCounter（页面在收）和不蒜子（页面在显示），
但它们的数字都是**页面运行时**由脚本填的，构建期拿不到——于是模板
只好自己编一个。

**这个任务把假数字删掉**：

1. 侧栏的🔥读 ``data/view-counts.json``（GoatCounter 的真实 PV 快照）。
   快照里没有这个页面 → **这一格不显示**，不显示一个假的🔥。
2. 首页的「近期热门」tab 同样按真实 PV 排；快照缺失、或者 PV 少到
   无法区分高下时，退回原来的 ``top`` 排序，并把 tab 改名成「编辑精选」——
   **不要让一个叫「热门」的 tab 装着手动排序的内容**。

快照由 ``tools/fetch-view-counts.py`` 生成。选 GoatCounter 而不是不蒜子：
它的 API 是**只读**的，不会像不蒜子那样每查一次就给那个路径 +1。

这里断言的是**行为**：模板渲染出来的 HTML 里有没有那个数字、数字是
多少——不是「代码里有没有某个字符串」。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_THEME = REPO_ROOT / "tools" / "patch-theme.py"
THEME_LAYOUT = REPO_ROOT / "themes" / "matery" / "layout" / "layout.ejs"
HOME_CONTENT = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "home-content.ejs"
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node 不在 PATH 上")


# --- 取模板 -----------------------------------------------------------------


def _patcher_sidebar() -> str:
    """``patch-theme.py`` 里那段注入用的侧栏模板。

    它是**生成器**：下次跑 patch-theme.py 时，这段会重新写进主题文件。
    主题文件（layout.ejs）里那段是手改过的（多了折叠开关），两者已经
    不是同一段文本了——所以这里两边都取出来，各自断言。
    """
    text = PATCH_THEME.read_text(encoding="utf-8")
    match = re.search(r'sidebar_ejs = """(.*?)"""', text, re.S)
    assert match, "patch-theme.py 里找不到 sidebar_ejs"
    return ast.literal_eval('"""' + match.group(1) + '"""')


def _theme_sidebar() -> str:
    """主题文件里实际生效的那段侧栏模板。"""
    text = THEME_LAYOUT.read_text(encoding="utf-8")
    start = text.find("<% if (site.categories && site.categories.length) { %>")
    end = text.find("<%# Per-page view counter is handled by Vercount embed below. %>")
    assert start >= 0, "layout.ejs 里找不到侧栏段"
    assert end > start, "layout.ejs 里找不到侧栏段的结尾"
    return text[start:end]


SIDEBAR_TEMPLATES = {
    "patcher": _patcher_sidebar,
    "theme": _theme_sidebar,
}


def _home_script() -> str:
    """home-content.ejs 里那个算 tab 数据的 ``<% ... %>`` 块。"""
    text = HOME_CONTENT.read_text(encoding="utf-8")
    for block in re.findall(r"<%(.*?)%>", text, re.S):
        if "var allPosts" in block:
            return block
    raise AssertionError("home-content.ejs 里找不到算 tab 数据的代码块")


# --- 在 node 里跑模板 -------------------------------------------------------

SIDEBAR_HARNESS = r"""
const ejs = require('ejs');
const fs = require('fs');
const tmpl = fs.readFileSync(process.argv[1], 'utf8');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const posts = spec.posts || [];
const site = {
  posts: {data: posts, length: posts.length},
  categories: {length: spec.categories || 0},
  data: spec.data || {},
};
const out = ejs.render(tmpl, {
  site: site,
  config: {root: '/'},
  url_for: function (p) { return p; },
  is_home: function () { return true; },
  __: function (s) { return s; },
});
// 客户端脚本里的 'hot-views' 与 '🔥' 是**代码**，不是渲染出来的数字。
// 断言页面上有没有那个数字，只能看渲染出来的标记。
const visible = out.replace(/<script[\s\S]*?<\/script>/g, '');
process.stdout.write(JSON.stringify({visible: visible}));
"""

HOME_HARNESS = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[1], 'utf8');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const posts = spec.posts || [];
const site = {
  posts: {
    length: posts.length,
    forEach: function (fn) { posts.forEach(fn); },
    toArray: function () { return posts.slice(); },
  },
  categories: {length: spec.categories || 0},
  data: spec.data || {},
};
const wordcount = function (s) { return String(s).length; };
const theme = {time: {year: 2020, month: 1, date: 1}};
const fn = new Function('site', 'wordcount', 'theme', script + '\n' +
  'return {hot: hot.map(function (p) { return p.path; }),' +
  ' hotTabName: (typeof hotTabName === "undefined" ? null : hotTabName)};');
process.stdout.write(JSON.stringify(fn(site, wordcount, theme)));
"""


def _run_node(harness: str, script_path: Path, payload: dict, tmp_path: Path) -> dict:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [NODE, "-e", harness, str(script_path), str(payload_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "node 那段脚本抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    return json.loads(result.stdout)


def _render_sidebar(template: str, spec: dict, tmp_path: Path) -> str:
    template_path = tmp_path / "sidebar.ejs"
    template_path.write_text(template, encoding="utf-8")
    return _run_node(SIDEBAR_HARNESS, template_path, spec, tmp_path)["visible"]


def _home_tabs(spec: dict, tmp_path: Path) -> dict:
    script_path = tmp_path / "home-script.js"
    script_path.write_text(_home_script(), encoding="utf-8")
    return _run_node(HOME_HARNESS, script_path, spec, tmp_path)


# --- 假的文章 ---------------------------------------------------------------


def _long_post(path: str, title: str, chars: int = 100000) -> dict:
    """一篇十万字的文章——旧的假公式会把它显示成「🔥 2000」。"""
    return {
        "path": path,
        "title": title,
        "content": "<p>" + ("字" * chars) + "</p>",
        "categories": {"data": []},
    }


# --- 1. 假数字没了 ---------------------------------------------------------


@needs_node
@pytest.mark.parametrize("source", sorted(SIDEBAR_TEMPLATES))
def test_the_page_no_longer_shows_a_length_based_view_count(source, tmp_path):
    """拿不到真实 PV 时，**这一格不显示**——不显示一个假的🔥。

    旧行为：一篇十万字的文章显示「🔥 2000」（= 字数 / 50）。
    """
    template = SIDEBAR_TEMPLATES[source]()
    html = _render_sidebar(template, {"posts": [_long_post("2026/08/18/db/aaa/index.html", "长文")]}, tmp_path)

    assert "hot-views" not in html, (
        "没有真实阅读量却还在显示那一格——宁可空着，也不显示假的"
    )
    assert "🔥" not in html, "页面里还留着假的🔥"
    assert "2000" not in html, "页面里还留着按字数算出来的数字"


@needs_node
@pytest.mark.parametrize("source", sorted(SIDEBAR_TEMPLATES))
def test_the_sidebar_shows_the_real_view_count_when_the_snapshot_has_one(source, tmp_path):
    """快照里有这个页面 → 显示**快照里的那个数**，不是字数算的。"""
    template = SIDEBAR_TEMPLATES[source]()
    html = _render_sidebar(
        template,
        {
            "posts": [_long_post("2026/08/18/db/aaa/index.html", "长文")],
            "data": {"view-counts": {"counts": {"2026/08/18/db/aaa": 42}}},
        },
        tmp_path,
    )

    assert "🔥 42" in html, "真实阅读量没有显示出来"


@needs_node
def test_the_sidebar_leaves_out_the_number_for_a_page_the_snapshot_does_not_know(tmp_path):
    """快照里没有的页面 → 那一格不显示（不是显示 0，也不是显示假的）。"""
    template = _theme_sidebar()
    html = _render_sidebar(
        template,
        {
            "posts": [
                _long_post("2026/08/18/db/aaa/index.html", "有 PV"),
                _long_post("2026/08/18/db/bbb/index.html", "没 PV"),
            ],
            "data": {"view-counts": {"counts": {"2026/08/18/db/aaa": 42}}},
        },
        tmp_path,
    )

    assert html.count("hot-views") == 1, (
        "只有快照里有数的那一篇才显示这一格，实际 {} 处".format(html.count("hot-views"))
    )
