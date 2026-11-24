#!/usr/bin/env python3
"""审校信号检查器 —— 把 review/README.md 里的机械指标变成可复现的信号。

为什么存在
----------
``review/README.md`` 定义了一套严谨的内容审校规范，但其中最容易漏的一类检查
（AI 味信号、证据密度、章节结构）靠人眼数：同一篇文章今天判「有 AI 味」、
明天判「没有」，谁都说不清依据，也无法回归。

这个脚本把这类**可计算的**指标固定下来，对每篇文章输出一组带编号的信号
（位置、摘录、计数）。它**不下结论**——「是不是空泛评价」「技术深度够不够」
仍然要读上下文的人来判断。工具只负责把「值得看一眼的地方」标出来。

信号不是门禁：命中信号不会让脚本返回非零退出码。一篇老文章的历史问题
不该永久卡住流水线。

用法::

    python3 tools/review-check.py docs/source-tracks/postgresql/transaction-mvcc/postgresql-mvcc/index.md
    python3 tools/review-check.py docs/database docs/db --json --out /tmp/s.json

只读：不修改任何被检文件，也不往仓库里写文件。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"

# 术语词表是**共享规则文件**（仓库根 `rules/terminology.json`），
# 读取器是 `tools/terminology_rules.py`。脚本自己跑时 `sys.path[0]`
# 就是 `tools/`，被当模块 import 时（测试里）未必在——所以自己塞进去。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminology_rules import load_terminology  # noqa: E402

HEADING = "heading"
PARAGRAPH = "paragraph"
CODE = "code"
LIST = "list"
TABLE = "table"
QUOTE = "quote"

FENCE_RE = re.compile(r"^\s*(```+|~~~+)(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
QUOTE_RE = re.compile(r"^\s*>")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# 链接与图片的区别在 ``!`` 上，而 ``!`` 出现在 ``[`` **之前**——
# 用 ``(?<!\!)`` 挂在 ``]`` 前面是拦不住图片的，只能把 ``!`` 收进捕获组。
LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


@dataclass
class Block:
    kind: str
    text: str
    line: int
    level: int = 0
    # 代码块的语言标记（```mermaid / ```c / ```shell …）。空串表示没有标记。
    # mermaid 的图要单独识别，所以这个信息不能丢在解析阶段。
    lang: str = ""


@dataclass
class Signal:
    rule: str
    severity: str
    line: int
    excerpt: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "excerpt": self.excerpt,
            "detail": self.detail,
        }


@dataclass
class Doc:
    path: Path
    pillar: str
    slug: str
    title: str
    text: str
    lines: list[str]
    blocks: list[Block]
    kind: str = "article"
    signals: list[Signal] = field(default_factory=list)
    depth: dict = field(default_factory=dict)

    @property
    def rel_path(self) -> str:
        """The path shown to the reader.

        Usually relative to the repository root. A file **outside** the
        repository (a scratch copy in a temp directory, a draft on
        another disk) still has to be checkable — the relative path is
        for humans, it is not a criterion — so fall back to the
        absolute path instead of raising.
        """
        try:
            return self.path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    def paragraphs(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == PARAGRAPH]

    def excerpt(self, line: int, limit: int = 120) -> str:
        """The source line at ``line`` (1-based), truncated."""
        if 1 <= line <= len(self.lines):
            text = self.lines[line - 1].strip()
        else:
            text = ""
        return text[:limit]


# 规则注册表：每个任务往里追加自己的规则函数。
RULES: list = []


# --- AI 味信号 -------------------------------------------------------------
#
# 对应 review/README.md 的「常见 AI 味信号」一节。每条规则只标位置，
# 不下结论——连接词多不等于文风差，得看上下文。

CONNECTORS = ("首先", "其次", "最后", "此外", "值得注意的是",
              "总而言之", "综上所述", "总的来说", "事实上")
CONNECTOR_RATIO = 0.15

VAGUE_WORDS = ("高效", "全面", "显著", "至关重要", "强大", "极大",
               "非常好", "行业领先", "完美")
LONG_PARAGRAPH = 200

GENERIC_ENDINGS = ("希望本文", "本文到此结束", "以上就是", "让我们一起")
GENERIC_ENDING_RE = re.compile(r"随着.{0,20}的发展")

SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;]")
DUPLICATE_THRESHOLD = 0.85
DUPLICATE_MIN_LEN = 12
DUPLICATE_MIN_CJK = 15
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _paragraphs_with_index(doc: Doc) -> list[tuple[int, Block]]:
    return [(index, b) for index, b in enumerate(doc.blocks) if b.kind == PARAGRAPH]


def rule_aif_01(doc: Doc) -> list[Signal]:
    """Paragraphs that open with a structural connector.

    Only the paragraph start counts: 「最后」 inside a sentence is not a
    structural connector, and counting it would drown the signal in noise.
    """
    paragraphs = doc.paragraphs()
    if not paragraphs:
        return []
    hits = []
    for block in paragraphs:
        for word in CONNECTORS:
            if block.text.startswith(word):
                hits.append((block.line, word))
                break
    ratio = len(hits) / len(paragraphs)
    if ratio <= CONNECTOR_RATIO:
        return []
    line = hits[0][0]
    detail = f"{len(hits)}/{len(paragraphs)} 段落以连接词开头（{ratio:.0%}）: " + \
             "、".join(f"L{ln} {word}" for ln, word in hits[:8])
    return [Signal("AIF-01", "warn", line, doc.excerpt(line), detail)]


def rule_aif_02(doc: Doc) -> list[Signal]:
    """Empty praise with nothing backing it up."""
    hits = []
    for index, block in _paragraphs_with_index(doc):
        for word in VAGUE_WORDS:
            if word not in block.text:
                continue
            has_number = re.search(r"\d", block.text) is not None
            next_kind = doc.blocks[index + 1].kind if index + 1 < len(doc.blocks) else ""
            supported = has_number or next_kind in (CODE, TABLE)
            if not supported:
                hits.append((block.line, word))
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 处空泛评价无证据支撑: " + \
             "、".join(f"L{ln} {word}" for ln, word in hits[:8])
    return [Signal("AIF-02", "warn", line, doc.excerpt(line), detail)]


def rule_aif_03(doc: Doc) -> list[Signal]:
    """Paragraphs long enough to hide several claims in one breath."""
    hits = [(b.line, len(b.text)) for b in doc.paragraphs() if len(b.text) > LONG_PARAGRAPH]
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 段超过 {LONG_PARAGRAPH} 字: " + \
             "、".join(f"L{ln}({size}字)" for ln, size in hits[:8])
    return [Signal("AIF-03", "warn", line, doc.excerpt(line), detail)]


def rule_aif_04(doc: Doc) -> list[Signal]:
    """The closing paragraph that says nothing."""
    paragraphs = doc.paragraphs()
    if not paragraphs:
        return []
    tail = paragraphs[-3:]
    hits = []
    for block in tail:
        for word in GENERIC_ENDINGS:
            if word in block.text:
                hits.append((block.line, word))
                break
        else:
            if GENERIC_ENDING_RE.search(block.text):
                hits.append((block.line, "随着…的发展"))
    if not hits:
        return []
    line = hits[0][0]
    detail = "结尾出现泛化收尾语: " + "、".join(f"L{ln} {word}" for ln, word in hits)
    return [Signal("AIF-04", "warn", line, doc.excerpt(line), detail)]


def rule_aif_05(doc: Doc) -> list[Signal]:
    """Sentences that say the same thing twice.

    Only sentences written in Chinese prose count.  Code-introduction
    lines like 「事务 XID=200 执行：」 and 「事务 XID=300 执行：」 are
    93% identical but are parallel structure, not redundancy -- flagging
    them would bury the real finding under noise.
    """
    sentences = []
    for block in doc.paragraphs():
        for piece in SENTENCE_SPLIT_RE.split(block.text):
            piece = piece.strip()
            if len(piece) < DUPLICATE_MIN_LEN:
                continue
            if len(CJK_RE.findall(piece)) < DUPLICATE_MIN_CJK:
                continue
            sentences.append((block.line, piece))
    buckets: dict[int, list[tuple[int, str]]] = {}
    for line, sentence in sentences:
        buckets.setdefault(len(sentence) // 5, []).append((line, sentence))
    pairs = []
    for group in buckets.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i][1], group[j][1]
                similarity = difflib.SequenceMatcher(None, a, b).ratio()
                if similarity >= DUPLICATE_THRESHOLD:
                    pairs.append((group[i][0], group[j][0], similarity))
    if not pairs:
        return []
    line = pairs[0][0]
    detail = f"{len(pairs)} 对近似重复句: " + \
             "、".join(f"L{a}~L{b}({sim:.2f})" for a, b, sim in pairs[:5])
    return [Signal("AIF-05", "warn", line, doc.excerpt(line), detail)]


RULES.extend([rule_aif_01, rule_aif_02, rule_aif_03, rule_aif_04, rule_aif_05])


# --- 技术深度五要素 ---------------------------------------------------------
#
# 对应 review/README.md 的「技术深度检查」一节。要素命中数是可数的事实，
# 是否达标仍然要读全文判断——DEP-00 只是提示，不是判决。

VERSION_RE = re.compile(
    r"(?i)\b(?:postgresql|pg|opengauss|linux|kernel|ubuntu|centos)\s+v?\d+(?:\.\d+)*"
    r"|\bv?\d+\.\d+(?:\.\d+)*\b"
)
BOUNDARY_WORDS = ("环境", "前提", "规模", "边界", "前置条件", "版本")

SOURCE_PATH_RE = re.compile(r"(?:src|backend|include)/[A-Za-z0-9_./-]+\.[ch]\b")
IDENTIFIER_CALL_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\s*\(")
MECHANISM_WORDS = ("调用链", "状态机", "执行器", "流程", "实现", "源码")

EVIDENCE_RE = re.compile(
    r"(?i)\b(?:select|insert|update|delete|create|explain|vacuum|psql|docker|gdb|strace|perf|tcpdump)\b"
)
EVIDENCE_SHELL_RE = re.compile(r"(?m)^\s*(\$ |#\s|docker |psql |gdb |strace |perf |tcpdump )")
EVIDENCE_LOG_RE = re.compile(r"(?m)^\s*(LOG|ERROR|WARNING|PANIC|FATAL)[:\s]")

TRADEOFF_WORDS = ("相比", "相比之下", "替代", "取舍", "权衡", "代价", "适用场景",
                  "优点", "缺点", "利弊", "优劣", "对比", "选型", "不建议", "更推荐")
PITFALL_WORDS = ("坑", "注意", "误区", "验证", "校验", "复现", "监控", "陷阱", "别用",
                 "不要用", "风险", "切勿", "务必", "检查", "观察")


def _count_regex(doc: Doc, pattern: re.Pattern) -> int:
    return len(pattern.findall(doc.text))


def _count_words(doc: Doc, words: tuple[str, ...]) -> int:
    return sum(doc.text.count(word) for word in words)


def rule_dep_01(doc: Doc) -> list[Signal]:
    """问题边界：版本、系统规模、前置条件。"""
    doc.depth["DEP-01"] = _count_regex(doc, VERSION_RE) + _count_words(doc, BOUNDARY_WORDS)
    return []


def rule_dep_02(doc: Doc) -> list[Signal]:
    """机制解释：源码定位与调用链。"""
    doc.depth["DEP-02"] = (_count_regex(doc, SOURCE_PATH_RE)
                            + _count_regex(doc, IDENTIFIER_CALL_RE)
                            + _count_words(doc, MECHANISM_WORDS))
    return []


def rule_dep_03(doc: Doc) -> list[Signal]:
    """可复现证据：能照着跑的命令、SQL 或日志。"""
    total = 0
    for block in doc.blocks:
        if block.kind != CODE:
            continue
        if EVIDENCE_RE.search(block.text) or EVIDENCE_SHELL_RE.search(block.text) \
                or EVIDENCE_LOG_RE.search(block.text):
            total += 1
    doc.depth["DEP-03"] = total
    return []


def rule_dep_04(doc: Doc) -> list[Signal]:
    """工程取舍：替代方案、代价、适用场景。"""
    doc.depth["DEP-04"] = _count_words(doc, TRADEOFF_WORDS)
    return []


def rule_dep_05(doc: Doc) -> list[Signal]:
    """踩坑与校验：怎么观察、怎么验证结果。"""
    doc.depth["DEP-05"] = _count_words(doc, PITFALL_WORDS)
    return []


def rule_dep_00(doc: Doc) -> list[Signal]:
    """要素命中少于 2 项：技术深度可能不够。"""
    elements = sum(1 for key in ("DEP-01", "DEP-02", "DEP-03", "DEP-04", "DEP-05")
                   if doc.depth.get(key, 0) > 0)
    doc.depth["DEP-00"] = 0 if elements >= 2 else 1
    if elements >= 2:
        return []
    return [Signal("DEP-00", "warn", 1, "",
                   f"只命中 {elements}/5 个技术深度要素（边界/机制/证据/取舍/校验）")]


RULES.extend([rule_dep_01, rule_dep_02, rule_dep_03, rule_dep_04, rule_dep_05, rule_dep_00])


# --- 结构、产物与元信息 -----------------------------------------------------

POSITIONING_RE = re.compile(
    r"本文.{0,20}(回答|解决|讲|介绍|将|会|带|拆|说|帮你|分析|浅析|梳理)"
    r"|本文是|这篇文章|为什么|难题|先说|目标\*{0,2}\s*[：:]"
)
TAKEAWAY_WORDS = ("清单", "检查表", "决策表", "排查", "下一步", "下一篇", "延伸阅读",
                   "相关阅读", "参考资料", "同系列", "前文", "总结", "小结", "要点",
                   "结语", "结论", "修改指南", "源码入口")

# 图片不是文章链接：``![]()`` 必须排除，否则图片路径会被判成断链。
# ``!`` 在 ``[`` 之前而不是 ``]`` 之前，所以只能把 ``!`` 收进捕获组来区分。
MD_LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def rule_str_01(doc: Doc) -> list[Signal]:
    """Fewer than three second-level sections."""
    count = sum(1 for b in doc.blocks if b.kind == HEADING and b.level == 2)
    if count >= 3:
        return []
    return [Signal("STR-01", "info", 1, "", f"二级章节只有 {count} 个（< 3）")]


def rule_str_02(doc: Doc) -> list[Signal]:
    """The opening does not say what problem the article solves.

    Quoted blocks and headings count: several articles put their
    positioning in a ``> 目标：…`` quote or in a 「一句话答案」 section
    rather than in a plain paragraph.
    """
    seen = 0
    for block in doc.blocks:
        if block.kind == HEADING and block.level == 1:
            continue  # the title is not positioning
        if block.kind not in (PARAGRAPH, QUOTE, HEADING):
            continue
        seen += 1
        if seen > 5:
            break
        if POSITIONING_RE.search(block.text):
            return []
        if block.text.rstrip().endswith("？"):
            return []
    return [Signal("STR-02", "info", 1, "", "开头 5 段没有说明文章解决什么问题")]


def rule_str_03(doc: Doc) -> list[Signal]:
    """The ending leaves the reader with nothing to carry away.

    The tail is inspected as the *last section* -- everything from the
    final H2 onwards -- not a fixed number of blocks: the takeaway is
    usually a heading plus a list（「参考资料」「同系列前文」「修改指南」
    「排查清单」), and a fixed window would miss it whenever the last
    section has subsections of its own.
    """
    start = 0
    for index, block in enumerate(doc.blocks):
        if block.kind == HEADING and block.level == 2:
            start = index
    for block in doc.blocks[start:]:
        if any(word in block.text for word in TAKEAWAY_WORDS):
            return []
    return [Signal("STR-03", "info", 1, "", "结尾没有可带走的产物（清单/参考资料/下一篇）")]


def _link_target_exists(target: str, post_dir: Path) -> bool:
    """Whether a relative article link points at something that exists.

    The rule is the one the old publisher used, and it is still how a
    reader reads a relative link: resolve the link as written against the
    post's own directory, and if that misses, fall back to the sibling
    directory one level up -- so ``./b/index.html`` inside
    ``docs/database/a/index.md`` means ``docs/database/b/``.

    Only existence is checked here; producing the permalink would need
    git lookups, and the review only needs to know the target is there.
    """
    candidate = (post_dir / target).resolve()
    if candidate.is_dir():
        return any((candidate / name).is_file()
                   for name in ("index.md", "index.html", "index.htm", "_index.md"))
    if candidate.is_file():
        return True
    if target.endswith((".html", ".htm")):
        if candidate.with_suffix(".md").is_file():
            return True
        return (candidate.parent / "index.md").is_file()
    return False


def rule_str_04(doc: Doc) -> list[Signal]:
    """Relative links that point at nothing."""
    post_dir = doc.path.parent
    hits = []
    for match in MD_LINK_RE.finditer(doc.text):
        if match.group(1) == "!":
            continue  # 图片
        raw = match.group(2)
        if raw.startswith(("http://", "https://", "//", "#", "mailto:", "data:")):
            continue
        if not raw.startswith(("./", "../")):
            continue
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        # 站上的链接里空格是 %20 编码的，磁盘上的文件名不是 —— 先解码再查。
        # 与 `tools/check-internal-links.py` 的 `decode()` 同一套规矩。
        target = unquote(target)
        # 先按写法解析，再回退兄弟目录——两步都不中才算断链。
        if _link_target_exists(target, post_dir):
            continue
        if _link_target_exists(target.lstrip("./"), post_dir.parent):
            continue
        line = doc.text[: match.start()].count("\n") + 1
        hits.append((line, target))
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 个相对链接指向不存在的文章: " + \
             "、".join(f"L{ln} {target}" for ln, target in hits[:6])
    return [Signal("STR-04", "warn", line, doc.excerpt(line), detail)]


def rule_str_05(doc: Doc) -> list[Signal]:
    """Wrong capitalisation of the product name."""
    hits = [number for number, line in enumerate(doc.lines, 1) if "Postgresql" in line]
    if not hits:
        return []
    return [Signal("STR-05", "info", hits[0], doc.excerpt(hits[0]),
                   f"{len(hits)} 行把 PostgreSQL 写成了 Postgresql")]


def rule_met_01(doc: Doc) -> list[Signal]:
    """The article is missing its author table."""
    for block in doc.blocks:
        if block.kind == TABLE and "编写人" in block.text:
            return []
    return [Signal("MET-01", "info", 1, "", "缺少「编写人 / 编写内容 / 编写时间」信息表")]


def rule_met_02(doc: Doc) -> list[Signal]:
    """The article is missing its H1 title."""
    if any(b.kind == HEADING and b.level == 1 for b in doc.blocks):
        return []
    return [Signal("MET-02", "info", 1, "", "缺少 H1 标题")]


# --- 术语纪律 -------------------------------------------------------------
#
# 对应 review/README.md 的「术语纪律」一节。要点只有一句：
# **要么用本领域有公认定义的术语，要么用通用描述，不造词。**
#
# 三条规则分工不同：
#   TERM-01 硬禁词——这些词在本领域**没有公认定义**，读者得先猜作者在说什么；
#   TERM-02 常见行话——能用，但换成具体说法更好，改不改由人定；
#   TERM-03 命名黑名单——已经判过「不合格」的名字（对仗式抽象短语）。
#
# 通用规则靠人判断（什么算「公认术语」不是机器能定的），机械能做的只有两件：
# 把硬禁词挑出来，把已被否掉的名字挑出来。

#: 词表从共享规则文件读一次就够了——同一轮检查里它不会变。
_TERMINOLOGY = load_terminology()
TERM_BANNED = _TERMINOLOGY["banned"]
TERM_SOFT = _TERMINOLOGY["soft"]
TERM_BAD_NAMES = _TERMINOLOGY["bad_names"]
TITLE_HARD_WORDS = _TERMINOLOGY["title_words"]
TITLE_SOFT_WORDS = _TERMINOLOGY["title_words_soft"]


def _term_hits(doc: Doc, table: dict) -> list[tuple[int, str]]:
    """Reader-visible lines containing any word from ``table``.

    扫**整篇原文**（含 front matter 与代码块），而不是只扫段落：
    front matter 的 description 会出现在站点列表页，mermaid 里的标签
    也会出现在图上——都是读者看得见的地方。front matter 的 ``---``
    分隔行跳过（里面没有词）。
    """
    hits: list[tuple[int, str]] = []
    for number, raw in enumerate(doc.lines, 1):
        text = raw.strip()
        if not text or text == "---":
            continue
        for word in table:
            if word in text:
                hits.append((number, word))
    return hits


def rule_term_01(doc: Doc) -> list[Signal]:
    """Terms with no agreed definition in this field."""
    hits = _term_hits(doc, TERM_BANNED)
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 处自造术语: " + "、".join(
        f"L{ln} {word}（{TERM_BANNED[word]}）" for ln, word in hits[:8])
    return [Signal("TERM-01", "warn", line, doc.excerpt(line), detail)]


def rule_term_02(doc: Doc) -> list[Signal]:
    """Common jargon that reads better when spelled out."""
    hits = _term_hits(doc, TERM_SOFT)
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 处行话建议具体化: " + "、".join(
        f"L{ln} {word}（{TERM_SOFT[word]}）" for ln, word in hits[:8])
    return [Signal("TERM-02", "info", line, doc.excerpt(line), detail)]


def rule_term_03(doc: Doc) -> list[Signal]:
    """Names already rejected: paired abstract phrases."""
    hits = _term_hits(doc, TERM_BAD_NAMES)
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 处命名不合格: " + "、".join(
        f"L{ln} {word}（{TERM_BAD_NAMES[word]}）" for ln, word in hits[:8])
    return [Signal("TERM-03", "warn", line, doc.excerpt(line), detail)]


RULES.extend([rule_term_01, rule_term_02, rule_term_03])


# --- 章节标题 -------------------------------------------------------------
#
# 对应 review/README.md 的「标题：层级、顺序、信息量」一节。
# 标题是读者唯一的导航：层级断了、顺序乱了、标题说的东西正文没讲，
# 读者都得自己猜。这一组规则机械上判得了的几件事：
#
#   HEAD-01 层级 —— H1 只能有一个且在最前；不允许跳级（H2 直接到 H4）
#   HEAD-02 长度 —— 标题要短，一眼扫得完
#   HEAD-03 措辞 —— 标题不用营销词与口水词（词表在 rules/terminology.json）
#   HEAD-04 顺序 —— 收束标题不能在中间；阶段词要按「背景→原理→实践→验证→扩展→总结」
#   HEAD-05 空节 —— 标题下面得有事讲
#   HEAD-06 对得上 —— 标题里的术语，这一节正文里得出现（info）
#
# 「标题能不能概括这一节」整体上要人判断：机器只能查机械的部分。

#: H2/H3 标题的字数上限。中文标题超过这个长度，读者扫目录就得多看一眼。
HEADING_MAX_CHARS = 24

#: 标题里的收束词：出现在后面还有同级标题的位置，就是顺序不对。
CLOSING_WORDS = ("总结", "小结", "结语", "回顾", "写在最后")

#: 一篇文章的阶段次序。同一组里的词不分先后，跨组就按这个顺序排。
#: 判据是读者的疑问顺序：先问「为什么/是什么」，再问「怎么做」，
#: 再问「怎么验证」，最后才是「还能怎么玩」。
STAGE_GROUPS = (
    ("背景", "问题", "现象", "动机"),
    ("原理", "机制", "原理与机制"),
    ("实现", "实践", "上手", "实战", "用法"),
    ("验证", "测试", "基准", "观测"),
    ("扩展", "进阶", "优化"),
    ("总结", "小结", "清单", "延伸"),
)

#: 标题里不查的英文词——它们是英文句子里到处都有的连接词，
#: 不是「这一节讲的东西」。
TITLE_STOPWORDS = {
    "the", "and", "of", "to", "in", "for", "on", "with", "by", "be",
    "as", "at", "from", "or", "an", "a", "is", "are", "it", "its",
    "this", "that", "we", "you", "how", "what", "why", "not",
}


def _headings(doc: Doc) -> list[tuple[int, Block]]:
    """All heading blocks, in document order."""
    return [(i, b) for i, b in enumerate(doc.blocks) if b.kind == HEADING]


def _is_module_readme(doc: Doc) -> bool:
    """``README.md`` 是模块说明与流程文档，**不是稿子**。

    标题规则管的是读者读到的文章骨架；模块说明里「## 七、这个目录现在是空的」
    这样的空节是刻意的，不是缺陷。
    """
    return doc.path.name == "README.md"


def _section_body(doc: Doc, start: int) -> str:
    """The text of the section that starts at block ``start``.

    到下一个**同级或更高级**的标题为止；子标题下的正文算这一节的内容。
    """
    level = doc.blocks[start].level
    parts: list[str] = []
    for block in doc.blocks[start + 1:]:
        if block.kind == HEADING and block.level <= level:
            break
        parts.append(block.text)
    return "\n".join(parts)


def _title_tokens(title: str) -> list[str]:
    """标题里的「专名」：ASCII 术语与引号里的说法。

    只取查得准的那两类——中文分词做不准，宁可不查：
    一个标题里的中文实词往往是普通名词（查了全是误报），
    而英文术语（WAL、MVCC）与引号里的说法（「三选二」）是能对上的。
    """
    tokens = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*", title):
        if len(word) < 2 or word.lower() in TITLE_STOPWORDS:
            continue
        tokens.append(word)
    for quoted in re.findall(r"[「『《]([^」』》]{2,})[」』》]", title):
        tokens.append(quoted)
    return tokens


def rule_head_01(doc: Doc) -> list[Signal]:
    """The heading tree is broken: several H1s, an H1 in the middle, or a jump."""
    if _is_module_readme(doc):
        return []
    headings = _headings(doc)
    if not headings:
        return []
    problems: list[str] = []
    h1s = [(i, b) for i, b in headings if b.level == 1]
    if len(h1s) > 1:
        problems.append(f"{len(h1s)} 个 H1（L{h1s[0][1].line}、L{h1s[1][1].line}…）")
    elif h1s and h1s[0][0] != 0:
        problems.append(f"H1 不在最前（L{h1s[0][1].line}）")
    previous = 0
    for _, block in headings:
        if block.level > previous + 1:
            problems.append(f"L{block.line} 从 H{previous} 跳到 H{block.level}")
        previous = block.level
    if not problems:
        return []
    line = headings[0][1].line
    return [Signal("HEAD-01", "warn", line, doc.excerpt(line),
                   "标题层级断了: " + "；".join(problems))]


def rule_head_02(doc: Doc) -> list[Signal]:
    """Titles too long to scan in a table of contents."""
    if _is_module_readme(doc):
        return []
    hits = []
    for _, block in _headings(doc):
        if block.level < 2:
            continue
        length = len(block.text.strip())
        if length > HEADING_MAX_CHARS:
            hits.append((block.line, length))
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 个标题超过 {HEADING_MAX_CHARS} 字: " + \
             "、".join(f"L{ln}({size}字)" for ln, size in hits[:8])
    return [Signal("HEAD-02", "warn", line, doc.excerpt(line), detail)]


def rule_head_03(doc: Doc) -> list[Signal]:
    """Marketing words and filler in titles.

    硬的一档（营销词）报 warn：这类词进标题就是跟内容抢戏。
    软的一档（深入、详解、初探……）报 info：它们不算错，
    但标题得另有「讲什么」的那一半。
    """
    if _is_module_readme(doc):
        return []
    hard: list[tuple[int, str]] = []
    soft: list[tuple[int, str]] = []
    for _, block in _headings(doc):
        title = block.text
        for word in TITLE_HARD_WORDS:
            if word in title:
                hard.append((block.line, word))
        for word in TITLE_SOFT_WORDS:
            if word in title:
                soft.append((block.line, word))
    if hard:
        line = hard[0][0]
        detail = f"{len(hard)} 个标题带营销词: " + \
                 "、".join(f"L{ln} {word}" for ln, word in hard[:8])
        return [Signal("HEAD-03", "warn", line, doc.excerpt(line), detail)]
    if soft:
        line = soft[0][0]
        detail = f"{len(soft)} 个标题带懒词: " + \
                 "、".join(f"L{ln} {word}" for ln, word in soft[:8])
        return [Signal("HEAD-03", "info", line, doc.excerpt(line), detail)]
    return []


def rule_head_04(doc: Doc) -> list[Signal]:
    """The order of the sections does not follow the reader's questions."""
    if _is_module_readme(doc):
        return []
    problems: list[str] = []
    headings = [(i, b) for i, b in _headings(doc) if b.level == 2]
    for position, (_, block) in enumerate(headings):
        if any(word in block.text for word in CLOSING_WORDS) and position != len(headings) - 1:
            problems.append(f"L{block.line}「{block.text}」是收束标题，后面还有 {len(headings) - position - 1} 节")
    stages: list[tuple[int, int, str]] = []
    for _, block in headings:
        for index, group in enumerate(STAGE_GROUPS):
            if any(word in block.text for word in group):
                stages.append((index, block.line, block.text))
                break
    for (before, line_a, title_a), (after, line_b, title_b) in zip(stages, stages[1:]):
        if after < before:
            problems.append(
                f"L{line_a}「{title_a}」排在 L{line_b}「{title_b}」前面，但后者的阶段更靠前")
    if not problems:
        return []
    line = headings[0][1].line if headings else 1
    return [Signal("HEAD-04", "warn", line, doc.excerpt(line),
                   "章节顺序不对: " + "；".join(problems))]


