#!/usr/bin/env python3
"""活动账本编译：账本 + 内容单元 → 站点的活动数据（四个数字 + 时间轴）。

**输入**

- `platforms/blog/site/data/activity.json` —— 站点的账本，一天一条。
- `content/units/` —— 内容单元（文档与视频）。**站点唯一的内容来源**，
  每个单元带着它被写出来的那一天（编译器取的是最早一次提交）。

**输出**

- `platforms/blog/site/data/activity.compiled.json` —— 编译结果：
  四个数字（连续 / 累计）+ 逐日记录（每天挂着当天写出来的东西）。

**四条口径**（写在账本的 `rules` 里，改口径不用改代码）

| 数字 | 怎么算 |
| --- | --- |
| 写作 | 当天有内容单元产出 |
| 学习 | 当天产出的单元落在学习线（`rules.learn_lines`） |
| 用 AI | 当天有产出，或账本里显式记了 `ai` |
| 偷懒 | 既没产出、账本里也没记（区间内的空档） |

**增量**

账本**只增不改**：历史不回头补，站点也不去挖仓库的旧历史。
`--append` 把今天补进账本——幂等，同一天不重复加。

用法：

    python3 platforms/blog/site/tools/build-activity.py            # 编译
    python3 platforms/blog/site/tools/build-activity.py --append   # 把今天记进账本
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# platforms/blog/site/tools/ → parents[4] 是仓库根，根 tools/ 里有 paths.py
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))

import yaml  # noqa: E402

from paths import CONTENT_UNITS  # noqa: E402

# 共享 URL 规则的读取器在根 `tools/`（`url_rules.py`）。
# **站点工具读它，根 tools/ 不反向 import 站点**——层间只有这一条关系。
from url_rules import unit_url  # noqa: E402

SITE = Path(__file__).resolve().parents[1]
LEDGER_PATH = SITE / "data" / "activity.json"
COMPILED_PATH = SITE / "data" / "activity.compiled.json"

#: 进时间轴的单元类型。分类页（category）是目录导航，不算「写出来的东西」。
LEARNABLE_KINDS = ("document", "video")


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"账本不存在：{LEDGER_PATH}")
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def load_units() -> list[dict]:
    """读内容单元，返回 [{id, title, kind, date, line}]。

    `date` 只留日期部分（编译器的 date 带时分秒）。
    `line` 是单元 id 的第一段——内容单元的 id 就是它相对 `content/units/`
    的路径，第一段就是那条线（`source-tracks` / `distributed` / `video`……）。
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
        kind = str(fm.get("kind") or "document")
        if kind not in LEARNABLE_KINDS:
            continue
        raw_date = str(fm.get("date") or "").strip()
        if not raw_date:
            continue
        unit_id = rel.removesuffix(".md")
        units.append(
            {
                "id": unit_id,
                "title": str(fm.get("title") or unit_id),
                "kind": kind,
                "date": raw_date[:10],
                "line": unit_id.split("/")[0],
            }
        )
    return units


def url_for(unit_id: str, kind: str) -> str:
    """单元 → 站上地址。

    **口径来自共享规则**：仓库根的 `rules/urls.json` 是全仓库唯一的那份，
    根 `tools/url_rules.py` 是它在工具层的读取器，站点那边（`src/lib/urls.ts`）
    读的是同一个文件。这里不自己拼前缀。
    """
    return unit_url(unit_id, kind)


def build_days(ledger: dict, units: list[dict]) -> dict[str, dict]:
    """逐日记录。返回 {日期: 记录}。"""
    rules = ledger.get("rules") or {}
    learn_lines = set(rules.get("learn_lines") or [])
    ai_counts_output = bool(rules.get("ai_counts_output", True))

    days: dict[str, dict] = {}

    def record(day: str) -> dict:
        return days.setdefault(
            day,
            {"date": day, "write": False, "learn": False, "ai": False, "n": 0, "note": "", "docs": []},
        )

    for unit in units:
        rec = record(unit["date"])
        rec["write"] = True
        if unit["line"] in learn_lines:
            rec["learn"] = True
        if ai_counts_output:
            rec["ai"] = True
        rec["docs"].append(
            {
                "id": unit["id"],
                "title": unit["title"],
                "kind": unit["kind"],
                "line": unit["line"],
                "url": url_for(unit["id"], unit["kind"]),
            }
        )
        rec["n"] = len(rec["docs"])

    # 账本后走：它能覆盖三条判定。
    # 覆盖「写作」是必要的——写完的稿子还没过审、没上站的时候，
    # 站点看不见它，但那天作者确实在写；账本记下来，那天就不算偷懒。
    for entry in ledger.get("days") or []:
        day = str(entry.get("date") or "").strip()
        if not day:
            continue
        rec = record(day)
        for flag in ("write", "learn", "ai"):
            if flag in entry:
                rec[flag] = bool(entry[flag])
        if entry.get("note"):
            rec["note"] = str(entry["note"])

    return days


def day_range(days: dict[str, dict], today: str) -> list[str]:
    """区间：从最早的一天到今天（含两端），一天一个。"""
    if not days:
        return [today]
    start = min(min(days), today)
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(today)
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += dt.timedelta(days=1)
    return out


