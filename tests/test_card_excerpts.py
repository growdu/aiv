"""首页卡片的摘要不能是残骸。

**病根**：卡片的摘要是 ``post.summary || strip_html(post.content)
.substring(0, 80)``——而 568 篇文章里只有 1 篇写了 ``<!-- more -->``，
``post.summary`` 基本上是空的。于是摘要 = **正文的前 80 个字**：线上 18 张
卡片里 3 张以「TL;DR」开头，另有几张是表格残骸、「[TOC]」、视频口播稿抬头。

读者看到「TL;DR」「[TOC]」这种开头，只会觉得这个博客没写完。

**这个检查器在渲染产物上跑**（``platforms/blog/site/public/index.html``），不是查模板——
模板改了但产物没重建，模板看着对、页面还是坏的，这正是要防的那件事。

它盯三样：

1. 摘要不以「TL;DR」「[TOC]」开头；
2. 摘要不以履历前缀开头（「初稿，」「修订：」——那是「这次改了什么」）；
3. 摘要不是空的。

用法：``python3 platforms/blog/site/tools/check-card-excerpts.py --public platforms/blog/site/public``。
退出码 0 = 全过；1 = 有问题（逐条打印）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "platforms" / "blog" / "site"
CHECKER = SITE / "tools" / "check-card-excerpts.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_card_excerpts", CHECKER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def _card(excerpt: str) -> str:
    return (
        '<a class="post-card" href="/2026/08/18/db/postgresql/">'
        '<div class="post-card__body">'
        '<h3 class="post-card__title">某篇文章</h3>'
        '<div class="post-card__excerpt">{}</div>'
        "</div></a>"
    ).format(excerpt)


def _write_index(tmp_path: Path, cards) -> Path:
    public = tmp_path / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / "index.html").write_text(
        "<html><body>" + "".join(cards) + "</body></html>", encoding="utf-8"
    )
    return public


# --- 好的产物 ---------------------------------------------------------------


def test_a_good_page_passes(tmp_path):
    """正常的摘要不该被挑刺。"""
    public = _write_index(
        tmp_path,
        [
            _card("这是一篇讲 PostgreSQL 查询管线的文章，从执行器讲到落盘。"),
            _card("另一篇讲复制槽的文章。"),
        ],
    )

    assert checker.check(public) == []


# --- 坏的产物 ---------------------------------------------------------------


def test_an_excerpt_starting_with_tldr_is_reported(tmp_path):
    """以「TL;DR」开头的摘要——那不是摘要。"""
    public = _write_index(tmp_path, [_card("TL;DR: 一句话说清这篇在讲什么。")])

    problems = checker.check(public)

    assert problems, "以 TL;DR 开头的摘要没被报出来"
    assert "TL;DR" in problems[0], problems[0]


def test_an_excerpt_starting_with_toc_is_reported(tmp_path):
    """以「[TOC]」开头的摘要——那是目录标记。"""
    public = _write_index(tmp_path, [_card("[TOC] 这不是摘要")])

    problems = checker.check(public)

    assert problems, "以 [TOC] 开头的摘要没被报出来"
    assert "[TOC]" in problems[0], problems[0]


def test_an_editing_history_sentence_is_reported(tmp_path):
    """以履历前缀开头的摘要——那是「这次改了什么」。"""
    public = _write_index(tmp_path, [_card("初稿，补充完善解决方案")])

    problems = checker.check(public)

    assert problems, "履历句没被报出来"
    assert "初稿" in problems[0], problems[0]


def test_an_empty_excerpt_is_reported(tmp_path):
    """空摘要——一张没有摘要的卡片看起来像坏掉了。"""
    public = _write_index(tmp_path, [_card("")])

    problems = checker.check(public)

    assert problems, "空摘要没被报出来"


def test_a_missing_product_is_reported(tmp_path):
    """没有产物要说清楚，别假装通过。"""
    problems = checker.check(tmp_path / "public")

    assert problems
    assert "找不到" in problems[0], problems[0]


def test_the_checker_counts_every_card(tmp_path):
    """18 张卡片都要看——只看第一张的话，后面 17 张坏了没人知道。"""
    cards = [_card("这是第 {} 张卡片的摘要，内容足够长不会被当成空的。".format(i)) for i in range(18)]
    cards[10] = _card("TL;DR: 第十一张坏了")
    public = _write_index(tmp_path, cards)

    problems = checker.check(public)

    assert len(problems) == 1, problems


def test_the_checker_runs_in_both_build_jobs():
    """检查器要挂在**两个** build job 里（主站 + 镜像）。

    只挂一个，那边的产物坏掉了没人知道——两个 job 部署的是两个站点。
    """
    workflow = (REPO / ".github" / "workflows" / "hexo.yml").read_text(encoding="utf-8")

    assert workflow.count("check-card-excerpts.py") == 2, (
        "检查器没有挂在两个 build job 里（现在挂了 {} 次）".format(
            workflow.count("check-card-excerpts.py")
        )
    )
