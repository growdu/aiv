"""起草摘要的工具得挑对人话。

**背景**：``sync-hexo.py`` 会从编辑履历表（``| 编写人 | 编写内容 |``）的
「编写内容」列抽一句写进 front matter 的 ``description``。那一列说的是
**「这次改了什么」**（「理顺结构与定位，修正错误写法」「补充完善解决方案」），
不是「这篇文章是什么」。85 篇文章的摘要因此是履历句；另有 483 篇没有
description，卡片摘要退回正文前 80 个字——线上有卡片以「TL;DR」「[TOC]」
开头。

**这个工具做什么**：从正文里抽**第一个真正的段落**，当候选摘要。抽的时候
按顺序跳过这些不是摘要的东西：

    履历表 → TL;DR 框 → [TOC] → 引用块 → 代码块 → 标题行 → 表格 →
    目录链接行 → 列表

**它不自动写回源文件**——``review/description-drafts.md`` 是一张给作者过目的
表（slug | 现在的履历句 | 起草的摘要 | 需人工确认 ☐）。要写回得显式加
``--write``。

**这里断言的是行为**：喂一段正文，看抽出来的是哪一句。工具挑错了句子，
测试就该红——「抽出来了一段话」不算通过。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "draft-descriptions.py"


def _load():
    spec = importlib.util.spec_from_file_location("draft_descriptions", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract():
    """契约层（``publish/publishkit``）——摘要的长度上限归它管。"""
    import sys

    publish_dir = str(REPO / "publish")
    if publish_dir not in sys.path:
        sys.path.insert(0, publish_dir)
    import publishkit

    return publishkit


TABLE = (
    "| 编写人 | 编写内容 | 编写时间 |\n"
    "| --- | --- | --- |\n"
    "| growdu | 初稿，补充完善解决方案 | 2024-01-01 |\n"
)


# --- 抽哪一句 ---------------------------------------------------------------


def test_it_takes_the_first_real_paragraph():
    """第一个真正的段落就是摘要。"""
    mod = _load()

    body = "# 标题\n\n这是一篇讲查询管线的文章，从执行器讲到落盘。\n\n后面还有别的段落。\n"

    assert mod.draft_description(body) == "这是一篇讲查询管线的文章，从执行器讲到落盘。"


def test_it_skips_the_editing_history_table():
    """履历表不是摘要——它是编辑记录。"""
    mod = _load()

    body = TABLE + "\n这是一篇讲 PostgreSQL 复制槽的文章。\n"

    assert mod.draft_description(body) == "这是一篇讲 PostgreSQL 复制槽的文章。"


def test_it_skips_the_tldr_box():
    """TL;DR 引用块不是摘要——它本来就是摘要，别重复。"""
    mod = _load()

    body = "> **TL;DR**\n> 一句话说清这篇在讲什么。\n\n正文的第一段才是摘要。\n"

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_the_table_of_contents():
    """``[TOC]`` 不是摘要。"""
    mod = _load()

    body = "[TOC]\n\n## 第一节\n\n正文的第一段才是摘要。\n"

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_code_blocks():
    """代码块不是摘要——一半的卡片摘要曾经是半行代码。"""
    mod = _load()

    body = (
        "```bash\n"
        "psql -h 127.0.0.1 -U postgres\n"
        "```\n\n"
        "正文的第一段才是摘要。\n"
    )

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_a_code_block_that_contains_a_blank_line():
    """代码块**中间**有空行时，块里的内容也不该漏出来。

    围栏代码块按空行切分后，第二段不再以 ````` 开头——于是那一段被当成了
    正文段落。有一批文章的摘要就是从代码块里漏出来的半行代码
    （``echo \"[*] 修复 certs/Makefile…``）。
    """
    mod = _load()

    body = (
        "```bash\n"
        "psql -h 127.0.0.1 -U postgres\n"
        "\n"
        "echo \"[*] 修复 certs/Makefile 中的 Canonical PEM 依赖\"\n"
        "```\n\n"
        "正文的第一段才是摘要。\n"
    )

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_a_fenced_block_that_is_indented_inside_a_list():
    """列表里的代码块，围栏前面有缩进——那也是代码。

    有一批文章的摘要就是从这种块里漏出来的（``function main() { … }``）。
    """
    mod = _load()

    body = (
        "- caller\n\n"
        "    ```shell\n"
        "    #!/bin/bash\n"
        "    var1=\"caller\"\n"
        "\n"
        "    function main()\n"
        "    {\n"
        "        echo \"hi\"\n"
        "    }\n"
        "    ```\n\n"
        "正文的第一段才是摘要。\n"
    )

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_a_numbered_list_item_written_with_a_dun_hao():
    """「1、$TMOUT 系统环境变量」是列表项，不是摘要。"""
    mod = _load()

    body = "1、$TMOUT 系统环境变量\n\n正文的第一段才是摘要。\n"

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_prefers_nothing_over_a_stub_too_short_to_mean_anything():
    """抽出来的段落太短，就**没有摘要**——别写一句「pg」上去。

    摘要会进 og:description、卡片、RSS。「pg」这种碎片写进去，
    读者看到的是「这个博客没写完」。
    """
    mod = _load()

    body = "# 标题\n\npg\n\n---\n"

    assert mod.draft_description(body) is None