def streak_of(active: set[str], today: str) -> tuple[int, str | None]:
    """连续天数：末尾连着的活跃天数。

    今天还没过完，所以今天没动不算断——从昨天接着数。
    返回 (连续天数, 最后一次活跃的日子)。
    """
    if not active:
        return 0, None
    d = dt.date.fromisoformat(today)
    if d.isoformat() not in active:
        d -= dt.timedelta(days=1)
    count = 0
    while d.isoformat() in active:
        count += 1
        d -= dt.timedelta(days=1)
    return count, max(active)


def compile_activity(today: str | None = None) -> dict:
    """编译活动数据。返回编译结果字典。"""
    ledger = load_ledger()
    units = load_units()
    days = build_days(ledger, units)

    today = today or dt.date.today().isoformat()
    span = day_range(days, today)

    write_days = {d for d, r in days.items() if r["write"]}
    learn_days = {d for d, r in days.items() if r["learn"]}
    ai_days = {d for d, r in days.items() if r["ai"]}
    # 偷懒 = 既没写东西、账本里也没记用了 AI 的日子。
    # 「写了但没记用了 AI」不算偷懒——那天作者在干活，只是没用 AI。
    slack_days = {
        d for d in span if not days.get(d, {}).get("write") and not days.get(d, {}).get("ai")
    }

    write_streak, write_last = streak_of(write_days, today)
    learn_streak, learn_last = streak_of(learn_days, today)
    ai_streak, ai_last = streak_of(ai_days, today)
    slack_streak, _ = streak_of(slack_days, today)

    last_output = max(write_days) if write_days else None
    since_output = (
        (dt.date.fromisoformat(today) - dt.date.fromisoformat(last_output)).days if last_output else None
    )

    return {
        "generated": today,
        "range": {
            "start": span[0],
            "end": today,
            "days": len(span),
        },
        "stats": {
            "write": {"label": "写作", "streak": write_streak, "total": len(write_days), "last": write_last},
            "learn": {"label": "学习", "streak": learn_streak, "total": len(learn_days), "last": learn_last},
            "ai": {"label": "用 AI", "streak": ai_streak, "total": len(ai_days), "last": ai_last},
            "slack": {"label": "偷懒", "streak": slack_streak, "total": len(slack_days), "last": None},
        },
        "since_output": since_output,
        "learn_lines": sorted((ledger.get("rules") or {}).get("learn_lines") or []),
        "days": [
            {
                "date": d,
                "write": days[d]["write"] if d in days else False,
                "learn": days[d]["learn"] if d in days else False,
                "ai": days[d]["ai"] if d in days else False,
                "n": days[d]["n"] if d in days else 0,
                "note": days[d]["note"] if d in days else "",
                "docs": days[d]["docs"] if d in days else [],
            }
            for d in span
        ],
    }


def append_today(today: str | None = None) -> str:
    """把今天记进账本。幂等——同一天不重复加。

    **只在今天有产出时才加**：没产出的日子账本不需要记——
    空档是「没记录」的自然结果，加一条空的反而把账本弄脏。

    返回三种状态：`added`（补上了）/ `already`（账本里已经有了）/
    `no-output`（今天还没有产出，不用记）。
    """
    today = today or dt.date.today().isoformat()
    ledger = load_ledger()
    entries = ledger.setdefault("days", [])
    if any(str(e.get("date")) == today for e in entries):
        return "already"

    # 今天有没有产出？有产出就记成「写了」——「用了 AI」按默认口径自动成立。
    units = load_units()
    if not any(u["date"] == today for u in units):
        return "no-output"
    entry: dict = {"date": today, "write": True}
    entries.append(entry)
    entries.sort(key=lambda e: str(e.get("date")))
    ledger["updated"] = today
    LEDGER_PATH.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return "added"


def main() -> int:
    ap = argparse.ArgumentParser(description="把账本 + 内容单元编译成站点的活动数据")
    ap.add_argument("--append", action="store_true", help="把今天记进账本（幂等）")
    ap.add_argument("--today", help="指定「今天」（YYYY-MM-DD），测试用")
    args = ap.parse_args()

    if not CONTENT_UNITS.is_dir():
        print(
            f"内容单元仓库不存在：{CONTENT_UNITS}\n"
            f"（先在仓库根跑 python3 tools/build-content-units.py）",
            file=sys.stderr,
        )
        return 2

    if args.append:
        day = args.today or dt.date.today().isoformat()
        status = append_today(day)
        if status == "added":
            print(f"账本里加上了 {day}")
        elif status == "already":
            print("账本里已经有今天了，没动")
        else:
            print(f"{day} 还没有产出，账本不用记（空档本来就是「没记录」）")
        return 0

    try:
        result = compile_activity(args.today)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"活动数据编译失败：{exc}", file=sys.stderr)
        return 2

    COMPILED_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    stats = result["stats"]
    print(
        f"活动数据：{result['range']['start']} → {result['range']['end']}"
        f"（{result['range']['days']} 天）\n"
        f"  写作：连续 {stats['write']['streak']} 天，累计 {stats['write']['total']} 天\n"
        f"  学习：连续 {stats['learn']['streak']} 天，累计 {stats['learn']['total']} 天\n"
        f"  用 AI：连续 {stats['ai']['streak']} 天，累计 {stats['ai']['total']} 天\n"
        f"  偷懒：连着 {stats['slack']['streak']} 天，累计 {stats['slack']['total']} 天"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
