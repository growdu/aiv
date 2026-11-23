"""两条线的审校归一成一张表。**信号不是门禁**（全局约束 11）。"""
from __future__ import annotations

from api.services.review import (
    document_gate,
    episode_gate,
    normalize_document_report,
    normalize_pyv_report,
)


def test_the_document_line_gets_a_target_derived_from_its_line():
    raw = {"docs": [{
        "source": "docs/a/b/c.md", "pillar": "a", "slug": "b/c", "kind": "article",
        "title": "T", "stats": {}, "depth": {}, "depth_ok": True,
        "signals": [{"rule": "AIF-01", "severity": "warn", "line": 42,
                     "excerpt": "片段", "detail": "说明"}],
    }]}
    report = normalize_document_report(raw, doc_id="a/b/c", path="docs/a/b/c.md")
    assert report["counts"] == {"error": 0, "warn": 1, "info": 0}
    signal = report["signals"][0]
    assert signal["layer"] == "document"
    assert signal["target"] == "第 42 行"
    assert signal["line"] == 42


def test_the_document_line_never_produces_an_error_count():
    raw = {"docs": [{"source": "x", "pillar": "a", "slug": "b", "kind": "article",
                     "title": "T", "stats": {}, "depth": {}, "depth_ok": True,
                     "signals": []}]}
    report = normalize_document_report(raw, doc_id="a/b", path="docs/a/b.md")
    assert report["counts"]["error"] == 0


def test_the_video_line_keeps_its_target_and_has_no_line():
    raw = {"episode": "a/b/c/short", "layer": "text",
           "counts": {"error": 0, "warn": 1, "info": 0},
           "signals": [{"rule": "VT-05", "layer": "text", "severity": "warn",
                        "target": "第3句", "excerpt": "片段", "detail": "说明"}],
           "notes": ["一条说明"]}
    report = normalize_pyv_report(raw, subject={"kind": "episode",
                                                 "id": "a/b/c/short",
                                                 "path": "video/episodes/a/b/c/short"})
    signal = report["signals"][0]
    assert signal["target"] == "第3句"
    assert signal["line"] is None
    assert report["notes"] == ["一条说明"]


def test_the_counts_are_recomputed_from_the_signals(tmp_path):
    """不抄输入里的 counts——两边算法不同的时候，抄了就对不上。"""
    raw = {"episode": "a/b/c/short", "layer": "text",
           "counts": {"error": 9, "warn": 0, "info": 0},
           "signals": [{"rule": "VT-05", "layer": "text", "severity": "warn",
                        "target": "第3句", "excerpt": "片段", "detail": "说明"}],
           "notes": []}
    report = normalize_pyv_report(raw, subject={"kind": "episode",
                                                 "id": "a/b/c/short",
                                                 "path": "video/episodes/a/b/c/short"})
    assert report["counts"] == {"error": 0, "warn": 1, "info": 0}


def test_a_document_without_a_review_record_is_blocked(tmp_path):
    gate = document_gate("a/b/c", repo_root=tmp_path)
    assert gate["status"] == "待审"
    assert gate["blocking"] is True


def test_a_merged_document_record_is_not_blocked(tmp_path):
    record = tmp_path / "review" / "a" / "b"
    record.mkdir(parents=True)
    (record / "c.md").write_text(
        "---\nstatus: 已合入\nsrc: a/b/c.md\n---\n\n# 审校\n", encoding="utf-8")
    gate = document_gate("a/b/c", repo_root=tmp_path)
    assert gate["status"] == "已合入"
    assert gate["blocking"] is False


def test_an_episode_without_review_md_is_blocked(tmp_path):
    gate = episode_gate("a/b/c/short", repo_root=tmp_path)
    assert gate["status"] == "待审"
    assert gate["blocking"] is True


def test_the_episode_status_line_is_parsed(tmp_path):
    ep = tmp_path / "video" / "episodes" / "a" / "b" / "c" / "short"
    ep.mkdir(parents=True)
    (ep / "review.md").write_text(
        "# 审核：ep01 标题\n\n- 期路径：a/b/c/short\n- 状态：已看帧\n\n"
        "## 优先修改\n\n1. 位置：\n   - 状态：待改\n",
        encoding="utf-8")
    gate = episode_gate("a/b/c/short", repo_root=tmp_path)
    assert gate["status"] == "已看帧"
    assert gate["blocking"] is True


def test_a_signal_never_blocks_the_gate(tmp_path):
    """**信号不是门禁**：命中信号不改变 gate。"""
    record = tmp_path / "review" / "a"
    record.mkdir(parents=True)
    (record / "b.md").write_text("---\nstatus: 已合入\n---\n", encoding="utf-8")
    raw = {"docs": [{"source": "docs/a/b.md", "pillar": "a", "slug": "a/b",
                     "kind": "article", "title": "T", "stats": {},
                     "depth": {}, "depth_ok": True,
                     "signals": [{"rule": "AIF-01", "severity": "error",
                                  "line": 1, "excerpt": "x", "detail": "d"}]}]}
    report = normalize_document_report(raw, doc_id="a/b", path="docs/a/b.md",
                                       repo_root=tmp_path)
    assert report["counts"]["error"] == 1
    assert report["gate"]["blocking"] is False
