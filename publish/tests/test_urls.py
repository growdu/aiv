"""契约层按共享规则拼地址。"""
import pytest
from publishkit import PublishKitError, urls


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


def test_a_missing_rules_file_is_a_publishkit_error(tmp_path):
    """读不到规则文件也是契约层的错——`PublishKitError` 那一族，不是裸的 OSError。

    契约层的约定：所有「有意抛出的」错都继承 `PublishKitError`，
    调用方一句 `except PublishKitError` 就能兜住。
    """
    missing = tmp_path / "nope.json"
    with pytest.raises(PublishKitError):
        urls.load_rules(missing)
    with pytest.raises(ValueError):
        urls.load_rules(missing)
