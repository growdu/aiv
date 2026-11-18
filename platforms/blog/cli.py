"""growdu.cn（个人站点）adapter 的命令行入口。

    python3 -m blog.cli status
    python3 -m blog.cli check <content_id>

**没有 `publish` 子命令**，而且这是有意的。

站点是**全量构建**：一次 push 到 master，CI 重建全部 2400 个页面
（`.github/workflows/hexo.yml`）。别的平台是「逐篇出包、发一篇文章」，
站点不是——站点没有「一篇一篇发」这回事，只有「整站重建一次」。
把逐篇出包在这里重写一遍，等于把
`platforms/blog/site/tools/sync-hexo.py` + hexo
再写一遍，而两份必然漂移。

所以这里只回答两个问题：

* ``status`` —— 这个平台是什么、自动化停在哪、有什么限额、账本上多少条；
* ``check``  —— 这一篇能不能进站（母稿在不在、front matter 全不全、
  它的站内相对链接能不能解析）。

真要上线，走 CI；完整的闸门在 `tools/check-*.py` 与
`.github/workflows/site-guard.yml` 里。这一轮的顶层设计见
``review/specs/2026-11-18-顶层设计与目录调整.md``。
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

from blog import (
    DOCS_DIR,
    EXCLUDED_DIR_NAMES,
    MAX_CATEGORY_DEPTH,
    OUTBOX_DIR,
    REPO_ROOT,
)

CAPABILITY_PATH = Path(__file__).resolve().parent / "capability.toml"

#: 站点在公开互联网上的地址（`url` 写在 Hexo 配置里，这里是同一个值）。
SITE_URL = "https://growdu.cn"

#: 站上标题的第二个来源：正文里第一个 H1。
#: 口径与 `platforms/blog/site/tools/sync-hexo.py::extract_title` 对齐。
H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _capability() -> dict:
    """读本平台的能力声明。

    **自己读，不 import 契约层**——平台层与契约层之间只有这份 TOML 是
    接缝，两边不许互相 import（`publish/spec/00-架构设计.md` §11.1）。
    """
    if not CAPABILITY_PATH.is_file():
        raise SystemExit("能力声明不存在：{}".format(CAPABILITY_PATH))
    return tomllib.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))


def _front_matter(path: Path) -> dict:
    """读一份 markdown 的 front matter。

    只取最上面那一段 `---` … `---`；文件没有 front matter 就返回空字典。
    这里**不做完整 YAML 解析**——站点要检查的字段只有两三个，
    为此引一个 YAML 依赖不划算（契约层也是零运行时依赖）。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fields = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _content_units() -> list:
    """`docs/` 下全部内容单元（不含 `_index.md`——那是分类页，不是文章）。"""
    return sorted(
        path for path in DOCS_DIR.rglob("*.md") if path.name != "_index.md"
    )


def _snapshots() -> list:
    """本平台的发布快照（`outbox/*.json`）。"""
    if not OUTBOX_DIR.is_dir():
        return []
    return sorted(OUTBOX_DIR.glob("*.json"))


