"""母稿解析：块编号与散文字数。

**口径**（与《长视频三档》§2.1 / §2.4 一致）：

| 口径 | 算什么 | 不算什么 |
| --- | --- | --- |
| 散文 | 去掉 front matter、标题行、代码块内、表格行之后，剩下的非空行的去空白字符数 | front matter |
| mermaid 块 | 语言标注为 `mermaid` 的围栏块 | — |
| code 块 | 其余围栏块 | — |
| table 块 | 连续的表格行 | — |

**夹具是合成的**
----------------
计划 Task 5 原本拿六期真实母稿当夹具（盯住它们的 mermaid 数 / 围栏块数 /
散文字数不漂）。但那六期 **2026-11-18 已清空**——规格 §2.4 自己写着
「这六期已清空，下表是那时的素材统计」，仓库里已经没有那些文件了。

所以口径改由**规格的定义**决定，不依赖具体母稿：这里用手写的夹具把每条规则
盯住，历史数字只校自身的一致性（最后一条测试）。夹具能失败，守卫才有用。
"""
from __future__ import annotations

import pytest

from pyv import motherdoc

FULL_DOC = """---
title: 测试母稿
tags: [测试]
---

# 母稿标题

这是第一段散文。

## 二级标题

- 列表第一项
- 列表第二项

```mermaid
graph TD
  A --> B
```

```python
x = 1
```

| 列一 | 列二 |
| --- | --- |
| 值一 | 值二 |

结尾的散文。
"""

MULTI_DOC = """```mermaid
graph TD
  A --> B
```

```mermaid
sequenceDiagram
  A ->> B: hi
```

```sql
SELECT 1;
```
"""

NESTED_DOC = """````markdown
```python
print("hello")
```
````

正文一句。
"""

HEADINGS_ONLY = """---
title: 只有 front matter
---

# 只有标题

## 二级标题

### 三级标题
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_prose_counts_only_what_is_read_out(tmp_path):
    """散文 = 去掉 front matter、标题、代码块、表格行之后剩下的非空行。

    夹具里的散文共 26 字：
    「这是第一段散文。」8 + 「- 列表第一项」6 + 「- 列表第二项」6
    + 「结尾的散文。」6。

    列表项的**项目符号**算进散文——规格只排除了标题、代码块、表格行，
    没排除列表标记。口径不许偷偷改。
    """
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", FULL_DOC))
    assert doc.prose_chars == 26


def test_the_front_matter_and_the_headings_are_not_prose(tmp_path):
    """front matter 与标题行都不算散文——只留这两样，散文就是 0。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", HEADINGS_ONLY))
    assert doc.prose_chars == 0
    assert doc.title == "只有标题"


def test_a_mermaid_block_and_a_code_block_are_counted_separately(tmp_path):
    """mermaid 块单独一类，code 块是其余围栏块。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", FULL_DOC))
    assert doc.count("mermaid") == 1
    assert doc.count("code") == 1
    assert doc.count("table") == 1


def test_the_blocks_are_numbered_within_their_own_kind(tmp_path):
    """`nth` 是同类块里的序号——mermaid 自己数自己的。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", MULTI_DOC))
    assert doc.count("mermaid") == 2
    assert doc.count("code") == 1
    assert [block.nth for block in doc.blocks_of("mermaid")] == [1, 2]
    assert [block.nth for block in doc.blocks_of("code")] == [1]


def test_the_consecutive_table_rows_are_one_block(tmp_path):
    """连续的表格行算**一块**，不是一行一块。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", FULL_DOC))
    table = motherdoc.find_block(doc, "table", 1)
    assert doc.count("table") == 1
    assert "| 列一 | 列二 |" in table.content
    assert "| 值一 | 值二 |" in table.content


def test_the_title_is_the_first_level_one_heading(tmp_path):
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", FULL_DOC))
    assert doc.title == "母稿标题"


def test_a_fence_is_paired_by_its_own_length(tmp_path):
    """四个反引号的围栏里可以放三个反引号的代码——那还是一个块。

    计划里的实现只看前三个字符，四反引号会被切成两半。
    """
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", NESTED_DOC))
    assert doc.count("code") == 1
    block = motherdoc.find_block(doc, "code", 1)
    assert "print(\"hello\")" in block.content
    assert doc.prose_chars == 5  # 「正文一句。」


def test_find_block_returns_the_nth_block_of_that_kind(tmp_path):
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", MULTI_DOC))
    first = motherdoc.find_block(doc, "mermaid", 1)
    second = motherdoc.find_block(doc, "mermaid", 2)
    assert first.nth == 1 and second.nth == 2
    assert "graph TD" in first.content
    assert "sequenceDiagram" in second.content


def test_find_block_raises_when_the_reference_is_wrong(tmp_path):
    """引用错了要当场报错——不静默返回 None。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", MULTI_DOC))
    with pytest.raises(LookupError):
        motherdoc.find_block(doc, "mermaid", 999)
    with pytest.raises(LookupError):
        motherdoc.find_block(doc, "nonexistent-kind", 1)


