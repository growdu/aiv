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
多少、tab 叫什么——不是「代码里有没有某个字符串」。
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
THEME_LAYOUT = REPO_ROOT / "themes" / "matery" / "layout" / "layout.ejs"
HOME_CONTENT = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "home-content.ejs"
FETCHER = REPO_ROOT / "tools" / "fetch-view-counts.py"
SNAPSHOT = REPO_ROOT / "data" / "view-counts.json"
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node 不在 PATH 上")


# --- 取模板 -----------------------------------------------------------------


def _theme_sidebar() -> str:
    """主题文件里实际生效的那段侧栏模板。

    侧栏模板现在**只有这一份**。``patch-theme.py`` 里原来还有一份抄本
    （注入用的生成器），可它跟这份早就对不上了——抄本少了折叠开关
    （``onclick="toggleSidebar('cat')"``）和定义 ``window.toggleSidebar``
    的那段脚本。抄本已经删掉，见 tests/test_patch_theme_sidebar.py。
    """
    text = THEME_LAYOUT.read_text(encoding="utf-8")
    start = text.find("<% if (site.categories && site.categories.length) { %>")
    end = text.find("<%# Per-page view counter is handled by Vercount embed below. %>")
    assert start >= 0, "layout.ejs 里找不到侧栏段"
    assert end > start, "layout.ejs 里找不到侧栏段的结尾"
    return text[start:end]


