#!/usr/bin/env python3
"""docs/ → content/units/：把已过审的母稿编译成**平台无关的内容单元**。

这一层是内容流的上游编译步骤，也是所有平台共用的那一半：
公众号、头条号、抖音、B 站、站点，读的都是 `content/units/` 里的内容单元，
不是 `docs/` 里的母稿。

**契约**

- 输入：`docs/` 下的目录文档（只有已过审的才在 `docs/` 里）。
- 输出：`content/units/` 下**同构**的一份（`docs/source-tracks/a/b.md`
  → `content/units/source-tracks/a/b.md`）。
- 内容单元 = 一篇 markdown + 一份 front matter。front matter 由母稿的
  front matter、目录链上的 `_index.md`、以及 git 历史推导出来。

**规矩（重要）**

1. **正文一个字都不许改**。这一层只做 front matter 的推导与**拷贝**。
   链接重写、图片重写、围栏语言归一化统统是渲染层的事（见站点侧 remark 插件）。
   旧站点的 `rewrite_images` / `rewrite_links` 是无视围栏的全局正则，
   会改到代码块里的内容——那套做法不许带过来。
2. **不许在这里发明分类**。分类只存在于目录里：一级目录 = 分类，
   二级目录 = 系列，一篇文档 = 一期（见 `review/specs/2026-11-18-目录即接口与分类增设.md`）。
3. **不许静默失败**。母稿缺 front matter 里的必需字段、目录链断了，
   都是错误，不是「留空继续」。

用法：

    python3 tools/build-content-units.py            # 编译
    python3 tools/build-content-units.py --check    # 只检查（幂等性 + 完整性）
    python3 tools/build-content-units.py --only <id>  # 只编一篇（只读，出一段 JSON）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from paths import CONTENT_UNITS, DOCS  # noqa: E402

#: 母稿 front matter 里允许透传给内容单元的字段。
#: 不在表里的字段不往下传——避免母稿随手写个字段就污染所有平台。
PASSTHROUGH = ("title", "date", "author", "description", "tags", "top", "draft")

#: 目录链上的分类名取自各级 `_index.md` 的 `cascade.categories`。
CASCADE_KEY = "cascade"

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class CompileError(Exception):
    """母稿编译不过。带文件与行号，指向具体那一份稿子。"""


@dataclass
class Unit:
    """一个内容单元：正文 + front matter。"""

    path: Path  # 相对 content/units/ 的路径
    title: str
    date: str
    author: str
    description: str
    kind: str  # document | category
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    extra: dict = field(default_factory=dict)


def split_front_matter(text: str) -> tuple[dict, str]:
    """拆出 front matter 与正文。正文原样返回，一个字都不动。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 4 :]
    body = body.lstrip("\n")
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise CompileError(f"front matter 不是合法 YAML：{exc}") from exc
    if not isinstance(fm, dict):
        raise CompileError("front matter 不是键值映射")
    return fm, body


def git_date(rel_path: Path) -> str:
    """取这篇稿子**最早一次提交**的时间。

    站点上的日期用的是「这篇内容什么时候开始写的」，不是最后一次改的时间。
    `git log` 倒着取第一行。`%ai` 带时区偏移，这里**只留墙钟时间**——
    旧站点踩过一个坑：带 `+0800` 的时间被 hexo 当 UTC 又折算一次，
    日期会莫名往前跳一天（见 `internal/blog/架构.md`）。
    """
    proc = subprocess.run(
        ["git", "log", "--format=%ai", "--follow", "--", str(rel_path)],
        cwd=DOCS.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return ""
    return lines[-1][:19]


def first_h1(body: str) -> str:
    m = H1_RE.search(body)
    return m.group(1).strip() if m else ""


def first_paragraph(body: str) -> str:
    """正文里第一段不是标题、不是表格、不是引用的文字。"""
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith(("#", ">", "|", "```", "---", "* ", "- ")):
            continue
        return re.sub(r"\s+", " ", block).strip()
    return ""


def ancestors(rel: Path) -> list[Path]:
    """从顶层到紧邻父级的 `_index.md` 列表。

    `docs/source-tracks/postgresql/getting-started/x.md`
    → `[source-tracks/_index.md, source-tracks/postgresql/_index.md,
       source-tracks/postgresql/getting-started/_index.md]`
    """
    out: list[Path] = []
    parts = rel.parts[:-1]
    for i in range(len(parts)):
        out.append(Path(*parts[: i + 1]) / "_index.md")
    return out


def read_index_chain(rel: Path) -> tuple[list[str], list[str]]:
    """走一遍目录链，收集分类链与标签链。

    分类链来自各级 `_index.md` 的 `cascade.categories`（一级目录 = 分类，
    二级 = 系列……）；标签链来自各级 `_index.md` 的 `tags`。
    """
    categories: list[str] = []
    tags: list[str] = []
    for idx in ancestors(rel):
        idx_path = DOCS / idx
        if not idx_path.exists():
            raise CompileError(
                f"目录链断了：{rel} 的上级 {idx} 没有 _index.md"
            )
        fm, _ = split_front_matter(idx_path.read_text(encoding="utf-8"))
        cascade = fm.get(CASCADE_KEY) or {}
        for name in cascade.get("categories") or []:
            if name not in categories:
                categories.append(name)
        for tag in fm.get("tags") or []:
            if tag not in tags:
                tags.append(tag)
    return categories, tags


def build_unit(path: Path) -> Unit:
    rel = path.relative_to(DOCS)
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)

    is_index = path.name == "_index.md"
    title = (fm.get("title") or "").strip()
    if not title:
        title = first_h1(body)
    if not title:
        raise CompileError(f"{rel} 没有标题（front matter 里没有 title，正文也没有 H1）")

    description = (fm.get("description") or "").strip()
    if not description:
        description = first_paragraph(body)
    if not description:
        raise CompileError(f"{rel} 没有描述（front matter 里没有 description，正文里也找不到第一段）")

    categories, tags = read_index_chain(rel)
    for tag in fm.get("tags") or []:
        if tag not in tags:
            tags.append(tag)

    date = fm.get("date")
    if isinstance(date, str) and date.strip():
        date = date.strip()
    else:
        date = git_date(path)
    if not date:
        raise CompileError(f"{rel} 找不到日期（front matter 里没有 date，git 里也查不到历史）")

    extra = {k: fm[k] for k in PASSTHROUGH if k in fm and k not in ("title", "date", "author", "description", "tags", "top", "draft")}

    return Unit(
        path=rel,
        title=title,
        date=str(date),
        author=str(fm.get("author") or "growdu"),
        description=description,
        kind="category" if is_index else "document",
        categories=categories,
        tags=tags,
        body=body,
        extra=extra,
    )