def test_it_skips_headings_and_tables():
    """标题行和表格行都不是摘要。"""
    mod = _load()

    body = (
        "## 目录\n\n"
        "| 名字 | 说明 |\n"
        "| --- | --- |\n"
        "| foo | bar |\n\n"
        "正文的第一段才是摘要。\n"
    )

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_skips_the_link_list():
    """目录链接行（``- [标题](#锚点)``）不是摘要。"""
    mod = _load()

    body = (
        "- [第一节](#第一节)\n"
        "- [第二节](#第二节)\n\n"
        "正文的第一段才是摘要。\n"
    )

    assert mod.draft_description(body) == "正文的第一段才是摘要。"


def test_it_strips_the_inline_markdown_markers():
    """摘要里的 markdown 标记到 meta / 卡片 / RSS 里是字面量。

    ``**PostgreSQL**`` 显示成带星号的——所以起草时就得去掉。
    """
    mod = _load()

    body = "这篇讲 **PostgreSQL** 的 `MVCC` 机制，和快照的关系。\n"

    got = mod.draft_description(body)

    assert got == "这篇讲 PostgreSQL 的 MVCC 机制，和快照的关系。"


def test_it_strips_the_markdown_links():
    """``[文字](链接)`` 只留文字——链接在摘要里是死的。"""
    mod = _load()

    body = "这篇讲 [复制槽](https://example.com/x) 和它的应用场景。\n"

    got = mod.draft_description(body)

    assert "复制槽" in got
    assert "https://example.com" not in got


def test_it_cuts_to_the_contract_limit():
    """契约上限 150 字（publish/spec/00-架构设计.md §4.1）。"""
    mod = _load()

    body = "长" * 400 + "\n"

    got = mod.draft_description(body)

    assert got is not None
    assert len(got) <= 150


def test_it_cuts_by_the_length_the_contract_counts():
    """引号在 front matter 里要转义——契约层按**转义后**的长度算。

    契约层（``publish/publishkit/contract.py`` 的 ``_unquote``）剥外层引号
    但**不反转义**：``\\"`` 在那里算 2 个字符。所以一段正好 150 字的正文，
    带 2 个英文双引号，进 front matter 就是 154 字——超上限，CI 报错。

    起草的时候就得按契约的口径算长度，不然写回去就是违约。
    """
    mod = _load()

    body = '"一张表的元数据"这段话里面有两个引号。' + "补字用的内容。" * 20

    got = mod.draft_description(body)

    assert got is not None
    line = 'description: "{}"\n'.format(mod.sync.yaml_escape(got))
    fields, _ = _contract().parse_front_matter("---\n" + line + "---\n")
    violations = _contract().validate_fields(fields)
    assert not violations, "{}：{}".format(got, violations)


def test_it_returns_nothing_when_there_is_no_paragraph_to_take():
    """只有代码和标题的文章，抽不出摘要——宁可没有，别硬凑。"""
    mod = _load()

    body = "# 标题\n\n```go\nfunc main() {}\n```\n"

    assert mod.draft_description(body) is None


# --- 写回源文件 -------------------------------------------------------------


def test_it_writes_the_description_into_an_existing_front_matter():
    """front matter 里已经有 description 的，**替换**它（不重复写一行）。"""
    mod = _load()

    text = (
        "---\n"
        'title: "某篇文章"\n'
        'description: "旧的摘要"\n'
        "---\n\n"
        "正文。\n"
    )

    got = mod.set_description(text, "新的摘要")

    assert 'description: "新的摘要"' in got
    assert "旧的摘要" not in got
    assert got.count("description:") == 1


