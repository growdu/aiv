#!/usr/bin/env python3
"""Markdown 保真闸门：扫出格式问题，逐条报 ``文件:行号``，有错就退 1。

这是**构建闸门**（build gate）：CI 跑它，退出码非 0 当构建失败。
它只看**格式**，不看内容质量——内容的对错是审校层的事。

用法
----
    python3 platforms/blog/site/tools/check-markdown.py            # 扫 docs/ 与 drafts/
    python3 platforms/blog/site/tools/check-markdown.py a.md b/   # 扫指定路径
    python3 platforms/blog/site/tools/check-markdown.py --max-errors 200

退出码
------
    0  没有错误（只有警告也算干净）
    1  有错误——CI 应当失败
    2  用法错误（路径不存在等）

输出
----
每个问题一行，格式 ``路径:行号: [规则] 消息``；警告行多一个 ``warn:`` 标记
（``路径:行号: warn: [规则] 消息``）。最后一行是汇总，计数**永远**按真实总数
算（``--max-errors`` 只截断打印，不截断统计）。

规则
====
错误（退出码 1）
----------------
``odd-fence``
    代码块没有闭合——开头那个围栏到文件尾都没等到收尾的围栏。
``nested-fence``
    围栏行缩进了 4 个空格以上。缩进 4 格的围栏在 Markdown 里是**缩进代码块**，
    不是围栏，渲染出来是一坨代码而不是代码框。
    （例外：围栏在某个列表项里、相对该项内容缩进不超过 3 格时，它是列表里的
    合法围栏——CommonMark 允许列表项内部的围栏按该项的缩进排版。本检查器认
    这个例外，否则 dpdk 那些文件里的嵌套代码块会全被误报。）
``fence-lang``
    围栏行上除了语言标签还有别的东西（`````sqlSELECT * FROM foo``），
    或者语言标签整个不认（高亮器和别名表里都没有）。
``lang-alias``
    语言是个**别名**，高亮器不认，要换成规范写法（``C`` → ``c``）。
    规范写法见 ``site/data/lang-alias.json``。
``mermaid-fence``
    ```` ```mermaid ```` 围栏行有行尾空白，或者整块是空的。
``mermaid-first-line``
    mermaid 块的第一行不是图类型关键字（``flowchart`` / ``graph`` /
    ``sequenceDiagram`` ……）。mermaid 解析不了，渲染直接空白。
``table-cols``
    表格的表头行、分隔行、数据行列数不一致。列数不一致的表格在 GFM 里
    根本不会被当成表格渲染。
``empty-fence``
    代码块里一行内容都没有。

警告（不影响退出码）
------------------
``fence-no-lang``
    围栏没有语言标签。高亮器不会上色，但内容还是能看——所以只是提醒。

怎么判断「语言不认」
--------------------
两个来源：

* ``site/data/lang-alias.json``：token → 规范写法。里面有别名（``C`` → ``c``），
  也有规范写法本身（``c`` → ``c``）。
* 本模块的 ``EXTRA_KNOWN``：高亮器认的常见写法（``shell``、``sh``、``console``……）。
  表里也记着它们的规范写法，但既然高亮器认，就不报——避免一次改几百个文件。

于是：token 在别名表里、且高亮器不认 → ``lang-alias``（给出规范写法）；
token 两边都不认 → ``fence-lang``（语言不认识）。
"""

import argparse
import json
import re
import sys
from collections import namedtuple
from pathlib import Path

# 站点的 tools/ 深了四层，根 tools/paths.py 是路径常量的唯一出处。
_SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(_SCRIPT.parents[4] / "tools"))
from paths import DOCS, REPO_ROOT, SITE_DATA  # noqa: E402

#: 草稿箱——改动稿先落这儿，过审才进 docs/（见 docs 里的流程协议）。
DRAFTS = REPO_ROOT / "drafts"

#: 围栏语言别名表。
LANG_ALIAS_FILE = SITE_DATA / "lang-alias.json"

#: 高亮器认的写法（常见别名）。这些 token 不报 lang-alias——
#: 别名表里也记着它们的规范写法，但既然高亮器认，就不值得为它改几百个文件。
EXTRA_KNOWN = frozenset(
    {
        "bat",
        "cfg",
        "cmd",
        "conf",
        "console",
        "csv",
        "dos",
        "ejs",
        "golang",
        "hpp",
        "js",
        "make",
        "md",
        "ps1",
        "rst",
        "sh",
        "shellscript",
        "shell",
        "text",
        "ts",
        "txt",
        "yml",
    }
)

