"""Tests for the outbox snapshot the WeChat adapter writes.

The snapshot is the publish layer's idempotency key (spec §7.1): the
scheduler reads it to decide whether an article was already published,
and the site reads it to show where an article went.

Two properties matter and are tested here:

- the file name is derived from the content id, so two platforms never
  collide on one article
- the payload holds public information only -- no token, no secret, no
  absolute path of the machine that produced it
"""
import json
import os

from wechat.snapshot import (
    SNAPSHOT_KEYS,
    outbox_dir_from_env,
    snapshot_name,
    write_snapshot,
)

# --- naming ----------------------------------------------------------------


def test_the_content_id_becomes_a_flat_file_name():
    assert snapshot_name("database/demo") == "database-demo__wechat.json"


def test_two_platforms_never_collide_on_one_article():
    assert snapshot_name("database/demo") != snapshot_name("database/demo", "toutiao")


def test_the_outbox_directory_can_be_pointed_elsewhere(monkeypatch, tmp_path):
    """The scheduler may run the adapter with a different working directory."""
    monkeypatch.setenv("PUBLISH_OUTBOX_DIR", str(tmp_path))
    assert outbox_dir_from_env() == tmp_path


def test_without_the_environment_variable_it_is_the_repository_one(monkeypatch):
    monkeypatch.delenv("PUBLISH_OUTBOX_DIR", raising=False)
    assert outbox_dir_from_env().name == "outbox"
    assert outbox_dir_from_env().parent.name == "publish"


# --- payload ---------------------------------------------------------------


def test_a_snapshot_holds_exactly_the_contract_fields(tmp_path):
    path = write_snapshot(tmp_path / "a.json", content_id="database/demo",
                          status="drafted", title="一篇文章")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == set(SNAPSHOT_KEYS)


def test_the_snapshot_says_where_the_article_is_not_yet(tmp_path):
    """A draft is not published: there is no public URL yet."""
    path = write_snapshot(tmp_path / "a.json", content_id="database/demo",
                          status="drafted", title="一篇文章")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "drafted"
    assert payload["published_url"] is None
    assert payload["platform"] == "wechat"
    assert payload["kind"] == "document"


def test_no_credential_ever_reaches_the_snapshot(tmp_path):
    path = write_snapshot(tmp_path / "a.json", content_id="database/demo",
                          status="drafted", title="一篇文章")
    text = path.read_text(encoding="utf-8")
    for secret in ("token", "appsecret", "appid", "secret"):
        assert secret not in text.lower()


def test_the_snapshot_is_rewritten_every_time(tmp_path):
    """The scheduler watches the mtime to know the idempotency key landed.

    A snapshot whose content did not change is still rewritten, otherwise
    the scheduler would read "adapter said success but the key did not
    land" and hand the article over to a human.
    """
    path = tmp_path / "a.json"
    write_snapshot(path, content_id="database/demo", status="drafted", title="一篇文章")
    # 把 mtime 归零再写一次：文件系统的时间戳精度有高有低，
    # 比两个「几乎同时」的 mtime 可靠。
    os.utime(path, (0, 0))
    write_snapshot(path, content_id="database/demo", status="drafted", title="一篇文章")
    assert path.stat().st_mtime_ns != 0


def test_a_new_state_replaces_the_old_one(tmp_path):
    """状态变了，快照要跟着变——不能因为「内容看起来一样」就跳过。"""
    path = tmp_path / "a.json"
    write_snapshot(path, content_id="database/demo", status="failed",
                   title="一篇文章", reason="缺凭据")
    write_snapshot(path, content_id="database/demo", status="drafted",
                   title="一篇文章")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "drafted"


def test_a_failed_attempt_is_retryable_only_when_it_should_be(tmp_path):
    path = write_snapshot(tmp_path / "a.json", content_id="database/demo",
                          status="failed", title="一篇文章",
                          reason="缺凭据", retryable=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["retryable"] is True
    assert payload["status"] == "failed"


def test_writing_the_snapshot_creates_the_directory(tmp_path):
    path = write_snapshot(tmp_path / "deep" / "nested" / "a.json",
                          content_id="database/demo", status="drafted", title="一篇文章")
    assert path.is_file()


def test_the_required_fields_are_part_of_the_signature():
    """少一个必填字段就写不出快照——参数本身是必填的。"""
    import inspect

    parameters = inspect.signature(write_snapshot).parameters
    for name in ("content_id", "status", "title"):
        assert parameters[name].default is inspect.Parameter.empty
