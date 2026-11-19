"""活动账本的守卫：四个数字、逐日记录与时间轴上的文档。

**背景**
------
首页那一条数字（连续写了多少天、偷懒多少天、学了多少天、用了多少 AI）
和 ``/timeline/`` 的时间轴，都读 ``data/activity.compiled.json``——
那是 ``tools/build-activity.py`` 拿**账本**（``data/activity.json``）
加内容单元编出来的。

账本只增不改，所以它最容易坏在几处：

1. **账本自己写坏了** —— 日期不合法、同一天记了两遍、记了还没到的日子。
2. **编译结果与账本脱节** —— 账本里加了一天，编译产物里没有（忘了重编）。
3. **数字与逐日记录对不上** —— 页面上写「连续 7 天」，逐日记录里数出来是 5 天。
4. **时间轴指着查无此人的文档** —— 挂了一个已经撤掉的稿子。

**这一层只看站点自己的东西**：账本、编译产物、内容单元。
内容单元本身是不是最新的，是根级 ``tools/build-content-units.py --check`` 的事，
不在这儿越界。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE, SITE_DATA

LEDGER_FILE = SITE_DATA / "activity.json"
COMPILED_FILE = SITE_DATA / "activity.compiled.json"

FLAGS = ("write", "learn", "ai")


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path} 不存在（先跑编译）")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger():
    return _load(LEDGER_FILE)


@pytest.fixture(scope="module")
def compiled():
    return _load(COMPILED_FILE)


def _unit_ids() -> set[str]:
    """内容单元里所有**要上站**的单元 id（分类页不进时间轴）。"""
    ids = set()
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        if rel.endswith("/_index.md") or rel == "_index.md":
            continue
        ids.add(rel.removesuffix(".md"))
    return ids


# ── 账本本身 ─────────────────────────────────────────────


def test_ledger_dates_are_valid(ledger):
    bad = []
    for entry in ledger.get("days") or []:
        day = str(entry.get("date") or "")
        try:
            dt.date.fromisoformat(day)
        except ValueError:
            bad.append(day)
    assert not bad, f"账本里有不合法或缺失的日期：{bad}"


def test_ledger_has_no_duplicate_days(ledger):
    days = [str(e.get("date")) for e in ledger.get("days") or []]
    dupes = sorted({d for d in days if days.count(d) > 1})
    assert not dupes, f"账本里同一天记了两遍：{dupes}"


def test_ledger_has_no_future_days(ledger):
    """还没到的日子先别记——那会让「连续天数」提前虚高。"""
    today = dt.date.today().isoformat()
    future = [str(e.get("date")) for e in ledger.get("days") or [] if str(e.get("date")) > today]
    assert not future, f"账本里记了还没到的日子：{future}"


def test_ledger_flags_are_booleans(ledger):
    bad = []
    for entry in ledger.get("days") or []:
        for flag in (*FLAGS,):
            if flag in entry and not isinstance(entry[flag], bool):
                bad.append((entry.get("date"), flag, entry[flag]))
    assert not bad, f"账本里的标记不是布尔值：{bad}"


def test_ledger_rules_have_learn_lines(ledger):
    rules = ledger.get("rules") or {}
    lines = rules.get("learn_lines")
    assert isinstance(lines, list) and lines, "账本的 rules.learn_lines 得是个非空的列表"
    assert all(isinstance(x, str) for x in lines), "learn_lines 里得都是字符串"


# ── 编译结果与账本对得上 ─────────────────────────────────


def test_compiled_covers_every_ledger_day(ledger, compiled):
    """账本里有的日子，编译结果里必须也有——忘了重编会被这里抓住。"""
    in_compiled = {day["date"] for day in compiled["days"]}
    missing = [str(e.get("date")) for e in ledger.get("days") or [] if str(e.get("date")) not in in_compiled]
    assert not missing, f"账本里有这些日子，编译结果里没有（忘了重编）：{missing}"


def test_compiled_days_are_contiguous(compiled):
    """逐日记录得从区间头一天排到今天，一天不缺——缺了就是「空档」算不准。"""
    days = [day["date"] for day in compiled["days"]]
    assert days == sorted(days), "逐日记录没有按时间排"
    if not days:
        pytest.skip("没有逐日记录")
    start = dt.date.fromisoformat(days[0])
    end = dt.date.fromisoformat(days[-1])
    expected = (end - start).days + 1
    assert len(days) == expected, f"逐日记录有缺口：{len(days)} 天，区间里应该 {expected} 天"


def test_stats_match_the_day_records(compiled):
    """页面上写的数，跟逐日记录数出来的一样。"""
    days = compiled["days"]
    for flag in FLAGS:
        marked = {day["date"] for day in days if day.get(flag)}
        stat = compiled["stats"][flag]
        assert stat["total"] == len(marked), (
            f"{flag} 的累计数 {stat['total']} 跟逐日记录数出来的 {len(marked)} 对不上"
        )
        assert stat["streak"] == _streak(marked, days[-1]["date"]), (
            f"{flag} 的连续数 {stat['streak']} 跟逐日记录数出来的对不上"
        )


def test_slack_is_the_gap(compiled):
    """偷懒 = 既没写东西、账本里也没记用了 AI 的日子。"""
    days = compiled["days"]
    slack = {day["date"] for day in days if not day.get("write") and not day.get("ai")}
    stat = compiled["stats"]["slack"]
    assert stat["total"] == len(slack), (
        f"偷懒的累计数 {stat['total']} 跟空档数 {len(slack)} 对不上"
    )


def _streak(active: set[str], today: str) -> int:
    """末尾连着的活跃天数——跟编译器的算法一样（今天没动不算断）。"""
    if not active:
        return 0
    d = dt.date.fromisoformat(today)
    if d.isoformat() not in active:
        d -= dt.timedelta(days=1)
    count = 0
    while d.isoformat() in active:
        count += 1
        d -= dt.timedelta(days=1)
    return count


# ── 时间轴上的文档 ───────────────────────────────────────


def test_timeline_docs_exist(compiled):
    """时间轴上挂着的每一篇都得是真实存在的内容单元。"""
    known = _unit_ids()
    missing = []
    for day in compiled["days"]:
        for doc in day.get("docs") or []:
            if doc["id"] not in known:
                missing.append(f"{doc['id']}（{day['date']}）")
    assert not missing, f"时间轴指着这些查无此人的内容单元：{missing}"


def test_timeline_urls_follow_the_site_rule(compiled):
    """URL 跟 `src/lib/urls.ts` 同一套规则：文档走 /docs/，视频走 /videos/。"""
    wrong = []
    for day in compiled["days"]:
        for doc in day.get("docs") or []:
            if doc["kind"] == "video":
                expected = f"/videos/{doc['id'].removeprefix('video/')}/"
            else:
                expected = f"/docs/{doc['id']}/"
            if doc["url"] != expected:
                wrong.append(f"{doc['id']}：{doc['url']} ≠ {expected}")
    assert not wrong, "时间轴上的链接跟站点的 URL 规则对不上：\n" + "\n".join(wrong)


def test_timeline_day_counts_match_its_docs(compiled):
    """每天那篇数（n）得等于它挂着的文档数。"""
    for day in compiled["days"]:
        assert day["n"] == len(day.get("docs") or []), (
            f"{day['date']} 的篇数 {day['n']} 跟挂着的文档数对不上"
        )