#: 围栏行：缩进 + 三个以上反引号（或波浪号）+ 信息串。
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
#: 合法的语言 token。
LANG_TOKEN_RE = re.compile(r"^[A-Za-z0-9_+#.-]+")
#: 列表项：缩进 + 标记 + 空格。
LIST_RE = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+)")
#: 表格分隔行里的一个格子。
DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")

#: mermaid 认的图类型关键字（块的第一行必须落在这些里面）。
MERMAID_GRAPH_KEYWORDS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "quadrantChart",
    "gitGraph",
)

#: 一条问题。
Problem = namedtuple("Problem", "path line rule message warning")


def load_alias_map(path=LANG_ALIAS_FILE):
    """读别名表：token → 规范写法。"""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def known_languages(alias_map):
    """高亮器认的 token 集合：别名表里的规范写法 + 别名表里的恒等项 + 常见别名。"""
    known = set(EXTRA_KNOWN)
    for token, canonical in alias_map.items():
        known.add(canonical)
        if token == canonical:
            known.add(token)
    return known


def _indent_of(line):
    """行首缩进宽度（一个 tab 当 4 格）。"""
    width = 0
    for char in line:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            break
    return width


def _fence_of(line):
    """这行是围栏行吗？返回 (缩进, 围栏字符, 围栏长度, 信息串)。"""
    match = FENCE_RE.match(line)
    if not match:
        return None
    marker = match.group(2)
    return _indent_of(line), marker[0], len(marker), match.group(3)


def _row_cells(line):
    """把一行表格切成格子；行里没有裸竖线就返回 None。

    竖线出现在代码块里（```a|b```）或者被转义（``a\\|b``）都不算分隔符。
    """
    text = line.strip()
    cells = []
    current = []
    in_code = False
    code_len = 0
    saw_pipe = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and text[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "`":
            end = index
            while end < len(text) and text[end] == "`":
                end += 1
            run = end - index
            if not in_code:
                in_code = True
                code_len = run
            elif run == code_len:
                in_code = False
            current.append(text[index:end])
            index = end
            continue
        if char == "|" and not in_code:
            cells.append("".join(current))
            current = []
            saw_pipe = True
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current))
    if not saw_pipe:
        return None
    if cells and not cells[0].strip():
        cells.pop(0)
    if cells and not cells[-1].strip():
        cells.pop()
    return cells


def _is_delimiter_row(cells):
    """这行是表格的分隔行吗（``| --- | --- |``）？"""
    return bool(cells) and all(
        DELIMITER_CELL_RE.fullmatch(cell.strip()) for cell in cells
    )


def _update_list_stack(stack, line, indent):
    """维护「当前打开的列表项的内容缩进」栈。

    CommonMark 里列表项的内容按标记宽度缩进；项内的围栏只要相对该项的
    内容缩进不超过 3 格，就仍然是围栏（不是缩进代码块）。这个栈就是用来
    判这件事的。
    """
    if not line.strip():
        return
    while stack and indent < stack[-1]:
        stack.pop()
    marker = LIST_RE.match(line)
    if marker and (not stack or indent >= stack[-1]):
        width = len(marker.group(2)) + len(marker.group(3))
        stack.append(indent + width)


def _fence_is_nested_ok(indent, list_indents):
    """缩进超过 3 格的围栏，还算不算围栏？

    顶层算不算，取决于它是不是在某个列表项里：相对该项内容缩进不超过
    3 格，就还是围栏（合法）；否则它渲染成缩进代码块。
    """
    return any(indent - item_indent <= 3 for item_indent in list_indents)


