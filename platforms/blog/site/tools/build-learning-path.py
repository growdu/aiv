#!/usr/bin/env python3
"""学习流编译：规则表 + 内容单元 → 站点的学习流数据。

**输入**

- `platforms/blog/site/data/learning-path.json` —— 人工策展的规则表（赛道 × 阶段）。
- `content/units/` —— 内容单元（文档与视频）。

**输出**

- `platforms/blog/site/data/learning-path.compiled.json` —— 站点直接读的编译结果：
  每条赛道、每个阶段、底下挂着哪些内容单元，外加一张「内容单元 → 赛道/阶段」的对照表。

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

用法：

    python3 platforms/blog/site/tools/build-learning-path.py            # 编译
    python3 platforms/blog/site/tools/build-learning-path.py --check    # 只检查
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# platforms/blog/site/tools/ → parents[4] 是仓库根，根 tools/ 里有 paths.py
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from paths import CONTENT_UNITS  # noqa: E402

SITE = Path(__file__).resolve().parents[1]
RULES_PATH = SITE / "data" / "learning-path.json"
COMPILED_PATH = SITE / "data" / "learning-path.compiled.json"

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
                "summary": track.get("summary", ""),
                "audience": track.get("audience", ""),
                "goal": track.get("goal", ""),
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

    result = {
        "generated": rules.get("updated", ""),
        "enabled": enabled,
        "tracks": tracks_out,
        "assignment": assignment,
    }
    return result, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="把规则表 + 内容单元编译成学习流数据")
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

    if args.check:
        if not COMPILED_PATH.exists():
            print("学习流数据不存在（该跑一次 build-learning-path.py）", file=sys.stderr)
            return 1
        if COMPILED_PATH.read_text(encoding="utf-8") != text:
            print("学习流数据与规则表/内容单元不同步", file=sys.stderr)
            return 1
        print("学习流数据是最新的")
        return 0

    COMPILED_PATH.write_text(text, encoding="utf-8")
    if not result.get("enabled", True):
        print("学习流：关着（规则表 enabled=false 或没有规则表）——不生成任何学习流页面")
        return 0
    total = sum(t["count"] for t in result["tracks"])
    empty = [
        f"{t['id']}/{s['id']}"
        for t in result["tracks"]
        for s in t["stages"]
        if s["count"] == 0
    ]
    print(f"学习流：{len(result['tracks'])} 条赛道，{total} 篇内容归属")
    if empty:
        print(f"空阶段 {len(empty)} 个（审校还没到）：{'、'.join(empty)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
