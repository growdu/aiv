"""坐标与草稿单元分类。**分类由路径形状决定，不另存字段**（规格 §6.1）。"""
from __future__ import annotations

from api.services.paths import (
    classify_draft,
    episode_to_draft,
    episode_to_skeleton_draft,
    list_draft_units,
)


def test_a_flat_markdown_under_two_levels_is_a_document():
    assert classify_draft("distributed/foundations/cap.md") == "document"


def test_the_index_page_is_its_own_kind():
    assert classify_draft("distributed/_index.md") == "index"


def test_a_flat_markdown_deeper_than_three_segments_is_still_a_document():
    """**目录的深度是仓库的事，不是形状的规则。**

    源向线比扁平稿深两级（方向/系列）——
    `source-tracks/postgresql/getting-started/篇.md` 仍是**一篇文档**，
    不是「形状对不上」。判它 unknown 的话，草稿箱会**跳过它**，
    建完的稿子就看不见了。
    """
    assert classify_draft(
        "source-tracks/postgresql/getting-started/pg19.md") == "document"


def test_listing_finds_a_deeper_flat_document(tmp_path):
    deep = tmp_path / "source-tracks" / "postgresql" / "getting-started"
    deep.mkdir(parents=True)
    (deep / "pg19.md").write_text("x", encoding="utf-8")

    units = list_draft_units(tmp_path)
    assert [u.draft_id for u in units] == [
        "source-tracks/postgresql/getting-started/pg19"]
    assert units[0].kind == "document"


def test_a_skeleton_lives_at_the_document_level_not_under_a_tier():
    assert classify_draft("_video/系列/合集/文档/skeleton.yaml") == "skeleton"


def test_a_tier_directory_is_an_episode():
    assert classify_draft("_video/系列/合集/文档/short") == "episode"


def test_an_unknown_shape_is_unknown():
    assert classify_draft("_video/系列/合集/文档/short/口播稿.md") == "unknown"
    assert classify_draft("系列/合集/文档") == "unknown"


def test_the_video_line_is_one_prefix_away_from_the_episode_coordinate():
    assert episode_to_draft("系列/合集/文档/short") == "_video/系列/合集/文档/short"
    assert episode_to_skeleton_draft("系列/合集/文档/short") == "_video/系列/合集/文档"


def test_listing_walks_the_tree_and_finds_both_kinds(tmp_path):
    (tmp_path / "分类" / "二级").mkdir(parents=True)
    (tmp_path / "分类" / "二级" / "篇.md").write_text("x", encoding="utf-8")
    video = tmp_path / "_video" / "系列" / "合集" / "文档"
    video.mkdir(parents=True)
    (video / "skeleton.yaml").write_text("x", encoding="utf-8")
    tier = video / "short"
    tier.mkdir()
    (tier / "口播稿.md").write_text("x", encoding="utf-8")

    units = list_draft_units(tmp_path)
    kinds = sorted(u.kind for u in units)
    assert kinds == ["document", "episode", "skeleton"]
    episode = next(u for u in units if u.kind == "episode")
    assert episode.draft_id == "_video/系列/合集/文档/short"
    assert episode.files == ("口播稿.md",)
