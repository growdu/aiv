"""讲稿骨架的守卫：一份母稿的讲法，三档共用。

**裁剪是机械的，删段凑字数是禁止的。** 一段进哪几档只看它的 `role`
（《长视频三档》§5.2 的表）。所以这些用例盯的是三件事：

1. **那张表不许自己发挥**——`ROLE_TIERS` 是规格的逐格照抄；
2. **裁剪只看 role，段序不动**——重排会让人以为内容被换过；
3. **坏掉的骨架要炸**——不认识的档位、不认识的 role，
   宁可报错也不让它安静地少一段（拼错的 role 会让那一段从三档里同时消失，
   而页面上看不出来）。
"""
from __future__ import annotations

import pytest

from pyv import skeleton as skeleton_mod
from pyv.skeleton import SkeletonError, TierError, select_segments

#: 一条典型的骨架：三档都能看出差别。
SKELETON = {
    "episode": "系列甲/合集甲/文档甲",
    "source": "docs/甲.md",
    "segments": [
        {"id": "s01", "role": "hook", "narration": ["开场白。"]},
        {"id": "s02", "role": "mechanism", "narration": ["机制第一句。", "机制第二句。"]},
        {"id": "s03", "role": "aside", "narration": ["支线。"]},
        {"id": "s04", "role": "evidence", "narration": ["证据。"]},
        {"id": "s05", "role": "conclusion", "narration": ["收束。"]},
    ],
}


def test_the_tiers_are_short_mid_full():
    """三档的名字与顺序是坐标的一部分，不是随便起的。"""
    assert skeleton_mod.TIERS == ("short", "mid", "full")


def test_the_role_table_matches_the_spec():
    """`ROLE_TIERS` 是《长视频三档》§5.2 那张表的**逐格照抄**。

    那张表是判据。代码里的这张表要是自己发挥，裁出来的片子
    跟规格说的就不是一回事了——而片子看上去仍然是「正常的视频」，
    没人会发现少了 `evidence`。
    """
    assert skeleton_mod.ROLE_TIERS == {
        "hook": ("short", "mid", "full"),
        "mechanism": ("mid", "full"),
        "evidence": ("mid", "full"),
        "conclusion": ("short", "mid", "full"),
        "aside": ("full",),
    }


def test_select_segments_by_role():
    """按 role 选段：short 只要钩子与收束，进阶版加机制与证据，完整版全要。"""
    assert [s["id"] for s in select_segments(SKELETON, "short")] == ["s01", "s05"]
    assert [s["id"] for s in select_segments(SKELETON, "mid")] == [
        "s01", "s02", "s04", "s05"]
    assert [s["id"] for s in select_segments(SKELETON, "full")] == [
        "s01", "s02", "s03", "s04", "s05"]


def test_unknown_tier_is_rejected():
    """档位拼错就是拼错——不能当成「什么都不讲」。

    当成什么都不讲会出一支空片子，而命令还报「成功」。
    """
    with pytest.raises(TierError):
        select_segments({"segments": []}, "medium")


def test_select_keeps_the_original_segment_order():
    """段序是骨架里的原样，**不重排**。

    重排会让人以为内容被换过——而「换了顺序」这件事没人能一眼看出来。
    """
    shuffled = {
        "segments": [
            {"id": "s03", "role": "aside", "narration": []},
            {"id": "s01", "role": "hook", "narration": []},
            {"id": "s02", "role": "mechanism", "narration": []},
        ]
    }
    assert [s["id"] for s in select_segments(shuffled, "full")] == [
        "s03", "s01", "s02"]


def test_a_segment_with_an_unknown_role_is_refused():
    """role 拼错的那一段，从**三档里同时消失**——所以要炸。

    `mechanim`（少个 s）在「按 role 过滤」的口径下没人要它：
    short 本来就不要机制，mid 与 full 要——但拼错的那份表里没有它，
    于是它在三档里全没了，而页面上看不出少了东西。
    """
    broken = {
        "segments": [
            {"id": "s01", "role": "hook", "narration": []},
            {"id": "s02", "role": "mechanim", "narration": []},
        ]
    }
    for tier in skeleton_mod.TIERS:
        with pytest.raises(SkeletonError):
            select_segments(broken, tier)


def test_a_segment_without_a_role_is_refused():
    """没有 role 的段跟 role 拼错的一样：没人要它。"""
    broken = {"segments": [{"id": "s01", "narration": []}]}
    with pytest.raises(SkeletonError):
        select_segments(broken, "short")


def test_render_narration_keeps_one_sentence_per_line():
    """口播稿文本一句一行——`align.parse_script` 认的是这个形状。"""
    text = skeleton_mod.render_narration(select_segments(SKELETON, "mid"))
    assert text == "开场白。\n机制第一句。\n机制第二句。\n证据。\n收束。"


