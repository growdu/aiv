"""首屏搜索框要用 78KB 的精简索引，别拖 13.5MB 的全文索引。

**为什么**：导航栏那个搜索弹窗（``_partial/search.ejs``）在**首次击键**时
fetch ``search.json``——实测 13,490,267 字节，线上 gzip 后 4,202,343 字节 /
0.45s。首屏搜索框如果复用它，读者打进第一个字母就要等 4.2MB。

**代价说清楚**：首屏搜索只匹配**标题和分类**，不搜正文。全站全文搜索仍在
顶部导航里（那才是需要全文索引的地方）。阶段 0 已经造好了精简索引
``search-lite.json``（约 80KB，每条只有 title / url / cat），404 页在用。

**这里断言的是行为**：真的把首屏那段 JS 拿�� node 里跑一遍——输入一个词，
结果列表里要出现那篇文章；超过 8 条要截断；回车要跳第一条。
只检查模板里有没有 ``id``、有没有 ``search-lite.json`` 字样，挡不住
「fetch 的是对的、但渲染是空的」这种坏法。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME_HERO = REPO / "themes" / "matery" / "layout" / "_partial" / "home-hero.ejs"
SYNC_SCRIPT = REPO / "tools" / "sync-hexo.py"
NODE = shutil.which("node")

#: 首屏搜索那段 JS 在模板里的标记——patcher 往同一个文件里注入打字机，
#: 光靠「取第一个 <script>」会取错。
SEARCH_MARKER = "<!-- HOME-SEARCH -->"

DRAFT = "---\ntitle: {title}\n---\n\n{body}\n"

CORPUS = {
    "db/postgresql.md": DRAFT.format(title="PostgreSQL 数据库", body="数据库正文。"),
    "cluster/paxos.md": DRAFT.format(title="Paxos 共识", body="共识协议正文。"),
    "life/intro.md": DRAFT.format(title="编程之路", body="随笔。"),
}


def _read(path: Path) -> str:
    assert path.is_file(), "找不到 {}".format(path)
    return path.read_text(encoding="utf-8")


def _search_script() -> str:
    """把首屏搜索那段 JS 从模板里抠出来。"""
    template = _read(HOME_HERO)

    assert SEARCH_MARKER in template, (
        "home-hero.ejs 里没有 {} —— 找不到首屏搜索的那段 JS".format(SEARCH_MARKER)
    )
    tail = template.split(SEARCH_MARKER, 1)[1]
    m = re.search(r"<script>(.*?)</script>", tail, re.S)
    assert m, "{} 后面没有 <script>".format(SEARCH_MARKER)
    return m.group(1)


# --- 静态契约 ---------------------------------------------------------------


def test_the_hero_search_box_has_a_stable_id():
    """首屏搜索框有 ``id="homeSearch"``。

    ``id`` 是这段 JS 和主题里的样式、以及将来别的脚本唯一的挂钩点。
    """
    hero = _read(HOME_HERO)

    assert 'id="homeSearch"' in hero, "首屏搜索框没有 id=\"homeSearch\""


def test_the_hero_search_uses_the_lite_index():
    """首屏搜索抓的是 ``/search-lite.json``，**不是** ``/search.json``。

    这条是防回归的关键：改回全文索引，第一次击键就是 4.2MB —— 而且
    不会报错，只是慢，测试必须挡住它。
    """
    script = _search_script()

    assert "/search-lite.json" in script, "首屏搜索没有抓精简索引"
    assert "/search.json" not in script, (
        "首屏搜索抓的是全文索引（13.5MB）——第一次击键不该下这个"
    )


def test_the_hero_search_renders_title_and_category():
    """结果里要同时有**标题**和**分类**。

    只显示标题：读者搜「数据库」得到一串名字，分不清哪篇是哪篇。
    """
    script = _search_script()

    assert re.search(r"\.title", script), "首屏搜索没有渲染标题"
    assert re.search(r"\.cat", script), "首屏搜索没有渲染分类"


def test_the_search_hint_says_what_it_can_search():
    """首屏搜索框下面要有一句说明：只按标题搜，全文搜在顶部导航。

    读者以为搜不到正文，是因为没人告诉他。
    """
    hero = _read(HOME_HERO)

    assert "全文搜索" in hero, "首屏搜索缺一句「全文搜索用顶部导航」的说明"


# --- 精简索引本身的字段 -----------------------------------------------------


def test_the_lite_index_has_the_fields_the_search_needs(tmp_path):
    """精简索引每条都要有 title / url / cat。

    索引是 sync 生成的（``source/`` 是 gitignore 的，CI 里没有现成文件），
    所以这里造一个临时语料跑一遍 sync，看它真的写出这三个字段。
    """
    for rel, text in CORPUS.items():
        path = tmp_path / "docs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    shutil.copy(REPO / "_config.matery.yml", tmp_path / "_config.matery.yml")

    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "sync-hexo.py 失败：\n{}\n{}".format(
        result.stdout, result.stderr
    )

    index = json.loads(
        (tmp_path / "source" / "search-lite.json").read_text(encoding="utf-8")
    )

    assert index, "精简索引是空的"
    for entry in index:
        assert set(entry) == {"title", "url", "cat"}, entry
        assert entry["title"], entry
        assert entry["url"].startswith("/"), entry


# --- 真的在 node 里跑一遍首屏那段 JS -----------------------------------------


HARNESS = r"""
const fs = require('fs');
const code = fs.readFileSync(process.argv[1], 'utf8');
const DATA = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const QUERY = process.argv[3];

