"""404 页的搜索得真的能搜到东西。

**病根**：404 页的搜索框 ``fetch('/search.xml')``，但站点里根本没有
``search.xml``——hexo-generator-searchdb 出的是 ``search.json``。于是这个
fetch 永远失败，永远走 catch 分支跳 Google site: 搜索（国内不可用）。

等于 404 页**没有搜索**。而 404 页是站内链接失效时唯一的导流出口。

**为什么不用 ``search.json``**：那是全文索引，13.5 MB。让一个「页面不存在」
的页面下载 13.5 MB 才能搜一个词，是把「搜索等于没有」换成「搜索慢到等于
没有」。所以另出一个精简索引 ``search-lite.json``——每篇只有
title / url / cat，几十 KB，404 页拿它做标题匹配。

代价说清楚：404 页的搜索只匹配**标题和分类**，不搜正文。站内完整搜索仍在
首页（那里有 MiniSearch 全文索引）。

这条测试除了看产物，还**真的在 node 里跑一遍 404 页的那段 JS**：
喂一个搜索词，断言结果列表里出现了匹配的文章。
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "tools" / "sync-hexo.py"
NODE = shutil.which("node")


def build_corpus(root: Path, drafts) -> None:
    for rel, text in drafts.items():
        path = root / "docs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    shutil.copy(REPO_ROOT / "_config.matery.yml", root / "_config.matery.yml")


def run_sync(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "sync-hexo.py 失败：\n{}\n{}".format(
        result.stdout, result.stderr
    )


DRAFT = "---\ntitle: {title}\n---\n\n{body}\n"

#: 标题里带引号——10 篇文章的标题里有引号（``AI 能"创造"吗？``）。
QUOTED_TITLE = 'AI 能"创造"吗？——从一团噪声到一幅画'

CORPUS = {
    "db/postgresql.md": DRAFT.format(title="PostgreSQL 数据库", body="数据库正文。"),
    "cluster/paxos.md": DRAFT.format(title="Paxos 共识", body="共识协议正文。"),
    "life/intro.md": DRAFT.format(title="编程之路", body="随笔。"),
    "ai/creative.md": DRAFT.format(title=QUOTED_TITLE, body="绘画正文。"),
}


def read_lite_index(root: Path):
    path = root / "source" / "search-lite.json"
    assert path.exists(), "sync 没有写出 source/search-lite.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- 产物 ------------------------------------------------------------------


def test_sync_writes_a_lightweight_search_index(tmp_path):
    """精简索引要有 title / url / cat 三样，URL 是 permalink 形态。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    index = read_lite_index(tmp_path)

    assert index, "精简索引是空的"
    for entry in index:
        assert set(entry) == {"title", "url", "cat"}, entry
        assert entry["url"].startswith("/2024/01/01/"), entry
        assert entry["url"].endswith("/"), entry


def test_the_index_covers_every_publishable_post(tmp_path):
    """每一篇文章都得在索引里——漏一篇就是那个词搜不到。

    ``blog/`` / ``tools/`` / ``page/`` 这些是站点自己的元文档，不算文章
    （跟 ``recent-posts.json`` 的口径一致）。
    """
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    index = read_lite_index(tmp_path)
    urls = {entry["url"] for entry in index}

    assert urls == {
        "/2024/01/01/db/postgresql/",
        "/2024/01/01/cluster/paxos/",
        "/2024/01/01/life/intro/",
        "/2024/01/01/ai/creative/",
    }, urls