def _find_blocks(lines, path=None):
    """找出文件里所有代码块。

    返回 ``(blocks, in_code, nested)``：blocks 里每项是
    ``(开围栏行号, 收围栏行号或 None, 缩进, 围栏字符, 围栏长度, 信息串)``，
    行号从 0 起；``in_code`` 是布尔数组，标出被代码块占住的行；``nested``
    是缩进代码块（不是围栏）的问题列表。
    """
    blocks = []
    in_code = [False] * len(lines)
    nested = []
    list_indents = []
    index = 0
    while index < len(lines):
        line = lines[index]
        indent = _indent_of(line)
        fence = _fence_of(line)
        if fence is None:
            _update_list_stack(list_indents, line, indent)
            index += 1
            continue
        fence_indent, char, length, info = fence
        _update_list_stack(list_indents, line, fence_indent)
        if fence_indent > 3 and not _fence_is_nested_ok(fence_indent, list_indents):
            # 缩进代码块，不是围栏。
            if path is not None:
                nested.append(
                    Problem(
                        path,
                        index + 1,
                        "nested-fence",
                        f"fence is indented {fence_indent} spaces: "
                        "it renders as an indented code block",
                        False,
                    )
                )
            index += 1
            continue
        closing = None
        for probe in range(index + 1, len(lines)):
            candidate = _fence_of(lines[probe])
            if candidate is None:
                continue
            probe_indent, probe_char, probe_len, probe_info = candidate
            if probe_char != char or probe_len < length or probe_info.strip():
                continue
            if probe_indent > fence_indent + 3:
                continue
            closing = probe
            break
        blocks.append((index, closing, fence_indent, char, length, info))
        if closing is None:
            for probe in range(index, len(lines)):
                in_code[probe] = True
            break
        for probe in range(index, closing + 1):
            in_code[probe] = True
        index = closing + 1
    return blocks, in_code, nested


def _check_language(problems, path, line_no, info, alias_map, known):
    """检查围栏行的语言标签。返回规范化后的语言（认不出来就是 None）。"""
    token_match = LANG_TOKEN_RE.match(info)
    token = token_match.group(0) if token_match else ""
    remainder = info[len(token) :].strip()
    if not token:
        problems.append(
            Problem(
                path,
                line_no,
                "fence-lang",
                f"fence line has content but no language tag: {info!r}",
                False,
            )
        )
        return None
    if remainder:
        problems.append(
            Problem(
                path,
                line_no,
                "fence-lang",
                f"fence line has content after the language tag: {info!r}",
                False,
            )
        )
        return None
    canonical = alias_map.get(token)
    if canonical is not None and token not in known:
        problems.append(
            Problem(
                path,
                line_no,
                "lang-alias",
                f"language {token!r} should be {canonical!r}",
                False,
            )
        )
        return canonical
    if token not in known:
        problems.append(
            Problem(
                path,
                line_no,
                "fence-lang",
                f"unknown language {token!r}",
                False,
            )
        )
        return None
    return token


def _check_mermaid(problems, path, lines, block, canonical_lang):
    """mermaid 块的专属检查。"""
    open_idx, close_idx = block[0], block[1]
    if canonical_lang != "mermaid":
        return
    line_no = open_idx + 1
    raw = lines[open_idx]
    if raw != raw.rstrip():
        problems.append(
            Problem(
                path,
                line_no,
                "mermaid-fence",
                "mermaid fence line has trailing whitespace",
                False,
            )
        )
    if close_idx is None:
        return
    content = [line for line in lines[open_idx + 1 : close_idx] if line.strip()]
    if not content:
        problems.append(
            Problem(path, line_no, "mermaid-fence", "mermaid block is empty", False)
        )
        return
    first = content[0].strip()
    if first.startswith("%%"):
        # mermaid 指令/注释行不算图的第一行，往后找真正的第一行。
        for line in content:
            candidate = line.strip()
            if candidate.startswith("%%"):
                continue
            first = candidate
            break
    if not any(first.startswith(word) for word in MERMAID_GRAPH_KEYWORDS):
        problems.append(
            Problem(
                path,
                line_no,
                "mermaid-first-line",
                f"mermaid block starts with {first[:40]!r}, "
                "which is not a diagram keyword",
                False,
            )
        )


