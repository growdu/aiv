#!/usr/bin/env python3
"""内容单元 → 站点要的文章（`source/_posts/`）。

**输入**

- `content/units/` —— 内容单元（所有平台共用的那一半，站点只是消费者之一）。

**输出**

- `source/_posts/<单元 id>.md` —— 一篇一个 markdown，front matter 里带
  `permalink`（站上的地址）与 `layout: post`。
- `source/docs/<路径>/index.md` —— 目录导航页（`kind: category` 的单元）。
- `source/_data/urls.json` —— 单元 id → 站点地址的对照表。
  **链接重写器（`tools/rewrite-links.mjs`）读它**：正文里那些相对链接
  （`../某篇.md`）要换成站上的地址，形状只有一处说了算——就是这张表。

**规矩**

1. **正文一个字都不改**。这一层只做 front matter 的改写与拷贝；
   链接重写是渲染层的事（`tools/rewrite-links.mjs`，在 AST 上改）。
2. **地址形状由 `tools/urls.py` 决定**（它读仓库根的 `rules/urls.json`）。
3. **不留残留**：`content/units/` 里撤掉的单元，`source/_posts/` 里也得撤掉。
4. **视频单元不进站点**（作者拍板：站上没有视频页）。它们给发布层用。
   但它们**仍然在地址表里**——正文里指向视频的相对链接要有个地址可换，
   那个地址归发布层负责落地，站内不生成页面。

用法::

    python3 platforms/blog/site/tools/build-posts.py
    python3 platforms/blog/site/tools/build-posts.py --check
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from paths import CONTENT_UNITS, DOCS  # noqa: E402
from urls import unit_url  # noqa: E402

SITE = Path(__file__).resolve().parents[1]
POSTS_DIR = SITE / "source" / "_posts"
PAGES_DIR = SITE / "source" / "docs"
DATA_DIR = SITE / "source" / "_data"
IMAGES_DIR = SITE / "source" / "images"

#: 图片扩展名。正文里的图片指向这些后缀的文件时才做重写。
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif")


def split_front_matter(text: str) -> tuple[dict, str]:
    """拆出 front matter 与正文。正文原样返回。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 4 :]
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"front matter 不是合法 YAML：{exc}") from exc
    if not isinstance(fm, dict):
        raise ValueError("front matter 不是键值映射")
    return fm, body.lstrip("\n")


def unit_files() -> list[Path]:
    return sorted(CONTENT_UNITS.rglob("*.md"))


def asset_files() -> list[Path]:
    """母稿里的非 markdown 文件（图片之类）。

    **图片现在还住在 `docs/` 里**——内容单元仓库（`content/units/`）只编
    markdown，图片没跟过来（编译器抽取那一轮会把它搬进
    `content/units/images/`，在那之前站点从 `docs/` 取）。

    `content/units/` 与 `docs/` **同构**，所以按同一套相对路径搬过去，
    站上的地址就是 `/images/<相对路径>`。
    """
    out = []
    if not DOCS.is_dir():
        return out
    for path in sorted(DOCS.rglob("*")):
        if path.is_file() and path.suffix.lower() != ".md":
            out.append(path)
    return out


def build_post(path: Path) -> tuple[dict, str, str]:
    """一个内容单元 → (kind, front matter 字典, 正文)。"""
    rel = path.relative_to(CONTENT_UNITS).as_posix()
    unit_id = rel[: -len(".md")]
    fm, body = split_front_matter(path.read_text(encoding="utf-8"))

    kind = str(fm.get("kind") or "document")
    title = str(fm.get("title") or unit_id)
    description = str(fm.get("description") or "")
    date = fm.get("date")
    author = fm.get("author")

    out: dict = {
        "title": title,
        "permalink": unit_url(unit_id, kind),
        # 母稿里的位置。下游（公众号、头条号）靠它追回原。
        "source_path": str(fm.get("source_path") or rel),
    }
    if kind == "category":
        # 目录导航页：不是文章，不进归档，也不进学习流。
        out["layout"] = "docs-index"
    else:
        out["layout"] = "post"
    if date:
        out["date"] = date
    if author:
        out["author"] = author
    if description:
        out["description"] = description
    categories = list(fm.get("categories") or [])
    tags = list(fm.get("tags") or [])
    if categories:
        out["categories"] = categories
    if tags:
        out["tags"] = tags
    if fm.get("top"):
        out["top"] = True
    if fm.get("tldr"):
        out["tldr"] = fm["tldr"]
    if fm.get("difficulty"):
        out["difficulty"] = fm["difficulty"]
    if fm.get("cover"):
        out["cover"] = fm["cover"]
    if fm.get("mathjax"):
        out["mathjax"] = True

    return kind, out, body


def render(fm: dict, body: str) -> str:
    head = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip("\n")
    return f"---\n{head}\n---\n\n{body.rstrip()}\n"