const handlers = {};
const input = {
    value: '',
    addEventListener: function (t, f) { handlers[t] = f; }
};
const list = {
    innerHTML: '',
    hidden: true,
    querySelector: function (sel) {
        if (sel !== 'a') return null;
        const m = /href="([^"]+)"/.exec(this.innerHTML);
        if (!m) return null;
        return { getAttribute: function (n) { return n === 'href' ? m[1] : null; } };
    }
};

global.document = {
    getElementById: function (id) {
        if (id === 'homeSearch') return input;
        if (id === 'homeSearchResults') return list;
        return null;
    }
};
let fetched = null;
global.fetch = function (url) {
    fetched = url;
    return Promise.resolve({ json: function () { return Promise.resolve(DATA); } });
};
global.window = { location: { href: '' } };

(async function () {
    eval(code);
    if (!handlers.input) { console.error('NO_INPUT_HANDLER'); process.exit(3); }
    input.value = QUERY;
    handlers.input();
    // 等过 200ms 的防抖 + 一次 promise 兑现
    await new Promise(function (r) { setTimeout(r, 400); });
    const beforeEnter = { html: list.innerHTML, fetched: fetched };
    if (handlers.keydown) {
        handlers.keydown({ key: 'Enter', preventDefault: function () {} });
    }
    console.log(JSON.stringify({
        html: beforeEnter.html,
        fetched: beforeEnter.fetched,
        href: global.window.location.href
    }));
})();
"""


def _run_search(tmp_path: Path, data, query: str):
    """把首屏那段 JS 放进 node 跑一遍，返回它渲染出来的结果。"""
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    script_path = tmp_path / "home-search.js"
    script_path.write_text(_search_script(), encoding="utf-8")

    data_path = tmp_path / "search-lite.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [NODE, "-e", HARNESS, str(script_path), str(data_path), query],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "首屏搜索的 JS 抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


INDEX = [
    {"title": "PostgreSQL 数据库内核", "url": "/2026/08/18/db/postgresql/", "cat": "db"},
    {"title": "Paxos 共识算法", "url": "/2026/08/18/cluster/paxos/", "cat": "cluster"},
    {"title": "查询管线全景", "url": "/2026/08/18/db/postgresql/learning-path/", "cat": "db"},
]


def test_typing_in_the_hero_search_finds_the_article(tmp_path):
    """输入一个词，结果列表里要出现那篇文章（标题 + 分类 + 链接）。

    这条测试在 node 里跑首屏**自己**的那段 JS，不是把逻辑抄一份到 Python
    里 —— 「fetch 抓对了、但结果渲染不出来」这类坏法只有真跑才现形。
    """
    payload = _run_search(tmp_path, INDEX, "数据库")

    assert payload["fetched"].endswith("/search-lite.json"), payload["fetched"]
    assert "PostgreSQL 数据库内核" in payload["html"], payload["html"]
    assert "/2026/08/18/db/postgresql/" in payload["html"], payload["html"]
    assert "db" in payload["html"], payload["html"]


def test_the_hero_search_matches_the_category_too(tmp_path):
    """分类名也能搜到 —— 「db」能搜出所有数据库文章。"""
    payload = _run_search(tmp_path, INDEX, "db")

    assert "PostgreSQL 数据库内核" in payload["html"], payload["html"]
    assert "Paxos 共识算法" not in payload["html"], payload["html"]


def test_the_hero_search_ignores_case(tmp_path):
    """大小写不敏感 —— ``postgresql`` 和 ``PostgreSQL`` 要能搜到同一篇。"""
    payload = _run_search(tmp_path, INDEX, "postgresql")

    assert "PostgreSQL 数据库内核" in payload["html"], payload["html"]


def test_the_hero_search_shows_at_most_eight_results(tmp_path):
    """最多 8 条。

    首屏不是文章列表——列 30 条会把首屏撑回折线以下，那正是这次要治的病。
    """
    many = [
        {"title": "数据库 第 {} 篇".format(i), "url": "/2026/08/18/db/p{}/".format(i), "cat": "db"}
        for i in range(12)
    ]
    payload = _run_search(tmp_path, many, "数据库")

    assert payload["html"].count('href="') == 8, payload["html"]


def test_pressing_enter_opens_the_first_match(tmp_path):
    """回车跳第一条 —— 搜到了还要再点一次，是多余的力气。"""
    payload = _run_search(tmp_path, INDEX, "数据库")

    assert payload["href"] == "/2026/08/18/db/postgresql/", payload["href"]


def test_a_query_that_matches_nothing_says_so(tmp_path):
    """搜不到也得有个说法 —— 空列表等于坏掉。"""
    payload = _run_search(tmp_path, INDEX, "这个词谁也搜不到")

    assert payload["html"].strip(), "搜不到时结果列表是空的"