def test_render_narration_does_not_truncate():
    """不按字数截断：字数落不进区间是守卫的事，不是这里的事。

    悄悄截断出来的片子看着像那么回事，实际上内容没了，
    而且没人知道少的是哪一段。
    """
    long_segment = [{"id": "s01", "role": "hook", "narration": ["很长的一句话。" * 200]}]
    text = skeleton_mod.render_narration(long_segment)
    assert text.count("很长的一句话。") == 200


def test_render_narration_of_nothing_is_empty():
    assert skeleton_mod.render_narration([]) == ""


def test_the_skeleton_is_parsed_from_yaml(tmp_path):
    """骨架是 YAML：形状照《长视频三档》§5.1。"""
    file = tmp_path / "skeleton.yaml"
    file.write_text(
        "episode: 系列甲/合集甲/文档甲\n"
        "segments:\n"
        "  - id: s01\n"
        "    role: hook\n"
        "    narration:\n"
        '      - "开场白。"\n',
        encoding="utf-8",
    )
    data = skeleton_mod.load_skeleton(file)
    assert data["episode"] == "系列甲/合集甲/文档甲"
    assert [s["id"] for s in select_segments(data, "short")] == ["s01"]


def test_a_skeleton_that_is_not_an_object_is_refused():
    """YAML 解析出来不是对象——骨架坏了，要说清楚。"""
    with pytest.raises(SkeletonError):
        skeleton_mod.parse_skeleton("- 只是一段列表\n")


def test_a_skeleton_without_segments_is_refused():
    with pytest.raises(SkeletonError):
        skeleton_mod.parse_skeleton("episode: 甲\n")


def test_a_missing_skeleton_file_is_refused(tmp_path):
    with pytest.raises(SkeletonError):
        skeleton_mod.load_skeleton(tmp_path / "skeleton.yaml")


# ---- 骨架本身的形状：坏掉的地方要当场说出来 ------------------------------
#
# 上面那些用例查的是「裁剪」的口径；这里查的是「这份骨架本身是不是坏的」。
# 坏骨架的共同点是**坏得看不出来**：拼错的 role、错位的字幕、重复的 id，
# 都不会让命令报错，只会让片子少东西或者字幕错位——所以要在读的时候炸。

GOOD_SKELETON = """
episode: 系列甲/合集甲/文档甲
source: docs/甲.md
segments:
  - id: s01
    role: hook
    visual:
      kind: scene
      renderer: pyv.scenes.s01_intro
      params: {title: "甲"}
    narration:
      - "开场白。"
    subtitles:
      - "开场白"
"""


def test_a_skeleton_with_an_unknown_role_is_refused_at_parse_time():
    """role 拼错的那一段从**三档里同时消失**——所以读的时候就要炸。

    `mechanim`（少个 s）在「按 role 过滤」的口径下没人要它：
    short 本来就不要机制，mid 与 full 要——但拼错的那份表里没有它，
    于是它在三档里全没了，而页面上看不出少了东西。
    """
    broken = GOOD_SKELETON.replace("role: hook", "role: mechanim")
    with pytest.raises(SkeletonError, match="role"):
        skeleton_mod.parse_skeleton(broken)


def test_a_skeleton_with_an_unknown_visual_kind_is_refused():
    """画面类型不认识 → 画面那一环不知道要画什么。"""
    broken = GOOD_SKELETON.replace("kind: scene", "kind: hologram")
    with pytest.raises(SkeletonError, match="kind"):
        skeleton_mod.parse_skeleton(broken)


def test_a_skeleton_whose_subtitles_do_not_match_the_narration_is_refused():
    """口播句数与字幕行数不一致 → 字幕会跟口播错位。

    `align` 只查得出**总数**对不上；错位它看不出来——所以在读骨架时就查。
    """
    broken = GOOD_SKELETON.replace(
        '      - "开场白"',
        '      - "开场白"\n      - "多出来的一行"',
    )
    with pytest.raises(SkeletonError, match="不一致"):
        skeleton_mod.parse_skeleton(broken)


def test_duplicate_segment_ids_are_refused():
    """段 id 重复 → 「引用第 3 段」时指向哪一段说不清。"""
    broken = GOOD_SKELETON + """  - id: s01
    role: conclusion
    narration:
      - "收束。"
"""
    with pytest.raises(SkeletonError, match="重复"):
        skeleton_mod.parse_skeleton(broken)


def test_a_segment_without_an_id_is_refused():
    """没有 id 的段没法被引用——也不该留在骨架里。"""
    broken = GOOD_SKELETON.replace("  - id: s01", "  - role: hook")
    with pytest.raises(SkeletonError, match="id"):
        skeleton_mod.parse_skeleton(broken)


def test_a_segment_without_visual_or_subtitles_is_still_fine():
    """没写的字段不查——纯口播段没有画面、没有字幕表是正常的。"""
    data = skeleton_mod.parse_skeleton(
        "episode: 甲\n"
        "segments:\n"
        "  - id: s01\n"
        "    role: hook\n"
        "    narration:\n"
        '      - "只有口播。"\n'
    )
    assert data["segments"][0]["id"] == "s01"
