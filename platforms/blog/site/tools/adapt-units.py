#!/usr/bin/env python3
"""把内容单元仓库（`content/units/`）接到站点的源目录（`source/_posts/`）。

站点是内容单元的**一个消费者**，不是一个所有者。内容单元住在 `content/units/`
（平台无关，所有平台共用）；站点要渲染它们，得先有一份自己的副本。

这个脚本现在只做**逐字节复制**——它不改 front matter、不改链接、不加字段。
站点的专属字段（`layout`、`permalink` 之类）是 sync 编译时写进内容单元的；
以后要拆成「平台无关的字段」+「站点适配时加的字段」，那是**下一个模块**的事，
不在这一步做。

用法：`python3 platforms/blog/site/tools/adapt-units.py`
"""

import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from paths import CONTENT_UNITS, SITE_POSTS  # noqa: E402


def main() -> int:
    if not CONTENT_UNITS.is_dir():
        print(f"内容单元仓库不存在：{CONTENT_UNITS}", file=sys.stderr)
        print("先跑 platforms/blog/site/tools/sync-hexo.py。", file=sys.stderr)
        return 1

    # 先清干净再拷——站点的那份是**副本**，每次构建都从内容单元仓库重来。
    if SITE_POSTS.exists():
        shutil.rmtree(SITE_POSTS)
    shutil.copytree(CONTENT_UNITS, SITE_POSTS)

    n = sum(1 for _ in SITE_POSTS.rglob("*.md"))
    print(f"已接入 {n} 个内容单元 → {SITE_POSTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
