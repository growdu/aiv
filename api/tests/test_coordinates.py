"""坐标选项：给界面做下拉框用的目录树。

**目录即接口**——分类、二级内容、系列、合集都只存在于目录里。
这里把草稿箱与母稿层的两棵树并起来，界面上就能只选**已存在**的坐标。
"""
from __future__ import annotations

from api.services.coordinates import document_tree, episode_tree


def test_the_document_tree_merges_the_draft_box_and_the_master_layer(tmp_path):
    drafts = tmp_path / "drafts"
    docs = tmp_path / "docs"
    (drafts / "distributed" / "foundations").mkdir(parents=True)
    (docs / "distributed" / "foundations").mkdir(parents=True)
    (docs / "source-tracks" / "postgresql" / "getting-started").mkdir(parents=True)

    tree = document_tree(drafts, docs)
    assert tree == [
        {"name": "distributed",
         "children": [{"name": "foundations", "children": []}]},
        {"name": "source-tracks",
         "children": [{"name": "postgresql",
                       "children": [{"name": "getting-started",
                                     "children": []}]}]},
    ]


def test_the_reserved_prefix_is_not_a_category(tmp_path):
    """`_` 开头的是保留名空间——**不是分类**，不进下拉框。"""
    (tmp_path / "_video" / "系列").mkdir(parents=True)
    (tmp_path / "distributed").mkdir()
    tree = document_tree(tmp_path)
    assert [node["name"] for node in tree] == ["distributed"]


def test_the_episode_tree_stops_before_the_tier(tmp_path):
    """期路径是四层（系列/合集/文档/档位）——**档位是固定的**，
    不进下拉框，树截到三层。"""
    root = tmp_path / "episodes"
    (root / "AIV" / "pg" / "row-lock" / "short").mkdir(parents=True)

    tree = episode_tree(root)
    assert tree == [{"name": "AIV",
                     "children": [{"name": "pg",
                                   "children": [{"name": "row-lock",
                                                 "children": []}]}]}]


def test_an_empty_tree_is_an_empty_list(tmp_path):
    assert document_tree(tmp_path / "没有", tmp_path / "也没有") == []
    assert episode_tree(tmp_path / "没有") == []