SIDEBAR_TEMPLATES = {
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

# 一个**自带**的极简 EJS 渲染器。
#
# 为什么不用 npm 里的 ejs：site-guard 那条 CI 只装 pytest，**没有
# node_modules**——契约测试不能依赖仓库里没装的东西（上一版就因为
# require('ejs') 在 CI 里整条红了）。这个渲染器只用 node 自带的能力，
# 支持侧栏模板用到的那几个标签：<% %> / <%= %> / <%- %> / <%# %>。
#
# 跟真 ejs 对过：同一份模板、同一份数据，渲染结果**逐字节相同**。
SIDEBAR_HARNESS = r"""
const fs = require('fs');
function renderEjs(tmpl, scope) {
  var code =
    'var __out = [];\n' +
    'function __lit(s){return s;}\n' +
    'function __esc(s){if(s===null||s===undefined)return "";' +
    'return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")' +
    '.replace(/"/g,"&quot;").replace(/\'/g,"&#39;");}\n' +
    'with (__scope) {\n';
  var re = /<%([=\-#]?)([\s\S]*?)-?%>/g;
  var last = 0, m;
  function lit(text) {
    if (text) { code += '__out.push(__lit(' + JSON.stringify(text) + '));\n'; }
  }
  while ((m = re.exec(tmpl)) !== null) {
    lit(tmpl.slice(last, m.index));
    var kind = m[1], body = m[2];
    if (kind === '#') {
      // 注释：不输出
    } else if (kind === '=') {
      code += '__out.push(__esc(' + body + '));\n';
    } else if (kind === '-') {
      code += '__out.push(' + body + ');\n';
    } else {
      code += body + '\n';
    }
    last = re.lastIndex;
  }
  lit(tmpl.slice(last));
  code += '}\nreturn __out.join("");';
  return new Function('__scope', code)(scope);
}
const tmpl = fs.readFileSync(process.argv[1], 'utf8');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const posts = spec.posts || [];
const site = {
  posts: {data: posts, length: posts.length},
  categories: {length: spec.categories || 0, each: function () {}},
  data: spec.data || {},
};
const out = renderEjs(tmpl, {
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


# --- 2. 首页 tab ------------------------------------------------------------


def _three_posts() -> list:
    return [
        {"path": "2026/08/18/db/aaa/index.html", "title": "AAA", "date": 1000, "top": 90, "content": "<p>a</p>"},
        {"path": "2026/08/18/db/bbb/index.html", "title": "BBB", "date": 2000, "top": 50, "content": "<p>b</p>"},
        {"path": "2026/08/18/db/ccc/index.html", "title": "CCC", "date": 3000, "top": 45, "content": "<p>c</p>"},
    ]


@needs_node
def test_the_hot_tab_reads_the_real_view_count_snapshot(tmp_path):
    """「近期热门」按快照里的真实 PV 排——不是按手写的 top 分数。

    这里故意让 PV 的高下与 ``top`` 的高下**相反**：CCC 的 top 只有 45，
    真实 PV 却是最高的。排序听 PV 的，才算真的换了数据源。
    """
    got = _home_tabs(
        {
            "posts": _three_posts(),
            "data": {
                "view-counts": {
                    "counts": {
                        "2026/08/18/db/aaa": 5,
                        "2026/08/18/db/bbb": 80,
                        "2026/08/18/db/ccc": 200,
                    }
                }
            },
        },
        tmp_path,
    )

    assert got["hot"][0] == "2026/08/18/db/ccc/index.html", got["hot"]
    assert got["hotTabName"] == "近期热门", got["hotTabName"]


@needs_node
def test_the_hot_tab_falls_back_when_the_snapshot_is_missing(tmp_path):
    """快照缺失 → 退回 ``top`` 排序，**并且 tab 改名成「编辑精选」**。

    一个叫「热门」的 tab 装着手动排序的内容，是在骗读者——所以名字要跟着变。
    """
    got = _home_tabs({"posts": _three_posts()}, tmp_path)

    assert got["hotTabName"] == "编辑精选", got["hotTabName"]
    # 回退时按 top 排：bbb(50) 在 ccc(45) 前面。
    assert got["hot"][:2] == [
        "2026/08/18/db/bbb/index.html",
        "2026/08/18/db/ccc/index.html",
    ], got["hot"]


@needs_node
def test_the_hot_tab_falls_back_when_there_is_not_enough_real_data(tmp_path):
    """只有一篇有 PV —— 分不出高下，退回 ``top`` 排序并改名。

    一篇有 PV 的「热门」tab 装的是另一套排序的内容，比没有还糟。
    """
    got = _home_tabs(
        {
            "posts": _three_posts(),
            "data": {"view-counts": {"counts": {"2026/08/18/db/ccc": 7}}},
        },
        tmp_path,
    )

    assert got["hotTabName"] == "编辑精选", got["hotTabName"]
    assert got["hot"][0] == "2026/08/18/db/bbb/index.html", got["hot"]


def test_the_hot_tab_label_is_bound_to_the_computed_name():
    """标签要跟着算出来的名字走——写死「近期热门」的话改名就不算数。"""
    text = HOME_CONTENT.read_text(encoding="utf-8")

    assert "<%= hotTabName %>" in text, "tab 标签没有用算出来的名字"
    assert "近期热门</a>" not in text, "tab 标签的名字写死了"


# --- 3. 抓取器 --------------------------------------------------------------


def _load_fetcher():
    spec = importlib.util.spec_from_file_location("fetch_view_counts", FETCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_fetcher_parses_a_goatcounter_response():
    """喂一个假的 GoatCounter 响应，断言解析出的 path→PV 映射。

    GoatCounter 的 ``/api/v0/stats/hits`` 返回 ``{"hits": [{"path": ..., "count": ...}]}``。
    """
    fetcher = _load_fetcher()
    payload = {
        "hits": [
            {
                "path": "/2026/08/18/db/postgresql/learning-path/03-query-pipeline/",
                "count": 42,
                "event": False,
                "path_id": 7,
            },
            {"path": "/archives/", "count": 3, "event": False, "path_id": 9},
        ],
        "more": False,
        "total": 2,
    }

    counts = fetcher.parse_counts(payload)

    assert counts["2026/08/18/db/postgresql/learning-path/03-query-pipeline"] == 42
    assert counts["archives"] == 3


def test_the_fetcher_normalizes_the_path_the_same_way_the_template_does():
    """快照里的键要和模板算出来的键**一模一样**，否则永远匹配不上。

    hexo 的 ``post.path`` 是 ``2026/08/18/db/aaa/index.html``，
    GoatCounter 记的是 ``/2026/08/18/db/aaa/``——两边都要归一到
    ``2026/08/18/db/aaa``。
    """
    fetcher = _load_fetcher()

    assert fetcher.normalize_path("/2026/08/18/db/aaa/") == "2026/08/18/db/aaa"
    assert fetcher.normalize_path("2026/08/18/db/aaa/index.html") == "2026/08/18/db/aaa"
    assert fetcher.normalize_path("/2026/08/18/db/aaa") == "2026/08/18/db/aaa"


# --- 4. 快照怎么进到站点里 -------------------------------------------------


def test_the_snapshot_file_is_a_valid_counts_object():
    """快照文件必须存在，且长成 ``{"counts": {...}}`` 的样子。"""
    assert SNAPSHOT.is_file(), "缺少 data/view-counts.json"

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert isinstance(data.get("counts"), dict), data


def _load_sync():
    spec = importlib.util.spec_from_file_location("sync_hexo_view_counts", REPO_ROOT / "tools" / "sync-hexo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_snapshot_reaches_the_hexo_data_dir(tmp_path):
    """快照必须被复制到 ``source/_data/``——hexo 才会把它挂到 site.data 上。

    复制不到 ``_data/`` 的话，模板里的 ``site.data['view-counts']``
    永远是 undefined，页面会一直显示不出阅读量。
    """
    sync = _load_sync()

    dest = sync.copy_view_counts_snapshot(src_dir=str(tmp_path))

    assert dest is not None, "快照没有被复制到 source/_data/"
    copied = json.loads(Path(dest).read_text(encoding="utf-8"))
    assert copied == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


# --- 6. 中文路径：GoatCounter 返回百分号编码，hexo 的 post.path 是原始 Unicode ---


def test_the_snapshot_key_matches_the_template_for_a_chinese_path():
    """GoatCounter 的 API 返回的是**百分号编码**的路径，hexo 的 ``post.path``
    是**原始 Unicode**。

    614 篇文章里有 358 篇（58.5%）的路径带中文。不解码的话，一多半的文章
    永远匹配不上——而且是**安静地**不匹配：「近期热门」只排那 42% 的 ASCII
    路径文章，看起来一切正常。
    """
    fetcher = _load_fetcher()

    assert fetcher.normalize_path(
        "/2022/04/13/pgsql/extension/pgsql%E6%89%A9%E5%B1%95/"
    ) == "2022/04/13/pgsql/extension/pgsql扩展"

    # 已经是原始 Unicode 的（有的 GoatCounter 实例存的是解码后的）也不能被改坏
    assert fetcher.normalize_path(
        "/2022/04/13/pgsql/extension/pgsql扩展/"
    ) == "2022/04/13/pgsql/extension/pgsql扩展"


def test_the_snapshot_key_matches_a_template_path_with_a_space():
    """带空格的路径同理（空格在 URL 里编码成 %20）。"""
    fetcher = _load_fetcher()

    assert fetcher.normalize_path("/2026/01/01/db/a%20b/") == "2026/01/01/db/a b"


def test_a_broken_escape_sequence_does_not_explode():
    """路径里出现落单的 % 时，解码要**原样保留**，不能抛异常也不能变成乱码。"""
    fetcher = _load_fetcher()

    assert fetcher.normalize_path("/2026/01/01/100%/") == "2026/01/01/100%"


# --- 7. HTTP 契约：URL、请求头、翻页 ----------------------------------------


class _FakeGoatCounter:
    """一个假的 GoatCounter：记下每次请求长什么样，按剧本回数据。

    真接口没有 key 跑不了，但**请求长什么样**是可以钉死的——URL 里有哪些
    参数、认证头是什么、翻页怎么翻。这些东西错了，刷新就是静悄悄地失败。
    """

    def __init__(self, pages):
        # pages: [{"hits": [...], "more": bool}, ...]
        self.pages = pages
        self.requests = []

    def __enter__(self):
        import http.server
        import threading

        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                import urllib.parse

                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                outer.requests.append(
                    {
                        "path": parsed.path,
                        "query": query,
                        "full": self.path,
                        "authorization": self.headers.get("Authorization"),
                    }
                )
                index = min(len(outer.requests) - 1, len(outer.pages) - 1)
                page = outer.pages[index]
                body = json.dumps(page).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False

    @property
    def api_base(self):
        return "http://127.0.0.1:{}/api/v0".format(self.port)


def _hit(path, count):
    return {"path": path, "count": count, "event": False, "path_id": 1}


def test_the_fetcher_asks_the_api_the_documented_way():
    """请求的 URL、参数、认证头要跟官方 API 文档对得上。"""
    fetcher = _load_fetcher()
    with _FakeGoatCounter([{"hits": [_hit("/a/", 1)], "more": False}]) as fake:
        fetcher.API_BASE = fake.api_base
        counts = fetcher.fetch_counts("SECRET", "growdu")

    assert counts == {"a": 1}, counts
    request = fake.requests[0]
    assert request["path"] == "/api/v0/stats/hits", request
    assert request["authorization"] == "Bearer SECRET", request
    assert request["query"]["path_by_name"] == ["true"], request
    assert request["query"]["limit"] == ["100"], request
    assert request["query"]["start"] and request["query"]["end"], request


def test_the_fetcher_pages_with_offset_instead_of_a_growing_url():
    """翻页用 ``offset``，**不是** ``exclude_paths``。

    exclude_paths 的办法是把已经拿到的路径全塞回下一次请求：600 条路径
    之后 URL 有 8 万多字符，多数服务器和代理在 8–32KB 就掐了——刷新会
    硬失败，而这件事在真接口上跑一次之前谁也发现不了。
    """
    fetcher = _load_fetcher()
    pages = [
        {"hits": [_hit("/p%d/" % i, i) for i in range(100)], "more": True},
        {"hits": [_hit("/p100/", 100)], "more": False},
    ]
    with _FakeGoatCounter(pages) as fake:
        fetcher.API_BASE = fake.api_base
        counts = fetcher.fetch_counts("SECRET", "growdu")

    assert len(counts) == 101, len(counts)
    assert [r["query"].get("offset", ["0"])[0] for r in fake.requests] == ["0", "100"]
    # URL 长度不随页数增长
    assert len(fake.requests[1]["full"]) < len(fake.requests[0]["full"]) + 50


def test_the_fetcher_refuses_to_count_the_same_path_twice():
    """翻页出错（同一页被返回两次）要**报错**，不能悄悄把阅读量翻倍。

    offset 没被服务端认的时候就会这样：每页都是前 100 条。悄悄翻倍比直接
    失败更糟——数字看着合理，其实全错。
    """
    fetcher = _load_fetcher()
    page = {"hits": [_hit("/a/", 5), _hit("/b/", 6)], "more": True}
    with _FakeGoatCounter([page, page]) as fake:
        fetcher.API_BASE = fake.api_base
        with pytest.raises(RuntimeError):
            fetcher.fetch_counts("SECRET", "growdu")


def test_the_fetcher_stops_after_too_many_pages():
    """服务端一直说 more，也不能无限翻下去。"""
    fetcher = _load_fetcher()
    pages = [{"hits": [_hit("/p%d/" % i, i)], "more": True} for i in range(3)]
    with _FakeGoatCounter(pages) as fake:
        fetcher.API_BASE = fake.api_base
        counts = fetcher.fetch_counts("SECRET", "growdu", max_pages=3)

    assert len(fake.requests) == 3, len(fake.requests)
    assert counts == {"p0": 0, "p1": 1, "p2": 2}, counts


def test_the_hot_tab_falls_back_when_every_post_has_the_same_view_count(tmp_path):
    """所有文章的 PV **都一样** → 分不出高下 → 退回 top，并改名。

    计划里写的是「PV 普遍低到**无法区分**」——不是「有几篇有 PV」。
    三篇都是 1 的时候，那个 tab 叫「近期热门」却给不出任何热门。
    """
    got = _home_tabs(
        {
            "posts": _three_posts(),
            "data": {
                "view-counts": {
                    "counts": {
                        "2026/08/18/db/aaa": 1,
                        "2026/08/18/db/bbb": 1,
                        "2026/08/18/db/ccc": 1,
                    }
                }
            },
        },
        tmp_path,
    )

    assert got["hotTabName"] == "编辑精选", got["hotTabName"]
    assert got["hot"][0] == "2026/08/18/db/bbb/index.html", got["hot"]


# --- 8. 刷新工作流不能把好数据悄悄抹掉 ---------------------------------------

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "fetch-view-counts.yml"


def test_the_fetcher_refuses_to_wipe_a_good_snapshot(tmp_path, monkeypatch):
    """抓不到东西时**不能**把快照写成空的。

    空快照 = 侧栏一个🔥都不显示 + 首页那个 tab 改名成「编辑精选」——
    整个功能被悄悄关掉，而 CI 是绿的。API 形状变了、key 过期、站点改名，
    都会让抓取结果变成空。
    """
    out = tmp_path / "view-counts.json"
    out.write_text(json.dumps({"counts": {"a": 1}}), encoding="utf-8")

    fetcher = _load_fetcher()
    monkeypatch.setenv("GOATCOUNTER_API_KEY", "SECRET")
    monkeypatch.setattr(fetcher, "fetch_counts", lambda *a, **k: {})

    rc = fetcher.main(["--out", str(out)])

    assert rc != 0, "空快照被写进去了"
    assert json.loads(out.read_text(encoding="utf-8"))["counts"] == {"a": 1}, (
        "原来好的数据被覆盖了"
    )


def test_the_fetcher_refuses_a_snapshot_that_lost_most_of_its_paths(tmp_path, monkeypatch):
    """路径数**骤减**也是坏信号：形状变了的话，会安静地少掉一大半。"""
    out = tmp_path / "view-counts.json"
    old = {"p%d" % i: i for i in range(100)}
    out.write_text(json.dumps({"counts": old}), encoding="utf-8")

    fetcher = _load_fetcher()
    monkeypatch.setenv("GOATCOUNTER_API_KEY", "SECRET")
    monkeypatch.setattr(fetcher, "fetch_counts", lambda *a, **k: {"p0": 1})

    rc = fetcher.main(["--out", str(out)])

    assert rc != 0, "只剩 1 条的快照被写进去了"
    assert json.loads(out.read_text(encoding="utf-8"))["counts"] == old


def test_the_refresh_workflow_is_pinned_to_master_and_runs_the_tests():
    """工作流直接推 master，所以要钉死在 master 上，推之前先跑测试。

    不钉的话，从别的分支手动触发这个工作流，那个分支上的提交会被
    rebase 到 master 再推上去。
    """
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ref: master" in text, "checkout 没有钉在 master 上"
    assert "pytest" in text, "推 master 之前没有跑测试"
    assert "workflow_dispatch" in text, "只剩自动触发就不是「手动刷新」了"
