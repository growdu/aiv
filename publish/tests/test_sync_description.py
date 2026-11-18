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
from pathlib import Path

# 集成测试的假仓库：把站点构建链的落点重定向到临时目录。
from sync_harness import SYNC_SCRIPT, build_corpus, content_units_dir, run_sync

REPO_ROOT = Path(__file__).resolve().parents[2]
DRAFT_SCRIPT = REPO_ROOT / "tools" / "draft-descriptions.py"
DOCS = REPO_ROOT / "docs"

#: publish/spec/00-架构设计.md §4.1：description ≤ 150 字。
DESCRIPTION_LIMIT = 150


def load_sync_module():
    """Load ``platforms/blog/site/tools/sync-hexo.py`` as a module.

    它是个脚本，不是包——所以用 importlib 按路径加载。
    """
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


def test_a_full_stop_after_the_prefix_is_stripped():
    """「初稿。」也是履历前缀——9 篇文章的摘要第一眼是「初稿。」。

    读者看到「初稿。」会以为文章没写完。
    """
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "初稿。从 PostgreSQL 18 源码出发，把目录快照讲清楚", "2026-11-11"]]

    assert module.edit_history_description(header, rows) == (
        "从 PostgreSQL 18 源码出发，把目录快照讲清楚"
    )


def test_a_prefix_followed_by_a_plus_is_stripped():
    """「初稿 + 第十二节增补：……」也算履历前缀。"""
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "初稿 + 第十二节增补：补充 ReorderBuffer 视角", "2026-11-11"]]

    assert module.edit_history_description(header, rows) == (
        "第十二节增补：补充 ReorderBuffer 视角"
    )


def test_the_description_is_plain_text():
    """摘要要能直接进 meta / 卡片 / RSS——裸 markdown 标记到那里是字面量。

    ``**PostgreSQL 目录快照**`` 显示在 OG 描述里就是「**PostgreSQL
    目录快照**」，不是加粗。
    """
    module = load_sync_module()

    header = ["编写人", "编写内容", "编写时间"]
    rows = [["growdu", "初稿，把 **PostgreSQL 目录快照** 和 `pg_class` 讲清楚", "2023-02-23"]]

    desc = module.edit_history_description(header, rows)

    assert desc == "把 PostgreSQL 目录快照 和 pg_class 讲清楚"


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


def test_a_table_written_by_修改人_is_stripped_too():
    """有的作者写的是「修改人 | 修改内容 | 修改时间」——那也是编辑履历表。

    这三篇的「修改内容」列是「文档初稿」这类空话，所以**不抽摘要**，
    但表得剥掉——留在正文里，它的 meta description 就还是表格残骸。
    """
    module = load_sync_module()

    text = (
        "正文。\n\n"
        "| 修改人 | 修改内容 | 修改时间 |\n"
        "| --- | --- | --- |\n"
        "| growdu | 文档初稿 | 2024-05-06 |\n\n"
        "后文。\n"
    )

    clean, desc = module.extract_edit_history(text)

    assert "修改人" not in clean
    assert "后文。" in clean
    assert desc is None


def test_no_edit_history_table_is_left_in_the_real_docs():
    """真实语料里凡是履历表，剥完之后都不该还在。

    这条比 ``find_edit_history_tables`` 更宽：它按**表头长相**找，不信
    抽取器自己的判断——抽取器认出来了却没剥掉（或者压根没认出来），
    都在这里现形。
    """
    module = load_sync_module()

    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^\|\s*(编写人|修改人|编辑人)\s*\|", text, re.M):
            continue
        clean, _ = module.extract_edit_history(text)
        assert not re.search(r"^\|\s*(编写人|修改人|编辑人)\s*\|", clean, re.M), path


