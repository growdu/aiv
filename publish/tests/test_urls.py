"""契约层按共享规则拼地址。"""
import pytest
from publishkit import urls


def test_a_document_url_is_the_docs_url():
    assert urls.doc_url("source-tracks/postgresql/x") == "/docs/source-tracks/postgresql/x/"


def test_a_category_url_drops_the_index_suffix():
    assert urls.doc_url("source-tracks/_index") == "/docs/source-tracks/"


def test_a_video_url_drops_the_video_prefix():
    assert urls.video_url("video/row-lock") == "/videos/row-lock/"


def test_the_unit_url_switches_on_the_kind():
    assert urls.unit_url("video/row-lock", "video") == "/videos/row-lock/"
    assert urls.unit_url("source-tracks/_index", "category") == "/docs/source-tracks/"
    assert urls.unit_url("a/b", "document") == "/docs/a/b/"


def test_a_rules_file_without_the_required_keys_is_refused(tmp_path):
    bad = tmp_path / "urls.json"
    bad.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        urls.load_rules(bad)
