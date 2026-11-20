"""个人站点（blog）adapter 的命令行入口。

    python3 -m blog.cli status
    python3 -m blog.cli check <content_id>

**没有 `publish` 子命令**，而且这是有意的。

站点是**全量构建**：一次 push 到 master，CI 重建全站
（`.github/workflows/site.yml`）。别的平台是「逐篇出包、发一篇文章」，
站点不是——站点没有「一篇一篇发」这回事，只有「整站重建一次」。
把逐篇出包在这里重写一遍，等于把
`site/tools/build-learning-path.py` + hexo
再写一遍，而两份必然漂移。

所以这里只回答两个问题：

* ``status`` —— 这个平台是什么、自动化停在哪、有什么限额、站上现在是什么样子；
* ``check``  —— 这一篇能不能进站（母稿过审了没有、编译器收不收、
  它在站上的地址是什么、归到学习流的哪一格）。

**「能不能进站」由编译器说了算。** 这一条检查不自己抄一遍编译规则，
而是去问权威：`tools/build-content-units.py --only <id>`。
规则只有一份，在编译器那儿。

真要上线，走 CI；完整的闸门在 `site/tools/check-markdown.py`、
`site/tests/` 与 `.github/workflows/site.yml` 里。
这一轮的顶层设计见
``review/specs/2026-11-18-顶层设计与目录调整.md``。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from blog import (
    CONTENT_UNITS_DIR,
    DRAFTS_DIR,
    DOCS_DIR,
    MAX_CATEGORY_DEPTH,
    OUTBOX_DIR,
    REPO_ROOT,
)

CAPABILITY_PATH = Path(__file__).resolve().parent / "capability.toml"
SITE_DIR = Path(__file__).resolve().parent / "site"
LEARNING_PATH = SITE_DIR / "data" / "learning-path.compiled.json"
DIST_DIR = SITE_DIR / "dist"


def _load_site_urls():
    """站点那一份地址规则（`site/tools/urls.py`）。

    **问它，不复刻。** 地址形状在站点里只有一处说了算；这里再抄一遍，
    两边迟早漂移。站点那一份读仓库根的 `rules/urls.json`，规则表不在时
    用同样的默认值兜底。
    """
    path = SITE_DIR / "tools" / "urls.py"
    spec = importlib.util.spec_from_file_location("blog_site_urls", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SITE_URLS = _load_site_urls()

#: 站点在公开互联网上的地址。**由使用者给**，框架不写死：
#: 环境变量 `SITE_URL`（Astro 构建与 CI 用的也是同一个变量）。
#: 没配 = 还没上线，status 里如实说「未配置」。
SITE_URL_ENV = "SITE_URL"

#: 内容单元编译器（平台无关，在根 `tools/`）。**只问它，不自己复刻规则。**
COMPILER = REPO_ROOT / "tools" / "build-content-units.py"

#: front matter 的标量字段解析（平台层零运行时依赖，不引 YAML）。
#:
#: 只取 `key: value` 这种一行一个的标量。编译器用 YAML 解析，
#: 这里口径**一致但更粗**：块状写法（`title: >`）这里读不出来。
#: 平台层用它做「有没有标题」的提示，不做权威判定——权威判定问编译器。
_FM_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


# --- 能力声明 ---------------------------------------------------------------


def _capability() -> dict:
    """读本平台的能力声明。

    **自己读，不 import 契约层**——平台层与契约层之间只有这份 TOML 是
    接缝，两边不许互相 import（`publish/spec/00-架构设计.md` §11.1）。
    """
    if not CAPABILITY_PATH.is_file():
        raise SystemExit("能力声明不存在：{}".format(CAPABILITY_PATH))
    return tomllib.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))


# --- 内容单元 ---------------------------------------------------------------


def _front_matter(path: Path) -> dict:
    """读一份 markdown 的 front matter（只取标量字段）。"""
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
        m = _FM_LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        fields[key] = value.strip('"').strip("'")
    return fields


def _content_units() -> list[dict]:
    """内容单元仓库里的全部单元。

    返回 `[{id, kind, title}]`——`id` 是相对 `content/units/` 的路径
    （不带 `.md`），那是站点与编译器之间唯一的键。
    """
    if not CONTENT_UNITS_DIR.is_dir():
        return []
    units = []
    for path in sorted(CONTENT_UNITS_DIR.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS_DIR).as_posix()
        fields = _front_matter(path)
        units.append(
            {
                "id": rel[:-3] if rel.endswith(".md") else rel,
                "kind": fields.get("kind", "document"),
                "title": fields.get("title", ""),
            }
        )
    return units


def _learning() -> dict:
    """学习流的编译结果（赛道 × 阶段 × 内容单元）。"""
    if not LEARNING_PATH.is_file():
        return {}
    try:
        return json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _site_url(unit_id: str, kind: str) -> str:
    """这个内容单元在站上的地址。

    **口径只有一处**：`site/tools/urls.py`（它读仓库根的 `rules/urls.json`）。
    分类页的 id 尾巴带 `_index`、视频的 id 开头带 `video/`——
    那是内容单元里的形状，不是 URL 里的形状，由它负责抹掉。
    """
    return SITE_URLS.unit_url(unit_id, kind)


def _compile_only(unit_id: str) -> dict:
    """问编译器一篇能不能编成内容单元。

    编译器的四条硬要求都在那儿：标题、描述、日期、目录链。
    少一条就是编不出来——站点上就少这一篇，而且**构建会断**。
    """
    proc = subprocess.run(
        [sys.executable, str(COMPILER), "--only", unit_id],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": proc.stderr.strip() or "编译器没有输出"}


def _in_drafts(unit_id: str) -> Path | None:
    """这篇稿子在草稿箱里吗（还没过审，所以还不在母稿层）。"""
    rel = unit_id[:-3] if unit_id.endswith(".md") else unit_id
    for candidate in (
        DRAFTS_DIR / f"{rel}.md",
        DRAFTS_DIR / rel / "index.md",
        DRAFTS_DIR / rel / "_index.md",
    ):
        if candidate.is_file():
            return candidate
    return None


# --- status -----------------------------------------------------------------


def _status() -> int:
    data = _capability()
    units = _content_units()
    snapshots = _snapshots()
    limits = data.get("limits", {})

    print("平台：{}（{}）".format(data.get("name", "?"), data.get("id", "?")))
    site_url = os.environ.get(SITE_URL_ENV, "")
    print("地址：{}".format(site_url or "未配置（设 {} 环境变量）".format(SITE_URL_ENV)))
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

    if not CONTENT_UNITS_DIR.is_dir():
        print("内容单元：还没编译（跑 python3 tools/build-content-units.py）")
    else:
        kinds = {}
        for unit in units:
            kinds[unit["kind"]] = kinds.get(unit["kind"], 0) + 1
        detail = "、".join(f"{k} {v}" for k, v in sorted(kinds.items()))
        print("内容单元：{} 篇（{}）".format(len(units), detail or "空"))

    learning = _learning()
    if learning:
        tracks = learning.get("tracks", [])
        total = sum(t.get("count", 0) for t in tracks)
        filled = sum(1 for t in tracks if t.get("count"))
        print(
            "学习流：{} 条赛道（{} 条有内容）、{} 篇内容归属".format(
                len(tracks), filled, total
            )
        )
    else:
        print("学习流：还没编译（跑 python3 platforms/blog/site/tools/build-learning-path.py）")

    if DIST_DIR.is_dir():
        pages = sum(1 for _ in DIST_DIR.rglob("*.html"))
        print("构建产物：{} 页（{}）".format(pages, DIST_DIR.relative_to(REPO_ROOT)))
    else:
        print("构建产物：还没构建（cd platforms/blog/site && npm run build）")

    print("发布快照：{} 份".format(len(snapshots)))
    if not snapshots:
        print("  （快照目录还空着——站点的账本还没建，见 docs/01-站点即第三方平台.md §5）")
    return 0


def _snapshots() -> list:
    """本平台的发布快照（`outbox/*.json`）。"""
    if not OUTBOX_DIR.is_dir():
        return []
    return sorted(OUTBOX_DIR.glob("*.json"))


# --- check ------------------------------------------------------------------


def _check(content_id: str) -> int:
    """预检一篇能不能进站。

    四件事，每一件都问权威，不自己复刻规则：

    1. **母稿在不在** —— `docs/` 里（已过审）还是在 `drafts/` 里（在改，没过审）；
    2. **编译器收不收** —— `tools/build-content-units.py --only`；
    3. **地址是什么** —— `site/src/lib/urls.ts` 的规则；
    4. **归到学习流的哪一格** —— 归不上就是**构建断掉**（漏归类不许静默）。
    """
    unit_id = content_id.strip().lstrip("/")
    if unit_id.endswith(".md"):
        unit_id = unit_id[:-3]

    # 视频单元不是从 docs/ 编译的——它是视频线自己的产物
    # （母稿在 `video/字幕-<主题>.md`，见 `tools/build-video-pages.py`）。
    if unit_id.startswith("video/"):
        return _check_video(unit_id)

    # ① 母稿在不在
    compiled = _compile_only(unit_id)
    if not compiled.get("ok"):
        error = compiled.get("error", "")
        draft = _in_drafts(unit_id)
        if draft is not None:
            print("目标：{}".format(draft.relative_to(REPO_ROOT)))
            print("形态：草稿（还在改，没过审）")
            print("✗ 不在母稿层：没过审，站点不编译它")
            print("  （过审之后它才会进 docs/，站点才会收录）")
            return 1
        print("✗ 找不到这一篇：docs/{}".format(unit_id))
        print("  （内容单元 id 是相对 content/units/ 的路径，不带 .md）")
        return 1

    kind = compiled.get("kind", "document")
    title = compiled.get("title", "")
    description = compiled.get("description", "")
    date = compiled.get("date", "")
    source_path = compiled.get("source_path", "")

    print("目标：docs/{}".format(source_path))
    print("形态：{}（内容单元 id：{}）".format(
        "分类页" if kind == "category" else "文档", compiled.get("unit_id", unit_id)
    ))
    print("标题：{}".format(title))
    print("描述：{}".format(description))
    print("日期：{}".format(date))
    if compiled.get("categories"):
        print("分类：{}".format(" / ".join(compiled["categories"])))

    # ② 编译器收不收 —— 过了才走到这里（收不了，上面就报错了）
    print("编译：通过（标题、描述、日期、目录链四项都齐）")

    # ③ 地址
    url = _site_url(compiled.get("unit_id", unit_id), kind)
    print("地址：{}".format(url))

    # ④ 学习流归属
    _report_assignment(compiled.get("unit_id", unit_id), learnable=(kind != "category"))

    # ⑤ 深度
    depth = len([s for s in url.strip("/").split("/") if s])
    if depth > MAX_CATEGORY_DEPTH:
        print("提醒：地址深了：{} 段（站点最深 {} 段）".format(depth, MAX_CATEGORY_DEPTH))
    else:
        print("深度：{} 段（站点最深 {} 段）".format(depth, MAX_CATEGORY_DEPTH))

    print("通过（发布前的完整闸门在 CI 里跑）")
    return 0


def _check_video(unit_id: str) -> int:
    """预检一期视频能不能进站。

    视频单元的母稿不在 `docs/`，在视频线自己的目录里
    （`video/字幕-<主题>.md`），由 `tools/build-video-pages.py` 编成内容单元。
    """
    path = CONTENT_UNITS_DIR / (unit_id + ".md")
    if not path.is_file():
        print("✗ 这一期还没编成内容单元：{}".format(path.relative_to(REPO_ROOT)))
        print("  （跑 python3 tools/build-video-pages.py）")
        return 1

    fields = _front_matter(path)
    print("目标：{}（视频内容单元）".format(path.relative_to(REPO_ROOT)))
    print("形态：视频（母稿在 video/ 那一线，不在 docs/）")
    print("标题：{}".format(fields.get("title", "")))
    print("日期：{}".format(fields.get("date", "")))
    print("地址：{}".format(_site_url(unit_id, "video")))
    _report_assignment(unit_id)
    print("通过（发布前的完整闸门在 CI 里跑）")
    return 0


def _report_assignment(unit_id: str, learnable: bool = True) -> None:
    """它归到学习流的哪一格。没归上——**构建会断**。

    分类页不进学习流（它是目录导航，不是内容），所以对分类页这一句不说。
    """
    learning = _learning()
    if not learning:
        if learnable:
            print("学习流：还没编译，归属查不了")
        return
    assignment = (learning.get("assignment") or {}).get(unit_id)
    if not assignment:
        if not learnable:
            return
        print("学习流：✗ 没归类——学习流编译会断（漏归类不许静默）")
        print("  （去 site/data/learning-path.json 给它写一条规则）")
        return
    track = next(
        (t for t in learning.get("tracks", []) if t["id"] == assignment.get("track")),
        None,
    )
    stage = None
    if track:
        stage = next(
            (s for s in track.get("stages", []) if s["id"] == assignment.get("stage")),
            None,
        )
    print(
        "学习流：{} / {} {}".format(
            assignment.get("track"),
            assignment.get("stage"),
            (stage or {}).get("title", ""),
        )
    )
    if assignment.get("fallback"):
        print("  （落在兜底阶段——它该有自己的规则）")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="blog.cli",
        description="个人站点（blog）adapter 的命令行入口",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="这个平台是什么、站上现在是什么样子")
    check = sub.add_parser("check", help="预检一篇能不能进站")
    check.add_argument("content_id", help="内容单元 id（相对 content/units/ 的路径）")

    args = parser.parse_args(argv)
    if args.command == "status":
        return _status()
    if args.command == "check":
        return _check(args.content_id)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
