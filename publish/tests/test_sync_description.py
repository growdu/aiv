"""编辑履历表不该进正文，也不该进摘要。

**病根**：85 篇文章正文顶上有一张编辑履历表：

    | 编写人 | 编写内容 | 编写时间 |
    | --- | --- | --- |
    | growdu | 初稿，把 Citus Columnar 从 2017 年 5.0 集成 cstore_fdw…… | 2023-02-23 |

这张表被当成正文抓走，污染了三处：``<meta name="description">``、
首页卡片摘要、RSS 的 ``<summary>``。实测 98 个页面的 meta description
是表格残骸。

**怎么处理**：把「编写内容」列抽出来当 ``description``——履历前缀
（「初稿，」「修订：」）说的是「这次改了什么」，不是「文章是什么」，
前缀得去掉——截到 150 字（契约上限），同时把整张表从正文里剥掉。
表不进正文，摘要自然干净。

源 front matter 里已经写了 ``description`` 的，以源为准，不覆盖。
"""

import importlib.util
import difflib
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "tools" / "sync-hexo.py"
DOCS = REPO_ROOT / "docs"

#: publish/spec/00-架构设计.md §4.1：description ≤ 150 字。
DESCRIPTION_LIMIT = 150


def load_sync_module():
    """Load ``tools/sync-hexo.py`` as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("sync_hexo_description", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_docs_files():
    return sorted(p for p in DOCS.rglob("*.md") if p.is_file())


# --- 单元：对真实 docs/ 树里的每一张履历表 --------------------------------


def test_the_real_docs_really_do_carry_these_tables():
    """先确认「病根还在」——抽取规则认错了的话，后面的断言都是空的。"""
    module = load_sync_module()

    total = 0
    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        total += len(module.find_edit_history_tables(text))

    assert total >= 80, "只认出 {} 张履历表——是规则认错了，还是文档变了？".format(total)


def test_every_table_in_the_real_docs_leaves_a_usable_description():
    """每张有内容的表都要抽出**一段能用的** description。"""
    module = load_sync_module()

    checked = 0
    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        for header, rows in module.find_edit_history_tables(text):
            desc = module.edit_history_description(header, rows)
            if desc is None:
                continue
            checked += 1
            assert desc.strip(), "{}：抽出来是空的".format(path)
            assert len(desc) <= DESCRIPTION_LIMIT, (
                "{}：description 有 {} 字，超了契约上限 {}".format(
                    path, len(desc), DESCRIPTION_LIMIT
                )
            )
            # 履历前缀的形态是「初稿，」「修订：」——关键词后面跟着分隔符。
            # 光秃秃一个关键词不是前缀（「补充完善解决方案」里的「补充」是正文）。
            assert not re.match(
                r"^(初稿|修订|校验|校对|更新|整理|补充)\s*[：:，,、]", desc
            ), "{}：履历前缀没去掉——{}".format(path, desc)

    assert checked >= 50, "只抽到 {} 段 description，比预期少太多".format(checked)


def test_no_table_survives_in_the_body():
    """剥完之后，正文里不该再有「编写人」这张表。"""
    module = load_sync_module()

    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        if not module.find_edit_history_tables(text):
            continue
        body, _ = module.extract_edit_history(text)
        assert not module.find_edit_history_tables(body), "{}：表还在正文里".format(
            path
        )


def test_only_table_lines_are_removed():
    """剥履历表只能剥表格行——正文一个字都不能少。

    这是给「剥离」这件事兜底：正则手滑就能把整篇文章剥没了，而这
    条测试会当场现形。
    """
    module = load_sync_module()

    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        if not module.find_edit_history_tables(text):
            continue
        clean, _ = module.extract_edit_history(text)
        removed = [
            line
            for line in difflib.unified_diff(
                text.split("\n"), clean.split("\n"), lineterm="", n=0
            )
            if line.startswith("-") and not line.startswith("---")
        ]
        for line in removed:
            body = line[1:].strip()
            assert body == "" or body.startswith("|"), (
                "{}：剥掉了不该剥的行——{}".format(path, line)
            )


def test_the_history_prefix_is_stripped():
    """「初稿，」「修订：」说的是改了什么，不是文章是什么。"""
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "初稿，把 Citus Columnar 的演进讲清楚", "2023-02-23"]]

    assert module.edit_history_description(header, rows) == (
        "把 Citus Columnar 的演进讲清楚"
    )


def test_a_table_that_only_says_draft_yields_no_description():
    """光秃秃一个「初稿」不是摘要——宁可没有，别把「初稿」写成 description。"""
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "初稿", "2023-06-08"]]

    assert module.edit_history_description(header, rows) is None


def test_the_latest_revision_wins():
    """表里可能有多行履历（每次改一行），最后一行才是最新的那次。"""
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [
        ["growdu", "初稿", "2023-06-03"],
        ["growdu", "补充完善解决方案", "2023-06-07"],
    ]

    assert module.edit_history_description(header, rows) == "补充完善解决方案"


def test_a_long_description_is_cut_to_the_contract_limit():
    """契约上限 150 字——超了就是违约。"""
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "长" * 400, "2023-06-08"]]

    desc = module.edit_history_description(header, rows)

    assert desc is not None
    assert len(desc) <= DESCRIPTION_LIMIT


def test_a_table_without_a_content_column_yields_no_description():
    """有的表只有「编写人 | 编写时间 | 适用版本」——没有内容列就没有摘要。"""
    module = load_sync_module()

    header = ["编写人", "编写时间", "适用版本"]
    rows = [["growdu", "2026-10-26", "matery 主题 + mermaid 10.9.8"]]

    assert module.edit_history_description(header, rows) is None


# --- 集成：真的跑一遍 sync-hexo.py ---------------------------------------


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


TABLE = (
    "| 编写人 | 编写内容 | 编写时间 |\n"
    "| --- | --- | --- |\n"
    "| growdu | 初稿，把 PostgreSQL 的 MVCC 讲清楚，顺带说清快照 | 2024-01-01 |\n"
)

CORPUS = {
    "db/postgresql.md": "---\ntitle: PostgreSQL 数据库\n---\n\n"
    + TABLE
    + "\n正文第一段。\n",
    "db/plain.md": "---\ntitle: 没有履历表\n---\n\n正文第一段。\n",
}


def read_generated(root: Path, rel: str) -> str:
    path = root / "source" / "_posts" / rel
    assert path.exists(), "sync 没有生成 {}".format(rel)
    return path.read_text(encoding="utf-8")


def test_the_generated_post_carries_a_description(tmp_path):
    """履历表的「编写内容」变成 front matter 的 description。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    post = read_generated(tmp_path, "db/postgresql.md")

    assert 'description: "把 PostgreSQL 的 MVCC 讲清楚，顺带说清快照"' in post, post


def test_the_table_is_gone_from_the_body(tmp_path):
    """履历表不进正文——它不是文章内容。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    post = read_generated(tmp_path, "db/postgresql.md")

    assert "| 编写人 |" not in post, post
    assert "正文第一段。" in post


def test_a_post_without_a_table_is_left_alone(tmp_path):
    """没有履历表的文章不该凭空多出一个 description。"""
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    post = read_generated(tmp_path, "db/plain.md")

    assert "description:" not in post, post


def test_a_description_written_by_hand_is_not_overwritten(tmp_path):
    """源 front matter 里已经写了 description 的，以源为准。"""
    corpus = {
        "db/postgresql.md": (
            "---\n"
            "title: PostgreSQL 数据库\n"
            'description: "我自己写的摘要"\n'
            "---\n\n" + TABLE + "\n正文第一段。\n"
        )
    }
    build_corpus(tmp_path, corpus)
    run_sync(tmp_path)

    post = read_generated(tmp_path, "db/postgresql.md")

    assert 'description: "我自己写的摘要"' in post, post
    assert post.count("description:") == 1, post
