"""自动生成的 description 该怎么用，不该由谁说了算。

**背景**：sync 从文章的编辑履历表（``| 编写人 | 编写内容 | 编写时间 |``）
里抽出一句话写进 front matter 的 ``description``——那是履历表的「编写内容」
列，说的是「这篇文章讲什么」，但**不总是**：有些格子写的是「理顺结构与定位，
修正错误写法」这种**编辑动作**，不是文章摘要。

两个下游会把它当文章摘要显示出来：

1. ``themes/matery/layout/_partial/post-tldr.ejs`` 的 TL;DR 框
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
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TLDR_PARTIAL = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "post-tldr.ejs"
HEAD_PARTIAL = REPO_ROOT / "themes" / "matery" / "layout" / "_partial" / "head.ejs"
PATCH_THEME = REPO_ROOT / "tools" / "patch-theme.py"


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
