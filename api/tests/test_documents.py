"""文档流：列母稿、读母稿、重建、看真页面。"""
from __future__ import annotations

import sys

from api.routes import documents
from api.services import preview
from api.services.commands import Command


def test_the_preview_url_has_the_docs_prefix():
    assert preview.site_preview_url("a/b/c") == "http://127.0.0.1:4000/docs/a/b/c/"


def test_the_preview_url_strips_the_category_suffix():
    """分类页的 `/_index` 后缀按规则表剥掉（与 `tools/url_rules.py` 一致）。"""
    assert preview.site_preview_url("distributed/_index") == \
        "http://127.0.0.1:4000/docs/distributed/"


def test_a_missing_document_is_404(client):
    assert client.get("/api/documents/没有这一篇").status_code == 404


def test_the_route_table_is_mounted(client):
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert "documents" in response.json()


def test_listing_shows_the_mother_drafts(client, monkeypatch, tmp_path):
    docs = tmp_path / "docs" / "分类" / "二级"
    docs.mkdir(parents=True)
    (docs / "篇.md").write_text("---\ntitle: 一篇\n---\n\n正文\n", encoding="utf-8")
    (tmp_path / "docs" / "README.md").write_text("模块说明\n", encoding="utf-8")
    monkeypatch.setattr(documents, "DOCS_DIR", tmp_path / "docs")

    units = client.get("/api/documents").json()["documents"]
    assert [u["id"] for u in units] == ["分类/二级/篇"]
    assert units[0]["title"] == "一篇"
    assert units[0]["path"] == "docs/分类/二级/篇.md"


def test_reading_a_document_returns_its_content(client, monkeypatch, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("---\ntitle: 甲\n---\n\n正文在这里\n", encoding="utf-8")
    monkeypatch.setattr(documents, "DOCS_DIR", docs)

    body = client.get("/api/documents/a").json()
    assert body["title"] == "甲"
    assert "正文在这里" in body["content"]


def test_the_rebuild_starts_one_job(client, monkeypatch, tmp_path):
    """重建是**一个**作业，三步串行——不是三个作业。"""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("---\ntitle: 甲\n---\n", encoding="utf-8")
    monkeypatch.setattr(documents, "DOCS_DIR", docs)
    monkeypatch.setattr(documents, "REBUILD_STEPS",
                        (Command(argv=[sys.executable, "-c", "print('编好了')"],
                                 cwd=tmp_path, key="fake"),))

    response = client.post("/api/documents/a/rebuild")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"].startswith("j-")
    assert body["status"] in {"queued", "running"}


def test_the_preview_route_reports_whether_the_server_is_up(client, monkeypatch):
    monkeypatch.setattr(documents.preview, "ensure_site_server",
                        lambda **kwargs: (True, "站点 dev server 已在跑"))
    body = client.get("/api/documents/a/b/preview").json()
    assert body["url"] == "http://127.0.0.1:4000/docs/a/b/"
    assert body["running"] is True