def rule_head_05(doc: Doc) -> list[Signal]:
    """A heading with nothing under it."""
    if _is_module_readme(doc):
        return []
    headings = _headings(doc)
    hits = []
    for position, (index, block) in enumerate(headings):
        if block.level < 2:
            continue
        body = _section_body(doc, index)
        if body.strip():
            continue
        nxt = headings[position + 1][1] if position + 1 < len(headings) else None
        if nxt is not None and nxt.level > block.level:
            continue      # 下面有子标题，不是空节
        hits.append(block.line)
    if not hits:
        return []
    line = hits[0]
    detail = f"{len(hits)} 个标题下面没有内容: " + \
             "、".join(f"L{ln}" for ln in hits[:8])
    return [Signal("HEAD-05", "warn", line, doc.excerpt(line), detail)]


def rule_head_06(doc: Doc) -> list[Signal]:
    """The terms in the title never show up in the section it names."""
    if _is_module_readme(doc):
        return []
    hits = []
    for index, block in _headings(doc):
        if block.level < 2:
            continue
        tokens = _title_tokens(block.text)
        if not tokens:
            continue
        body = _section_body(doc, index)
        if not body.strip():
            continue
        missing = [t for t in tokens if t.lower() not in body.lower()]
        if missing and len(missing) == len(tokens):
            hits.append((block.line, missing))
    if not hits:
        return []
    line = hits[0][0]
    detail = f"{len(hits)} 个标题里的说法在本节正文里没出现: " + \
             "、".join(f"L{ln}（{'、'.join(words)}）" for ln, words in hits[:6])
    return [Signal("HEAD-06", "info", line, doc.excerpt(line), detail)]


