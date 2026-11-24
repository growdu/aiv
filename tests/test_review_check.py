"""单元 + 集成测试：审校信号检查器 tools/review-check.py。

为什么要测这个工具
----------------
它替人做「AI 味信号、证据密度、章节结构」这类机械检查。如果它算错，
审校记录就会把错误的位置写进正文修改建议——比没有工具更糟。

两类测试：
* 单元：解析与身份推导，给最小输入；
* 集成：真的跑一遍 CLI，检查它能吃下真实文章目录。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from paths import DOCS, REPO_ROOT, ROOT_TOOLS
TOOL = ROOT_TOOLS / "review-check.py"


def run_tool(*args):
    """跑一次审校检查器。

    **解码必须显式。** ``text=True`` 按 ``locale.getpreferredencoding()``
    解码（中文 Windows 是 cp936），而子进程输出的是 UTF-8——两边对不上，
    UnicodeDecodeError 就发生在读取线程里，``stdout`` 变成 None，
    失败时连报错内容都读不到。
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
    )


def load_tool():
    """Import review-check.py as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("review_check", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["review_check"] = module
    spec.loader.exec_module(module)
    return module


def make_doc(tmp_path: Path, text: str):
    module = load_tool()
    path = tmp_path / "index.md"
    path.write_text(text, encoding="utf-8")
    return module.load_doc(path)


def test_derive_identity_from_page_bundle(tmp_path):
    module = load_tool()
    path = tmp_path / "database" / "postgresql-mvcc" / "index.md"
    path.parent.mkdir(parents=True)
    path.write_text("# t\n", encoding="utf-8")
    pillar, slug = module.derive_identity(path, tmp_path)
    assert slug == "postgresql-mvcc"
    assert pillar == "database"


def test_derive_identity_from_single_file(tmp_path):
    module = load_tool()
    path = tmp_path / "database" / "pg-dont-do-this.md"
    path.parent.mkdir(parents=True)
    path.write_text("# t\n", encoding="utf-8")
    pillar, slug = module.derive_identity(path, tmp_path)
    assert (pillar, slug) == ("database", "pg-dont-do-this")


def test_derive_identity_keeps_nested_path(tmp_path):
    module = load_tool()
    path = tmp_path / "db" / "postgresql" / "xxx.md"
    path.parent.mkdir(parents=True)
    path.write_text("# t\n", encoding="utf-8")
    pillar, slug = module.derive_identity(path, tmp_path)
    assert (pillar, slug) == ("db", "postgresql/xxx")


def test_parse_blocks_splits_heading_paragraph_and_code():
    module = load_tool()
    lines = [
        "# 标题",
        "",
        "第一段。",
        "",
        "```sql",
        "SELECT 1;",
        "```",
        "",
        "## 二级标题",
        "",
        "第二段。",
    ]
    blocks = module.parse_blocks(lines)
    kinds = [b.kind for b in blocks]
    assert kinds == ["heading", "paragraph", "code", "heading", "paragraph"]
    assert blocks[0].level == 1
    assert blocks[3].level == 2
    assert blocks[2].text.strip() == "SELECT 1;"


def test_parse_blocks_detects_table_and_list():
    module = load_tool()
    lines = [
        "| a | b |",
        "| --- | --- |",
        "",
        "- 第一项",
        "- 第二项",
    ]
    blocks = module.parse_blocks(lines)
    assert [b.kind for b in blocks] == ["table", "list"]


def test_load_doc_reads_first_h1_as_title(tmp_path):
    module = load_tool()
    path = tmp_path / "index.md"
    path.write_text("# PostgreSQL MVCC\n\n正文。\n", encoding="utf-8")
    doc = module.load_doc(path)
    assert doc.title == "PostgreSQL MVCC"


def _corpus(tmp_path: Path) -> Path:
    """造一棵自己的语料树。

    **不用仓库里的 `docs/`**——那条规矩是死的：仓库里曾经有过什么内容，
    这条用例就跟着变成假红（`docs/` 现在是空的，内容在框架起来之后再做）。
    语料自己造，身份按 `--docs-root` 指到这棵树。
    """
    root = tmp_path / "docs"
    (root / "life" / "aiv").mkdir(parents=True)
    (root / "life" / "aiv" / "人格规范.md").write_text(
        "# 人格规范\n\n这一段是正文，够长到能过最起码的结构检查。\n\n"
        "## 一节\n\n另一段正文。\n",
        encoding="utf-8",
    )
    (root / "life" / "_index.md").write_text(
        "# 人生与成长\n\n分类页。\n", encoding="utf-8"
    )
    return root


def test_cli_json_output_has_expected_shape(tmp_path):
    """集成：真跑一次 CLI，检查 JSON 结构。"""
    root = _corpus(tmp_path)
    target = root / "life" / "aiv" / "人格规范.md"
    result = run_tool(str(target), "--json", "--docs-root", str(root))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "docs" in payload
    doc = payload["docs"][0]
    assert doc["pillar"] == "life"
    assert doc["slug"] == "aiv/人格规范"
    assert doc["stats"]["paragraphs"] > 0
    assert isinstance(doc["signals"], list)


def test_cli_runs_over_a_whole_pillar(tmp_path):
    """集成：整目录跑一遍，不许崩。"""
    root = _corpus(tmp_path)
    pillar = root / "life"
    result = run_tool(str(pillar), "--json", "--docs-root", str(root))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    expected = sorted(p for p in pillar.rglob("*.md"))
    assert len(payload["docs"]) == len(expected)
    assert {d["pillar"] for d in payload["docs"]} == {"life"}


def test_cli_reports_missing_path():
    result = run_tool(str(DOCS / "does-not-exist"))
    assert result.returncode == 1
    assert "路径不存在" in result.stderr


# 审校过的正文合入后，段落不该又长回去——AIF-03 盯的就是「单段 > 200 字」。
# 改文章时把两段并回一段，这条测试会报出来：审校完的稿子不能带新债。
#
# **审校工作面由范围文档定**（桶 5 = `docs/` 全集减去排除清单），
# 不是写死的路径清单：内容进来时范围文档更新，工作面就跟着变；
# 内容清空时工作面是空的，这条测试自动空转（现在正是这样）。
SCOPE_DOC = REPO_ROOT / "review" / "scope" / "2026-11-14-scope-classification.md"
EXCLUDED_PATH_RE = re.compile(r"^- `(docs/[^`]+)`$", re.M)


def review_surface() -> list[Path]:
    """`docs/` 里面向读者的技术文章（审校工作面）。"""
    text = SCOPE_DOC.read_text(encoding="utf-8")
    section = text.split("## 排除清单", 1)[1]
    excluded = set(EXCLUDED_PATH_RE.findall(section))
    out = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel not in excluded:
            out.append(path)
    return out


def test_reviewed_articles_have_no_long_paragraph_signal():
    """集成：已合入审校的文章不该再被 AIF-03 命中。"""
    for path in review_surface():
        result = run_tool(str(path), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        hits = [s for s in payload["docs"][0]["signals"]
                if s["rule"] == "AIF-03" and s["severity"] == "warn"]
        assert not hits, f"{path} 还有超长段落：{hits}"


# --- AIF 规则 -------------------------------------------------------------


def test_aif_01_flags_paragraphs_opening_with_connectors(tmp_path):
    text = "\n\n".join([
        "首先看第一件事。",
        "其次看第二件事。",
        "最后看第三件事。",
        "此外还有补充。",
        "这段是正常叙述，不带连接词开头。",
    ]) + "\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_aif_01(doc)
    assert len(signals) == 1
    assert signals[0].rule == "AIF-01"
    assert signals[0].severity == "warn"


def test_aif_01_ignores_connectors_used_inside_a_sentence(tmp_path):
    text = "\n\n".join([
        "这个方案最后落地了。",
        "他首先想到的是数据。",
        "这是一段普通叙述。",
    ]) + "\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_aif_01(doc) == []


def test_aif_02_flags_praise_without_evidence(tmp_path):
    doc = make_doc(tmp_path, "PostgreSQL 的性能非常显著。\n")
    signals = load_tool().rule_aif_02(doc)
    assert len(signals) == 1
    assert signals[0].rule == "AIF-02"


def test_aif_02_accepts_praise_backed_by_a_number(tmp_path):
    doc = make_doc(tmp_path, "PostgreSQL 的性能提升了 30%。\n")
    assert load_tool().rule_aif_02(doc) == []


def test_aif_03_flags_a_long_paragraph(tmp_path):
    doc = make_doc(tmp_path, "长" * 250 + "\n")
    signals = load_tool().rule_aif_03(doc)
    assert len(signals) == 1
    assert signals[0].rule == "AIF-03"


def test_aif_04_flags_generic_ending(tmp_path):
    text = "第一段讲清楚机制。\n\n第二段讲清楚取舍。\n\n希望本文对你有帮助。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_aif_04(doc)
    assert len(signals) == 1
    assert signals[0].rule == "AIF-04"


def test_aif_05_flags_near_duplicate_sentences(tmp_path):
    text = (
        "在并发场景下，写入会阻塞另一个事务的读取操作。\n\n"
        "在并发场景下，写入会阻塞另一个事务的读取行为。\n"
    )
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_aif_05(doc)
    assert len(signals) == 1
    assert signals[0].rule == "AIF-05"


def test_aif_05_ignores_parallel_code_introduction_lines(tmp_path):
    """回归：「事务 XID=200 执行：」和「事务 XID=300 执行：」是并列结构，不是冗余。"""
    text = (
        "事务 XID=200 执行：\n\n"
        "```sql\nDELETE FROM account WHERE id = 1;\n```\n\n"
        "事务 XID=300 执行：\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_aif_05(doc) == []


# --- DEP 规则 -------------------------------------------------------------


def test_dep_counts_each_element(tmp_path):
    text = (
        "# 标题\n\n"
        "本文基于 PostgreSQL 17.2 环境，源码路径是 src/backend/access/heap/heapam.c。\n\n"
        "```sql\nSELECT * FROM pg_class;\n```\n\n"
        "相比之下，逻辑复制代价更高，适用场景也不同。\n\n"
        "注意这里的坑：要用 pg_stat_statements 验证。\n"
    )
    doc = make_doc(tmp_path, text)
    module = load_tool()
    module.check_doc(doc)
    for key in ("DEP-01", "DEP-02", "DEP-03", "DEP-04", "DEP-05"):
        assert doc.depth[key] > 0, key
    assert doc.depth["DEP-00"] == 0


def test_dep_00_flags_a_shallow_article(tmp_path):
    doc = make_doc(tmp_path, "# 标题\n\n这是一篇很短的文章，讲了一点点东西。\n")
    module = load_tool()
    module.check_doc(doc)
    assert doc.depth["DEP-00"] == 1


def test_dep_03_needs_a_code_block_not_prose(tmp_path):
    doc = make_doc(tmp_path, "正文里提到 SELECT 这个关键字，但没有代码块。\n")
    module = load_tool()
    module.check_doc(doc)
    assert doc.depth["DEP-03"] == 0


def test_dep_04_counts_tradeoff_wording_beyond_comparison(tmp_path):
    """回归：只认「相比/替代」会漏掉用「优点/缺点」讲取舍的文章。"""
    doc = make_doc(tmp_path, "它的优点是简单，缺点是不好扩展。\n")
    module = load_tool()
    module.check_doc(doc)
    assert doc.depth["DEP-04"] > 0


# --- STR / MET 规则 --------------------------------------------------------


def test_str_04_accepts_a_sibling_article_link(tmp_path):
    module = load_tool()
    pillar = tmp_path / "database"
    (pillar / "postgresql-mvcc").mkdir(parents=True)
    (pillar / "postgresql-mvcc" / "index.md").write_text("# t\n", encoding="utf-8")
    (pillar / "pg-dont-do-this").mkdir()
    (pillar / "pg-dont-do-this" / "index.md").write_text("# t\n", encoding="utf-8")
    doc = module.load_doc(pillar / "postgresql-mvcc" / "index.md")
    doc.text = "见 [同系列](./pg-dont-do-this/index.html)\n"
    doc.lines = doc.text.split("\n")
    doc.blocks = module.parse_blocks(doc.lines)
    assert module.rule_str_04(doc) == []


def test_str_04_flags_a_link_to_a_missing_article(tmp_path):
    module = load_tool()
    pillar = tmp_path / "database"
    (pillar / "postgresql-mvcc").mkdir(parents=True)
    (pillar / "postgresql-mvcc" / "index.md").write_text("# t\n", encoding="utf-8")
    doc = module.load_doc(pillar / "postgresql-mvcc" / "index.md")
    doc.text = "见 [不存在的](./no-such-article/index.html)\n"
    doc.lines = doc.text.split("\n")
    doc.blocks = module.parse_blocks(doc.lines)
    signals = module.rule_str_04(doc)
    assert len(signals) == 1
    assert signals[0].rule == "STR-04"


def test_str_04_ignores_image_paths(tmp_path):
    """图片不是文章链接：图片路径散落在别处，判成断链就是误报。"""
    module = load_tool()
    pillar = tmp_path / "database"
    (pillar / "postgresql-mvcc").mkdir(parents=True)
    (pillar / "postgresql-mvcc" / "index.md").write_text("# t\n", encoding="utf-8")
    doc = module.load_doc(pillar / "postgresql-mvcc" / "index.md")
    doc.text = "![图](./images/somewhere-else/heap.png)\n"
    doc.lines = doc.text.split("\n")
    doc.blocks = module.parse_blocks(doc.lines)
    assert module.rule_str_04(doc) == []


def test_met_01_flags_a_missing_author_table(tmp_path):
    doc = make_doc(tmp_path, "# 标题\n\n正文。\n")
    signals = load_tool().rule_met_01(doc)
    assert len(signals) == 1
    assert signals[0].rule == "MET-01"


def test_met_01_accepts_the_author_table(tmp_path):
    text = ("# 标题\n\n| 编写人 | 编写内容 | 编写时间 |\n| --- | --- | --- |\n"
            "| growdu | 初稿 | 2026-08-20 |\n\n正文。\n")
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_met_01(doc) == []


def test_str_02_flags_a_missing_opening_positioning(tmp_path):
    doc = make_doc(tmp_path, "# 标题\n\n正文开始了。\n\n第二段。\n\n第三段。\n")
    signals = load_tool().rule_str_02(doc)
    assert len(signals) == 1
    assert signals[0].rule == "STR-02"


def test_str_02_accepts_a_positioning_sentence(tmp_path):
    """回归：「本文会沿着源码拆给你看」也是定位句，不能当成没有定位。"""
    text = (
        "# 标题\n\n"
        "先讲个场景。\n\n"
        "PostgreSQL 选择了一条路。\n\n"
        "本文会沿着 src/backend/access/heap/ 的源码，把这条链路一步步拆给你看。\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_02(doc) == []


def test_str_03_accepts_a_reference_section(tmp_path):
    """回归：结尾的「参考资料」是标题+列表，只看段落会全判成没有产物。"""
    text = (
        "# 标题\n\n"
        "正文讲完了。\n\n"
        "## 参考资料\n\n"
        "- PostgreSQL 17 源码：src/backend/access/heap/heapam.c\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_03(doc) == []


def test_parse_blocks_skips_leading_front_matter():
    """回归：51 篇文章带 YAML front matter，它不是正文段落。"""
    module = load_tool()
    lines = [
        "---",
        'title: "PostgreSQL 目录快照源码级深度拆解"',
        "date: 2026-10-27 10:00:00",
        "---",
        "",
        "# 正文标题",
        "",
        "真正的第一段。",
    ]
    blocks = module.parse_blocks(lines)
    kinds = [b.kind for b in blocks]
    assert kinds == ["heading", "paragraph"]
    assert blocks[1].text == "真正的第一段。"


def test_str_02_accepts_a_later_positioning_sentence(tmp_path):
    """回归：「本文的目的就是把这 7 个维度讲透」—— 讲 字在 20 字开外。"""
    text = (
        "# 标题\n\n"
        "上一篇我们列了清单。\n\n"
        "那么问题来了——为什么有的数据库能脱颖而出？\n\n"
        "答案藏在这 7 个维度里。本文的目的就是把这 7 个维度讲透。\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_02(doc) == []


def test_str_02_accepts_positioning_in_a_quote_block(tmp_path):
    """回归：定位写在 `> 目标：…` 引用块里，不能当成没有定位。"""
    text = "# 标题\n\n> 目标：理解 PostgreSQL 堆表的页面布局与 MVCC 可见性。\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_02(doc) == []


def test_str_02_accepts_positioning_written_as_analysis(tmp_path):
    """回归：「本文主要分析下…」也是定位句。"""
    text = "# 标题\n\n上期讲过 WAL。本文主要分析下 checkpoint 机制。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_02(doc) == []


def test_str_03_accepts_a_conclusion_section(tmp_path):
    """回归：结尾的「结语 + 结论表」是产物，不能判成没有。"""
    text = (
        "# 标题\n\n"
        "正文讲完了。\n\n"
        "## 结语\n\n"
        "| 维度 | 结论 |\n| --- | --- |\n| 一个订阅几个 worker | 1 个 |\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_03(doc) == []


def test_str_03_accepts_a_modification_guide(tmp_path):
    """回归：「修改指南：要改哪些文件」是货真价实的可带走产物。"""
    text = (
        "# 标题\n\n"
        "正文讲完了。\n\n"
        "## 修改指南：要加新 worker 类型时碰哪些文件\n\n"
        "1. `src/include/replication/worker_internal.h`：加枚举值\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_03(doc) == []


def test_str_03_scans_the_whole_last_section(tmp_path):
    """回归：最后一个大节下面还有子节时，产物标题不能因为「不在最后 8 块」而漏掉。"""
    text = (
        "# 标题\n\n"
        "正文讲完了。\n\n"
        "## 修改指南\n\n"
        "### 12.1 改枚举\n\n"
        "加一个新值。\n\n"
        "### 12.2 改 launcher\n\n"
        "加一个分支。\n\n"
        "### 12.3 改 worker\n\n"
        "改分发逻辑。\n\n"
        "### 12.4 改 Babelfish\n\n"
        "补一张状态表。\n"
    )
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_03(doc) == []


def test_str_02_accepts_a_bold_target_marker(tmp_path):
    """回归：「**目标**：…」带 markdown 强调时也要认得出是定位句。"""
    text = "# 标题\n\n**目标**：理解 PostgreSQL 堆表的页面布局与 MVCC 可见性。\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_str_02(doc) == []


# --- FIG 规则：图示可读性 ------------------------------------------------
#
# 「流程图不能太长，布局要合理，不然一眼看不完」——这一节判的是
# 图的**尺寸**，不是图画得对不对。超限只说明「该拆」。


def _mermaid(source: str) -> str:
    """把一段 mermaid 源码包成一篇 markdown 文章。"""
    return f"# 标题\n\n```mermaid\n{source}\n```\n"


# (mermaid 源码, (框数, 最长路径的框数, 最大扇出))
#
# 这些数字是人工核过的：框数只算 id，最长路径按整图算（不是按行），
# 扇出按**不同的目标**算（同一条边的两种画法只算一条支线）。
MERMAID_SIZE_CASES = (
    ("graph TB\n    A --> B --> C\n", (3, 3, 1)),
    ("graph TB\n    A --> B\n    B --> C\n    C --> D\n", (4, 4, 1)),
    ("graph TB\n    A -->|说明|B\n", (2, 2, 1)),
    ("graph TB\n    subgraph one\n    A --> B\n    end\n", (2, 2, 1)),
    ("stateDiagram-v2\n    [*] --> S1\n    S1 --> S2\n", (2, 2, 1)),
    ("graph TB\n    A --> B\n    B --> A\n", (2, 2, 1)),
    ("graph LR\n    Root --> A\n    Root --> B\n    Root --> C\n", (4, 2, 3)),
    # 同一条边的两种画法（实线 + 虚线）指向同一个目标：只算一条支线
    ("graph TB\n    A --> B\n    A -.-> B\n", (2, 2, 1)),
)


def test_mermaid_size_matches_the_expected_shape():
    """单元：mermaid 尺寸解析的定版用例。"""
    module = load_tool()
    for source, expected in MERMAID_SIZE_CASES:
        assert module._mermaid_size(source) == expected, source


def test_fig_01_flags_a_diagram_with_too_many_boxes(tmp_path):
    body = "\n".join(f"    N{i} --> M{i}" for i in range(16))
    doc = make_doc(tmp_path, _mermaid("graph TB\n" + body))
    signals = load_tool().rule_fig_01(doc)
    assert len(signals) == 1
    assert signals[0].rule == "FIG-01"
    assert signals[0].severity == "warn"


def test_fig_01_accepts_a_balanced_diagram(tmp_path):
    """结构规整的图不该被判超限——只看框数会把好图也抓进来。"""
    body = [f"    Root --> A{i}" for i in range(1, 5)]
    for i in range(1, 5):
        body.append(f"    A{i} --> A{i}L")
        body.append(f"    A{i} --> A{i}R")
    doc = make_doc(tmp_path, _mermaid("graph TB\n" + "\n".join(body)))
    assert load_tool().rule_fig_01(doc) == []


def test_fig_01_flags_a_chain_that_is_too_long(tmp_path):
    chain = " --> ".join(f"S{i}" for i in range(10))
    doc = make_doc(tmp_path, _mermaid(f"graph TB\n{chain}"))
    assert len(load_tool().rule_fig_01(doc)) == 1


def test_fig_01_counts_a_chain_written_one_edge_per_line(tmp_path):
    """回归：链一行写一条边时，图照样是长条，不能漏判。

    按「单行有几个节点」去数的话，这种图每行只有 2 个节点，
    一条十步的链会被算成 2——这是最容易漏的一种写法。
    """
    body = "\n".join(f"    S{i} --> S{i + 1}" for i in range(10))
    doc = make_doc(tmp_path, _mermaid("graph TB\n" + body))
    assert len(load_tool().rule_fig_01(doc)) == 1


def test_fig_01_flags_a_node_with_too_many_branches(tmp_path):
    body = "\n".join(f"    Root --> T{i}" for i in range(8))
    doc = make_doc(tmp_path, _mermaid("graph TB\n" + body))
    assert len(load_tool().rule_fig_01(doc)) == 1


def test_fig_01_ignores_a_plain_code_block(tmp_path):
    """不是 mermaid 的代码块不判——里面写几行步骤是正常事。"""
    body = "\n".join(f"step {i}" for i in range(60))
    doc = make_doc(tmp_path, f"# 标题\n\n```text\n{body}\n```\n")
    assert load_tool().rule_fig_01(doc) == []


def test_fig_01_aggregates_into_one_signal_per_article(tmp_path):
    """一篇一条信号：图的个数不该把「信号」列撑爆。"""
    parts = []
    for k in range(3):
        body = "\n".join(f"    N{k}_{i} --> M{k}_{i}" for i in range(16))
        parts.append(f"```mermaid\ngraph TB\n{body}\n```\n")
    doc = make_doc(tmp_path, "# 标题\n\n" + "\n".join(parts))
    signals = load_tool().rule_fig_01(doc)
    assert len(signals) == 1
    assert "3 张图超限" in signals[0].detail


def test_fig_01_does_not_count_the_diagram_header_as_a_box(tmp_path):
    """回归：``stateDiagram-v2`` 是图类型，不是图里的一个框。"""
    module = load_tool()
    body = "stateDiagram-v2\n    [*] --> S1\n    S1 --> S2\n"
    assert module._mermaid_size(body) == (2, 2, 1)
    doc = make_doc(tmp_path, _mermaid(body))
    assert module.rule_fig_01(doc) == []


def test_fig_01_counts_a_node_whose_name_starts_with_end(tmp_path):
    """回归：``end`` 是收尾一个 subgraph 的关键字，不能把 ``endpoint`` 也吞掉。"""
    module = load_tool()
    assert module._mermaid_size("graph TB\n    endpoint --> server\n") == (2, 2, 1)


def test_fig_01_longest_path_is_stable_on_a_graph_with_a_cycle():
    """回归：图里有环时，最长路径必须每次算出同一个数。

    早先的实现用「在途标记」在 DFS 里当场截断环，而 DFS 从哪个框出发
    取决于 ``set`` 的迭代顺序 —— 字符串的哈希每进程随机，于是同一张图
    在不同进程里算出不同的路径长度（实测 3 / 4 / 5 都出现过）。
    FIG-01 命中与否跟着抖，审校台账上的 warn 数也跟着抖：
    同一棵树连跑四次，warn 在 509 与 510 之间来回跳。

    这张图的最长简单路径是 4 个框：A→B→D→E（环 A→B→C→A 只能算一次）。
    """
    snippet = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('review_check', {str(TOOL)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "sys.modules['review_check'] = m\n"
        "spec.loader.exec_module(m)\n"
        "print(m._longest_path({'A','B','C','D','E'},"
        " [('A','B'),('B','C'),('C','A'),('B','D'),('D','E')]))\n"
    )
    values = set()
    for seed in ("1", "2", "3", "4", "5", "6"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True, encoding="utf-8", errors="replace",
            cwd=REPO_ROOT, env=env,
        )
        values.add(proc.stdout.strip())
    assert len(values) == 1, f"同一张图在不同哈希种子下算出不同的结果：{values}"
    assert values == {"4"}


def test_fig_01_flags_an_over_long_mindmap(tmp_path):
    body = "mindmap\n" + "\n".join(f"    分支{i}" for i in range(21))
    doc = make_doc(tmp_path, _mermaid(body))
    assert len(load_tool().rule_fig_01(doc)) == 1


def test_fig_01_accepts_a_mindmap_within_the_limit(tmp_path):
    body = "mindmap\n" + "\n".join(f"    分支{i}" for i in range(20))
    doc = make_doc(tmp_path, _mermaid(body))
    assert load_tool().rule_fig_01(doc) == []


def test_fig_02_flags_a_reference_far_from_the_figure(tmp_path):
    filler = "\n\n".join(f"第 {i} 段正文。" for i in range(8))
    text = ("# 标题\n\n下图给出这条链路。\n\n" + filler
            + "\n\n```mermaid\ngraph TB\n    A --> B\n```\n")
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_fig_02(doc)
    assert len(signals) == 1
    assert signals[0].rule == "FIG-02"
    assert signals[0].severity == "info"


def test_fig_02_accepts_a_reference_right_above_the_figure(tmp_path):
    text = "# 标题\n\n下图给出这条链路。\n\n```mermaid\ngraph TB\n    A --> B\n```\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_fig_02(doc) == []


def test_fig_02_ignores_a_reference_when_there_is_no_figure(tmp_path):
    text = "# 标题\n\n下图给出这条链路，但下面并没有图。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_fig_02(doc) == []


def test_fig_02_finds_a_reference_in_the_middle_of_a_paragraph(tmp_path):
    """回归：引用常常写在段落中间，按「块首行」找会整个漏掉。"""
    filler = "\n\n".join(f"第 {i} 段正文。" for i in range(8))
    text = ("# 标题\n\n这一段先说了背景，\n下图给出这条链路。\n\n" + filler
            + "\n\n```mermaid\ngraph TB\n    A --> B\n```\n")
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_fig_02(doc)
    assert len(signals) == 1
    assert "下图" in signals[0].detail


def test_the_checker_reports_fig_signals_for_a_real_article(tmp_path):
    """集成：CLI 跑一遍，六张超限的图聚合成一条 FIG-01。

    面向读者的技术文章清空之后没有「真实文章」可跑了，
    这里用一份临时稿把这条聚合行为钉住——它是审校排队列时看的那一列：
    六张图超限是「这篇的图整体太密」**一件事**，不是六条信号。
    """
    diagram = "\n".join(f"    N{i} --> N{i + 1}" for i in range(20))
    block = "```mermaid\ngraph TB\n" + diagram + "\n```"
    target = tmp_path / "六张图.md"
    target.write_text("# 标题\n\n" + "\n\n".join([block] * 6) + "\n", encoding="utf-8")
    result = run_tool(str(target), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    signals = payload["docs"][0]["signals"]
    fig1 = [s for s in signals if s["rule"] == "FIG-01"]
    assert fig1, "六张超限的图，检查器却没报 FIG-01"
    assert fig1[0]["severity"] == "warn"
    # 聚合信号：位置全部写进 detail，而不是每张图一条
    assert "6 张图超限" in fig1[0]["detail"]


def test_stats_count_mermaid_figures_not_just_markdown_images(tmp_path):
    """回归：一篇满是流程图的文章不该报「图 0」。

    ``images`` 只数 markdown 图片语法；mermaid 的图也是图，
    摘要里漏掉它，审校的人就看不出这篇到底有多少张图。
    """
    module = load_tool()
    text = ("# 标题\n\n```mermaid\ngraph TB\n    A --> B\n```\n\n"
            "![图](./images/x.png)\n")
    path = tmp_path / "index.md"
    path.write_text(text, encoding="utf-8")
    doc = module.load_doc(path)
    module.REPO_ROOT = tmp_path        # to_report 要靠它换算相对路径
    report = module.to_report(doc)
    assert report["stats"]["mermaid"] == 1
    assert report["stats"]["images"] == 1


def test_the_text_report_shows_the_total_figure_count(tmp_path):
    """回归：人读摘要里的「图 N」要是 mermaid 与图片之和。"""
    module = load_tool()
    text = ("# 标题\n\n```mermaid\ngraph TB\n    A --> B\n```\n\n"
            "![图](./images/x.png)\n")
    path = tmp_path / "index.md"
    path.write_text(text, encoding="utf-8")
    doc = module.load_doc(path)
    module.REPO_ROOT = tmp_path
    rendered = module.render_text([doc])
    assert "图 2（mermaid 1 + 图片 1）" in rendered


# --- TERM 规则（术语纪律）-------------------------------------------------
#
# 判据在 review/specs/2026-11-24-术语纪律与反造词.md：
# 要么用有公认定义的术语，要么用通用描述，不造词。


def test_term_01_flags_a_coined_term(tmp_path):
    doc = make_doc(tmp_path, "# 标题\n\n发布管线分三步。\n")
    signals = load_tool().rule_term_01(doc)
    assert len(signals) == 1
    assert signals[0].rule == "TERM-01"
    assert signals[0].severity == "warn"
    assert "流程" in signals[0].detail


def test_term_01_scans_the_front_matter(tmp_path):
    """description 会出现在站点列表页——读者看得见，就得一并查。"""
    text = "---\ntitle: 一篇文章\ndescription: 一条查询管线。\n---\n\n# 标题\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_term_01(doc)
    assert len(signals) == 1
    assert signals[0].line == 3


def test_term_01_scans_code_blocks(tmp_path):
    """mermaid 的标签会出现在图上，图上的词也是词。"""
    text = ("# 标题\n\n```mermaid\ngraph TB\n    A[发布管线] --> B\n```\n")
    doc = make_doc(tmp_path, text)
    assert len(load_tool().rule_term_01(doc)) == 1


def test_term_02_is_info_level(tmp_path):
    """行话那一档是「建议」，不是「硬禁」。"""
    doc = make_doc(tmp_path, "# 标题\n\n这一版沉淀了一批改动。\n")
    signals = load_tool().rule_term_02(doc)
    assert len(signals) == 1
    assert signals[0].rule == "TERM-02"
    assert signals[0].severity == "info"


def test_term_03_flags_a_rejected_name(tmp_path):
    doc = make_doc(tmp_path, "# 起步与全景\n\n这一段讲整体。\n")
    signals = load_tool().rule_term_03(doc)
    assert len(signals) == 1
    assert signals[0].rule == "TERM-03"
    assert signals[0].severity == "warn"


def test_clean_text_has_no_term_signal(tmp_path):
    doc = make_doc(tmp_path, "# 架构总览\n\n一条 SQL 从解析到返回要穿过哪些文件。\n")
    module = load_tool()
    assert module.rule_term_01(doc) == []
    assert module.rule_term_02(doc) == []
    assert module.rule_term_03(doc) == []


def content_surface() -> list[Path]:
    """对外内容：`docs/` 与 `drafts/` 里的 markdown。

    审的是 `drafts/` 里那一份（改动稿不覆盖 `docs/`），所以两棵都要看。
    隐藏目录不进（`.remember/`、`.worktrees/` 这些不是仓库的一部分）。
    """
    out: list[Path] = []
    for root in (DOCS, REPO_ROOT / "drafts"):
        for path in sorted(root.rglob("*.md")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part.startswith(".") for part in rel.split("/")):
                continue
            out.append(path)
    return out


def test_content_has_no_coined_term_or_rejected_name():
    """集成：对外内容不该带自造术语，也不该用已被否掉的命名。

    只卡 warn 档（TERM-01/TERM-03）。TERM-02 是「建议具体化」，
    改不改由人定，不该让测试红。
    """
    for path in content_surface():
        result = run_tool(str(path), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        hits = [s for s in payload["docs"][0]["signals"]
                if s["rule"] in ("TERM-01", "TERM-03") and s["severity"] == "warn"]
        assert not hits, f"{path} 还有自造术语或不合格命名：{hits}"


def test_learning_path_stage_titles_follow_the_terminology_rule():
    """学习流的阶段名登记在 JSON 里，检查器只读 markdown——这一条由人守。

    阶段名要跟 `docs/` 里的目录页标题一致，两边都得说人话。
    """
    module = load_tool()
    data = json.loads(
        (REPO_ROOT / "platforms" / "blog" / "site" / "data" / "learning-path.json")
        .read_text(encoding="utf-8")
    )
    bad = []
    for track in data["tracks"]:
        for stage in track["stages"]:
            for word in list(module.TERM_BANNED) + list(module.TERM_BAD_NAMES):
                if word in stage["title"]:
                    bad.append(f"{track['id']}/{stage['id']}「{stage['title']}」含「{word}」")
    assert not bad, bad


# --- HEAD 规则（标题判据）------------------------------------------------
#
# 判据在 review/specs/2026-11-24-标题与章节顺序.md：
# 层级要断得住、顺序跟读者的疑问顺序一致、标题要概括这一节、标题要精简紧凑。


def test_head_01_flags_a_second_h1(tmp_path):
    text = "# 标题\n\n正文。\n\n# 另一个标题\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_01(doc)
    assert len(signals) == 1
    assert signals[0].rule == "HEAD-01"


def test_head_01_flags_a_skipped_level(tmp_path):
    text = "# 标题\n\n## 二级\n\n正文。\n\n#### 四级\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_01(doc)
    assert len(signals) == 1
    assert "跳到 H4" in signals[0].detail


def test_head_02_flags_a_long_title(tmp_path):
    text = "# 标题\n\n## " + "很长的标题" * 6 + "\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_02(doc)
    assert len(signals) == 1
    assert signals[0].rule == "HEAD-02"


def test_head_03_flags_a_marketing_word(tmp_path):
    text = "# 标题\n\n## 一文读懂 PostgreSQL 内核\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_03(doc)
    assert len(signals) == 1
    assert signals[0].severity == "warn"


def test_head_03_reports_a_lazy_word_as_info(tmp_path):
    text = "# 标题\n\n## 深入 WAL\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_03(doc)
    assert len(signals) == 1
    assert signals[0].severity == "info"


def test_head_04_flags_a_closing_heading_in_the_middle(tmp_path):
    text = "# 标题\n\n## 原理\n\n正文。\n\n## 小结\n\n正文。\n\n## 验证\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_04(doc)
    assert len(signals) == 1
    assert "收束标题" in signals[0].detail


def test_head_04_flags_stages_in_the_wrong_order(tmp_path):
    text = "# 标题\n\n## 实践：怎么用\n\n正文。\n\n## 原理：为什么\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_04(doc)
    assert len(signals) == 1
    assert "顺序不对" in signals[0].detail


def test_head_05_flags_an_empty_section(tmp_path):
    text = "# 标题\n\n## 空的一节\n\n## 有内容的一节\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_05(doc)
    assert len(signals) == 1
    assert signals[0].rule == "HEAD-05"


def test_head_05_accepts_a_section_whose_content_is_a_subheading(tmp_path):
    text = "# 标题\n\n## 有子标题的一节\n\n### 子标题\n\n正文。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_head_05(doc) == []


def test_head_06_flags_a_term_the_section_never_mentions(tmp_path):
    text = "# 标题\n\n## WAL 与检查点\n\n这一节讲的是别的。\n"
    doc = make_doc(tmp_path, text)
    signals = load_tool().rule_head_06(doc)
    assert len(signals) == 1
    assert signals[0].severity == "info"


def test_head_06_accepts_a_term_the_section_uses(tmp_path):
    text = "# 标题\n\n## WAL 与检查点\n\n这一节讲 WAL 怎么落盘。\n"
    doc = make_doc(tmp_path, text)
    assert load_tool().rule_head_06(doc) == []


def test_head_rules_skip_module_readme(tmp_path):
    """README 是模块说明，不是稿子——它的空节是刻意的。"""
    module = load_tool()
    path = tmp_path / "README.md"
    path.write_text("# 说明\n\n## 七、这个目录现在是空的\n\n## 下一节\n\n正文。\n",
                    encoding="utf-8")
    doc = module.load_doc(path)
    assert module.rule_head_02(doc) == []
    assert module.rule_head_05(doc) == []


def test_content_has_no_broken_heading_structure():
    """集成：对外内容的标题层级、长度、顺序不该有问题。

    只卡 warn 档。HEAD-03（info 级）、HEAD-06（info 级）不卡——
    标题用词与「标题的词正文没跟着用」都要人判断。
    """
    for path in content_surface():
        result = run_tool(str(path), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        hits = [s for s in payload["docs"][0]["signals"]
                if s["rule"].startswith("HEAD-") and s["severity"] == "warn"]
        assert not hits, f"{path} 的标题有问题：{hits}"