def build_all() -> tuple[
    dict[str, str], dict[str, str], dict[str, str], list[Path], dict[str, int]
]:
    """编出全部文章与目录页。

    返回 (文档单元 id → 文件内容, 目录页单元 id → 文件内容,
    单元 id → 地址, 图片文件列表, 各种 kind 的单元数)。

    **视频单元没有页面**，但**在地址表里**——正文里指向视频的相对链接
    要有个地址可换。
    """
    posts: dict[str, str] = {}
    pages: dict[str, str] = {}
    urls: dict[str, str] = {}
    images: list[Path] = []
    kinds: dict[str, int] = {}
    for path in unit_files():
        kind, fm, body = build_post(path)
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        unit_id = rel[: -len(".md")]
        urls[unit_id] = fm["permalink"]
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "video":
            continue
        if kind == "category":
            pages[unit_id] = render(fm, body)
        else:
            posts[unit_id] = render(fm, body)
    for path in asset_files():
        if path.suffix.lower() in IMAGE_SUFFIXES:
            images.append(path)
    return posts, pages, urls, images, kinds


def page_path(unit_id: str) -> Path:
    """目录页单元 id → 它在 `source/` 里的位置。

    `_index` 的尾巴抹掉，目录名就是页面所在的目录。
    """
    directory = unit_id[: -len("_index")] if unit_id.endswith("_index") else unit_id
    return PAGES_DIR / directory / "index.md"


def write_all(
    posts: dict[str, str],
    pages: dict[str, str],
    urls: dict[str, str],
    images: list[Path],
) -> None:
    """把编出来的东西写进磁盘，并清掉残留。"""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for unit_id, text in posts.items():
        target = POSTS_DIR / f"{unit_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")

    # 撤掉的单元不许留在磁盘上。
    for existing in sorted(POSTS_DIR.rglob("*.md")):
        rel = existing.relative_to(POSTS_DIR).as_posix()
        unit_id = rel[: -len(".md")]
        if unit_id not in posts:
            existing.unlink()
    for d in sorted(POSTS_DIR.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    # 目录页。整棵目录重写：撤掉的目录页不许留在磁盘上。
    if PAGES_DIR.exists():
        shutil.rmtree(PAGES_DIR)
    for unit_id, text in pages.items():
        target = page_path(unit_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    (DATA_DIR / "urls.json").write_text(
        json.dumps(urls, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 图片：内容单元里的图片原样搬进 source/images/，
    # 正文里的相对路径由重写器改成 /images/<相对路径>。
    #
    # **撤掉的图片也不许留在磁盘上**——跟文章同一个道理。源稿删了一张图，
    # 产物里就得没有它，否则站上会挂着一张「已经没有对应文章」的图片，
    # 而构建日志会说「图片 0 张」，看不出产物里有残留。
    keep: set[Path] = set()
    for path in images:
        rel = path.relative_to(DOCS)
        target = IMAGES_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != path.read_bytes():
            shutil.copyfile(path, target)
        keep.add(target)
    if IMAGES_DIR.exists():
        # 反向排序：文件先于它所在的目录被处理，空目录才好收。
        for existing in sorted(IMAGES_DIR.rglob("*"), reverse=True):
            if existing.is_dir():
                if not any(existing.iterdir()):
                    existing.rmdir()
            elif existing not in keep:
                existing.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="把内容单元编成站点要的文章")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args()

    if not CONTENT_UNITS.is_dir():
        print(
            f"内容单元仓库不存在：{CONTENT_UNITS}\n"
            f"（先在仓库根跑 python3 tools/build-content-units.py）",
            file=sys.stderr,
        )
        return 2

    try:
        posts, pages, urls, images, kinds = build_all()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"文章编译失败：{exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = []
        for unit_id, text in posts.items():
            target = POSTS_DIR / f"{unit_id}.md"
            if not target.exists():
                problems.append(f"{unit_id}：文章不存在（该跑一次 build-posts.py）")
            elif target.read_text(encoding="utf-8") != text:
                problems.append(f"{unit_id}：文章与内容单元不同步")
        for existing in sorted(POSTS_DIR.rglob("*.md")):
            rel = existing.relative_to(POSTS_DIR).as_posix()
            if rel[: -len(".md")] not in posts:
                problems.append(f"{rel}：文章还在，但内容单元已经撤掉了")
        for unit_id, text in pages.items():
            target = page_path(unit_id)
            if not target.exists():
                problems.append(f"{unit_id}：目录页不存在（该跑一次 build-posts.py）")
            elif target.read_text(encoding="utf-8") != text:
                problems.append(f"{unit_id}：目录页与内容单元不同步")
        for existing in sorted(PAGES_DIR.rglob("index.md")):
            rel = existing.parent.relative_to(PAGES_DIR).as_posix()
            unit_id = f"{rel}/_index"
            if unit_id not in pages:
                problems.append(f"{rel}：目录页还在，但内容单元已经撤掉了")
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print(f"文章与内容单元一致（{len(posts)} 篇，{len(pages)} 个目录页）")
        return 0

    write_all(posts, pages, urls, images)
    print(
        f"文章：{len(posts)} 篇，目录页 {len(pages)} 个，"
        f"视频单元 {kinds.get('video', 0)} 个（不进站点），图片 {len(images)} 张"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