RULES.extend([rule_head_01, rule_head_02, rule_head_03,
              rule_head_04, rule_head_05, rule_head_06])


# --- 图示可读性 --------------------------------------------------------
#
# 「流程图不能太长，布局要合理，不然一眼看不完」——这一条机械上判得了：
# 一张图有多少个框、顺着一路走最多几步、从一个框分出去几条支线。
# 阈值是经验值，不是硬标准：图超限说明**该拆**，不是说图画错了。
#
# 三个指标各自对应一种「看不完」，单看框数不够：
#   框多   → 扫一眼看不到全貌（一张图摆了两面墙）
#   路径长 → 顺着一路走要一直往下，接不上前后（流程图太长）
#   分支多 → 一个点炸开十几条线，视线来回跳（架构图布局乱）
# 13 个框但结构规整的图不算超限，9 个框连成一条长链的图算。

MERMAID_MAX_NODES = 15          # 一张图里的框数上限
MERMAID_MAX_PATH = 8            # 一条流程最多几步
MERMAID_MAX_FANOUT = 6          # 一个框最多分出几条支线
MERMAID_MAX_MINDMAP_LINES = 20  # mindmap 的内容行数上限
FIGURE_REF_MAX_DISTANCE = 10    # 「下图」到图之间允许隔的行数

