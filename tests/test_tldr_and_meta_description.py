"""自动生成的 description 不该改变文章页长什么样。

**背景**：sync 从文章的编辑履历表（``| 编写人 | 编写内容 | 编写时间 |``）
里抽出一句话写进 front matter 的 ``description``——那是履历表的「编写内容」
列，说的是「这篇文章讲什么」，但**不总是**：有些格子写的是「理顺结构与定位，
修正错误写法」这种**编辑动作**，不是文章摘要。

两个下游因此会把它当文章摘要显示出来：

1. ``themes/matery/layout/_partial/post-tldr.ejs`` 的 TL;DR 框
   （``page.tldr || page.summary || page.description``）
2. ``head.ejs`` 的 ``og:description`` / ``twitter:description``

**TL;DR 框**：这条 fallback 是给「description 永远为空」的时候写的
（发布规格里明写着这一条），在 description 第一次有值之前它是死代码。
现在它活了，代价是 84 篇文章凭空多出一个 TL;DR 框——里面装的是履历句，
其中 11 篇正文开头本来就有自己的 ``> **TL;DR**`` 引用块，同一个页面两个
TL;DR。所以 description 不进 TL;DR 框：框只认作者写的 ``tldr`` /
``summary``。

**og / twitter description**：那里**要**用 description（规格 §4.1 就是这么
定的），但不能转义两次——``<%= %>`` 本来就会转义 HTML，手工再
``.replace(/"/g, '&quot;')`` 一次，页面里就变成 ``&amp;quot;``，
读者看到的是 ``&quot;``。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TLDR_PARTIAL = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "post-tldr.ejs"
HEAD_PARTIAL = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "head.ejs"
PATCH_THEME = REPO_ROOT / "tools" / "patch-theme.py"


def test_the_tldr_box_does_not_read_the_generated_description():
    """TL;DR 框只认作者写的 tldr / summary。"""
    tldr = TLDR_PARTIAL.read_text(encoding="utf-8")
    # 只看代码：注释里正好写着「NOT page.description」——注释不是行为。
    code = re.sub(r"<%/\*.*?\*/%>", "", tldr, flags=re.S)

    assert "page.tldr || page.summary" in code, code
    assert "page.description" not in code, (
        "TL;DR 框又拿 description 了——那是履历表的「编写内容」列，不是文章摘要"
    )


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
