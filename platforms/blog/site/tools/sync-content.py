#!/usr/bin/env python3
"""把内容单元同步进站点工程，并准备静态资源。

做四件事：

1. `content/units/` → `src/content/units/`（Astro 的 content collection 读的副本）。
   **构建产物，不入库**——内容单元本身不入库，副本更不该入库。
2. `docs/` 里的图片 → `public/images/`（按 docs/ 相对路径落盘，不转码）。
   站点里图片走 `/images/<docs 相对路径>`。
3. `node_modules/mermaid/dist/mermaid.esm.min.mjs` → `public/js/`。
   流程图在**客户端**渲染（理由见 design 文档 §七），自托管，不走 CDN。
4. 清掉上一次构建留下的过期文件。

用法：

    python3 platforms/blog/site/tools/sync-content.py
    python3 platforms/blog/site/tools/sync-content.py --check   # 只检查是否同步
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))

from paths import CONTENT_UNITS, DOCS  # noqa: E402

SITE = Path(__file__).resolve().parents[1]
UNITS_DST = SITE / "src" / "content" / "units"
PUBLIC = SITE / "public"
IMAGES_DST = PUBLIC / "images"
JS_DST = PUBLIC / "js"

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif"}

MERMAID_SRC = SITE / "node_modules" / "mermaid" / "dist" / "mermaid.esm.min.mjs"
MERMAID_DST = JS_DST / "mermaid.esm.min.mjs"


def sync_units(check: bool) -> list[str]:
    """内容单元 → 站点副本。返回不一致的地方（check 模式）。"""
    problems: list[str] = []
    want = {
        p.relative_to(CONTENT_UNITS).as_posix(): p.read_bytes()
        for p in sorted(CONTENT_UNITS.rglob("*.md"))
    }
    have = {
        p.relative_to(UNITS_DST).as_posix(): p.read_bytes()
        for p in sorted(UNITS_DST.rglob("*.md"))
    } if UNITS_DST.exists() else {}

    for rel, data in want.items():
        if have.get(rel) != data:
            problems.append(f"units/{rel}")
    for rel in have:
        if rel not in want:
            problems.append(f"units/{rel}（过期）")

    if not check:
        if UNITS_DST.exists():
            shutil.rmtree(UNITS_DST)
        for rel, data in want.items():
            target = UNITS_DST / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return problems


def sync_images(check: bool) -> list[str]:
    """docs/ 里的图片 → public/images/。"""
    problems: list[str] = []
    want = {
        p.relative_to(DOCS).as_posix(): p.read_bytes()
        for p in sorted(DOCS.rglob("*"))
        if p.is_file() and p.suffix.lower() in IMG_EXT
    }
    have = {
        p.relative_to(IMAGES_DST).as_posix(): p.read_bytes()
        for p in sorted(IMAGES_DST.rglob("*"))
        if p.is_file()
    } if IMAGES_DST.exists() else {}

    for rel, data in want.items():
        if have.get(rel) != data:
            problems.append(f"images/{rel}")
    for rel in have:
        if rel not in want:
            problems.append(f"images/{rel}（过期）")

    if not check:
        if IMAGES_DST.exists():
            shutil.rmtree(IMAGES_DST)
        for rel, data in want.items():
            target = IMAGES_DST / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return problems


def sync_mermaid(check: bool) -> list[str]:
    """mermaid 的 ESM 包 → public/js/（自托管，流程图在客户端渲染）。"""
    if not MERMAID_SRC.exists():
        return ["mermaid：node_modules 里没装（跑一次 npm install）"]
    problems: list[str] = []
    data = MERMAID_SRC.read_bytes()
    if not MERMAID_DST.exists() or MERMAID_DST.read_bytes() != data:
        problems.append("js/mermaid.esm.min.mjs")
        if not check:
            JS_DST.mkdir(parents=True, exist_ok=True)
            MERMAID_DST.write_bytes(data)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="把内容单元与静态资源同步进站点工程")
    ap.add_argument("--check", action="store_true", help="只检查，不写盘")
    args = ap.parse_args()

    problems = sync_units(args.check) + sync_images(args.check) + sync_mermaid(args.check)

    if args.check:
        if problems:
            for p in problems:
                print(f"  ✗ {p}", file=sys.stderr)
            print(f"\n{len(problems)} 处不同步", file=sys.stderr)
            return 1
        print("内容单元与静态资源都是同步的")
        return 0

    # 写入模式：problems 是「刚才不同步、现在已同步」的清单，不是失败。
    print(
        f"内容单元与静态资源已同步"
        + (f"（本次更新 {len(problems)} 处）" if problems else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
