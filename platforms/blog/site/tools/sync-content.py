#!/usr/bin/env python3
"""把内容单元同步进站点工程 —— **平台层调用的那个入口**。

**为什么它还在**：公众号、头条号这些平台层一直按这个名字调它
（`platforms/wechat/cli.py` 的 `sync` 命令把它当第二步跑）。
那是一条**已发布的接缝**，改名字要连着改下游，不在这一轮里。

**它现在做什么**：把内容单元编成站点的文章（`source/_posts/`），
并把母稿里的图片搬进 `source/images/`。
真正干活的脚本是同目录的 `build-posts.py` —— 那儿才有 hexo 的细节
（permalink、front matter、目录形状）。

用法：

    python3 platforms/blog/site/tools/sync-content.py
    python3 platforms/blog/site/tools/sync-content.py --check   # 只检查是否同步
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SITE_TOOLS = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]

#: 真正干活的脚本。
BUILD_POSTS = SITE_TOOLS / "build-posts.py"


def main() -> int:
    if not BUILD_POSTS.is_file():
        print(f"找不到 {BUILD_POSTS}", file=sys.stderr)
        return 2
    result = subprocess.run(
        [sys.executable, str(BUILD_POSTS), *sys.argv[1:]],
        cwd=str(REPO_ROOT),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