MERMAID_EDGE_RE = re.compile(r"(?:-\.->|-\.-|==>|--[xo]|-->|---)")
MERMAID_ID_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")
# 图类型声明。用正则而不是 startswith：``stateDiagram-v2`` 的版本后缀
# 要认出来，``graphical`` 这种节点名又不能被当成图类型。
MERMAID_HEADER_RE = re.compile(
    r"^(?:graph|flowchart|sequencediagram|classdiagram|statediagram|"
    r"state-diagram|mindmap|timeline|erdiagram|gantt|journey|pie|quadrantchart)\b")
# 整行就是这一个词的（``end`` 收尾一个 subgraph）。
MERMAID_SKIP_EXACT = ("end",)
# 行首是这些前缀的（``style A fill:#fff`` 之类）。
MERMAID_SKIP_PREFIX = (
    "subgraph", "style ", "class ", "click ", "linkstyle",
    "classdef", "direction", "note ", "note:", "acctitle:",
    "accdescr:", "%%",
)


def _is_mermaid_header(low: str) -> bool:
    """这一行是不是图类型声明（``graph TB`` / ``stateDiagram-v2`` / ``mindmap``）。"""
    return bool(MERMAID_HEADER_RE.match(low))


def _is_mermaid_noise(low: str) -> bool:
    """这一行是不是图里的修饰语句（不是框，也不是边）。"""
    if low in MERMAID_SKIP_EXACT:
        return True
    return low.startswith(MERMAID_SKIP_PREFIX)


