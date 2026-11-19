#!/usr/bin/env python3
"""把要发到博客的文档同步一份到 docs/life/aiv/。

`video/` 是仓库根级模块（与 `platforms/` 同级），整个目录不在 `docs/` 下面，
而站点只扫 `docs/`——所以要发布的文档必须在 `docs/life/aiv/`
留一份，否则那些规范页面会从站上消失。

这里是「哪些文档要发布」的唯一真相：

- 专题页 + 三篇规范 + 各模块说明：面向读者的内容，继续发
- 不含 `pipeline/` 下的内部设计、实施计划与测试夹具：
  那是工程内部产物，不是文章。尤其是 `persona_script_bad.md`
  ——它是故意写坏的测试样本，绝不能发到公网上。

**发布出去的文件名就是 URL 的一段**，所以白名单里的名字有两条硬要求：

- 一律小写：站点会把 URL 段小写化，`README.md` 上去变成 `readme/`，
  别处按原名写的链接就对不上。
- 不能叫 `index.md`：那是目录落地页的位置，一篇叫 `index.md` 的稿子
  会跟同目录的分类页抢同一个 URL，稿子直接消失。

不合规就在这里拒绝发布——名字是接口的一部分，不是随手起的。

改完 `video/` 里的文档后跑一次：

    python3 video/scripts/sync_publish_docs.py

`pipeline/tests/test_publish_copy.py` 盯着两份是否一致，漂了会红。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

AIV_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AIV_ROOT.parent
PUBLISH_DIR = REPO_ROOT / "docs" / "life" / "aiv"

# 要在 docs/life/aiv/ 留一份的文档（相对 video/）
PUBLISH_DOCS = (
    "视频线总览.md",
    "人格规范.md",
    "形象与音色规范.md",
    "背景音乐规范.md",
    "brand/readme.md",
    "brand/scripts/readme.md",
    "character/readme.md",
    "music/readme.md",
    "voice/readme.md",
)

# 站点的 URL 段：小写，且「index」是目录落地页的 reserved word。
RESERVED_NAMES = ("index.md",)


def check_names() -> None:
    """白名单里的名字必须能当 URL 段用。"""
    problems = []
    for rel in PUBLISH_DOCS:
        name = Path(rel).name
        if name != name.lower():
            problems.append(f"{rel}：文件名要小写（站点会把 URL 段小写化）")
        if name in RESERVED_NAMES:
            problems.append(f"{rel}：{name} 是目录落地页的位置，不能拿来当稿子的名字")
        for part in Path(rel).parts[:-1]:
            if part != part.lower():
                problems.append(f"{rel}：目录名 {part} 要小写（站点会把 URL 段小写化）")
    if problems:
        raise SystemExit("发布名单里的名字不合规：\n  " + "\n  ".join(problems))


def copy_all() -> list[str]:
    """把白名单里的文档复制到发布目录，返回复制了哪些。"""
    check_names()
    copied: list[str] = []
    for rel in PUBLISH_DOCS:
        src = AIV_ROOT / rel
        if not src.is_file():
            raise SystemExit(f"缺少文档：{src}")
        dst = PUBLISH_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    return copied


if __name__ == "__main__":
    done = copy_all()
    for rel in done:
        print(f"已同步 → docs/life/aiv/{rel}")
    print(f"共 {len(done)} 篇")
    sys.exit(0)
