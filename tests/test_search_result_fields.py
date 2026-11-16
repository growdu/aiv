"""站内搜索的渲染不能因为字段形态不同而崩掉。

**病根**：MiniSearch 的 ``saveStoredFields`` 走的也是 ``extractField``。
主题在 ``search.ejs`` 里给 MiniSearch 配了一个自定义 ``extractField``
（数组先 join 成字符串再喂给分词器），于是**存下来的** ``categories`` /
``tags`` 也是那个字符串，而不是 ``search.json`` 里的数组。

渲染时却按数组调 ``.join(' · ')``::

    var cats = (r.categories && r.categories.length) ? r.categories.join(' · ') : '';

字符串也有 ``length``，所以那句守卫挡不住——真跑起来是::

    TypeError: r.categories.join is not a function

线上唯一的主动检索入口就这么 100% 失效了。

这条测试**真的跑一遍主题里的那段 JS**：把 ``search.ejs`` 的内联脚本抠出来，
配上 MiniSearch 与几个 DOM 替身，在 node 里喂一条搜索结果，断言渲染完成、
且分类出现在结果里。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH_EJS = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "search.ejs"
MINISEARCH_JS = (
    REPO_ROOT / "themes" / "matery" / "source" / "libs" / "minisearch" / "minisearch.min.js"
)

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node 不在 PATH 上，这条测试跑不了主题里的 JS"
)


#: 把 search.ejs 的内联脚本抠出来，在 node 里配上替身跑一遍。
#:
#: 替身只补主题用到的那几个：jQuery 的 ready 与 ajax、两个 DOM 节点、
#: MiniSearch 本体。搜索词从输入框的 value 里取（模板里 handler 绑在
#: $input 上），所以这里给替身节点塞一个 value 再触发 input 事件。
HARNESS = r"""
const fs = require('fs');

const ejs = fs.readFileSync(process.argv[1], 'utf8');
const match = ejs.match(/<script type="text\/javascript">([\s\S]*?)<\/script>/);
if (!match) { console.error('NO_INLINE_SCRIPT'); process.exit(2); }
// EJS 标签（url_for 之类）在浏览器里由 hexo 填；这里换成占位符——
// ajax 的 url 替身不关心。
const code = match[1].replace(/<%[\s\S]*?%>/g, 'EJS_PLACEHOLDER');

const mod = require(process.argv[2]);
global.MiniSearch = mod.default || mod;

const DOCS = [
    {
        title: 'PostgreSQL 数据库',
        url: '/2024/01/01/db/postgresql/',
        content: '<p>正文里提到 WAL 与事务。</p>',
        categories: ['数据库', 'PostgreSQL'],
        tags: ['数据库', 'PostgreSQL']
    }
];

let inputHandlers = [];
const inputEl = {
    value: '',
    addEventListener: function (type, fn) { if (type === 'input') inputHandlers.push(fn); }
};
const resultEl = { innerHTML: '' };

global.document = {
    getElementById: function (id) {
        if (id === 'searchInput') return inputEl;
        if (id === 'searchResult') return resultEl;
        return null;
    }
};

global.$ = function (arg) { if (typeof arg === 'function') arg(); };
$.ajax = function (opts) {
    opts.success(DOCS.map(function (d) { return Object.assign({ id: d.url }, d); }));
};

eval(code);

if (!inputHandlers.length) { console.error('NO_INPUT_HANDLER'); process.exit(3); }
inputEl.value = 'PostgreSQL';
inputHandlers[0]();

console.log(JSON.stringify({ html: resultEl.innerHTML }));
"""


def run_node(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, "-e", script, *[str(a) for a in args]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )


def test_the_inline_search_script_is_still_there():
    """先确认这条测试有东西可测：主题里的内联脚本没被挪走。

    没有这一条，脚本被改名或挪走时，测试会以「脚本不存在」的方式失败——
    失败原因和「搜索崩了」是两回事，不能混。
    """
    text = SEARCH_EJS.read_text(encoding="utf-8")

    assert '<script type="text/javascript">' in text
    assert "r.categories" in text


def test_minisearch_stores_the_extracted_field_not_the_original_array():
    """根因：MiniSearch 存下来的字段是 ``extractField`` 的输出。

    这是库的行为（``saveStoredFields`` 用同一个 extractField 取值），
    与主题无关：所以「存下来的是字符串」这件事不会因为改了主题而变，
    渲染端必须按这个事实来写。
    """
    script = r"""
const mod = require(process.argv[1]);
const MiniSearch = mod.default || mod;
const idx = new MiniSearch({
    idField: 'id',
    fields: ['title', 'categories'],
    storeFields: ['title', 'categories'],
    extractField: function (doc, field) {
        var v = doc[field];
        if (Array.isArray(v)) return v.join(' ');
        return v == null ? '' : String(v);
    }
});
idx.addAll([{ id: '1', title: 't', categories: ['数据库'] }]);
const stored = idx.search('t')[0].categories;
console.log(JSON.stringify({ type: typeof stored, value: stored }));
"""
    result = run_node(script, MINISEARCH_JS)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["type"] == "string", payload
    assert payload["value"] == "数据库", payload


def test_search_rendering_survives_a_string_field():
    """红：分类字段是字符串时，渲染必须完成，不能抛 TypeError。

    这条测试跑的是**主题里那段 JS 本身**——不是把逻辑抄一份到 Python 里
    再测一遍。抄一份的话，改了主题而测试还在绿，等于没测。
    """
    result = run_node(HARNESS, SEARCH_EJS, MINISEARCH_JS)

    assert result.returncode == 0, (
        "搜索渲染抛异常了：\n{}\n{}".format(result.stdout, result.stderr)
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    html = payload["html"]

    assert "PostgreSQL 数据库" in html, html
    # 分类与标签是**数组**，渲染时要用 ' · ' 连接——这一条断的是「分隔符
    # 还在不在」。只断言「数据库」三个字是废的：标题里就有这三个字，
    # 分类整个没渲染出来它也照样过。
    assert '<span class="search-result-meta">数据库 · PostgreSQL</span>' in html, html
    assert "数据库 · PostgreSQL" in html, html
    assert "is not a function" not in result.stderr, result.stderr


def test_search_rendering_survives_a_post_without_categories():
    """没有分类、没有标签的文章也得渲染得出来。

    这条不是红的（空数组 join 出来是空串，本来就不崩），但它守着
    「渲染端不许假设字段长什么样」这条底线：修 B1 的人很容易把
    守卫写成只认字符串，那样的文章就会重新变成空白结果。
    """
    script = HARNESS.replace(
        "categories: ['数据库', 'PostgreSQL'],\n        tags: ['数据库', 'PostgreSQL']",
        "categories: [],\n        tags: []",
    )
    result = run_node(script, SEARCH_EJS, MINISEARCH_JS)

    assert result.returncode == 0, (
        "搜索渲染抛异常了：\n{}\n{}".format(result.stdout, result.stderr)
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "PostgreSQL 数据库" in payload["html"], payload["html"]