def render(unit: Unit) -> str:
    """把内容单元写成 markdown + front matter。正文原样。"""
    fm: dict = {
        "title": unit.title,
        "date": unit.date,
        "author": unit.author,
        "description": unit.description,
        "kind": unit.kind,
        "categories": unit.categories,
        "tags": unit.tags,
        "source_path": unit.path.as_posix(),
    }
    for key, value in unit.extra.items():
        fm[key] = value

    head = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip("\n")
    return f"---\n{head}\n---\n\n{unit.body.lstrip()}\n"


def compile_units() -> list[Unit]:
    units: list[Unit] = []
    for path in sorted(DOCS.rglob("*.md")):
        units.append(build_unit(path))
    return units


def locate_source(rel_id: str) -> Path:
    """在 `docs/` 里定位一篇稿子。

    `rel_id` 是相对 `docs/` 的路径，带不带 `.md` 都认。三种形态都找：

    | 形态 | 位置 | 内容单元 id |
    | --- | --- | --- |
    | flat 稿 | `docs/<名>.md` | `<名>` |
    | bundle 稿 | `docs/<名>/index.md` | `<名>/index` |
    | 分类页 | `docs/<名>/_index.md` | `<名>/_index` |
    """
    rel = rel_id.strip().lstrip("/")
    if rel.endswith(".md"):
        rel = rel[:-3]
    for candidate in (DOCS / f"{rel}.md", DOCS / rel / "index.md", DOCS / rel / "_index.md"):
        if candidate.is_file():
            return candidate
    raise CompileError(f"docs/ 里找不到这一篇：{rel_id}")


def compile_only(rel_id: str) -> dict:
    """只编译一篇，返回它推导出来的字段。**不动磁盘。**

    给「这一篇能不能进站」这类问题用的——**规则只在这里有一份**，
    平台层（`platforms/blog/cli.py`）问的是这个编译器，不是自己抄一遍规则。
    """
    path = locate_source(rel_id)
    unit = build_unit(path)
    rel = unit.path.as_posix()
    unit_id = rel[:-3] if rel.endswith(".md") else rel
    return {
        "ok": True,
        "unit_id": unit_id,
        "kind": unit.kind,
        "title": unit.title,
        "description": unit.description,
        "date": unit.date,
        "author": unit.author,
        "categories": unit.categories,
        "tags": unit.tags,
        "source_path": rel,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="把 docs/ 编译成 content/units/")
    ap.add_argument(
        "--check",
        action="store_true",
        help="只检查：编译到内存里，跟磁盘上已有的内容单元比对，不一致就非零退出",
    )
    ap.add_argument(
        "--only",
        metavar="ID",
        help="只编一篇（相对 docs/ 的路径，带不带 .md 都认），只读，出一段 JSON",
    )
    args = ap.parse_args()

    if args.only:
        try:
            result = compile_only(args.only)
        except CompileError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        units = compile_units()
    except CompileError as exc:
        print(f"编译失败：{exc}", file=sys.stderr)
        return 2

    rendered = {u.path: render(u) for u in units}

    if args.check:
        problems = []
        for rel, text in rendered.items():
            target = CONTENT_UNITS / rel
            if not target.exists():
                problems.append(f"{rel}：内容单元不存在（该跑一次 build-content-units.py）")
                continue
            if target.read_text(encoding="utf-8") != text:
                problems.append(f"{rel}：内容单元与 docs/ 不同步")
        for existing in sorted(CONTENT_UNITS.rglob("*.md")):
            rel = existing.relative_to(CONTENT_UNITS)
            if rel.parts and rel.parts[0] == "video":
                continue  # 视频单元由 tools/build-video-pages.py 产出
            if rel not in rendered:
                problems.append(f"{rel}：内容单元还在，但 docs/ 里已经没有了（撤出的存量没清干净）")
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print(f"内容单元与 docs/ 一致（{len(rendered)} 篇）")
        return 0

    written = 0
    for rel, text in rendered.items():
        target = CONTENT_UNITS / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            written += 1

    # docs/ 里撤掉但内容单元还在的（除视频单元），清掉——它们是撤出存量的残留。
    removed = 0
    for existing in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = existing.relative_to(CONTENT_UNITS)
        if rel.parts and rel.parts[0] == "video":
            continue
        if rel not in rendered:
            existing.unlink()
            removed += 1
    for d in sorted(CONTENT_UNITS.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    print(f"内容单元：{len(rendered)} 篇（写入 {written}，清理残留 {removed}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
