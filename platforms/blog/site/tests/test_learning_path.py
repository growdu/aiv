"""学习流的守卫：每个内容单元都**恰好**落在一条赛道的一个阶段里。

**背景**
------
学习流（``/learning/``）是站点的门面——它告诉读者「从哪儿开始、下一站在哪」。
它是由规则表（``data/learning-path.json``）算出来的（``tools/build-learning-path.py``），
所以它有三种坏法，每一种都得有人拦：

1. **漏归类** —— 新加一篇稿子，忘了写规则，它就悄悄从学习流里消失了。
   读者看到的阶梯是「完整」的，实际上少了一块。
2. **重复归类** —— 同一篇落进两条赛道或两个阶段，读者要读两遍，
   而且「这一级有多少篇」这个数字开始骗人。
3. **落到兜底桶** —— 规则没命中，单元被扔进 ``fallback_stage``。
   兜底桶是**构建期就该炸**的东西：它意味着「这篇我也不知道该放哪」。

**还有一层**：编译结果有**两面**。

- ``data/learning-path.compiled.json`` 是**账本**——文档与视频都在里面，
  发布层要问「这一期归哪一格」；
- ``source/_data/learning.json`` 是**站上那一面**——只有文档。
  站上没有视频页（作者拍板），把视频列进学习流页面，点过去就是一个 404。

**契约**
--------
1. 每个 ``kind=document|video`` 的内容单元都归到了**恰好一条**赛道的一个阶段。
2. 兜底桶是空的。
3. 规则表结构合法：赛道 id 唯一、阶段 id 递增、``fallback_stage`` 存在、
   ``catch_all`` 只出现在**最后一个**阶段（写在中间会把后面阶段全吞掉）。
4. 编译产物与内容单元对得上（``--check`` 通过）。
5. 站上那一面不含视频；学习流关着时两面都不生成。

**这一层只看站点自己的东西**：内容单元（``content/units/``）与编译结果。
内容单元本身是不是最新的，是根级 ``tools/build-content-units.py --check`` 的事，
不在这儿越界。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_tool
from paths import CONTENT_UNITS, SITE, SITE_DATA

SITE_ROOT = SITE
RULES_FILE = SITE_DATA / "learning-path.json"
COMPILED_FILE = SITE_DATA / "learning-path.compiled.json"
LEARNING_DATA = SITE_ROOT / "source" / "_data" / "learning.json"
TOOL = SITE_ROOT / "tools" / "build-learning-path.py"

build_learning_path = load_tool("build-learning-path.py")


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path} 不存在（先跑编译）")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rules():
    return _load(RULES_FILE)


@pytest.fixture(scope="module")
def compiled():
    return _load(COMPILED_FILE)


@pytest.fixture(scope="module")
def site_view():
    return _load(LEARNING_DATA)


def _unit_ids() -> list[str]:
    """内容单元里所有**要上站**的单元 id（分类页不进学习流）。"""
    ids = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        if rel.endswith("/_index.md") or rel == "_index.md":
            continue  # 分类页
        ids.append(rel.removesuffix(".md"))
    return ids


# ── 规则表本身的结构 ─────────────────────────────────────


def test_track_ids_are_unique(rules):
    ids = [t["id"] for t in rules["tracks"]]
    assert len(ids) == len(set(ids)), f"赛道 id 重复：{ids}"


def test_source_tracks_are_named_after_their_direction(rules):
    """赛道 id 是**方向名**，不是搬内容时的内部叫法。

    `db-internals` / `linux-network` / `dataplane` 是搬家时用的内部叫法，
    而赛道 id 进了 URL（`/learning/<id>/`）与 CSS class——**读者看得到**。
    """
    ids = {t["id"] for t in rules["tracks"]}
    assert {"postgresql", "linux", "dpdk"} <= ids
    assert not ({"db-internals", "linux-network", "dataplane"} & ids), (
        "赛道 id 还是搬家时的内部叫法——它进 URL，读者看得到"
    )


def test_every_track_id_is_a_legal_slug(rules):
    """赛道 id 进了 URL，也进了 CSS class——它必须是合法 slug。"""
    for track in rules["tracks"]:
        assert re.fullmatch(r"[a-z0-9-]+", track["id"]), track["id"]


def test_every_track_has_exactly_one_lane_color(rules):
    """赛道 id 换了名，CSS 里的 class 名也得跟着换。

    不换的后果很具体：那条赛道**掉回默认色**
    （`var(--lane-color, #009688)`）——页面看上去还是好的，
    只是几条赛道撞了色，谁也说不清哪条是哪条。

    **只数「定义了赛道色」的 class**：`.lane-card--planned` 那种
    状态修饰符（虚线边）不是配色，不算一条赛道。
    """
    css = (SITE_ROOT / "themes" / "matery" / "source" / "css"
           / "tech.css").read_text(encoding="utf-8")
    classes = set(re.findall(
        r"\.lane-card--([a-z0-9-]+)\s*\{[^}]*--lane-color:", css))
    ids = {t["id"] for t in rules["tracks"]}
    assert classes == ids, (
        "赛道配色与赛道 id 对不上："
        f"CSS 里有而规则表里没有 {sorted(classes - ids)}；"
        f"规则表里有而 CSS 里没有 {sorted(ids - classes)}"
    )


# ── 筹备中（status: planned）────────────────────────────────


def test_the_status_field_is_known(rules):
    """状态位只有两种意思：缺省（active）与 `planned`（筹备中）。

    写错的状态位不会有人报错——它只是**静默地**按 active 处理，
    于是那条赛道的「筹备中」标记不出现，而页面上一个赛道四个空阶段，
    读者以为课程烂尾了。
    """
    for track in rules["tracks"]:
        status = track.get("status")
        assert status in (None, "active", "planned"), (
            f"{track['id']} 的 status 是 {status!r}，"
            "只认 active / planned"
        )


def test_a_planned_track_declares_its_syllabus(rules):
    """筹备中的赛道是**公开宣布的课程大纲**，不是洞。

    所以它得把大纲写出来：阶段不少于两段（两段才叫课程，
    一段是单篇），每段都有标题、有「读完能做什么」、
    有**明确写着将来收什么的规则**。
    """
    planned = [t for t in rules["tracks"] if t.get("status") == "planned"]
    assert planned, "至少有一条筹备中的赛道（ceph）"

    for track in planned:
        assert len(track["stages"]) >= 2, (
            f"{track['id']} 是筹备中，却只声明了 {len(track['stages'])} 个阶段——"
            "一段不算课程大纲"
        )
        for stage in track["stages"]:
            assert stage.get("title"), f"{track['id']}/{stage['id']} 没有标题"
            assert stage.get("goal"), (
                f"{track['id']}/{stage['id']} 没写「读完能做什么」——"
                "宣布的大纲要说得清每段学完会什么"
            )
            assert stage.get("match"), (
                f"{track['id']}/{stage['id']} 没声明将来收什么"
            )


def test_a_planned_stage_lives_inside_its_own_track(rules):
    """筹备中赛道的每个阶段都得落在**自己这条赛道**的范围内。

    阶段的前缀写着 `source-tracks/ceph/`，赛道的 `track_match` 却写着别的——
    那这条赛道永远收不到文章，而页面上四个阶段全是空的，
    看着像「还没写」，其实是规则写错了地方。
    """
    for track in rules["tracks"]:
        if track.get("status") != "planned":
            continue
        scope = [
            rule["path_prefix"]
            for rule in track.get("track_match", [])
            if "path_prefix" in rule
        ]
        assert scope, f"{track['id']} 没有 track_match，收不到任何内容"
        for stage in track["stages"]:
            for rule in stage.get("match", []):
                prefix = rule.get("path_prefix")
                if not prefix:
                    continue
                assert any(prefix.startswith(s) for s in scope), (
                    f"{track['id']}/{stage['id']} 的规则 {prefix} "
                    f"不在本赛道范围内 {scope}"
                )


def test_a_planned_track_has_no_fallback_bucket(rules):
    """筹备中的赛道**不设兜底阶段**。

    兜底桶的作用是「先别让构建崩」——但它同时会把
    「内容没有专属规则」这件事**藏起来**。筹备中的赛道还没有内容，
    兜底桶只会让人以为规则写全了；等第一篇文章来了，
    没有专属规则就该在编译期炸出来（漏归类），而不是悄悄落进兜底。
    """
    for track in rules["tracks"]:
        if track.get("status") != "planned":
            continue
        assert not track.get("fallback_stage"), (
            f"{track['id']} 是筹备中，不该有兜底阶段 "
            f"{track.get('fallback_stage')}"
        )


def test_every_stage_declares_where_its_articles_come_from(rules):
    """每个阶段都得写清楚「我的文章从哪来」。

    没有匹配规则的阶段**永远收不到文章**——那是课程里的一个洞：
    页面上它占一行，读者点进去是空的。

    这条对筹备中的赛道也一样：筹备中允许**规则指向还不存在的目录**
    （文章还没写），不允许**规则缺失**（那不是「还没写」，是「漏了」）。
    """
    for track in rules["tracks"]:
        for stage in track["stages"]:
            assert stage.get("match"), (
                f"{track['id']}/{stage['id']} 没有匹配规则——"
                "它收不到任何文章"
            )


def test_video_entries_are_keyed_by_episode_number(rules):
    """视频条目按**期号**写（`video/<期号>`），**不带档位后缀**。

    档位不在 content_id 里——一期就是一期。带档位后缀的话，
    三档各出一个内容单元，同一期在学习流里就会出现三次：
    读者在同一级阶梯上看见三条几乎一样的视频。
    """
    for track in rules["tracks"]:
        for stage in track["stages"]:
            for rule in stage.get("match", []):
                exact = rule.get("path_exact")
                if not exact or not exact.startswith("video/"):
                    continue
                assert not re.search(r"-(short|mid|full)$", exact), (
                    f"{track['id']}/{stage['id']} 的视频条目 {exact} 带档位后缀"
                )


# ── 「筹备中」要看得见 ─────────────────────────────────────


def _view_with_status(status: str) -> dict:
    """一份只含一条赛道的站上视图（`status` 可变）。"""
    return {
        "total": 0,
        "enabled": True,
        "tracks": [
            {
                "id": "示例",
                "title": "示例赛道",
                "icon": "",
                "summary": "",
                "audience": "",
                "goal": "",
                "status": status,
                "stages": [
                    {"id": "L1", "title": "第一段", "goal": "",
                     "units": [], "count": 0},
                ],
                "count": 0,
            }
        ],
    }


def test_the_learning_page_marks_a_planned_track():
    """筹备中的赛道在学习路径页上带「筹备中」标记。

    **「筹备中」和「规则缺失」在数据上长得一样**（都是 0 篇）——
    读者看的是页面，不是数据，所以区别得**看得见**。
    """
    pages = build_learning_path.render_learning_pages(
        _view_with_status("planned"), [])
    assert "筹备中" in pages["learning/index.md"], "总览页上没标「筹备中」"
    assert "筹备中" in pages["learning/示例/index.md"], "赛道页上没标「筹备中」"


def test_an_active_track_is_not_marked_as_planned():
    """正常赛道不许挂「筹备中」——那个标记有分量。"""
    pages = build_learning_path.render_learning_pages(
        _view_with_status("active"), [])
    assert "筹备中" not in pages["learning/index.md"]
    assert "筹备中" not in pages["learning/示例/index.md"]


def test_the_planned_badge_reaches_the_browser():
    """徽标要真的渲染出来——页面上得**看得见**那个标记。"""
    dist = SITE_ROOT / "dist"
    if not dist.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    for name in ("index.html", "learning/index.html", "learning/ceph/index.html"):
        path = dist / name
        if not path.exists():
            continue
        assert "筹备中" in path.read_text(encoding="utf-8"), (
            f"{name} 上没有「筹备中」标记"
        )


def test_stage_ids_increase_within_a_track(rules):
    for track in rules["tracks"]:
        numbers = [int(s["id"][1:]) for s in track["stages"]]
        assert numbers == sorted(numbers), f"{track['id']} 的阶段 id 不是递增的：{numbers}"


def test_fallback_stage_exists(rules):
    for track in rules["tracks"]:
        fallback = track.get("fallback_stage")
        if fallback is None:
            continue
        stage_ids = [s["id"] for s in track["stages"]]
        assert fallback in stage_ids, f"{track['id']} 的兜底阶段 {fallback} 不存在"


def test_catch_all_only_in_last_stage(rules):
    """兜底规则写在中间阶段会把后面阶段的内容全吞掉——真踩过的坑。"""
    for track in rules["tracks"]:
        stages = track["stages"]
        for index, stage in enumerate(stages):
            has_catch_all = "catch_all" in stage.get("match", {})
            if has_catch_all:
                assert index == len(stages) - 1, (
                    f"{track['id']} 的 {stage['id']} 里有 catch_all，"
                    f"但它不是最后一个阶段"
                )


def _skip_if_disabled(compiled: dict) -> None:
    """学习流这个模块关着的时候，「每个单元都得归类」不成立——没开的模块不配规则。"""
    if compiled.get("enabled", True) is False:
        pytest.skip("学习流关着（规则表 enabled: false）")


# ── 归属：每个单元恰好一处，没有兜底 ───────────────────────


def test_every_unit_is_assigned_exactly_once(compiled):
    _skip_if_disabled(compiled)
    assignment = compiled["assignment"]
    unit_ids = _unit_ids()

    missing = [uid for uid in unit_ids if uid not in assignment]
    assert not missing, f"这些单元没被归类（学习流里会凭空少一块）：{missing}"

    extra = [uid for uid in assignment if uid not in unit_ids]
    assert not extra, f"编译结果里有内容单元不存在的条目：{extra}"


def test_no_unit_relies_on_fallback(compiled):
    _skip_if_disabled(compiled)
    fallbacks = [
        uid for uid, a in compiled["assignment"].items() if a.get("fallback")
    ]
    assert not fallbacks, f"这些单元落进了兜底桶（规则没命中）：{fallbacks}"


def test_a_unit_is_not_in_two_tracks(compiled):
    """一个单元只能属于一条赛道。规则表里两条赛道的 path_prefix 撞了就会犯。"""
    _skip_if_disabled(compiled)
    seen: dict[str, str] = {}
    for uid, a in compiled["assignment"].items():
        key = f"{a['track']}/{a['stage']}"
        assert uid not in seen or seen[uid] == key, (
            f"{uid} 同时出现在 {seen.get(uid)} 和 {key}"
        )
        seen[uid] = key


def test_stage_counts_match_the_unit_lists(compiled):
    for track in compiled["tracks"]:
        for stage in track["stages"]:
            assert stage["count"] == len(stage["units"]), (
                f"{track['id']}/{stage['id']} 的 count 与 units 长度对不上"
            )


# ── 站上那一面：只有文档 ─────────────────────────────────


def test_the_site_side_has_no_videos(site_view):
    """站上没有视频页（作者拍板）——学习流页面里不许出现指向视频的链接。"""
    offenders = []
    for track in site_view["tracks"]:
        for stage in track["stages"]:
            offenders += [u for u in stage["units"] if u.startswith("video/")]
    assert not offenders, f"站上那一面列了视频（点过去是 404）：{offenders}"


def test_the_site_side_counts_only_documents(site_view):
    """首页的「N 篇」与赛道卡的篇数，说的是同一件事：站上有的文章。"""
    counted = sum(track["count"] for track in site_view["tracks"])
    assert site_view["total"] == counted, "总篇数与各赛道的篇数对不上"


def test_the_ledger_keeps_the_videos(compiled):
    """账本那一面仍然记着视频——发布层要问「这一期归哪一格」。"""
    videos = [uid for uid in compiled["assignment"] if uid.startswith("video/")]
    ledger_videos = [
        unit
        for track in compiled["tracks"]
        for stage in track["stages"]
        for unit in stage["units"]
        if unit.startswith("video/")
    ]
    assert ledger_videos == videos, "账本里的视频条目与对照表对不上"


# ── 学习流可以整个关掉 ───────────────────────────────────


def test_disabling_the_learning_path_produces_nothing(tmp_path, monkeypatch):
    """模块关着 → 不映射、不报错、一个页面都不生成。"""
    rules_file = tmp_path / "learning-path.json"
    rules_file.write_text(
        json.dumps({"enabled": False, "tracks": []}), encoding="utf-8"
    )
    monkeypatch.setattr(build_learning_path, "RULES_PATH", rules_file)
    monkeypatch.setattr(build_learning_path, "CONTENT_UNITS", tmp_path / "units")

    result, problems = build_learning_path.compile_learning_path()
    assert result["enabled"] is False
    assert result["tracks"] == []
    assert problems == [], f"关着的模块不该报问题：{problems}"


# ── 编译产物是最新的 ─────────────────────────────────────


def test_compiled_output_is_up_to_date():
    """编译结果必须跟内容单元对得上（`--check` 通过）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        cwd=str(SITE_ROOT),
    )
    assert result.returncode == 0, (
        "学习流编译结果不是最新的，先跑 build-learning-path.py：\n"
        f"{result.stdout}\n{result.stderr}"
    )
