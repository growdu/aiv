"""mermaid 围栏的守卫：```mermaid 变成页面上的 ``<div class="mermaid">``。

**背景**
------
mermaid 是**客户端**渲染的：页面里得有一个 ``<div class="mermaid">``，
浏览器端的 mermaid 库才认得它。所以围栏必须在渲染时变成 div。

**为什么有两道过滤器**
----------------------
hexo 核心有个 ``backtick_code_block`` 过滤器，它在 ``before_post_render``
阶段把围栏里的代码**先高亮成 HTML**（站点配置了 ``syntax_highlighter: prismjs``）。
于是围栏到 markdown 渲染器手里的时候已经不是围栏了——是一段
``<pre><code class="language-mermaid">``。

所以站点的 ``scripts/mermaid.js`` 有两道：

1. ``before_post_render``：围栏还在的时候换成 div（关掉服务端高亮时走这条）；
2. ``after_post_render``：剩下的 ``<pre><code class="language-mermaid">``
   换成 div（开着服务端高亮时走这条——**现在走的是这条**）。

**代码块不许被误伤**：普通代码块（``python``、``bash``……）不能被换成 div，
里面的内容一个字都不许改。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from paths import SITE

SITE_ROOT = SITE
SCRIPT = SITE_ROOT / "scripts" / "mermaid.js"

#: 在 node 里把站点的过滤器跑一遍。stub 出来的 hexo 只提供
#: `extend.filter.register`——过滤器自己只用这一样。
HARNESS = """
const fs = require('fs');
const filters = {};
global.hexo = {
  extend: {
    filter: {
      register: (name, fn) => { filters[name] = fn; }
    }
  }
};
require(process.argv[2]);
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
let content = payload;
if (filters['before_post_render']) {
  content = filters['before_post_render']({ content: content }).content;
}
if (filters['after_post_render']) {
  content = filters['after_post_render']({ content: content }).content;
}
process.stdout.write(content);
"""


@pytest.fixture(scope="module")
def render(tmp_path_factory):
    """把一段 markdown 过一遍站点的过滤器，返回渲染后的内容。"""
    harness = tmp_path_factory.mktemp("mermaid") / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")

    def _render(content: str) -> str:
        payload = tmp_path_factory.mktemp("mermaid-in") / "in.json"
        payload.write_text(json.dumps(content), encoding="utf-8")
        result = subprocess.run(
            ["node", str(harness), str(SCRIPT), str(payload)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"过滤器跑挂了：{result.stderr}"
        return result.stdout

    return _render


def test_a_mermaid_fence_becomes_a_mermaid_div(render):
    out = render("```mermaid\ngraph LR\n  A --> B\n```\n")
    assert '<div class="mermaid">' in out, out
    assert "graph LR" in out


def test_the_diagram_source_is_escaped(render):
    """div 里塞的是原始 HTML——内容要先转义，浏览器再还原成字符。"""
    out = render('```mermaid\ngraph LR\n  A["<标签>"] --> B\n```\n')
    assert "&lt;标签&gt;" in out, out
    assert "<标签>" not in out, out


def test_the_pre_code_form_is_converted_too(render):
    """服务端高亮先把它变成了 ``<pre><code class="language-mermaid">``——
    这一路也得认。"""
    out = render(
        '<pre class="language-mermaid" data-language="mermaid">'
        '<code class="language-mermaid">graph LR\n  A --&gt; B</code></pre>'
    )
    assert '<div class="mermaid">' in out, out
    assert "language-mermaid" not in out, out


def test_ordinary_code_blocks_are_left_alone(render):
    """普通代码块不许被当成 mermaid。"""
    source = "```python\nprint('这不是 mermaid')\n```\n"
    out = render(source)
    assert 'class="mermaid"' not in out, out
    assert "这不是 mermaid" in out, out


def test_text_outside_code_blocks_is_untouched(render):
    source = "这一段是正文，里面有 `mermaid` 这个词。\n"
    assert render(source) == source


def test_a_fence_without_a_language_is_not_mermaid(render):
    out = render("```\n就是一段代码\n```\n")
    assert 'class="mermaid"' not in out, out
