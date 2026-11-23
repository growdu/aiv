"""身份从缝里读，**不写死**（全局约束 2）。"""
from __future__ import annotations

import json

from api.services import identity


def test_the_outbox_projection_is_the_common_subset():
    """各平台快照的键数不一样：有的九个键、有的是十个——只投影公共子集。"""
    assert identity.OUTBOX_COMMON == ("platform", "status", "reason", "updated_at",
                                      "content_id", "title", "published_url")


def test_the_capability_list_is_scanned_not_written_down():
    ids = [p["id"] for p in identity.platform_capabilities()]
    assert ids == sorted(ids)
    assert ids, "应该至少扫到一个平台"
    # 平台 id 全是小写 slug，不是显示名。
    for platform_id in ids:
        assert platform_id == platform_id.lower()
        assert " " not in platform_id


def test_the_site_identity_comes_from_the_config_file():
    site = identity.site_identity()
    assert "name" in site and "tagline" in site


def test_the_site_identity_does_not_leak_the_note_field():
    """`note` 是给人看的说明，不端出去。"""
    site = identity.site_identity()
    assert "note" not in site


def test_the_brand_identity_comes_from_the_config_file():
    brand = identity.brand_identity()
    assert "name" in brand and "token" in brand


def test_the_capability_carries_its_limits_and_media():
    """限额与媒体规格是能力声明的一部分——前端要靠它做提示。"""
    platform = identity.platform_capabilities()[0]
    assert "limits" in platform
    assert "media" in platform
    assert "id" in platform


def test_the_outbox_projects_only_the_common_keys(tmp_path, monkeypatch):
    """一个键多的快照，投影后只剩公共的那几个。"""
    monkeypatch.setattr(identity, "PLATFORMS_DIR", tmp_path)
    outbox = tmp_path / "某平台" / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "一篇.json").write_text(json.dumps({
        "platform": "某平台", "status": "packaged", "reason": "等人工",
        "updated_at": "2026-11-23", "content_id": "a/b",
        "title": "标题", "published_url": None,
        "package_dir": "别端出去", "automation": "manual",
    }, ensure_ascii=False), encoding="utf-8")

    snapshots = identity.outbox_snapshots()
    assert len(snapshots) == 1
    assert set(snapshots[0]) == set(identity.OUTBOX_COMMON)
    assert "package_dir" not in snapshots[0]


def test_a_missing_key_is_not_filled_with_a_default(tmp_path, monkeypatch):
    """缺了的键就缺着——补出来的 `published_url: null` 与「还没发」是两回事。"""
    monkeypatch.setattr(identity, "PLATFORMS_DIR", tmp_path)
    outbox = tmp_path / "某平台" / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "一篇.json").write_text(json.dumps({
        "platform": "某平台", "status": "packaged",
    }, ensure_ascii=False), encoding="utf-8")

    snapshots = identity.outbox_snapshots()
    assert snapshots[0] == {"platform": "某平台", "status": "packaged"}


def test_the_config_route_returns_site_and_brand(client):
    body = client.get("/api/config").json()
    assert "site" in body and "brand" in body


def test_the_platforms_route_lists_the_platforms(client):
    body = client.get("/api/platforms").json()
    assert body["platforms"]
    assert "id" in body["platforms"][0]


def test_the_outbox_route_lists_the_snapshots(client):
    body = client.get("/api/publish/outbox").json()
    assert "snapshots" in body
