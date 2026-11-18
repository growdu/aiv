"""首页「编辑推荐」那一格装的是**策展清单**里的那几篇。

**为什么要有这条**：``data/featured.json`` 里 ``featured`` 那组是作者维护的
策展清单（跟首屏那三篇代表作同一个文件），但它一度**谁都不读**——
「编辑推荐」tab 排的是 ``top >= 70`` 这个阈值，跟策展毫无关系。
作者改了清单，页面纹丝不动，而构建和测试都不会红。

这里在 node 里跑 ``home-content.ejs`` 里那段算 tab 数据的代码（假 site），
断言那一格装的**就是**清单里那几篇——顺序也按清单来。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "platforms" / "blog" / "site"
HOME_CONTENT = SITE / "themes" / "matery" / "layout" / "_partial" / "home-content.ejs"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="这台机器上没有 node")


def _home_script() -> str:
    """home-content.ejs 里那个算 tab 数据的 ``<% ... %>`` 块。"""
    text = HOME_CONTENT.read_text(encoding="utf-8")
    for block in re.findall(r"<%(.*?)%>", text, re.S):
        if "var allPosts" in block:
            return block
    raise AssertionError("home-content.ejs 里找不到算 tab 数据的代码块")


# 一个只吃 node 自带能力的假 site：够跑那段代码，不碰 node_modules
# （site-guard 那条 CI 只装 pytest）。
HARNESS = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[1], 'utf8');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const posts = spec.posts || [];
const site = {
  posts: {
    length: posts.length,
    forEach: function (fn) { posts.forEach(fn); },
    toArray: function () { return posts.slice(); }
  },
  categories: {length: 0},
  data: spec.data || {}
};
const wordcount = function (s) { return String(s).length; };
const theme = {time: {year: 2020, month: 1, date: 1}};
const fn = new Function('site', 'wordcount', 'theme', script + '\n' +
  'return {featured: (typeof featured === "undefined" ? null :' +
  ' featured.map(function (p) { return p.path; }))};');
process.stdout.write(JSON.stringify(fn(site, wordcount, theme)));
"""


def _featured_paths(spec: dict, tmp_path: Path) -> list:
    script_path = tmp_path / "home-script.js"
    script_path.write_text(_home_script(), encoding="utf-8")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(script_path), str(payload_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "node 那段脚本抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    return json.loads(result.stdout)["featured"]


def _post(slug: str, top: int = 0, day: int = 1) -> dict:
    return {
        "_id": slug,
        "path": "2026/08/{:02d}/{}/".format(day, slug),
        "title": slug,
        "top": top,
        "date": day,
    }


@needs_node
def test_the_featured_tab_shows_the_curated_list(tmp_path):
    """「编辑推荐」装的就是 ``data/featured.json`` 里 ``featured`` 那几篇。

    两条线索一起断：
      - 清单里的 ``db/ccc`` 分数很低（5），它**在**那一格里 —— 说明不是阈值挑的；
      - 分数很高的 ``db/aaa``（90）**不在**那一格里 —— 说明不是阈值挑的。
    """
    posts = [
        _post("db/aaa", top=90, day=1),
        _post("db/bbb", top=85, day=2),
        _post("db/ccc", top=5, day=3),
        _post("db/ddd", top=80, day=4),
    ]
    spec = {
        "posts": posts,
        "data": {"featured": {"featured": ["db/ccc", "db/ddd"]}},
    }

    assert _featured_paths(spec, tmp_path) == [
        "2026/08/03/db/ccc/",
        "2026/08/04/db/ddd/",
    ]


@needs_node
def test_the_featured_tab_keeps_the_order_of_the_curated_list(tmp_path):
    """清单的**顺序**是作者定的（谁先谁后），不能被 top 分数重排。"""
    posts = [
        _post("db/aaa", top=90, day=1),
        _post("db/bbb", top=10, day=2),
    ]
    spec = {
        "posts": posts,
        "data": {"featured": {"featured": ["db/bbb", "db/aaa"]}},
    }

    assert _featured_paths(spec, tmp_path) == [
        "2026/08/02/db/bbb/",
        "2026/08/01/db/aaa/",
    ]


@needs_node
def test_the_featured_tab_falls_back_to_the_old_threshold_without_a_list(tmp_path):
    """清单没抄进 ``source/_data/`` 时退回旧阈值，不能那一格空着。

    ``site.data.featured`` 是 undefined 的场合：sync 没跑、或者清单还没建。
    """
    posts = [
        _post("db/aaa", top=90, day=1),
        _post("db/bbb", top=30, day=2),
    ]

    assert _featured_paths({"posts": posts, "data": {}}, tmp_path) == [
        "2026/08/01/db/aaa/"
    ]


@needs_node
def test_a_curated_slug_that_points_at_nowhere_is_skipped(tmp_path):
    """清单里有条 slug 对不上文章，就跳过那一条，别把整格拖下水。

    ``db/ccc`` 的分数很低（5）——所以这一格**只可能**是清单给的，
    不是阈值给的。
    """
    posts = [_post("db/ccc", top=5, day=3)]
    spec = {
        "posts": posts,
        "data": {"featured": {"featured": ["db/gone", "db/ccc"]}},
    }

    assert _featured_paths(spec, tmp_path) == ["2026/08/03/db/ccc/"]
