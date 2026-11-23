"""草稿箱的路由：列、读、写、过审。

**这些测试不许碰真的 `drafts/`**——所以它们把路由里的 `DRAFTS_DIR`
与 `REPO_ROOT` 换到临时目录。
"""
from __future__ import annotations

import json

from api.routes import drafts


def _drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, "DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(drafts, "REPO_ROOT", tmp_path)
    return tmp_path / "drafts"


def test_the_draft_box_is_listed(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    (root / "分类" / "二级").mkdir(parents=True)
    (root / "分类" / "二级" / "篇.md").write_text("---\ntitle: 篇\n---\n", encoding="utf-8")

    units = client.get("/api/drafts").json()["units"]
    assert [u["draft_id"] for u in units] == ["分类/二级/篇"]
    assert units[0]["kind"] == "document"
    assert units[0]["promotable"] is True


def test_an_index_page_is_listed_but_not_promotable(client, tmp_path, monkeypatch):
    """索引页**要列**，只是不给过审按钮——界面上标原因。"""
    root = _drafts(tmp_path, monkeypatch)
    (root / "分类").mkdir(parents=True)
    (root / "分类" / "_index.md").write_text("x\n", encoding="utf-8")

    unit = client.get("/api/drafts").json()["units"][0]
    assert unit["kind"] == "index"
    assert unit["promotable"] is False
    assert "死链" in unit["reason"]


def test_saving_only_touches_the_keys_in_the_body(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    (root / "_video" / "系列" / "合集" / "文档" / "short").mkdir(parents=True)
    (root / "_video" / "系列" / "合集" / "文档" / "short" / "口播稿.md").write_text(
        "旧", encoding="utf-8")
    (root / "_video" / "系列" / "合集" / "文档" / "short" / "contract.json").write_text(
        "{}", encoding="utf-8")

    response = client.put("/api/drafts/_video/系列/合集/文档/short",
                          json={"files": {"口播稿.md": "新"}})
    assert response.status_code == 200
    tier = root / "_video" / "系列" / "合集" / "文档" / "short"
    assert (tier / "口播稿.md").read_text(encoding="utf-8") == "新"
    assert (tier / "contract.json").read_text(encoding="utf-8") == "{}"


def test_saving_a_file_name_that_would_escape_is_400(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    (root / "分类" / "二级").mkdir(parents=True)
    (root / "分类" / "二级" / "篇.md").write_text("x", encoding="utf-8")

    response = client.put("/api/drafts/分类/二级/篇",
                          json={"files": {"../../逃逸.md": "x"}})
    assert response.status_code == 400


def test_promote_copies_and_reports_the_manual_steps(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    (root / "分类" / "二级").mkdir(parents=True)
    (root / "分类" / "二级" / "篇.md").write_text("正文", encoding="utf-8")

    response = client.post("/api/drafts/分类/二级/篇/promote")
    assert response.status_code == 200
    body = response.json()
    assert body["targets"] == ["docs/分类/二级/篇.md"]
    assert len(body["manual_steps"]) == 3
    assert (tmp_path / "docs" / "分类" / "二级" / "篇.md").read_text(
        encoding="utf-8") == "正文"


def test_promote_refuses_an_index_page(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    (root / "分类").mkdir(parents=True)
    (root / "分类" / "_index.md").write_text("x", encoding="utf-8")

    response = client.post("/api/drafts/分类/_index/promote")
    assert response.status_code == 400


def test_the_ai_draft_route_is_501(client):
    """它**不是**「没有这条路径」，是「说好了要做，还没做」。"""
    assert client.post("/api/drafts/draft").status_code == 501


def test_creating_a_document_draft(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    response = client.post("/api/drafts",
                           json={"kind": "document",
                                 "draft_id": "新分类/新二级/新篇",
                                 "title": "新篇"})
    assert response.status_code == 200
    assert (root / "新分类" / "新二级" / "新篇.md").exists()


def test_creating_an_episode_draft_writes_the_three_facts(client, tmp_path, monkeypatch):
    root = _drafts(tmp_path, monkeypatch)
    response = client.post("/api/drafts",
                           json={"kind": "episode",
                                 "draft_id": "_video/系列/合集/文档/short",
                                 "title": "标题"})
    assert response.status_code == 200
    tier = root / "_video" / "系列" / "合集" / "文档" / "short"
    contract = json.loads((tier / "contract.json").read_text(encoding="utf-8"))
    assert contract["episode"] == "系列/合集/文档/short"