def test_the_404_page_no_longer_looks_for_a_file_that_does_not_exist(tmp_path):
    """``search.xml`` 从 404 页里消失。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    page = (tmp_path / "source" / "404.html").read_text(encoding="utf-8")

    # 只看代码，不看注释——那段 JS 里留了注释说明「当年就是去 fetch 一个不存在的
    # 文件」，注释里当然会出现 search.xml。断言要管的是**代码**还会不会去取它。
    code = re.sub(r"^\s*//.*$", "", page, flags=re.M)

    assert "search.xml" not in code, "404 页还在去取那个不存在的文件"
    assert "DOMParser" not in code, "还在按 Atom feed 解析 search.xml"
    assert "search-lite.json" in code


# --- 真的跑一遍 404 页的那段 JS -------------------------------------------

HARNESS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) { console.error('NO_SCRIPT'); process.exit(2); }
const code = match[1];

const DATA = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

const handlers = {};
const els = {
    'search-form': { addEventListener: function (t, f) { handlers[t] = f; } },
    'q': { value: process.argv[3] },
    'recent-list': { innerHTML: '' }
};
const divider = { textContent: '最近发布' };

global.document = {
    getElementById: function (id) { return els[id] || null; },
    querySelector: function () { return divider; }
};
let fetched = null;
global.fetch = function (url) {
    fetched = url;
    return Promise.resolve({ json: function () { return Promise.resolve(DATA); } });
};

(async function () {
    eval(code);
    if (!handlers.submit) { console.error('NO_SUBMIT_HANDLER'); process.exit(3); }
    await handlers.submit({ preventDefault: function () {} });
    await new Promise(function (r) { setTimeout(r, 100); });
    console.log(JSON.stringify({
        html: els['recent-list'].innerHTML,
        fetched: fetched,
        divider: divider.textContent
    }));
})();
"""


def run_404_script(root: Path, query: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            NODE,
            "-e",
            HARNESS,
            str(root / "source" / "404.html"),
            str(root / "source" / "search-lite.json"),
            query,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
    )


def test_searching_on_the_404_page_finds_the_article(tmp_path):
    """红→绿：404 页的搜索框输入一个词，结果列表里得有那篇文章。

    这条测试在 node 里跑 404 页**自己的**那段 JS（不是抄一份逻辑到
    Python 里），所以「fetch 了一个不存在的文件」「结果渲染不出来」
    这类问题都会在这里现形。
    """
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    result = run_404_script(tmp_path, "PostgreSQL")

    assert result.returncode == 0, "404 页的搜索抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert payload["fetched"].endswith("/search-lite.json"), payload["fetched"]
    assert "PostgreSQL 数据库" in payload["html"], payload["html"]
    assert "/2024/01/01/db/postgresql/" in payload["html"], payload["html"]


def test_a_query_that_matches_nothing_says_so(tmp_path):
    """搜不到也得有个说法——空列表等于坏掉。"""
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    result = run_404_script(tmp_path, "这个词谁也搜不到")

    assert result.returncode == 0, "404 页的搜索抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert payload["html"].strip(), "搜不到时结果列表是空的"


def test_the_lite_index_is_small_enough_to_fetch_from_an_error_page(tmp_path):
    """精简索引的意义就在于小。13.5 MB 的全文索引不该出现在 404 页上。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    size = (tmp_path / "source" / "search-lite.json").stat().st_size

    assert size < 200 * 1024, "精简索引有 {} 字节，太大了".format(size)


def test_a_title_containing_quotes_survives_the_index(tmp_path):
    """标题里有引号时，索引里的标题不能被截断。

    **病根**：生成出来的 front matter 是 ``title: "AI 能\\"创造\\"吗？"``
    （引号被 YAML 转义过）。按 ``[^"']+`` 取值会在**第一个**引号处停下，
    10 篇文章的标题在索引里只剩「AI 能\\」——404 页上搜这些文章搜不到。
    """
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    index = read_lite_index(tmp_path)
    titles = {entry["title"] for entry in index}

    assert QUOTED_TITLE in titles, sorted(titles)


def test_the_result_count_counts_every_match_not_only_the_ones_shown(tmp_path):
    """「搜索结果 (N)」里的 N 要是**匹配的总数**，不是显示出来的条数。

    404 页一次只列 10 条。如果 N 写的是列出来的条数，搜「数据库」命中 25 篇
    却显示「搜索结果 (10)」——读者以为只有 10 篇，越界的 15 篇**消失得无声无息**。
    """
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    corpus = {
        "db/p{:02d}.md".format(i): DRAFT.format(
            title="数据库 第 {} 篇".format(i), body="正文。"
        )
        for i in range(12)
    }
    build_corpus(tmp_path, corpus)
    run_sync(tmp_path)

    result = run_404_script(tmp_path, "数据库")

    assert result.returncode == 0, "404 页的搜索抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert "12" in payload["divider"], payload["divider"]
    assert "10" in payload["divider"], payload["divider"]