def test_the_description_survives_the_content_contract():
    """生成的 description 必须过得了内容契约的长度上限。

    **病根**：契约层用自己的小解析器读 front matter
    （``publish/publishkit/contract.py`` 的 ``_unquote``），它剥外层引号
    但**不反转义**——于是 ``\\"`` 在那里算 2 个字符。sync 按未转义的长度
    封顶 150，契约按转义后的长度封顶 150：每多一个引号就多 2。
    4 篇文章因此在 CI 上违规（``tools/check-content-contract.py`` 退出 1）。

    这条测试用**契约层自己的解析器**判长度——两边口径必须一致。
    """
    from publishkit import parse_front_matter, validate_fields

    module = load_sync_module()

    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        for header, rows in module.find_edit_history_tables(text):
            desc = module.edit_history_description(header, rows)
            if desc is None:
                continue
            line = 'description: "{}"\n'.format(module.yaml_escape(desc))
            fields, _ = parse_front_matter("---\n" + line + "---\n")
            violations = validate_fields(fields)
            assert not violations, "{}：{}".format(path, violations)


# --- 集成：真的跑一遍 sync-hexo.py ---------------------------------------


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
    """读编译出来的内容单元（内容单元仓库住在 ``content/units/``）。"""
    path = content_units_dir(root) / rel
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


# --- 阶段 1 的 Task 5：摘要改成「这篇文章是什么」 ---------------------------


def load_draft_module():
    """Load ``tools/draft-descriptions.py`` as a module（它留在根 tools/）。"""
    spec = importlib.util.spec_from_file_location("draft_descriptions", DRAFT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unquote(raw: str) -> str:
    """front matter 里的值 → 语义值。

    ``_fm_scalar`` 原样带回值（**带引号**）：``"PG 里\\"一张表\\"……"``。
    要拿它跟契约层比长度，就得先剥外层引号、再反转义——否则会**转义两次**：
    ``\\"`` 变成 ``\\\\"``，长度凭空多出 2 个字符，150 字的摘要被误判成 154。

    契约层（``publish/publishkit/contract.py`` 的 ``_unquote``）剥外层引号
    但**不反转义**——所以它量的就是转义后的长度。这两边必须对齐。
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\\\", "\\")


def effective_description(module, sync_module, text):
    """这篇文章**最终**会用哪一句摘要。

    front matter 里写了 description 的以源为准（sync 不覆盖）；
    没写的，起草工具从正文里抽第一段真正的段落。
    """
    fm, body = sync_module.split_fm(text)
    if fm is not None:
        raw = sync_module._fm_scalar(fm, "description")
        if raw:
            return _unquote(raw)
    return module.draft_description(body)


def test_the_description_is_not_an_editing_history_sentence():
    """摘要**不以履历前缀开头**。

    这条直接盯着阶段 0 遗留的那个问题：履历表的「编写内容」列说的是
    「这次改了什么」（「初稿，补充完善解决方案」「理顺结构与定位，修正
    错误写法」），不是「这篇文章是什么」。前缀没去掉，读者在卡片上读到的
    就是一句编辑记录。
    """
    module = load_draft_module()
    sync_module = load_sync_module()

    checked = 0
    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        desc = effective_description(module, sync_module, text)
        if not desc:
            continue
        checked += 1
        assert not sync_module.HISTORY_PREFIX_RE.match(desc), (
            "{}：摘要还带着履历前缀——{}".format(path, desc)
        )

    assert checked >= 50, "只检查了 {} 篇的摘要，比预期少太多".format(checked)


def test_a_drafted_description_fits_the_contract_limit():
    """起草的摘要也要过得了契约的长度上限（150 字）。

    按**契约层自己的解析器**判长度——它剥外层引号但不反转义，两边口径
    必须一致（和上面那条 ``test_the_description_survives_the_content_contract``
    同一个道理）。
    """
    from publishkit import parse_front_matter, validate_fields

    module = load_draft_module()
    sync_module = load_sync_module()

    checked = 0
    for path in real_docs_files():
        text = path.read_text(encoding="utf-8")
        desc = effective_description(module, sync_module, text)
        if not desc:
            continue
        checked += 1
        assert len(desc) <= DESCRIPTION_LIMIT, (
            "{}：摘要有 {} 字，超了契约上限 {}".format(path, len(desc), DESCRIPTION_LIMIT)
        )
        line = 'description: "{}"\n'.format(sync_module.yaml_escape(desc))
        fields, _ = parse_front_matter("---\n" + line + "---\n")
        violations = validate_fields(fields)
        assert not violations, "{}：{}".format(path, violations)

    assert checked >= 50, "只检查了 {} 篇的摘要，比预期少太多".format(checked)
