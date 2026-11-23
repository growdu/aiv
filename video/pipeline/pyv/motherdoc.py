"""母稿解析：mermaid 块、代码块、表格、散文字数。

母稿（`docs/` 下的 md）是唯一真相。长视频的「画面」直接来自它——
图渲染成 PNG、代码块高亮、表格排版，都不用重新手写内容。
这是「画面不用手写」的第一步。

**计数口径**（与《长视频三档》§2.1 / §2.4 一致，改一处就要改另一处）：

| 口径 | 算什么 | 不算什么 |
| --- | --- | --- |
| **散文** | 去掉 front matter、标题行（`#` 开头）、代码块内、表格行（`|` 开头）之后，剩下的非空行的去空白字符数 | front matter |
| **mermaid 块** | 语言标注为 `mermaid` 的围栏块 | — |
| **code 块** | 其余围栏块 | — |
| **table 块** | 连续的表格行（连续的一段算**一块**） | — |

压缩比拿**散文**做分子：代码与表格在成片里是**画面**、不是被读出来的字，
拿全文做分子会把「画面已经讲清楚的部分」也算成「没讲」（规格 EV-07）。

**两条口径上的老实话**：

- 列表项的**项目符号**（`- `、`1. `）算进散文——规格的规则是「剩下的非空行的
  去空白字符数」，只排除了标题、代码块、表格行，没排除列表标记。
  一个列表项多算一两个字符，对压缩比的影响可以忽略，但**口径不许偷偷改**。
- 围栏按**自己的反引号数量**配对：四个反引号的围栏里可以放三个反引号的代码，
  那算一个块，不会被切成两半。

**引用错了要当场报错**：找不到块就抛 `LookupError`，不静默返回 `None`——
引用错了却安静地产出一支缺画面的片子，比直接炸掉糟糕得多。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: front matter：文件开头的 `---` 到下一个 `---`。
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)",
                             re.DOTALL)

#: 围栏行：三个以上的反引号或波浪号，后面跟语言标注。
FENCE_RE = re.compile(r"^(`{3,}|~{3,})[ \t]*(.*)$")

#: mermaid 块的语言标注。
MERMAID_LANG = "mermaid"

#: 块类型。
KIND_MERMAID = "mermaid"
KIND_CODE = "code"
KIND_TABLE = "table"


@dataclass(frozen=True)
class Block:
    """母稿里的一个可复用内容块。

    `nth` 是**同类块里**的序号，从 1 起——mermaid 块自己数自己的，
    code 块自己数自己的（规格 §5.3：「`nth` 的计数口径按块类型分别计」）。
    """

    kind: str
    nth: int
    content: str


@dataclass(frozen=True)
class MotherDoc:
    """一篇母稿。"""

    path: Path
    title: str
    blocks: tuple[Block, ...]
    prose_chars: int

    def count(self, kind: str) -> int:
        """某一类块的数量。"""
        return sum(1 for block in self.blocks if block.kind == kind)

    def blocks_of(self, kind: str) -> tuple[Block, ...]:
        """某一类块，按原文顺序。"""
        return tuple(block for block in self.blocks if block.kind == kind)


def _dense(text: str) -> int:
    """去掉所有空白后的字符数。"""
    return len(re.sub(r"\s+", "", text))


def _strip_front_matter(text: str) -> str:
    """去掉开头的 front matter。没有 front matter 就原样返回。"""
    return FRONT_MATTER_RE.sub("", text, count=1)


def _fence_lang(info: str) -> str:
    """围栏的语言标注：`python`、`mermaid`、空串。

    信息串里可以有别的参数（```` ```python title=x ````），只取第一个词。
    """
    info = info.strip()
    if not info:
        return ""
    return info.split()[0].strip().lower()


def _parse_blocks(lines: list[str]) -> tuple[list[Block], int]:
    """扫出所有块，顺带累加散文字数。"""
    blocks: list[Block] = []
    prose = 0
    counters = {KIND_MERMAID: 0, KIND_CODE: 0, KIND_TABLE: 0}

    index = 0
    # 围栏状态：打开时记下字符与长度，只有同字符、长度不短于它的才算闭合。
    fence_char = ""
    fence_len = 0
    fence_lang = ""
    fence_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if fence_char:
            # 围栏里：先看是不是闭合行，不是就把这行收进块里。
            match = FENCE_RE.match(stripped)
            if (match and match.group(1)[0] == fence_char
                    and len(match.group(1)) >= fence_len
                    and not match.group(2).strip()):
                kind = KIND_MERMAID if fence_lang == MERMAID_LANG else KIND_CODE
                counters[kind] += 1
                blocks.append(Block(kind=kind, nth=counters[kind],
                                    content="\n".join(fence_lines)))
                fence_char = ""
                fence_lines = []
            else:
                fence_lines.append(line)
            index += 1
            continue

        match = FENCE_RE.match(stripped)
        if match:
            fence_char = match.group(1)[0]
            fence_len = len(match.group(1))
            fence_lang = _fence_lang(match.group(2))
            fence_lines = []
            index += 1
            continue

        if stripped.startswith("|"):
            # 连续的表格行算**一块**
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            counters[KIND_TABLE] += 1
            blocks.append(Block(kind=KIND_TABLE, nth=counters[KIND_TABLE],
                                content="\n".join(table_lines)))
            continue

        if stripped.startswith("#"):
            # 标题行不算散文
            index += 1
            continue

        if stripped:
            prose += _dense(stripped)
        index += 1

    return blocks, prose


def load_motherdoc(path: str | Path) -> MotherDoc:
    """读一篇母稿。

    文件不存在就直接报错（`FileNotFoundError`）——母稿没了是大事，
    不能当成「这篇没有块」继续往下走。
    """
    target = Path(path)
    text = target.read_text(encoding="utf-8", errors="replace")
    body = _strip_front_matter(text)
    lines = body.splitlines()
    blocks, prose = _parse_blocks(lines)
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return MotherDoc(path=target, title=title, blocks=tuple(blocks),
                     prose_chars=prose)


def find_block(doc: MotherDoc, kind: str, nth: int) -> Block:
    """按「类型 + 同类序号」找块。找不到就报错——引用错了要当场发现。"""
    for block in doc.blocks:
        if block.kind == kind and block.nth == nth:
            return block
    raise LookupError(
        f"{doc.path.name} 里没有 {kind} 类的第 {nth} 块"
        f"（该类共 {doc.count(kind)} 块）"
    )
