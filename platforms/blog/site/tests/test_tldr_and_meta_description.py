"""自动生成的 description 该怎么用，不该由谁说了算。

**背景**：sync 从文章的编辑履历表（``| 编写人 | 编写内容 | 编写时间 |``）
里抽出一句话写进 front matter 的 ``description``——那是履历表的「编写内容」
列，说的是「这篇文章讲什么」，但**不总是**：有些格子写的是「理顺结构与定位，
修正错误写法」这种**编辑动作**，不是文章摘要。

两个下游会把它当文章摘要显示出来：

1. ``platforms/blog/site/themes/matery/layout/_partial/post-tldr.ejs`` 的 TL;DR 框
2. ``head.ejs`` 的 ``og:description`` / ``twitter:description``

**这条契约在 2026-11-16 被反转了（阶段 1 的 Task 4）。**

原来：TL;DR 框只认作者写的 ``tldr`` / ``summary``，description 不进框。
理由是那时候 description 是履历句——84 篇文章会凭空多出一个装履历句的
TL;DR 框，其中 11 篇正文开头本来就有自己的 ``> **TL;DR**`` 引用块，同一个
页面两个 TL;DR。

现在：Task 5 把那 85 条履历句换成**真摘要**之后，理由就不成立了；而且
不反转的话，Task 5 的成果读者一样看不见（85 条新摘要一条都不露脸）。
所以 TL;DR 框改成 ``page.tldr || page.summary || page.description``——
**作者显式写的永远优先**，description 只是最后一档。

**og / twitter description**：那里**要**用 description（规格 §4.1 就是这么
定的），但不能转义两次——``<%= %>`` 本来就会转义 HTML，手工再
``.replace(/"/g, '&quot;')`` 一次，页面里就变成 ``&amp;quot;``，
读者看到的是 ``&quot;``。

**``<meta name="description">``**（搜索结果和链接预览里显示的那一句）：
主题自己的逻辑只看 ``page.summary``——568 篇文章里只有 1 篇写了
``<!-- more -->``，于是这一句**一直是正文的前 120 个字**：
``static XLogCtlData *XLogCtl = NULL;`` 这种代码残骸会出现在搜索结果里。
文章 front matter 里的 ``description`` 该在这里说话。
"""

import json
import re
import shutil
import subprocess

from paths import REPO_ROOT, SITE
TLDR_PARTIAL = SITE / "themes" / "matery" / "layout" / "_partial" / "post-tldr.ejs"
HEAD_PARTIAL = SITE / "themes" / "matery" / "layout" / "_partial" / "head.ejs"
PATCH_THEME = SITE / "tools" / "patch-theme.py"
NODE = shutil.which("node")


#: head.ejs 开头那个 ``<% ... %>`` 脚本块——description 的算法就在里面。
def _head_script() -> str:
    """抠出 head.ejs 的第一个 ``<% ... %>`` 块。

    主题在那个块里算 ``description``，块里还有 ``is_archive()`` 这些
    hexo 的全局函数——测试里得给它们打桩。
    """
    text = HEAD_PARTIAL.read_text(encoding="utf-8")
    m = re.search(r"<%(.*?)%>", text, re.S)
    assert m, "head.ejs 里没有找到 <% ... %> 块"
    return m.group(1)