def test_a_missing_file_raises(tmp_path):
    """母稿没了是大事，不能当成「这篇没有块」继续走。"""
    with pytest.raises(FileNotFoundError):
        motherdoc.load_motherdoc(tmp_path / "no-such-doc.md")


# ---- 语言标注与引用解析 ---------------------------------------------------


def test_a_block_carries_the_language_of_its_fence(tmp_path):
    """代码块要靠语言标注选词法——没有它所有代码都按纯文本画。"""
    doc = motherdoc.load_motherdoc(_write(tmp_path, "a.md", FULL_DOC))
    code = motherdoc.find_block(doc, "code", 1)
    mermaid = motherdoc.find_block(doc, "mermaid", 1)
    table = motherdoc.find_block(doc, "table", 1)
    assert code.lang == "python"
    assert mermaid.lang == "mermaid"
    assert table.lang == ""


def test_resolve_ref_returns_the_block_the_reference_points_at(tmp_path):
    """引用 → 块。绝对路径直接认（夹具就靠它指到临时目录）。"""
    path = _write(tmp_path, "a.md", MULTI_DOC)
    block = motherdoc.resolve_ref({"doc": str(path), "nth": 2}, "mermaid")
    assert block.nth == 2
    assert "sequenceDiagram" in block.content


def test_resolve_ref_reads_relative_paths_from_the_given_root(tmp_path):
    """相对路径按 `root` 解析（默认是仓库根）。"""
    _write(tmp_path, "a.md", MULTI_DOC)
    block = motherdoc.resolve_ref({"doc": "a.md", "nth": 1}, "mermaid",
                                   root=tmp_path)
    assert "graph TD" in block.content


def test_resolve_ref_refuses_a_broken_reference(tmp_path):
    """引用错了当场报错——不静默返回空块。"""
    path = _write(tmp_path, "a.md", MULTI_DOC)
    with pytest.raises(FileNotFoundError):
        motherdoc.resolve_ref({"doc": str(tmp_path / "no.md"), "nth": 1},
                              "mermaid")
    with pytest.raises(ValueError):
        motherdoc.resolve_ref({"doc": str(path), "nth": 99}, "mermaid")
    with pytest.raises(ValueError):
        motherdoc.resolve_ref({"doc": str(path)}, "mermaid")
    with pytest.raises(ValueError):
        motherdoc.resolve_ref({"doc": str(path), "nth": "x"}, "mermaid")
    with pytest.raises(ValueError):
        motherdoc.resolve_ref({"doc": str(path), "nth": 0}, "mermaid")
    with pytest.raises(ValueError):
        motherdoc.resolve_ref({"doc": "", "nth": 1}, "mermaid")


# 规格 §2.4 的历史统计（那六期已清空，这里只校它自身的一致性）。
SAMPLES = (
    # 主题, mermaid 数, 围栏块总数
    ("并行解码", 21, 97),
    ("CSN 全序", 4, 56),
    ("WAL 顺序", 7, 28),
    ("并行 apply", 7, 27),
    ("结构化 DDL", 3, 50),
    ("行锁", 29, 119),
)


def test_the_historical_sample_table_is_self_consistent():
    """规格 §2.4 记的数字自己对得上：377 个围栏块、71 个 mermaid、306 个纯代码。

    文件没了，只能校数字本身——但**口径**（围栏块含 mermaid）与规格一致，
    这个断言就是口径的锚。
    """
    fences = sum(fences for _, _, fences in SAMPLES)
    mermaid = sum(mermaid for _, mermaid, _ in SAMPLES)
    assert fences == 377
    assert mermaid == 71
    assert fences - mermaid == 306