def _mermaid_graph(body: str) -> tuple[set[str], list[tuple[str, str]]]:
    """把 mermaid 源码解析成 (框的集合, 有向边列表)。

    框 id 的取法：mermaid 里节点可以写成 ``A``、``A[文字]``、``A(文字)``、
    ``A((文字))``，只有开头的标识符是 id，后面的是形状与文字。
    边上的说明有三种写法（``A-->|说明|B``、``A-- 说明 -->B``、``A-->B: 说明``），
    先去掉说明，剩下的才切得干净。
    """
    nodes: set[str] = set()
    edges: list[tuple[str, str]] = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if _is_mermaid_header(low) or _is_mermaid_noise(low):
            continue
        if low.startswith(("participant ", "actor ")):
            m = MERMAID_ID_RE.match(line.split(None, 1)[1].strip())
            if m:
                nodes.add(m.group(1))
            continue
        line = re.sub(r"\|[^|]*\|", " ", line)
        line = re.sub(r"--\s+[^->|]*\s*-->", " --> ", line)
        chain: list[str] = []
        for part in MERMAID_EDGE_RE.split(line):
            part = part.strip()
            if not part:
                continue
            m = MERMAID_ID_RE.match(part)
            if not m:
                continue
            nodes.add(m.group(1))
            chain.append(m.group(1))
        edges.extend(zip(chain, chain[1:]))
    return nodes, edges