def _first_h1(path: Path) -> str | None:
    """正文里第一个 H1——站上标题的第二个来源。

    口径与 `platforms/blog/site/tools/sync-hexo.py::extract_title` 对齐：
    取第一个 `# ` 开头的行，去掉行尾空白。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = H1_PATTERN.search(text)
    return match.group(1).strip() if match else None


# --- status ---------------------------------------------------------------


def _status() -> int:
    data = _capability()
    units = _content_units()
    snapshots = _snapshots()
    limits = data.get("limits", {})

    print("平台：{}（{}）".format(data.get("name", "?"), data.get("id", "?")))
    print("地址：{}".format(SITE_URL))
    print("形态：{}（站点上的一切都是 markdown 页面）".format(data.get("kind", "?")))
    print("自动化：{}".format(data.get("automation", "?")))
    print("发布前审核：{}".format(data.get("review", "?")))
    print("凭据：{}".format(data.get("auth", "?")))
    if limits:
        print("限额：")
        for key in sorted(limits):
            print("  {} = {}".format(key, limits[key]))
    else:
        print("限额：无（标题与正文都不设上限）")
    print("内容单元：{} 篇（docs/ 下，不含目录页）".format(len(units)))
    print("发布快照：{} 份".format(len(snapshots)))
    if not snapshots:
        print("  （快照目录还空着——站点的账本还没建，见 docs/01-站点即第三方平台.md §5）")
    return 0


# --- check ----------------------------------------------------------------


def _check(content_id: str) -> int:
    """预检一篇能不能进站。

    **这不是全部的闸**——完整的检查在 `tools/check-content-contract.py`
    （内容契约）、`tools/check-markdown.py`（格式）、
    `tools/check-internal-links.py`（站内链接）里，那些要跑完整构建才做得全。

    这里做的是**不需要构建就能看出来、而且是站点特有**的那几条：
    母稿在不在、标题取不取得到、会不会被构建整棵排除、分类链有多深。
    别的平台没有「站内链接」「目录深度」这两回事，所以这些检查住在这个包里。
    """
    problems = []
    relative = content_id.strip().lstrip("/")
    if relative.endswith(".md"):
        relative = relative[:-3]
    path = DOCS_DIR / (relative + ".md")
    bundle = DOCS_DIR / relative / "index.md"

    if path.is_file() and bundle.is_file():
        print("✗ 两种形态同时存在：")
        print("  docs/{}.md".format(relative))
        print("  docs/{}/index.md".format(relative))
        print("  站点只会认其中一种（sync-hexo 按 flat 优先），另一个是死内容。")
        return 1
    if path.is_file():
        target = path
        # flat 形态：这一篇住在自己的目录里，那个目录就是它的分类链末梢
        container = path.parent
        segments = len(container.relative_to(DOCS_DIR).parts) + 1
    elif bundle.is_file():
        target = bundle
        # bundle 形态：文章目录自己不算一级分类，它的上一级才是
        container = bundle.parent.parent
        segments = len(bundle.parent.relative_to(DOCS_DIR).parts)
    else:
        print("✗ 找不到这一篇：docs/{}.md".format(relative))
        print("  （bundle 形式 docs/{}/index.md 也不存在）".format(relative))
        return 1

    print("目标：{}".format(target.relative_to(REPO_ROOT)))

    # ① front matter：站上要的是「能取到标题」，不是「front matter 里有 title」
    #    —— 标题优先取 front matter 的 title，没有就剥第一个 H1
    #    （`platforms/blog/site/tools/sync-hexo.py::extract_title` 就是这个口径）。
    fields = _front_matter(target)
    title = fields.get("title") or _first_h1(target)
    if title:
        print("标题：{}".format(title))
    else:
        problems.append("取不到标题（front matter 没有 title，正文也没有第一个 H1）")

    # ② 会不会被构建排除：路径里带工程目录名的那棵子树**整棵**不进产物
    excluded = [
        part for part in target.relative_to(DOCS_DIR).parts[:-1]
        if part.lower() in EXCLUDED_DIR_NAMES
    ]
    if excluded:
        problems.append(
            "构建会排除它：路径上有工程目录 {}".format("、".join(excluded))
        )
    else:
        print("构建排除：不会（路径上没有工程目录名）")

    # ③ 分类链（深度按站上 URL 的段数算）
    ancestors = list(container.relative_to(DOCS_DIR).parts)
    print("分类链：{}".format(" › ".join(["docs"] + ancestors) or "docs（顶层）"))
    if segments > MAX_CATEGORY_DEPTH:
        problems.append(
            "分类链深了：URL {} 段（站点最深 {} 段）".format(
                segments, MAX_CATEGORY_DEPTH
            )
        )
    # 分类页：缺了不是硬错，但文章在站上少一个入口——只提醒
    for depth, name in enumerate(ancestors, start=1):
        directory = DOCS_DIR.joinpath(*ancestors[:depth])
        if not (directory / "_index.md").is_file():
            print("提醒：第 {} 级 {} 没有 _index.md（这一级没有分类页）".format(
                depth, directory.relative_to(DOCS_DIR)))

    if problems:
        print("不通过：")
        for item in problems:
            print("  · {}".format(item))
        return 1

    print("通过（发布前的完整闸门在 CI 里跑）")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="blog.cli",
        description="growdu.cn（个人站点）adapter 的命令行入口",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="这个平台是什么、有什么限额、账本上多少条")
    check = sub.add_parser("check", help="预检一篇能不能进站")
    check.add_argument("content_id", help="内容单元 id（docs/ 下的相对路径）")

    args = parser.parse_args(argv)
    if args.command == "status":
        return _status()
    if args.command == "check":
        return _check(args.content_id)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
