#!/usr/bin/env python3
"""把第三方库从 `node_modules/` 搬进站点。

**为什么搬而不是引 CDN**：站点要在离线的环境里也能打开（内网、
离线归档、CI 的产物检查）。第三方库跟着 `package.json` 走，构建时搬进
`source/lib/`，构建产物就是自洽的。

**搬哪些**：只有主题的 `source/libs/` 里没有、但模板要引的那些。
目前是 mermaid（主题树里没有它，主题的 `_config.yml` 里指向
`/lib/mermaid/mermaid.min.js`）。

用法::

    python3 platforms/blog/site/tools/copy-vendor.py
    python3 platforms/blog/site/tools/copy-vendor.py --check
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
NODE_MODULES = SITE / "node_modules"
LIB_DIR = SITE / "source" / "lib"

#: (node_modules 里的相对路径, 站点里的相对路径)
VENDORS = (
    ("mermaid/dist/mermaid.min.js", "mermaid/mermaid.min.js"),
)


def copy_all() -> list[tuple[Path, Path]]:
    """把每个库搬过去。返回 [(源, 目标)]。"""
    jobs = []
    for src_rel, dst_rel in VENDORS:
        src = NODE_MODULES / src_rel
        dst = LIB_DIR / dst_rel
        if not src.exists():
            print(
                f"第三方库不在：{src}\n（先在站点目录跑 npm install）",
                file=sys.stderr,
            )
            raise SystemExit(2)
        jobs.append((src, dst))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="把第三方库搬进站点")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args()

    try:
        jobs = copy_all()
    except OSError as exc:
        print(f"搬第三方库失败：{exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = []
        for src, dst in jobs:
            if not dst.exists():
                problems.append(f"{dst.relative_to(SITE)}：不存在（该跑一次 copy-vendor.py）")
            elif dst.read_bytes() != src.read_bytes():
                problems.append(f"{dst.relative_to(SITE)}：与 node_modules 里的不一样")
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print(f"第三方库与 node_modules 一致（{len(jobs)} 个）")
        return 0

    for src, dst in jobs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)

    print(f"第三方库：{len(jobs)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
