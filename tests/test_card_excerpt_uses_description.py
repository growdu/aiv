"""卡片摘要和 TL;DR 框要读 description。

**病根**：``post-card.ejs`` 是 ``post.summary || strip_html(post.content)
.substring(0, 80)``。而 568 篇文章里只有 1 篇写了 ``<!-- more -->``——
``post.summary`` 基本上是空的。于是摘要 = **正文的前 80 个字**：线上 18 张
卡片里 3 张以「TL;DR」开头，另有几张是表格残骸、``[TOC]``、视频口播稿抬头。

``post-tldr.ejs`` 是 ``page.tldr || page.summary``——同样基本为空，于是
TL;DR 框基本不出现。

**阶段 0 已经把 85 条 description 写进了 front matter**，但这两个模板都不读
它——那 85 条至今没在卡片上露过面。

**这里要反转阶段 0 的一个决定。** 阶段 0 明确写过「description 只喂 og /
twitter，不喂 TL;DR 框，不喂卡片摘要」——理由是那时候 description 是**履历句**
（说的是「这次改了什么」）。Task 5 把它们换成真摘要之后，这个理由就不成立
了。不反转的话，Task 5 的成果读者一样看不见。

**优先级**：作者显式写的东西（``<!-- more -->`` 的 ``summary``、front matter
里的 ``tldr``）永远优先于自动生成的 description。

这里断言的是**行为**：把模板里那条取值表达式抠出来，在 node 里用不同的
``post`` 跑一遍，看真的落到了哪一句上——只检查模板里有没有出现
``description`` 这个词，挡不住「顺序反了，作者写的被自动摘要盖掉」。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PARTIAL = REPO / "themes" / "matery" / "layout" / "_partial"
POST_CARD = PARTIAL / "post-card.ejs"
POST_TLDR = PARTIAL / "post-tldr.ejs"
NODE = shutil.which("node")


def _read(path: Path) -> str:
    assert path.is_file(), "找不到 {}".format(path)
    return path.read_text(encoding="utf-8")


def _expression(path: Path, name: str) -> str:
    """把模板里 ``var <name> = <表达式>;`` 那条抠出来。

    语句末尾的 ``;`` 是**语法**的分号，但字符串字面量里的 ``;`` 不是
    （``'TL;DR'`` 里就有一个）——所以这里扫字符串，不靠正则找分号：
    正则 ``(.+?);`` 会在字符串里那个分号处停下，抠出来的表达式是断的。
    """
    template = _read(path)
    m = re.search(r"var\s+" + name + r"\s*=\s*", template)
    assert m, "{} 里没有找到 var {} = ...".format(path.name, name)

    i = m.end()
    quote = None
    while i < len(template):
        ch = template[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ";":
            break
        i += 1
    else:
        raise AssertionError("{} 里 var {} = 这条没有结尾".format(path.name, name))

    return template[m.end() : i].strip()


HARNESS = r"""
const fs = require('fs');
const expr = fs.readFileSync(process.argv[1], 'utf8');
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const strip_html = function (s) { return String(s).replace(/<[^>]*>/g, ''); };
const fn = new Function('post', 'page', 'strip_html', 'return ' + expr + ';');
const out = cases.map(function (c) {
    return fn(c.post || {}, c.page || {}, strip_html);
});
console.log(JSON.stringify(out));
"""


def _evaluate(path: Path, name: str, cases, tmp_path: Path):
    """在 node 里跑那条取值表达式，返回每个用例的结果。"""
    if NODE is None:
        import pytest

        pytest.skip("node 不在 PATH 上")

    expr_path = tmp_path / "expr.js"
    expr_path.write_text(_expression(path, name), encoding="utf-8")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        __import__("json").dumps(cases, ensure_ascii=False), encoding="utf-8"
    )

    result = subprocess.run(
        [NODE, "-e", HARNESS, str(expr_path), str(cases_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "取值表达式抛异常了：\n{}\n{}".format(
        result.stdout, result.stderr
    )
    return __import__("json").loads(result.stdout.strip().splitlines()[-1])


# --- 卡片摘要 ---------------------------------------------------------------


def test_the_card_falls_back_to_the_description(tmp_path):
    """卡片没有作者摘要时，用 description 当摘要。"""
    got = _evaluate(
        POST_CARD,
        "excerpt",
        [{"post": {"description": "一篇讲查询管线的文章"}}],
        tmp_path,
    )

    assert "一篇讲查询管线的文章" in got[0], got[0]


def test_the_author_written_excerpt_wins_over_the_description(tmp_path):
    """作者写了 ``<!-- more -->``（``summary``）时，摘要优先。

    作者显式写的东西不能被自动生成的 description 盖掉。
    """
    got = _evaluate(
        POST_CARD,
        "excerpt",
        [
            {
                "post": {
                    "summary": "作者自己写的摘要",
                    "description": "自动生成的描述",
                }
            }
        ],
        tmp_path,
    )

    assert "作者自己写的摘要" in got[0], got[0]
    assert "自动生成的描述" not in got[0], got[0]


def test_the_card_still_has_a_last_resort_fallback(tmp_path):
    """两者都没有时，仍然退回正文的前 80 个字。

    不能空——一张没有摘要的卡片看起来像坏掉了。
    """
    got = _evaluate(
        POST_CARD,
        "excerpt",
        [{"post": {"content": "<p>这是正文的第一段，足够长一点以便被截断，后面还有很多字。</p>"}}],
        tmp_path,
    )

    assert got[0].strip(), "卡片摘要空了"
    assert "这是正文的第一段" in got[0], got[0]
    assert len(got[0]) <= 90, got[0]


# --- TL;DR 框 ---------------------------------------------------------------


def test_the_tldr_box_falls_back_to_the_description(tmp_path):
    """TL;DR 框没有 ``tldr``、没有 ``summary`` 时，用 description。"""
    got = _evaluate(
        POST_TLDR,
        "tldr",
        [{"page": {"description": "一句话说清这篇在讲什么"}}],
        tmp_path,
    )

    assert "一句话说清这篇在讲什么" in got[0], got[0]


def test_the_author_written_tldr_wins_over_the_description(tmp_path):
    """作者写了 ``tldr:`` 时，用它——description 不能盖掉它。"""
    got = _evaluate(
        POST_TLDR,
        "tldr",
        [{"page": {"tldr": "作者自己写的 TL;DR", "description": "自动生成的描述"}}],
        tmp_path,
    )

    assert "作者自己写的 TL;DR" in got[0], got[0]
    assert "自动生成的描述" not in got[0], got[0]


def test_the_tldr_box_stays_away_when_the_body_already_has_one(tmp_path):
    """正文里已经有自己的 TL;DR 块时，别再画第二个。

    有 4 篇文章正文开头就是 ``> **TL;DR**：……``（或 ``## TL;DR`` 小节）。
    description 进了框之后，同一个页面上会上下两个 TL;DR——读者会以为
    页面坏掉了。
    """
    got = _evaluate(
        POST_TLDR,
        "tldr",
        [
            {
                "page": {
                    "description": "自动生成的描述",
                    "content": "<blockquote><p><strong>TL;DR</strong>：作者自己写的</p></blockquote>",
                }
            }
        ],
        tmp_path,
    )

    assert not got[0], "正文里已经有 TL;DR 块了，框里又塞了一句：{}".format(got[0])


def test_the_author_written_excerpt_wins_over_the_description_in_the_tldr_box(
    tmp_path,
):
    """``<!-- more -->`` 的摘要也优先于 description。

    跟卡片一个道理：作者显式写的东西优先。
    """
    got = _evaluate(
        POST_TLDR,
        "tldr",
        [{"page": {"summary": "作者自己写的摘要", "description": "自动生成的描述"}}],
        tmp_path,
    )

    assert "作者自己写的摘要" in got[0], got[0]
    assert "自动生成的描述" not in got[0], got[0]
