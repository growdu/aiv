"""统一审校的路由：两条线一张表。

**这些测试不许跑真的审校命令**——它们把路由里的 `capture` 换成假的。
"""
from __future__ import annotations

import json

from api.routes import review

EPISODE = "系列/合集/文档/short"


def _overview_tables(tmp_path, monkeypatch):
    """摆出两条线的那两张表。"""
    monkeypatch.setattr(review, "REPO_ROOT", tmp_path)
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "INDEX.md").write_text(
        "## 怎么读这张表\n\n"
        "| 列 | 含义 |\n| --- | --- |\n| 记录 | 审校记录 |\n\n"
        "| 记录 | 支柱 | 状态 | 信号 | 待确认 | 不阻塞 | 批次 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| [甲](a/b.md) | a | 已合入 | 0 | 0 | 0 | 1 |\n",
        encoding="utf-8")
    (tmp_path / "video" / "review").mkdir(parents=True)
    (tmp_path / "video" / "review" / "INDEX.md").write_text(
        "| 期号 | 期路径 | 标题 | 状态 | 文本层信号 | 成片层信号 | 待确认项 | 批次 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| ep01 | {EPISODE} | 标题 | 建议中 | 1 | 2 | 3 | 1 |\n",
        encoding="utf-8")


def test_the_overview_projects_both_lines_onto_the_same_columns(
        client, tmp_path, monkeypatch):
    _overview_tables(tmp_path, monkeypatch)

    rows = client.get("/api/review/overview").json()["rows"]
    assert [r["layer"] for r in rows] == ["document", "episode"]
    assert rows[0]["id"] == "a/b"
    assert rows[0]["status"] == "已合入"
    assert rows[1]["signals"] == 3        # 文本层 + 成片层
    assert rows[1]["pending"] == 3
    assert rows[1]["title"] == "标题"


def test_the_overview_is_empty_when_there_are_no_tables(client, tmp_path,
                                                        monkeypatch):
    monkeypatch.setattr(review, "REPO_ROOT", tmp_path)
    assert client.get("/api/review/overview").json()["rows"] == []


def test_the_document_review_returns_the_unified_shape(client, tmp_path,
                                                       monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("---\ntitle: 甲\n---\n\n正文\n", encoding="utf-8")
    monkeypatch.setattr(review, "DOCS_DIR", docs)
    raw = {"docs": [{"source": "a.md", "slug": "a", "title": "甲",
                     "signals": [{"rule": "R1", "severity": "warn", "line": 3,
                                  "excerpt": "x", "detail": "d"}]}]}
    monkeypatch.setattr(review, "capture",
                        lambda command, **kwargs: (0, json.dumps(raw)))

    body = client.get("/api/review/documents/a").json()
    assert body["layer"] == "document"
    assert body["counts"]["warn"] == 1
    assert body["signals"][0]["target"] == "第 3 行"
    assert body["gate"]["status"] == "待审"      # 没有审校记录


def test_a_document_that_does_not_exist_is_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(review, "DOCS_DIR", tmp_path / "docs")
    assert client.get("/api/review/documents/没有这一篇").status_code == 404


def test_the_review_command_failing_is_reported_not_faked(client, tmp_path,
                                                           monkeypatch):
    """命令没跑成 → **报告还是那个形状，但明说出了什么事**。"""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(review, "DOCS_DIR", docs)
    monkeypatch.setattr(review, "capture", lambda command, **kwargs: (2, "起不来"))

    body = client.get("/api/review/documents/a").json()
    assert body["signals"] == []
    assert body["counts"]["error"] == 0
    assert any("没跑成" in note for note in body["notes"])


def test_the_episode_review_returns_the_unified_shape(client, tmp_path,
                                                      monkeypatch):
    episodes_dir = tmp_path / "video" / "episodes"
    (episodes_dir / EPISODE).mkdir(parents=True)
    monkeypatch.setattr(review, "EPISODES_DIR", episodes_dir)
    raw = {"episode": EPISODE, "layer": "text", "counts": {},
           "signals": [{"rule": "R2", "layer": "text", "severity": "info",
                        "target": "第 3 句", "excerpt": "x", "detail": "d"}],
           "notes": []}
    monkeypatch.setattr(review, "capture",
                        lambda command, **kwargs: (0, json.dumps(raw)))

    body = client.get(f"/api/review/episodes/{EPISODE}").json()
    assert body["subject"]["kind"] == "episode"
    assert body["layer"] == "text"        # 视频线有两层：text / video
    assert body["counts"]["info"] == 1
    assert body["signals"][0]["target"] == "第 3 句"
    assert body["signals"][0]["line"] is None


def test_an_episode_that_does_not_exist_is_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(review, "EPISODES_DIR", tmp_path / "video" / "episodes")
    assert client.get(f"/api/review/episodes/{EPISODE}").status_code == 404


def test_the_run_route_refuses_an_unknown_episode(client, tmp_path, monkeypatch):
    monkeypatch.setattr(review, "EPISODES_DIR", tmp_path / "video" / "episodes")
    response = client.post(f"/api/review/episodes/{EPISODE}/run")
    assert response.status_code == 404


def test_the_run_route_starts_a_job(client, tmp_path, monkeypatch):
    episodes_dir = tmp_path / "video" / "episodes"
    (episodes_dir / EPISODE).mkdir(parents=True)
    monkeypatch.setattr(review, "EPISODES_DIR", episodes_dir)

    response = client.post(f"/api/review/episodes/{EPISODE}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"].startswith("j-")
