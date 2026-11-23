#!/usr/bin/env python3
"""学习流编译：规则表 + 内容单元 → 站点的学习流数据与页面。

**输入**

- `platforms/blog/site/data/learning-path.json` —— 人工策展的规则表（赛道 × 阶段）。
- `content/units/` —— 内容单元（文档与视频）。

**输出**

- `platforms/blog/site/data/learning-path.compiled.json` —— 编译结果（**账本**）：
  每条赛道、每个阶段、底下挂着哪些内容单元，外加一张「内容单元 → 赛道/阶段」的对照表。
  文档与视频都在里面——发布层要问「这一期归哪一格」。
- `platforms/blog/site/source/_data/learning.json` —— 模板读的数据（首页的面板读它）。
  这是**站上那一面**：只列文档（站上没有视频页）。
- `platforms/blog/site/source/learning/index.md` —— 学习流总览页。
- `platforms/blog/site/source/learning/<赛道>/index.md` —— 每条赛道一页。

**规矩**

1. **漏归类不许静默**。一篇文档或一期视频没落到任何赛道，编译失败——
   不是「先放兜底里」，是**构建断掉**。往站点上加一条内容却忘了给它写规则，
   必须在 CI 里看得见。
2. **阶段可以空**。某阶段还没有内容是正常的（审校还没到那儿），
   空阶段照样渲染，只是页面上是灰的——空缺是可见的。
3. **只映射文档与视频**。分类页（`kind: category`）是目录导航，不进学习流。
4. **学习流可以整个关掉**。规则表 `data/learning-path.json` 里
   `enabled: false`（或者干脆没有这个文件）→ 学习流这个模块不存在：
   不映射、不报错、一个页面都不生成。站点退成普通的文档站。
5. **模板不生成内容**。页面的正文由这里按规则表编出来，主题只负责把它
   放进框里。规则改了，页面跟着变；不要在模板里手写文章列表。

用法：

    python3 platforms/blog/site/tools/build-learning-path.py            # 编译
    python3 platforms/blog/site/tools/build-learning-path.py --check    # 只检查
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# platforms/blog/site/tools/ → parents[4] 是仓库根，根 tools/ 里有 paths.py
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from paths import CONTENT_UNITS  # noqa: E402
from urls import unit_url  # noqa: E402

SITE = Path(__file__).resolve().parents[1]
RULES_PATH = SITE / "data" / "learning-path.json"
COMPILED_PATH = SITE / "data" / "learning-path.compiled.json"
LEARNING_DATA = SITE / "source" / "_data" / "learning.json"
LEARNING_PAGES = SITE / "source" / "learning"

#: 进学习流的单元类型。分类页（category）是目录导航，不进。
LEARNABLE_KINDS = ("document", "video")


def load_units() -> list[dict]:
    """读内容单元，返回 [{path, title, kind, categories, tags}]。

    path 是相对 content/units/ 的路径，**不带 .md**——规则表按这个形式写。
    """
    units = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        text = path.read_text(encoding="utf-8")
        fm: dict = {}
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                loaded = yaml.safe_load(text[3:end]) or {}
                if isinstance(loaded, dict):
                    fm = loaded
        unit_path = rel[:-3] if rel.endswith(".md") else rel
        units.append(
            {
                "path": unit_path,
                "title": str(fm.get("title") or unit_path),
                "kind": str(fm.get("kind") or "document"),
                "categories": list(fm.get("categories") or []),
                "tags": list(fm.get("tags") or []),
                "source_path": str(fm.get("source_path") or rel),
            }
        )
    return units


def match_rule(rule: dict, unit: dict) -> bool:
    """一条规则对不对得上这个内容单元。

    规则里可以出现多个键，**全部满足**才算命中（`any` / `all` 除外）。
    """
    if not rule:
        return False
    if rule.get("catch_all"):
        return True

    checks = []
    for key, value in rule.items():
        if key in ("any", "all"):
            continue
        if key == "path_prefix":
            checks.append(unit["path"].startswith(value))
        elif key == "path_exact":
            checks.append(unit["path"] == value)
        elif key == "path_regex":
            checks.append(re.search(value, unit["path"]) is not None)
        elif key == "category":
            checks.append(value in unit["categories"])
        elif key == "tag":
            checks.append(value in unit["tags"])
        elif key == "title_contains":
            checks.append(value in unit["title"])
        else:
            raise ValueError(f"规则里有不认识的匹配键：{key}")

    if "any" in rule:
        return any(match_rule(sub, unit) for sub in rule["any"])
    if "all" in rule:
        return all(match_rule(sub, unit) for sub in rule["all"])
    if not checks:
        return False
    return all(checks)


def load_rules() -> dict:
    """读规则表。

    **规则表可以没有**——那意思是「不用学习流这个模块」。
    也可以在表里写 `enabled: false` 显式关掉。两种都编出一份空的学习流，
    并且**不检查漏归类**（没开的模块不配规则是正常的）。
    """
    if not RULES_PATH.exists():
        return {"enabled": False, "tracks": []}
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if rules.get("enabled") is False:
        return {"enabled": False, "tracks": []}
    return rules


def compile_learning_path() -> tuple[dict, list[str]]:
    """编译学习流。返回 (编译结果, 问题列表)。"""
    rules = load_rules()
    enabled = rules.get("enabled", True)
    units = [u for u in load_units() if u["kind"] in LEARNABLE_KINDS]

    problems: list[str] = []
    assignment: dict[str, dict] = {}
    tracks_out = []

    for track in rules["tracks"]:
        stages_out = []
        for stage in track["stages"]:
            members = []
            for unit in units:
                if unit["path"] in assignment:
                    continue
                if not any(match_rule(r, unit) for r in track.get("track_match", [])):
                    continue
                if any(match_rule(r, unit) for r in stage.get("match", [])):
                    members.append(unit["path"])
                    assignment[unit["path"]] = {
                        "track": track["id"],
                        "stage": stage["id"],
                    }
            stages_out.append(
                {
                    "id": stage["id"],
                    "title": stage["title"],
                    "goal": stage.get("goal", ""),
                    "units": members,
                    "count": len(members),
                }
            )

        # 落到这条赛道、但哪个阶段都没匹配上的 → 兜底阶段。
        # 兜底桶**理应**是空的（每篇内容都该有自己的规则），有东西就报出来。
        fallback_id = track.get("fallback_stage")
        fallback_members = []
        if fallback_id:
            for unit in units:
                if unit["path"] in assignment:
                    continue
                if any(match_rule(r, unit) for r in track.get("track_match", [])):
                    fallback_members.append(unit["path"])
                    assignment[unit["path"]] = {
                        "track": track["id"],
                        "stage": fallback_id,
                        "fallback": True,
                    }
            if fallback_members:
                problems.append(
                    f"{track['id']} 的兜底阶段 {fallback_id} 收了 "
                    f"{len(fallback_members)} 个内容单元（它们该有自己的规则）："
                    + "、".join(fallback_members)
                )

        tracks_out.append(
            {
                "id": track["id"],
                "title": track["title"],
                "icon": track.get("icon", ""),
                "summary": track.get("summary", ""),
                "audience": track.get("audience", ""),
                "goal": track.get("goal", ""),
                # 状态位：**筹备中**（planned）的赛道允许空阶段——
                # 那是公开宣布的课程大纲，不是洞。渲染层靠它打「筹备中」标记。
                "status": track.get("status", "active"),
                "fallback_stage": fallback_id,
                "stages": stages_out,
                "count": sum(s["count"] for s in stages_out),
            }
        )

    # 漏归类：既不在任何赛道，也不在任何兜底桶里。
    # 学习流关着的时候不查——没开的模块不配规则是正常的，不是漏。
    if enabled:
        for unit in units:
            if unit["path"] not in assignment:
                problems.append(
                    f"漏归类：{unit['path']}（{unit['title']}）没落到任何赛道，"
                    f"学习流规则表里得给它写一条"
                )

    total = sum(t["count"] for t in tracks_out)
    result = {
        "generated": rules.get("updated", ""),
        "enabled": enabled,
        "total": total,
        "tracks": tracks_out,
        "assignment": assignment,
    }
    return result, problems


# ── 页面生成 ────────────────────────────────────────────────────────


def _front_matter(title: str) -> str:
    return (
        "---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        "layout: learning\n"
        "type: learning\n"
        "---\n\n"
    )


def _unit_info(units_by_path: dict[str, dict]) -> dict[str, dict]:
    """内容单元 → {标题, 地址, 分类}。地址由 `tools/urls.py` 决定。"""
    out = {}
    for path, unit in units_by_path.items():
        out[path] = {
            "title": unit["title"],
            "url": unit_url(path, unit["kind"]),
            "categories": unit["categories"],
        }
    return out


def site_view(result: dict, units: list[dict]) -> dict:
    """编译结果 → **站上那一面**。

    **为什么有两面**：编译结果（`data/learning-path.compiled.json`）是
    **归类账本**——文档与视频都记在里面，发布层要问「这一期归哪一格」。
    站上那一面只列**文档**：站上没有视频页（作者拍板），把视频列进学习流
    页面，点过去就是一个 404。

    所以这里只做一件事：把视频从页面与计数里摘掉，账本本身不动。
    """
    kinds = {u["path"]: u["kind"] for u in units}
    tracks = []
    total = 0
    for track in result.get("tracks") or []:
        stages = []
        track_total = 0
        for stage in track.get("stages") or []:
            members = [p for p in stage.get("units") or [] if kinds.get(p) != "video"]
            stages.append(
                {
                    "id": stage["id"],
                    "title": stage["title"],
                    "goal": stage.get("goal", ""),
                    "units": members,
                    "count": len(members),
                }
            )
            track_total += len(members)
        tracks.append(
            {
                "id": track["id"],
                "title": track["title"],
                "icon": track.get("icon", ""),
                "summary": track.get("summary", ""),
                "audience": track.get("audience", ""),
                "goal": track.get("goal", ""),
                # 筹备中的赛道把状态位带到站上——页面据此打「筹备中」标记。
                "status": track.get("status", "active"),
                "stages": stages,
                "count": track_total,
            }
        )
        total += track_total
    return {
        "generated": result.get("generated", ""),
        "enabled": result.get("enabled", True),
        "total": total,
        "tracks": tracks,
    }


def _planned_badge(track: dict) -> str:
    """筹备中的赛道在标题旁边挂一个徽标。

    **「筹备中」和「规则缺失」在数据上长得一样**（都是 0 篇）。
    读者看的是页面，不是数据——所以区别得**看得见**。
    """
    if track.get("status") != "planned":
        return ""
    return ' <span class="lane-badge lane-badge--planned">筹备中</span>'


def render_learning_pages(result: dict, units: list[dict]) -> dict[str, str]:
    """编出学习流的页面。返回 {相对 source/ 的路径: 正文}。

    页面列的是**站上有的东西**：视频没有页面，不列（否则就是站内死链）。
    """
    by_path = {u["path"]: u for u in units}
    info = _unit_info(by_path)
    tracks = result.get("tracks") or []
    total = result.get("total") or 0

    pages: dict[str, str] = {}

    # ── 总览页 ─────────────────────────────────────────────────────
    lines = [
        _front_matter("学习路径"),
        "# 学习路径",
        "",
        f"全站 {total} 篇内容，按**赛道**和**阶段**排成了一条可以从头读到尾的路。",
        "每条赛道都说明了：读它之前该会什么、读完能做什么、下一篇读哪篇。",
        "",
        "**不是分类，是顺序。** 内容按主题分了类，那是**检索**用的；",
        "这里是**导航**用的 —— 告诉你先读什么。",
        "",
        "## 赛道地图",
        "",
    ]
    for track in tracks:
        icon = f"{track['icon']} " if track.get("icon") else ""
        badge = _planned_badge(track)
        lines.append(
            f"### [{track['title']}](/learning/{track['id']}/){badge} · {track['count']} 篇")
        lines.append("")
        if track.get("summary"):
            lines.append(track["summary"])
            lines.append("")
        lines.append("| 阶段 | 主题 | 文章数 |")
        lines.append("| --- | --- | ---: |")
        for stage in track["stages"]:
            lines.append(f"| **{stage['id']}** | {stage['title']} | {stage['count']} |")
        lines.append("")
    pages["learning/index.md"] = "\n".join(lines).rstrip() + "\n"

    # ── 每条赛道一页 ───────────────────────────────────────────────
    for track in tracks:
        badge = _planned_badge(track)
        lines = [
            _front_matter(f"{track['title']} · 学习路径"),
            f"# {track['title']}{badge}",
            "",
        ]
        if track.get("summary"):
            lines += [f"> {track['summary']}", ""]
        if track.get("audience"):
            lines += [f"**适合谁**：{track['audience']}", ""]
        if track.get("goal"):
            lines += [f"**读完能做什么**：{track['goal']}", ""]
        lines += ["[← 回到学习路径总览](/learning/)", "", "## 阶段一览", ""]
        lines += ["| 阶段 | 主题 | 文章数 | 读完这一阶段，你该能做到 |"]
        lines += ["| --- | --- | ---: | --- |"]
        for stage in track["stages"]:
            goal = stage.get("goal", "").replace("|", "\\|")
            lines.append(f"| **{stage['id']}** | {stage['title']} | {stage['count']} | {goal} |")
        lines.append("")
        for stage in track["stages"]:
            lines.append(f"## {stage['id']} · {stage['title']}")
            lines.append("")
            if stage.get("goal"):
                lines += [stage["goal"], ""]
            if not stage["units"]:
                lines += ["_这一阶段还没有内容。_", ""]
                continue
            for unit_path in stage["units"]:
                meta = info.get(unit_path)
                if not meta:
                    continue
                cats = " / ".join(meta["categories"])
                suffix = f" — {cats}" if cats else ""
                lines.append(f"- [{meta['title']}]({meta['url']}){suffix}")
            lines.append("")
        pages[f"learning/{track['id']}/index.md"] = "\n".join(lines).rstrip() + "\n"

    return pages


def write_pages(pages: dict[str, str]) -> None:
    """把页面写进 `source/learning/`，并清掉残留。"""
    if LEARNING_PAGES.exists():
        shutil.rmtree(LEARNING_PAGES)
    for rel, text in pages.items():
        target = LEARNING_PAGES.parent / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def clear_pages() -> None:
    """学习流关着的时候，把它的页面与数据清干净。"""
    if LEARNING_PAGES.exists():
        shutil.rmtree(LEARNING_PAGES)
    if LEARNING_DATA.exists():
        LEARNING_DATA.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="把规则表 + 内容单元编译成学习流数据与页面")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args()

    # 内容单元仓库是**上游**的产物（根 tools/build-content-units.py 编出来的）。
    # 它不在的时候必须喊出来——不然会编出一份「0 篇内容」的学习流，
    # 站点照样构建成功，只是内容全没了。那种「绿着的空」比报错难查得多。
    if not CONTENT_UNITS.is_dir():
        print(
            f"内容单元仓库不存在：{CONTENT_UNITS}\n"
            f"（先在仓库根跑 python3 tools/build-content-units.py）",
            file=sys.stderr,
        )
        return 2

    try:
        result, problems = compile_learning_path()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"学习流编译失败：{exc}", file=sys.stderr)
        return 2

    if problems:
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print(f"\n{len(problems)} 处问题", file=sys.stderr)
        return 1

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    enabled = result.get("enabled", True)
    if enabled:
        units = load_units()
        view = site_view(result, units)
        pages = render_learning_pages(view, units)
        learning_data = json.dumps(view, ensure_ascii=False, indent=2) + "\n"
    else:
        pages = {}
        learning_data = None

    if args.check:
        problems = []
        if not COMPILED_PATH.exists():
            problems.append("学习流数据不存在（该跑一次 build-learning-path.py）")
        elif COMPILED_PATH.read_text(encoding="utf-8") != text:
            problems.append("学习流数据与规则表/内容单元不同步")

        if enabled:
            if not LEARNING_DATA.exists():
                problems.append("source/_data/learning.json 不存在")
            elif LEARNING_DATA.read_text(encoding="utf-8") != learning_data:
                problems.append("source/_data/learning.json 与规则表不同步")
            for rel, body in pages.items():
                target = LEARNING_PAGES.parent / rel
                if not target.exists():
                    problems.append(f"{target.relative_to(SITE)}：不存在")
                elif target.read_text(encoding="utf-8") != body:
                    problems.append(f"{target.relative_to(SITE)}：与规则表不同步")
        else:
            if LEARNING_DATA.exists():
                problems.append("学习流关着，但 source/_data/learning.json 还在")
            if LEARNING_PAGES.exists():
                problems.append("学习流关着，但 source/learning/ 还在")

        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print("学习流数据与页面是最新的")
        return 0

    COMPILED_PATH.write_text(text, encoding="utf-8")
    if not enabled:
        clear_pages()
        print("学习流：关着（规则表 enabled=false 或没有规则表）——不生成任何学习流页面")
        return 0

    LEARNING_DATA.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_DATA.write_text(learning_data, encoding="utf-8")
    write_pages(pages)

    total = result["total"]
    site_total = sum(t["count"] for t in view["tracks"])
    empty = [
        f"{t['id']}/{s['id']}"
        for t in view["tracks"]
        for s in t["stages"]
        if s["count"] == 0
    ]
    print(
        f"学习流：{len(result['tracks'])} 条赛道，{total} 篇内容归属"
        f"（站上列 {site_total} 篇，视频没有页面），{len(pages)} 个页面"
    )
    if empty:
        print(f"空阶段 {len(empty)} 个（审校还没到）：{'、'.join(empty)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
