"""草稿箱的读写。**保存只写草稿箱**（全局约束 4）。"""
from __future__ import annotations

import json

import pytest

from api.services import drafts
from api.services.paths import DraftUnit


def _unit(tmp_path, kind, draft_id, files):
    path = tmp_path / draft_id
    path.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (path / name).write_text(body, encoding="utf-8")
    return DraftUnit(kind=kind, draft_id=draft_id, path=path,
                     files=tuple(sorted(files)))


def test_reading_a_unit_returns_file_name_to_content(tmp_path):
    unit = _unit(tmp_path, "episode", "_video/a/b/c/short",
                 {"口播稿.md": "稿", "contract.json": "{}"})
    assert drafts.read_unit(unit) == {"口播稿.md": "稿", "contract.json": "{}"}


def test_write_touches_only_the_keys_in_the_body(tmp_path):
    unit = _unit(tmp_path, "episode", "_video/a/b/c/short",
                 {"口播稿.md": "旧", "contract.json": "{}"})
    drafts.write_unit(unit, {"口播稿.md": "新"})
    assert (unit.path / "口播稿.md").read_text(encoding="utf-8") == "新"
    assert (unit.path / "contract.json").read_text(encoding="utf-8") == "{}"


def test_write_refuses_a_file_name_that_would_escape_the_unit(tmp_path):
    unit = _unit(tmp_path, "episode", "_video/a/b/c/short", {"口播稿.md": "x"})
    with pytest.raises(ValueError):
        drafts.write_unit(unit, {"../../逃逸.md": "x"})


def test_creating_a_blank_document(tmp_path):
    unit = drafts.create_unit("document", draft_id="新分类/新二级/新篇",
                              title="新篇", root=tmp_path)
    assert unit.kind == "document"
    assert unit.files == ("新篇.md",)
    body = (unit.path / "新篇.md").read_text(encoding="utf-8")
    assert body.startswith("---")
    assert "title: 新篇" in body


def test_creating_an_episode_writes_the_three_facts(tmp_path):
    """两个 `episode` 字段**含义不同**（规格 §7.4）：
    口播稿里是**三层**文档路径，contract 里是**四层**期路径。"""
    unit = drafts.create_unit("episode", draft_id="_video/系列/合集/文档/short",
                              title="标题", root=tmp_path)
    assert unit.files == ("contract.json", "publish.json", "口播稿.md")
    contract = json.loads((unit.path / "contract.json").read_text(encoding="utf-8"))
    assert contract["episode"] == "系列/合集/文档/short"
    publish = json.loads((unit.path / "publish.json").read_text(encoding="utf-8"))
    assert publish["episode"] == "系列/合集/文档/short"
    script = (unit.path / "口播稿.md").read_text(encoding="utf-8")
    assert "episode: 系列/合集/文档" in script
    assert "tier: short" in script


def test_finding_a_unit_that_does_not_exist_raises(tmp_path):
    with pytest.raises(drafts.DraftNotFound):
        drafts.find_unit("没有/这一篇", root=tmp_path)