def test_it_adds_a_front_matter_when_the_file_has_none():
    """没有 front matter 的源文件，加一个——sync 以源为准，不覆盖。"""
    mod = _load()

    text = "# 某篇文章\n\n正文。\n"

    got = mod.set_description(text, "新的摘要")

    assert got.startswith("---\n")
    assert 'description: "新的摘要"' in got
    assert "# 某篇文章" in got


def test_it_keeps_the_body_untouched():
    """只动 front matter——正文一个字都不能改。"""
    mod = _load()

    body = "# 某篇文章\n\n正文的第一段。\n\n第二段。\n"
    got = mod.set_description(body, "新的摘要")

    assert got.endswith(body)


# --- 跑一遍工具 -------------------------------------------------------------


def _run_tool(root: Path, *args):
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=str(root),
        capture_output=True,
        text=True,
    )


def _corpus(root: Path) -> None:
    (root / "docs" / "db").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "db" / "one.md").write_text(
        "---\ntitle: 第一篇\n---\n\n" + TABLE + "\n这是第一篇的正文摘要。\n",
        encoding="utf-8",
    )
    (root / "docs" / "db" / "two.md").write_text(
        "这是第二篇的正文摘要，没有 front matter。\n", encoding="utf-8"
    )


def test_the_tool_writes_a_review_table(tmp_path):
    """工具产出一张给作者过目的表。"""
    _corpus(tmp_path)

    result = _run_tool(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    table = (tmp_path / "review" / "description-drafts.md").read_text(encoding="utf-8")
    assert "db/one.md" in table
    assert "这是第一篇的正文摘要。" in table
    assert "db/two.md" in table


def test_the_tool_does_not_touch_the_source_files_by_default(tmp_path):
    """默认**不**写回源文件——作者要过目。"""
    _corpus(tmp_path)

    result = _run_tool(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    one = (tmp_path / "docs" / "db" / "one.md").read_text(encoding="utf-8")
    assert "description:" not in one, one


def test_the_tool_writes_back_when_asked(tmp_path):
    """``--write`` 才写回源文件。"""
    _corpus(tmp_path)

    result = _run_tool(tmp_path, "--write")

    assert result.returncode == 0, result.stdout + result.stderr
    one = (tmp_path / "docs" / "db" / "one.md").read_text(encoding="utf-8")
    assert 'description: "这是第一篇的正文摘要。"' in one, one
    two = (tmp_path / "docs" / "db" / "two.md").read_text(encoding="utf-8")
    assert 'description: "这是第二篇的正文摘要，没有 front matter。"' in two, two


def test_the_tool_does_not_overwrite_a_description_someone_already_wrote(tmp_path):
    """已经有摘要的，``--write`` **不碰**。

    摘要写进 front matter 之后，人工改过的那几条比工具起草的更准。
    工具再跑一次就把它们盖回「正文的第一段」——那是拿自动稿换人工稿，
    方向反了。人工稿要留着，除非显式说「覆盖」。
    """
    _corpus(tmp_path)
    two = tmp_path / "docs" / "db" / "two.md"
    two.write_text(
        "---\n" 'description: "人工改过的摘要"\n' "---\n\n" "这是第二篇的正文摘要。\n",
        encoding="utf-8",
    )

    result = _run_tool(tmp_path, "--write")

    assert result.returncode == 0, result.stdout + result.stderr
    assert 'description: "人工改过的摘要"' in two.read_text(encoding="utf-8")


def test_the_tool_overwrites_when_told_to(tmp_path):
    """``--overwrite`` 就是要盖掉人工稿——显式说出来的事照做。"""
    _corpus(tmp_path)
    two = tmp_path / "docs" / "db" / "two.md"
    two.write_text(
        "---\n" 'description: "人工改过的摘要"\n' "---\n\n" "这是第二篇的正文摘要。\n",
        encoding="utf-8",
    )

    result = _run_tool(tmp_path, "--write", "--overwrite")

    assert result.returncode == 0, result.stdout + result.stderr
    text = two.read_text(encoding="utf-8")
    assert 'description: "这是第二篇的正文摘要。"' in text, text
    assert "人工改过的摘要" not in text, text