def _longest_path(nodes: set[str], edges: list[tuple[str, str]]) -> int:
    """顺着一路走最多能经过几个框。

    图里可能有环（重试、回滚），所以先把环切掉再算路径：环上转一圈
    不算变长，这正是「这条路有多长」该有的意思。

    **切环必须确定性**：早先的实现用「在途标记」在 DFS 里遇到环就当场截断，
    而 DFS 从哪个框出发取决于 ``set`` 的迭代顺序 —— 字符串的哈希每进程随机，
    于是同一张图每次跑出来的路径长度可能差 1，FIG-01 命中与否也跟着抖。
    （实测：同一棵树上连跑四次，warn 信号 509 与 510 之间来回跳。）

    现在改成标准做法：先做一次确定性 DFS，把「指向在途节点的边」（回边）
    标出来删掉，剩下的图一定是 DAG，再在 DAG 上算最长路径。
    起点与后继都按 id 排序，于是同一张图永远得到同一个数。
    """
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, set()).add(dst)
    adjacency = {src: sorted(dsts) for src, dsts in adjacency.items()}

    # 1) 确定性 DFS：找出回边（指向在途节点的边）
    color: dict[str, int] = {}          # 0 未访问 / 1 在途 / 2 已完成
    back_edges: set[tuple[str, str]] = set()

    def classify(start: str) -> None:
        stack = [(start, iter(adjacency.get(start, ())))]
        color[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[node] = 2
                stack.pop()
                continue
            state = color.get(nxt, 0)
            if state == 0:
                color[nxt] = 1
                stack.append((nxt, iter(adjacency.get(nxt, ()))))
            elif state == 1:
                back_edges.add((node, nxt))

    for node in sorted(nodes):
        if color.get(node, 0) == 0:
            classify(node)

    # 2) DAG 上的最长路径（记忆化）
    memo: dict[str, int] = {}

    def walk(node: str) -> int:
        if node in memo:
            return memo[node]
        best = 1
        for nxt in adjacency.get(node, ()):
            if (node, nxt) in back_edges:
                continue
            best = max(best, 1 + walk(nxt))
        memo[node] = best
        return best

    return max((walk(node) for node in sorted(nodes)), default=1)


def _max_fanout(edges: list[tuple[str, str]]) -> int:
    """一个框最多分出去几条支线（同一条目标只算一条）。"""
    out: dict[str, set[str]] = {}
    for src, dst in edges:
        out.setdefault(src, set()).add(dst)
    return max((len(v) for v in out.values()), default=0)


def _mermaid_size(body: str) -> tuple[int, int, int]:
    """(框数, 最长路径的框数, 最大扇出)。"""
    nodes, edges = _mermaid_graph(body)
    return len(nodes), _longest_path(nodes, edges), _max_fanout(edges)


def _mermaid_content_lines(body: str) -> int:
    """图里真正有内容的行数（去掉类型声明和空行）。"""
    count = 0
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if _is_mermaid_header(low) or _is_mermaid_noise(low):
            continue
        count += 1
    return count


def rule_fig_01(doc: Doc) -> list[Signal]:
    """A flow/architecture diagram is too big to read at a glance.

    Mermaid renders a long chain into one very long strip, and a diagram
    with dozens of nodes turns into a wall. Both are fixable by splitting
    the diagram, so the signal points at the block, not at the drawing.

    一篇一条信号：一张图超限是「这张图要拆」，六张图超限也还是同一件事
    （这篇的图整体太密），拆成六条信号只会把「信号」这一列撑爆——
    那一列是用来排审校队列的。
    """
    hits: list[tuple[int, str]] = []
    for block in doc.blocks:
        if block.kind != CODE or block.lang != "mermaid":
            continue
        if block.text.strip().lower().startswith("mindmap"):
            lines = _mermaid_content_lines(block.text)
            if lines > MERMAID_MAX_MINDMAP_LINES:
                hits.append((block.line, f"L{block.line} mindmap {lines} 行"))
            continue
        nodes, path, fanout = _mermaid_size(block.text)
        reasons: list[str] = []
        if nodes > MERMAID_MAX_NODES:
            reasons.append(f"{nodes} 个框")
        if path > MERMAID_MAX_PATH:
            reasons.append(f"一条流程 {path} 步")
        if fanout > MERMAID_MAX_FANOUT:
            reasons.append(f"一个框分出 {fanout} 条支线")
        if reasons:
            hits.append((block.line, f"L{block.line} " + "、".join(reasons)))
    if not hits:
        return []
    line = hits[0][0]
    detail = (f"{len(hits)} 张图超限（框数>{MERMAID_MAX_NODES}、"
              f"单条流程>{MERMAID_MAX_PATH} 步、单个框分出>{MERMAID_MAX_FANOUT} 条支线、"
              f"mindmap>{MERMAID_MAX_MINDMAP_LINES} 行）："
              + "、".join(text for _, text in hits[:6])
              + "，建议拆成几张、每张只讲一段")
    return [Signal("FIG-01", "warn", line, doc.excerpt(line), detail)]


FIGURE_REF_RE = re.compile(r"(下|上)图")


def block_span(block: Block) -> tuple[int, int]:
    """这个块占的物理行范围（含首尾）。

    代码块的 ``line`` 是围栏所在行，正文在它后面，所以结束行要 +1；
    其它块的 ``text`` 包含自己的第一行，直接按换行数算。
    """
    if block.kind == CODE:
        return block.line, block.line + block.text.count("\n") + 1
    return block.line, block.line + block.text.count("\n")


def _figure_blocks(doc: Doc) -> list[tuple[int, int]]:
    """图块的 (起始行, 结束行)：mermaid 代码块与图片行。"""
    spans: list[tuple[int, int]] = []
    for block in doc.blocks:
        if block.kind == CODE and block.lang == "mermaid":
            spans.append(block_span(block))
    for number, line in enumerate(doc.lines, 1):
        if IMAGE_RE.search(line):
            spans.append((number, number))
    spans.sort()
    return spans


def rule_fig_02(doc: Doc) -> list[Signal]:
    """A "see the diagram below" reference is too far from the diagram.

    The reader is told to look down, then has to scroll past a screen of
    text (or a different diagram) before the picture arrives.
    """
    spans = _figure_blocks(doc)
    if not spans:
        return []
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(doc.lines, 1):
        if block_kind(doc, number) not in (PARAGRAPH, LIST):
            continue
        for m in FIGURE_REF_RE.finditer(line):
            direction = m.group(1)
            if direction == "下":
                later = [s for s in spans if s[0] > number]
                if not later:
                    continue
                target = later[0]
                distance = target[0] - number
            else:
                earlier = [s for s in spans if s[1] < number]
                if not earlier:
                    continue
                target = earlier[-1]
                distance = number - target[1]
            if distance > FIGURE_REF_MAX_DISTANCE:
                hits.append((number, f"L{number}「{m.group(0)}」→图在 L{target[0]}，隔 {distance} 行"))
    if not hits:
        return []
    line = hits[0][0]
    detail = (f"{len(hits)} 处「下图/上图」离图太远"
              f"（超过 {FIGURE_REF_MAX_DISTANCE} 行）："
              + "、".join(text for _, text in hits[:6]))
    return [Signal("FIG-02", "info", line, doc.excerpt(line), detail)]


def block_kind(doc: Doc, line: int) -> str:
    """The kind of the block that **covers** ``line`` (empty string if none).

    Must be a range lookup, not a lookup by the block's first line: a
    paragraph spans several lines, and「下图」usually sits in the middle
    of one. Matching only the first line would miss most references.
    """
    for block in doc.blocks:
        start, end = block_span(block)
        if start <= line <= end:
            return block.kind
    return ""


RULES.extend([rule_str_01, rule_str_02, rule_str_03, rule_str_04,
              rule_str_05, rule_met_01, rule_met_02,
              rule_fig_01, rule_fig_02])


# --- 稿子 vs 索引页 ----------------------------------------------------
#
# 这一层的接口由**目录层级**承担：`_index.md` 是索引页，其余 `.md` 是稿子。
# 稿子与索引页适用不同的规则集：
#
# - 索引页是一张清单。它不该有「编写人信息表」，也不该被要求「三个二级章节」
#   或「五个技术深度要素」——那些是**稿子**的判据，套到清单上全是噪声。
# - 但链接、拼写、H1、图示这些对两者一样要查。
#
# 所以这里按**文件名**分流，不靠 front matter 自报身份：层级说了它是什么，
# 检查器就照着办。

ARTICLE_ONLY = {
    # AI 味信号：清单页没有需要润色的散文
    "rule_aif_01", "rule_aif_02", "rule_aif_03", "rule_aif_04", "rule_aif_05",
    # 技术深度五要素：判的是稿子的内容密度
    "rule_dep_01", "rule_dep_02", "rule_dep_03", "rule_dep_04",
    "rule_dep_05", "rule_dep_00",
    # 结构：章节数、开头定位、结尾产物
    "rule_str_01", "rule_str_02", "rule_str_03",
    # 元信息：编写人信息表
    "rule_met_01",
}


def doc_kind(path: Path) -> str:
    """``index`` 还是 ``article`` —— 由目录层级判定。"""
    return "index" if path.name == "_index.md" else "article"


def derive_identity(path: Path, docs_root: Path = DOCS_ROOT) -> tuple[str, str]:
    """Derive ``(pillar, slug)`` from a docs/-relative path.

    ``docs/source-tracks/postgresql/transaction-mvcc/postgresql-mvcc/index.md`` -> ``("database", "postgresql-mvcc")``
    ``docs/source-tracks/postgresql/extensions-perf/pg-dont-do-this.md``      -> ``("database", "pg-dont-do-this")``
    ``docs/db/postgresql/xxx.md``             -> ``("db", "postgresql/xxx")``

    ``docs_root`` exists so the rule can be exercised on a temporary tree
    instead of the repository's own ``docs/``.
    """
    try:
        rel = path.resolve().relative_to(docs_root.resolve())
    except ValueError:
        return "", path.stem
    parts = list(rel.parts)
    if len(parts) == 1:
        return "", parts[0].rsplit(".", 1)[0]
    pillar = parts[0]
    rest = parts[1:]
    if rest and rest[-1] in ("index.md", "README.md"):
        rest = rest[:-1]
    else:
        rest[-1] = rest[-1].rsplit(".", 1)[0]
    return pillar, "/".join(rest)


def parse_blocks(lines: list[str]) -> list[Block]:
    """Split markdown source lines into typed blocks.

    A leading YAML front matter block (``---`` ... ``---``) is metadata,
    not prose -- 51 of the 282 reviewed articles have one -- so it is
    skipped instead of being parsed as paragraphs.
    """
    blocks: list[Block] = []
    i = 0
    total = len(lines)
    if lines and lines[0].strip() == "---":
        j = 1
        while j < total and lines[j].strip() != "---":
            j += 1
        i = j + 1
    while i < total:
        raw = lines[i]
        line_no = i + 1
        if not raw.strip():
            i += 1
            continue

        fence = FENCE_RE.match(raw)
        if fence:
            marker = fence.group(1)
            body = []
            j = i + 1
            while j < total and not lines[j].strip().startswith(marker[:3]):
                body.append(lines[j])
                j += 1
            blocks.append(Block(CODE, "\n".join(body), line_no,
                                lang=fence.group(2).strip().split()[0].lower()
                                if fence.group(2).strip() else ""))
            i = j + 1
            continue

        heading = HEADING_RE.match(raw)
        if heading:
            blocks.append(Block(HEADING, heading.group(2).strip(), line_no, len(heading.group(1))))
            i += 1
            continue

        if TABLE_RE.match(raw):
            body = []
            j = i
            while j < total and TABLE_RE.match(lines[j]):
                body.append(lines[j])
                j += 1
            blocks.append(Block(TABLE, "\n".join(body), line_no))
            i = j
            continue

        if LIST_RE.match(raw):
            body = []
            j = i
            while j < total and (LIST_RE.match(lines[j]) or
                                 (lines[j].startswith(("  ", "\t")) and lines[j].strip())):
                body.append(lines[j])
                j += 1
            blocks.append(Block(LIST, "\n".join(body), line_no))
            i = j
            continue

        if QUOTE_RE.match(raw):
            body = []
            j = i
            while j < total and QUOTE_RE.match(lines[j]):
                body.append(lines[j])
                j += 1
            blocks.append(Block(QUOTE, "\n".join(body), line_no))
            i = j
            continue

        body = []
        j = i
        while j < total and lines[j].strip() \
                and not FENCE_RE.match(lines[j]) \
                and not HEADING_RE.match(lines[j]) \
                and not TABLE_RE.match(lines[j]) \
                and not LIST_RE.match(lines[j]) \
                and not QUOTE_RE.match(lines[j]):
            body.append(lines[j])
            j += 1
        blocks.append(Block(PARAGRAPH, "\n".join(body), line_no))
        i = j
    return blocks


def collect_files(paths: list[str]) -> list[Path]:
    """Expand the CLI arguments into a sorted, de-duplicated list of files."""
    found: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if candidate.is_file():
            found.append(candidate.resolve())
        elif candidate.is_dir():
            root = candidate.resolve()
            for child in sorted(candidate.rglob("*.md")):
                # 隐藏目录只看**候选根之下**的那几段：仓库自己就住在
                # ``.worktrees/`` 这类隐藏路径下时，按绝对路径的每一段
                # 去判会把整棵树都当成隐藏目录——目录参数于是检出 0 篇。
                rel = child.resolve().relative_to(root)
                if any(part.startswith(".") for part in rel.parts):
                    continue
                found.append(child.resolve())
        else:
            raise FileNotFoundError(raw)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def load_doc(path: Path, docs_root: Path = DOCS_ROOT) -> Doc:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.split("\n")
    blocks = parse_blocks(lines)
    pillar, slug = derive_identity(path, docs_root)
    title = ""
    for block in blocks:
        if block.kind == HEADING:
            title = block.text
            break
    return Doc(path=path, pillar=pillar, slug=slug, title=title,
               text=raw, lines=lines, blocks=blocks, kind=doc_kind(path))


def check_doc(doc: Doc) -> Doc:
    doc.signals = []
    doc.depth = {}
    for rule in RULES:
        if doc.kind == "index" and rule.__name__ in ARTICLE_ONLY:
            continue
        for signal in rule(doc):
            doc.signals.append(signal)
    return doc


def to_report(doc: Doc) -> dict:
    depth_ok = sum(1 for key, value in doc.depth.items() if key != "DEP-00" and value > 0) >= 2
    return {
        "source": doc.rel_path,
        "pillar": doc.pillar,
        "slug": doc.slug,
        "kind": doc.kind,
        "title": doc.title,
        "stats": {
            "chars": len(doc.text),
            "paragraphs": len(doc.paragraphs()),
            "h2": sum(1 for b in doc.blocks if b.kind == HEADING and b.level == 2),
            "code_blocks": sum(1 for b in doc.blocks if b.kind == CODE),
            "tables": sum(1 for b in doc.blocks if b.kind == TABLE),
            "images": len(IMAGE_RE.findall(doc.text)),
            # mermaid 的图也是图。只数 markdown 图片语法的话，一篇有 22 张
            # 流程图的文章会报「图 0」。
            "mermaid": sum(1 for b in doc.blocks
                           if b.kind == CODE and b.lang == "mermaid"),
            "links": sum(1 for m in LINK_RE.finditer(doc.text) if m.group(1) != "!"),
        },
        "depth": doc.depth,
        "depth_ok": depth_ok,
        "signals": [s.to_dict() for s in doc.signals],
    }


def render_text(docs: list[Doc]) -> str:
    out: list[str] = []
    for doc in docs:
        report = to_report(doc)
        stats = report["stats"]
        out.append(f"{report['source']}  [{report['pillar']}/{report['slug']}]")
        out.append(f"  {report['title']}")
        out.append(
            "  段落 {paragraphs} · 章节 {h2} · 代码块 {code_blocks} · "
            "图 {figures}（mermaid {mermaid} + 图片 {images}） · 链接 {links}".format(
                **stats, figures=stats["mermaid"] + stats["images"])
        )
        depth = report["depth"]
        if depth:
            out.append("  深度 " + " ".join(f"{k}={v}" for k, v in sorted(depth.items())))
        for signal in report["signals"]:
            mark = "⚠" if signal["severity"] == "warn" else "·"
            out.append(f"  {mark} {signal['rule']} L{signal['line']}  {signal['detail']}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="审校信号检查器")
    parser.add_argument("paths", nargs="+", help="要检查的文件或目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是人读摘要")
    parser.add_argument("--out", help="输出到文件（默认 stdout）")
    parser.add_argument(
        "--docs-root",
        default=str(DOCS_ROOT),
        help="算「支柱/篇名」时的根目录（默认：仓库的 docs/）。"
             "换一棵树就换这个值——在临时目录里造语料验规则时用得着。",
    )
    args = parser.parse_args(argv)

    try:
        files = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(f"路径不存在: {exc}", file=sys.stderr)
        return 1

    docs_root = Path(args.docs_root)
    docs = [check_doc(load_doc(path, docs_root)) for path in files]
    if args.json:
        text = json.dumps({"docs": [to_report(d) for d in docs]}, ensure_ascii=False, indent=2)
    else:
        text = render_text(docs)

    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