def _check_tables(problems, path, lines, in_code):
    """检查表格的列数是否一致。"""
    index = 0
    while index < len(lines):
        if in_code[index]:
            index += 1
            continue
        line = lines[index]
        if _indent_of(line) >= 4:
            index += 1
            continue
        cells = _row_cells(line)
        if cells is None or index + 1 >= len(lines):
            index += 1
            continue
        delimiter = _row_cells(lines[index + 1])
        if delimiter is None or not _is_delimiter_row(delimiter):
            index += 1
            continue
        header_count = len(cells)
        if len(delimiter) != header_count:
            problems.append(
                Problem(
                    path,
                    index + 1,
                    "table-cols",
                    f"header has {header_count} cells "
                    f"but the separator has {len(delimiter)}",
                    False,
                )
            )
        probe = index + 2
        while probe < len(lines):
            if in_code[probe] or not lines[probe].strip():
                break
            row = _row_cells(lines[probe])
            if row is None:
                break
            if len(row) != header_count:
                problems.append(
                    Problem(
                        path,
                        probe + 1,
                        "table-cols",
                        f"row has {len(row)} cells, header has {header_count}",
                        False,
                    )
                )
            probe += 1
        index = probe


def check_text(text, path, alias_map, known):
    """检查一份 markdown，返回问题列表。"""
    problems = []
    lines = text.splitlines()
    blocks, in_code, nested = _find_blocks(lines, path)
    problems.extend(nested)

    for open_idx, close_idx, fence_indent, _char, _length, info in blocks:
        line_no = open_idx + 1
        if close_idx is None:
            problems.append(
                Problem(
                    path,
                    line_no,
                    "odd-fence",
                    "code block opened here is never closed",
                    False,
                )
            )
            continue
        stripped = info.strip()
        canonical = None
        if not stripped:
            problems.append(
                Problem(
                    path,
                    line_no,
                    "fence-no-lang",
                    "fence has no language tag",
                    True,
                )
            )
        else:
            canonical = _check_language(
                problems, path, line_no, stripped, alias_map, known
            )
            _check_mermaid(problems, path, lines, (open_idx, close_idx), canonical)
        if not any(line.strip() for line in lines[open_idx + 1 : close_idx]):
            # 空 mermaid 块由 mermaid-fence 报，不重复报一遍 empty-fence。
            if canonical != "mermaid":
                problems.append(
                    Problem(
                        path,
                        line_no,
                        "empty-fence",
                        "code block has no content",
                        False,
                    )
                )

    _check_tables(problems, path, lines, in_code)
    return problems


def iter_markdown(targets):
    """列出要扫的 markdown 文件（顺序稳定）。"""
    seen = set()
    for target in targets:
        target = Path(target)
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(target.rglob("*.md"))
        else:
            raise FileNotFoundError(target)
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            yield path


def _display_path(path):
    """仓库里的文件显示成仓库相对路径，仓库外的显示原样。"""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def scan(targets, alias_map=None, known=None):
    """扫一批目标，返回问题列表。"""
    if alias_map is None:
        alias_map = load_alias_map()
    if known is None:
        known = known_languages(alias_map)
    problems = []
    for path in iter_markdown(targets):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise OSError(f"读不了 {path}: {error}") from error
        display = _display_path(path)
        problems.extend(check_text(text, display, alias_map, known))
    problems.sort(key=lambda item: (item.path, item.line, item.rule))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check-markdown",
        description="扫 markdown 的格式问题（构建闸门：有错就退 1）。",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="要扫的文件或目录（默认 docs/ 与 drafts/）",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=50,
        help="最多打印多少行问题（默认 50；汇总计数始终是真实总数）",
    )
    args = parser.parse_args(argv)

    if args.max_errors < 0:
        print("--max-errors 不能是负数", file=sys.stderr)
        return 2

    targets = [Path(item) for item in args.paths] or [DOCS, DRAFTS]
    try:
        problems = scan(targets)
    except (FileNotFoundError, OSError) as error:
        print(f"用不了这个路径：{error}", file=sys.stderr)
        return 2

    errors = [item for item in problems if not item.warning]
    warnings = [item for item in problems if item.warning]

    printed = 0
    for item in problems:
        if printed >= args.max_errors:
            break
        marker = "warn: " if item.warning else ""
        print(f"{item.path}:{item.line}: {marker}[{item.rule}] {item.message}")
        printed += 1
    if printed < len(problems):
        print(f"... 还有 {len(problems) - printed} 条没打印（--max-errors 截断的）")

    counts = {}
    for item in problems:
        key = f"warn:{item.rule}" if item.warning else item.rule
        counts[key] = counts.get(key, 0) + 1
    detail = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(
        f"summary: errors={len(errors)} warnings={len(warnings)}"
        + (f" | {detail}" if detail else "")
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