HARNESS = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[1], 'utf8');
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const strip_html = function (s) { return String(s).replace(/<[^>]*>/g, ''); };
const noop = function () { return false; };
const fn = new Function(
    'page', 'config', 'strip_html', '__', 'is_archive', 'is_month', 'is_year',
    'is_category', 'is_tag', 'theme',
    script + '\nreturn description;'
);
const out = cases.map(function (c) {
    return fn(c.page || {}, c.config || {}, strip_html, function (s) { return s; },
              noop, noop, noop, noop, noop, {favicon: '/favicon.png'});
});
console.log(JSON.stringify(out));
"""


def _meta_description(cases, tmp_path):
    """在 node 里跑 head.ejs 那段算 description 的代码。"""
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    script_path = tmp_path / "head-script.js"
    script_path.write_text(_head_script(), encoding="utf-8")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [NODE, "-e", HARNESS, str(script_path), str(cases_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "head.ejs 那段代码抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_meta_description_uses_the_articles_own_description(tmp_path):
    """文章 front matter 里的 description 进 ``<meta name="description">``。

    主题自己的逻辑只看 ``page.summary``——于是这一句是**正文的前 120 个字**。
    代码文章的第一段就是代码，搜索结果里就出现一段 C 代码。
    """
    got = _meta_description(
        [
            {
                "page": {
                    "title": "xlog",
                    "description": "xlog 笔记：XLogCtlData 全局变量，以及写入与刷新的状态结构。",
                    "__post": True,
                    "content": "<p>static XLogCtlData *XLogCtl = NULL;</p>",
                },
                "config": {"title": "growdu", "description": "站点描述"},
            }
        ],
        tmp_path,
    )

    assert "XLogCtlData 全局变量" in got[0], got[0]
    assert "XLogCtl = NULL" not in got[0], got[0]


def test_the_authors_own_summary_still_wins_over_the_description(tmp_path):
    """作者写了 ``<!-- more -->`` 的，summary 优先。"""
    got = _meta_description(
        [
            {
                "page": {
                    "title": "某篇",
                    "summary": "作者自己写的摘要",
                    "description": "自动生成的描述",
                    "__post": True,
                    "content": "<p>正文</p>",
                },
                "config": {"title": "growdu", "description": "站点描述"},
            }
        ],
        tmp_path,
    )

    assert "作者自己写的摘要" in got[0], got[0]
    assert "自动生成的描述" not in got[0], got[0]


def test_a_post_without_any_description_still_gets_something(tmp_path):
    """两样都没有的，退回正文的前 120 个字——不能空。

    空的一句 meta description 会被搜索引擎当成「没有摘要」，比丑一点的
    正文开头还差。
    """
    got = _meta_description(
        [
            {
                "page": {
                    "title": "某篇",
                    "__post": True,
                    "content": "<p>这是正文的第一段，足够长以便被截断到一百二十个字。</p>",
                },
                "config": {"title": "growdu", "description": "站点描述"},
            }
        ],
        tmp_path,
    )

    assert "这是正文的第一段" in got[0], got[0]


def test_a_non_post_page_still_uses_the_site_description(tmp_path):
    """不是文章的页面（首页、归档页）用站点描述。"""
    got = _meta_description(
        [
            {
                "page": {"title": "归档"},
                "config": {"title": "growdu", "description": "站点描述"},
            }
        ],
        tmp_path,
    )

    assert got[0] == "站点描述", got[0]


def test_the_tldr_box_falls_back_to_the_description_only_after_the_authors_own():
    """TL;DR 框：作者写的优先，description 只是最后一档。

    反转前的契约是「description 不进 TL;DR 框」——那条契约在 2026-11-16
    被阶段 1 的 Task 4 反转了（履历句换成真摘要之后，理由不成立了）。

    这里断的是**顺序**：``page.tldr`` 和 ``page.summary`` 必须在
    ``page.description`` 前面。description 排到前面就等于自动摘要盖掉
    作者显式写的东西。

    行为本身（哪个值真的落到了框里）在
    ``tests/test_card_excerpt_uses_description.py`` 里用 node 跑一遍。
    """
    tldr = TLDR_PARTIAL.read_text(encoding="utf-8")
    # 只看代码：注释里正好在讲这条契约——注释不是行为。
    code = re.sub(r"<%/\*.*?\*/%>", "", tldr, flags=re.S)

    assert "page.tldr || page.summary ||" in code, code
    assert "page.description || page.summary" not in code, (
        "description 排到了作者写的 summary 前面——自动摘要不能盖掉作者写的"
    )
    assert "page.summary || page.tldr" not in code, (
        "summary 排到了作者写的 tldr 前面——作者显式写的 tldr 最优先"
    )
    assert "page.description" in code, "TL;DR 框不读 description 了"


def test_the_og_description_is_not_escaped_twice():
    """``<%= %>`` 已经转义过一次了，手工再 replace 一次就成了 ``&amp;quot;``。"""
    head = HEAD_PARTIAL.read_text(encoding="utf-8")

    for line in head.splitlines():
        if "og:description" in line or "twitter:description" in line:
            assert "&quot;" not in line, line


def test_the_theme_patcher_injects_the_same_un_escaped_tags():
    """head.ejs 是 patch-theme.py 生成的——两处必须一致，否则下次跑 patch 又坏了。"""
    patch = PATCH_THEME.read_text(encoding="utf-8")

    for line in patch.splitlines():
        if "og:description" in line or "twitter:description" in line:
            assert "&quot;" not in line, line
