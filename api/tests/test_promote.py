"""过审 = 只复制。**不写审校记录、不补 INDEX、不 commit**（规格 D9 / 全局约束 5）。"""
from __future__ import annotations

import pytest

from api.services.drafts import PromoteError, promote_unit
from api.services.paths import DraftUnit


def _document_unit(tmp_path, draft_id="分类/二级/篇", name="篇.md", body="正文"):
    path = tmp_path / draft_id.rsplit("/", 1)[0]
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(body, encoding="utf-8")
    return DraftUnit(kind="document", draft_id=draft_id, path=path, files=(name,))


def _episode_unit(tmp_path, draft_id="_video/系列/合集/文档/short", files=None):
    files = files if files is not None else {
        "口播稿.md": "稿",
        "contract.json": "{}",
        "publish.json": "{}",
    }
    path = tmp_path / draft_id
    path.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (path / name).write_text(body, encoding="utf-8")
    return DraftUnit(kind="episode", draft_id=draft_id, path=path,
                     files=tuple(sorted(files)))


def test_a_document_is_copied_into_docs(tmp_path):
    unit = _document_unit(tmp_path)
    result = promote_unit(unit, repo_root=tmp_path)
    assert result.targets == ("docs/分类/二级/篇.md",)
    assert (tmp_path / "docs" / "分类" / "二级" / "篇.md").read_text(
        encoding="utf-8") == "正文"


def test_promote_copies_only_the_tracked_facts(tmp_path):
    """旁白 / 时间轴 / 渲染帧是**产物**，跟过去会撞 EPISODE_PRODUCT_PATTERNS 守卫。"""
    unit = _episode_unit(tmp_path, files={
        "口播稿.md": "稿",
        "contract.json": "{}",
        "publish.json": "{}",
        "narration.mp3": "假音频",
        "storyboard.json": "{}",
    })
    result = promote_unit(unit, repo_root=tmp_path)
    assert result.targets == (
        "video/episodes/系列/合集/文档/short/口播稿.md",
        "video/episodes/系列/合集/文档/short/contract.json",
        "video/episodes/系列/合集/文档/short/publish.json",
    )
    assert not (tmp_path / "video" / "episodes" / "系列" / "合集" / "文档" / "short"
                / "narration.mp3").exists()


def test_promote_leaves_the_draft_where_it_was(tmp_path):
    unit = _document_unit(tmp_path)
    promote_unit(unit, repo_root=tmp_path)
    assert (unit.path / "篇.md").exists()


def test_promote_reports_the_three_manual_steps(tmp_path):
    unit = _document_unit(tmp_path)
    result = promote_unit(unit, repo_root=tmp_path)
    assert len(result.manual_steps) == 3


def test_an_index_page_is_refused(tmp_path):
    path = tmp_path / "分类"
    path.mkdir(parents=True, exist_ok=True)
    (path / "_index.md").write_text("x", encoding="utf-8")
    unit = DraftUnit(kind="index", draft_id="分类/_index", path=path,
                     files=("_index.md",))
    with pytest.raises(PromoteError):
        promote_unit(unit, repo_root=tmp_path)


def test_a_bundle_is_refused(tmp_path):
    path = tmp_path / "分类" / "二级" / "篇"
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.md").write_text("x", encoding="utf-8")
    unit = DraftUnit(kind="bundle", draft_id="分类/二级/篇", path=path,
                     files=("index.md",))
    with pytest.raises(PromoteError):
        promote_unit(unit, repo_root=tmp_path)


def test_a_skeleton_goes_to_the_document_level(tmp_path):
    path = tmp_path / "_video" / "系列" / "合集" / "文档"
    path.mkdir(parents=True, exist_ok=True)
    (path / "skeleton.yaml").write_text("scenes: []\n", encoding="utf-8")
    unit = DraftUnit(kind="skeleton", draft_id="_video/系列/合集/文档", path=path,
                     files=("skeleton.yaml",))
    result = promote_unit(unit, repo_root=tmp_path)
    assert result.targets == ("video/episodes/系列/合集/文档/skeleton.yaml",)
    assert (tmp_path / "video" / "episodes" / "系列" / "合集" / "文档"
            / "skeleton.yaml").exists()


def test_promote_notices_an_overwrite(tmp_path):
    unit = _document_unit(tmp_path)
    (tmp_path / "docs" / "分类" / "二级").mkdir(parents=True)
    (tmp_path / "docs" / "分类" / "二级" / "篇.md").write_text("旧的", encoding="utf-8")
    result = promote_unit(unit, repo_root=tmp_path)
    assert result.overwritten == ("docs/分类/二级/篇.md",)
