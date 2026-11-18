#!/usr/bin/env python3
"""起草文章摘要（front matter 的 ``description``）。

**背景**：``sync-hexo.py`` 从编辑履历表（``| 编写人 | 编写内容 |``）的
「编写内容」列抽一句写进 front matter 的 ``description``。那一列说的是
**「这次改了什么」**——「理顺结构与定位，修正错误写法」「补充完善解决方案」，
不是「**这篇文章是什么**」。85 篇文章的摘要因此是履历句；另有 483 篇没有
description，卡片摘要退回正文前 80 个字（线上有卡片以「TL;DR」「[TOC]」开头）。

**这个工具做什么**：从正文里抽**第一个真正的段落**，当候选摘要。抽的时候按
顺序跳过这些不是摘要的东西：

    履历表 → TL;DR 框 → [TOC] → 引用块 → 代码块 → 标题行 → 表格 →
    目录链接行 → 列表

**它默认不写回源文件**：跑一次只产出 ``review/description-drafts.md``——
一张给作者过目的表（slug | 现在的摘要 | 起草的摘要 | 需人工确认 ☐）。
要写回得显式加 ``--write``。

**``--write`` 不覆盖已经写了摘要的文章**：摘要一旦写进 front matter，
人工改过的那几条就比工具起草的准；再跑一次把它们盖回「正文的第一段」，
是拿自动稿换人工稿。真要盖，显式加 ``--overwrite``。

**为什么不是「自动写回」**：自动起草的摘要个别可能不像人话，作者要过一遍。
工具把活干到「初稿」这一步，判断留给人。

用法::

    python3 tools/draft-descriptions.py            # 只出复核表
    python3 tools/draft-descriptions.py --write    # 顺便写回 docs/ 的 front matter
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# 站点的构建链搬进了 platforms/blog/site/——sync-hexo.py 现在住在那里。
SYNC_SCRIPT = REPO_ROOT / "platforms" / "blog" / "site" / "tools" / "sync-hexo.py"

#: 摘要的下限：比这更短的段落当摘要没有意义（读者看不出这篇文章讲什么）。
#: 「pg」「idm」「node1」这种碎片就在这个门槛底下——它们会被丢掉，
#: 那篇文章宁可**没有**摘要（退回正文前 80 个字），也不要一句碎片。
MIN_DESCRIPTION_CHARS = 10


def _load_sync():
    """``sync-hexo.py`` 是脚本不是包——用 importlib 把它当模块加载。

    复用它的 front matter 解析、履历表剥离、markdown 去标记和长度封顶，
    是为了**两边口径一致**：起草的摘要写进 front matter 之后，sync 搬运
    它的方式必须和起草时算长度的方式一样。
    """
    spec = importlib.util.spec_from_file_location("sync_hexo_draft", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = _load_sync()


# --- 抽摘要 -----------------------------------------------------------------

#: 一块内容「不是摘要」的开头。
_SKIP_PREFIXES = (
    "#",  # 标题行
    ">",  # 引用块（含 TL;DR 框）
    "|",  # 表格
    "!",  # 图片
    "```",  # 代码围栏
    "~~~",
    "---",  # 分隔线
    "<",  # HTML 块
)


def _looks_like_a_list(line: str) -> bool:
    # 列表项：``- `` / ``* `` / ``1. `` / ``1) `` / 「1、」（中文顿号）
    return bool(re.match(r"^([-*+]|\d+[.)、])\s*", line))


#: 围栏代码块——**整块**剥掉，不能按空行切。
#:
#: 按空行切的时候，代码块里那个空行会把块切成两半，后半段不再以
#: ```` ``` ```` 开头，于是被当成了正文段落——有一批文章的摘要就是从
#: 代码块里漏出来的半行代码。围栏允许缩进：列表里的代码块围栏前面
#: 有空格。
_FENCE_RE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$",
    re.S | re.M,
)


def _strip_code_fences(text: str) -> str:
    """把围栏代码块整块去掉。"""
    return _FENCE_RE.sub("", text)


def _is_only_links(lines) -> bool:
    """整块都是 ``[文字](链接)``——那是目录，不是摘要。"""
    return all(
        re.match(r"^\s*[-*+]?\s*\[.*\]\(.*\)\s*$", line) for line in lines
    )


def _paragraph_text(block: str):
    """一块内容里的那段话（不是摘要就返回 ``None``）。"""
    lines = [line for line in block.split("\n") if line.strip()]
    if not lines:
        return None

    first = lines[0].strip()
    for prefix in _SKIP_PREFIXES:
        if first.startswith(prefix):
            return None
    if _looks_like_a_list(first):
        return None
    if re.match(r"^\[TOC\]", first, re.IGNORECASE):
        return None
    if _is_only_links(lines):
        return None
    if any("<!-- more -->" in line for line in lines):
        return None

    text = " ".join(line.strip() for line in lines)
    # 图片整个去掉，链接只留文字——摘要进 meta / 卡片 / RSS，链接是死的。
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # **粗体** / `代码` / *斜体*：那些标记到那里是字面量。
    text = sync._plain_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(">").strip()
    if not text:
        return None
    return sync._fit_description(text)


def draft_description(body: str):
    """正文 → 一句候选摘要（挑不出就返回 ``None``）。

    先剥掉编辑履历表（它不是文章内容，而且它自己那一句是履历句），
    再按空行分块，从前往后找第一段真正的段落。
    """
    clean, _ = sync.extract_edit_history(body or "")
    clean = _strip_code_fences(clean)

    fallback = None
    for block in re.split(r"\n\s*\n", clean):
        text = _paragraph_text(block)
        if not text:
            continue
        if fallback is None:
            fallback = text
        if len(text) >= MIN_DESCRIPTION_CHARS:
            return text
    # 只有一段够短的碎片（「pg」「node1」）时，宁可**没有摘要**——
    # 摘要会进 og:description、卡片、RSS，写一句碎片进去，
    # 读者看到的是「这个博客没写完」。
    if fallback and len(fallback) >= MIN_DESCRIPTION_CHARS:
        return fallback
    return None


# --- 写回 front matter ------------------------------------------------------


def set_description(text: str, description: str) -> str:
    """把 ``description`` 写进 front matter，正文一个字不动。

    已经有 front matter 的替换那一行；没有的加一个（sync 以源为准，
    不覆盖——所以写进去就是定了）。
    """
    line = 'description: "{}"'.format(sync.yaml_escape(description))

    fm, body = sync.split_fm(text)
    if fm is None:
        return "---\n" + line + "\n---\n" + text

    out = []
    replaced = False
    for raw in fm.split("\n"):
        if not replaced and re.match(r"^description\s*:", raw):
            out.append(line)
            replaced = True
            continue
        out.append(raw)
    fm_new = "\n".join(out)
    if not replaced:
        fm_new = fm_new.rstrip("\n") + "\n" + line

    return "---\n" + fm_new + "\n---\n" + body


# --- 走一遍 docs/ ------------------------------------------------------------


def iter_posts(docs_dir: Path):
    """``docs/`` 下所有会被发布成文章的文件（跳过 ``_index`` 和工程目录）。"""
    for root, dirs, files in os.walk(docs_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        sync.prune_excluded_dirs(dirs)
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            if name == "_index.md":
                continue
            path = Path(root) / name
            yield path, path.relative_to(docs_dir).as_posix()


def current_description(text: str):
    """front matter 里现在的 description（没有就是空串）。"""
    fm, _ = sync.split_fm(text)
    if fm is None:
        return ""
    raw = sync._fm_scalar(fm, "description")
    if not raw:
        return ""
    return raw.strip().strip('"').strip("'")


def build_table(rows) -> str:
    """复核表：slug | 现在的摘要 | 起草的摘要 | 需人工确认。"""
    lines = [
        "# 摘要复核表",
        "",
        "这是 `tools/draft-descriptions.py` 从正文里起草的文章摘要",
        "（front matter 的 `description`）。**请过目。**",
        "",
        "- 「现在的摘要」= 现在 front matter 里生效的值。空 = 这篇文章还没有摘要，",
        "  卡片摘要退回正文的前 80 个字。",
        "- 「起草的摘要」= 工具从正文里抽的第一段真正的段落。",
        "",
        "两列不一样，说明那一条是**人工改过的**——以「现在的摘要」为准。",
        "",
        "确认过的那些，把 ☐ 改成 ☑；`tools/draft-descriptions.py --write`",
        "会把「起草的摘要」写进 `docs/` 的 front matter（sync 以源为准，不覆盖）。",
        "",
        "⚠️ `--write` **不覆盖**已经写了摘要的文章（人工稿留着）。",
        "真要盖，显式加 `--overwrite`。",
        "",
        "| 文章 | 现在的摘要 | 起草的摘要 | 确认 |",
        "| --- | --- | --- | --- |",
    ]
    for rel, old, new in rows:
        lines.append("| `{}` | {} | {} | ☐ |".format(rel, old or "（空）", new or "（没抽出来）"))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="起草文章摘要")
    parser.add_argument(
        "--docs",
        default="docs",
        help="文章源目录（默认 docs/，相对于当前目录——和 sync-hexo.py 一个口径）",
    )
    parser.add_argument(
        "--out",
        default="review/description-drafts.md",
        help="复核表的输出位置",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="把起草的摘要写回源文件的 front matter（默认只出复核表）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="连已经写了摘要的文章也覆盖（默认不碰人工写过的）",
    )
    args = parser.parse_args(argv)

    docs_dir = Path(args.docs)
    out_path = Path(args.out)

    rows = []
    written = 0
    kept = 0
    for path, rel in iter_posts(docs_dir):
        text = path.read_text(encoding="utf-8")
        _, body = sync.split_fm(text)

        draft = draft_description(body)
        rows.append((rel, current_description(text), draft))

        if args.write and draft:
            # 已经写了摘要的，默认**不碰**：人工改过的那几条比工具起草的准，
            # 拿自动稿盖掉人工稿是往回走。要盖就显式说 `--overwrite`。
            if current_description(text) and not args.overwrite:
                kept += 1
                continue
            new_text = set_description(text, draft)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                written += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_table(rows), encoding="utf-8")

    drafted = sum(1 for _, _, d in rows if d)
    print("Drafted {} descriptions from {} posts".format(drafted, len(rows)))
    print("Review table: {}".format(out_path))
    if args.write:
        print("Written back to {} source files".format(written))
        if kept:
            print("Kept {} existing descriptions (use --overwrite to replace)".format(kept))
    return 0


if __name__ == "__main__":
    sys.exit(main())
