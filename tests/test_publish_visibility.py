"""Contract tests for the publish-visibility pipeline.

Two build steps turn the publish layer's state into something a reader can
see on the site:

- ``tools/build-video-pages.py`` turns each AIV episode's narration script
  into a content unit (``source/_posts/video/<episode>.md``) plus a
  collection page.
- ``tools/build-publish-index.py`` summarises ``platforms/<platform>/outbox/*.json``
  into ``source/_data/publish_index.json``, which the theme renders as the
  "where else did this go" block.

Both are build steps over committed inputs, so they are testable without
touching the repository: the tools read their inputs from module-level
path constants, which the tests point at temporary directories.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"


def load_tool(name):
    """Import one of the build tools as a module.

    ``main()`` is guarded by ``if __name__ == '__main__'``, so importing
    only defines functions -- it does not rewrite ``source/``.
    """
    spec = importlib.util.spec_from_file_location(
        "tool_under_test_{}".format(name.replace("-", "_")), TOOLS / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


video_pages = load_tool("build-video-pages")
publish_index = load_tool("build-publish-index")


# --- 视频内容单元 ---------------------------------------------------------


def test_the_episode_registry_comes_from_the_makefile():
    """期号与口播稿的对应关系只有一处真相：video/pipeline/Makefile。"""
    episodes = video_pages.read_episode_scripts()

    assert "row-lock" in episodes
    assert "structured-ddl" in episodes
    assert episodes["row-lock"].endswith(".md")


def test_a_sibling_link_becomes_the_sibling_page():
    body = "承接：[《结构化 DDL》](./字幕-结构化DDL.md)（EP05）"
    rewritten = video_pages.rewrite_links(
        body, {"./字幕-结构化DDL.md": "/2026/11/12/video/structured-ddl/"}
    )

    assert "/2026/11/12/video/structured-ddl/" in rewritten
    assert "字幕-结构化DDL.md" not in rewritten


def test_a_link_without_a_published_counterpart_keeps_its_text():
    """站内没有对应页面的链接，宁可留字不带链接——死链比纯文本更糟。"""
    body = "选题依据：[`选题库.md`](./选题库.md) 的 EP06"
    rewritten = video_pages.rewrite_links(body, {})

    assert "选题库.md" in rewritten
    assert "](" not in rewritten


def test_the_permalink_follows_the_site_rule():
    assert (
        video_pages.permalink("2026-11-12", "video/row-lock")
        == "/2026/11/12/video/row-lock/"
    )
    assert video_pages.permalink("", "video/row-lock") == "/video/row-lock/"


def test_a_video_page_carries_its_kind_and_its_platforms(tmp_path, monkeypatch):
    """视频页是内容单元（kind: video），并带上它发到过的平台。"""
    aiv = tmp_path / "video"
    (aiv / "contracts").mkdir(parents=True)
    (aiv / "pipeline").mkdir()
    (aiv / "字幕-行锁.md").write_text(
        '---\ntitle: "两个事务改同一行，谁先谁后"\ndate: 2026-11-12\n---\n\n'
        "# 口播稿\n\n大家好。\n",
        encoding="utf-8",
    )
    (aiv / "contracts" / "row-lock.json").write_text(
        json.dumps({"episode": "row-lock", "title": "两个事务改同一行，谁先谁后"}),
        encoding="utf-8",
    )
    (aiv / "pipeline" / "Makefile").write_text(
        "ifeq ($(EP),row-lock)\nSCRIPT := $(ROOT)/字幕-行锁.md\nendif\n",
        encoding="utf-8",
    )

    platforms = tmp_path / "platforms"
    for platform in ("bilibili", "channels"):
        outbox = platforms / platform / "outbox"
        outbox.mkdir(parents=True)
        (outbox / f"row-lock__{platform}.json").write_text(
            json.dumps(
                {"content_id": "row-lock", "platform": platform, "status": "packaged"}
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(video_pages, "AIV_ROOT", aiv)
    monkeypatch.setattr(video_pages, "MAKEFILE", aiv / "pipeline" / "Makefile")
    monkeypatch.setattr(video_pages, "CONTRACTS_DIR", aiv / "contracts")
    monkeypatch.setattr(video_pages, "PLATFORMS_DIR", platforms)
    monkeypatch.setattr(video_pages, "POSTS_DIR", tmp_path / "posts")

    assert video_pages.main([]) == 0

    page = (tmp_path / "posts" / "video" / "row-lock.md").read_text(encoding="utf-8")
    assert "kind: video" in page
    assert "  - bilibili" in page
    assert "  - channels" in page
    assert "两个事务改同一行，谁先谁后" in page


def test_the_video_pages_tool_does_not_write_the_series_page(tmp_path, monkeypatch):
    """合集页（系列页）由 ``build-series-page.py`` 写——一个文件一个写入者。

    两个工具写同一个文件，谁赢要看流水线顺序；改了一处却没生效，
    排查起来最费时间。
    """
    aiv = tmp_path / "video"
    (aiv / "contracts").mkdir(parents=True)
    (aiv / "pipeline").mkdir()
    (aiv / "字幕-行锁.md").write_text(
        '---\ntitle: "两个事务改同一行，谁先谁后"\ndate: 2026-11-12\n---\n\n# 口播稿\n',
        encoding="utf-8",
    )
    (aiv / "contracts" / "row-lock.json").write_text(
        json.dumps({"episode": "row-lock", "title": "两个事务改同一行，谁先谁后"}),
        encoding="utf-8",
    )
    (aiv / "pipeline" / "Makefile").write_text(
        "ifeq ($(EP),row-lock)\nSCRIPT := $(ROOT)/字幕-行锁.md\nendif\n",
        encoding="utf-8",
    )
    platforms = tmp_path / "platforms"
    (platforms / "toutiao" / "outbox").mkdir(parents=True)

    monkeypatch.setattr(video_pages, "AIV_ROOT", aiv)
    monkeypatch.setattr(video_pages, "MAKEFILE", aiv / "pipeline" / "Makefile")
    monkeypatch.setattr(video_pages, "CONTRACTS_DIR", aiv / "contracts")
    monkeypatch.setattr(video_pages, "PLATFORMS_DIR", platforms)
    monkeypatch.setattr(video_pages, "POSTS_DIR", tmp_path / "posts")

    assert video_pages.main([]) == 0
    assert not (tmp_path / "source" / "videos" / "index.md").exists()


def test_the_video_pages_tool_reads_the_real_snapshots():
    """真的仓库里的 567 条快照，一条都不能漏。

    别的用例把快照目录指到临时目录——**路径写错时它们照样绿**。
    这一条对着真仓库：漏掉任何一个平台的目录，站点就会把
    「已经发过的」当成「没发过」。
    """
    records = video_pages.read_outbox()
    assert len(records) == 567, f"读到 {len(records)} 条快照，应为 567"


# --- 发布索引 -------------------------------------------------------------


def test_the_index_maps_a_content_id_to_its_page():
    """content_id 是内容单元相对 source/_posts 的路径（去后缀）。"""
    posts = {
        "database/demo": {
            "title": "一篇",
            "url": "/2026/01/01/database/demo/",
            "kind": "post",
        }
    }
    assert publish_index.match_content_id("database/demo", posts) == "database/demo"


def test_a_video_snapshot_finds_its_page_by_name():
    """视频快照的 content_id 是期号，页面在 video/ 下面。"""
    posts = {
        "video/row-lock": {
            "title": "行锁",
            "url": "/2026/11/12/video/row-lock/",
            "kind": "video",
        }
    }
    assert publish_index.match_content_id("row-lock", posts) == "video/row-lock"


def test_an_ambiguous_name_is_not_guessed():
    posts = {
        "video/row-lock": {"title": "a", "url": "/a/", "kind": "video"},
        "docs/row-lock": {"title": "b", "url": "/b/", "kind": "post"},
    }
    assert publish_index.match_content_id("row-lock", posts) is None


def test_the_index_splits_articles_from_videos(tmp_path, monkeypatch):
    posts_dir = tmp_path / "source" / "_posts"
    (posts_dir / "database").mkdir(parents=True)
    (posts_dir / "video").mkdir(parents=True)
    (posts_dir / "database" / "demo.md").write_text(
        '---\ntitle: "一篇"\ndate: 2026-01-02 03:04:05\nkind: post\n---\n',
        encoding="utf-8",
    )
    (posts_dir / "video" / "row-lock.md").write_text(
        '---\ntitle: "行锁"\ndate: 2026-11-12\nkind: video\n---\n',
        encoding="utf-8",
    )

    platforms = tmp_path / "platforms"
    toutiao = platforms / "toutiao" / "outbox"
    toutiao.mkdir(parents=True)
    bilibili = platforms / "bilibili" / "outbox"
    bilibili.mkdir(parents=True)
    (toutiao / "database-demo__toutiao.json").write_text(
        json.dumps(
            {
                "content_id": "database/demo",
                "platform": "toutiao",
                "status": "packaged",
                "title": "一篇",
            }
        ),
        encoding="utf-8",
    )
    (bilibili / "row-lock__bilibili.json").write_text(
        json.dumps(
            {
                "content_id": "row-lock",
                "platform": "bilibili",
                "status": "published",
                "title": "行锁",
                "published_url": "https://www.bilibili.com/video/BV1",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(publish_index, "POSTS_DIR", posts_dir)
    monkeypatch.setattr(publish_index, "PLATFORMS_DIR", platforms)

    index = publish_index.build_index()

    assert set(index["articles"]) == {"database/demo"}
    assert set(index["videos"]) == {"video/row-lock"}
    assert index["articles"]["database/demo"]["url"] == "/2026/01/02/database/demo/"
    assert (
        index["videos"]["video/row-lock"]["platforms"][0]["platform_name"] == "哔哩哔哩"
    )
    assert index["stats"]["published"] == 1
    assert index["stats"]["unmatched"] == []


def test_a_snapshot_without_a_page_is_reported_not_hidden(tmp_path, monkeypatch):
    """找不到内容单元的快照要报出来，不能悄悄丢掉。"""
    posts_dir = tmp_path / "source" / "_posts"
    posts_dir.mkdir(parents=True)
    platforms = tmp_path / "platforms"
    wechat = platforms / "wechat" / "outbox"
    wechat.mkdir(parents=True)
    (wechat / "gone__wechat.json").write_text(
        json.dumps({"content_id": "gone", "platform": "wechat", "status": "drafted"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(publish_index, "POSTS_DIR", posts_dir)
    monkeypatch.setattr(publish_index, "PLATFORMS_DIR", platforms)

    index = publish_index.build_index()

    assert index["stats"]["unmatched"] == ["gone"]
    assert index["articles"] == {}


def test_the_index_is_written_as_json(tmp_path, monkeypatch):
    posts_dir = tmp_path / "source" / "_posts"
    posts_dir.mkdir(parents=True)
    platforms = tmp_path / "platforms"
    (platforms / "toutiao" / "outbox").mkdir(parents=True)
    monkeypatch.setattr(publish_index, "POSTS_DIR", posts_dir)
    monkeypatch.setattr(publish_index, "PLATFORMS_DIR", platforms)

    out = tmp_path / "data" / "publish_index.json"
    assert publish_index.main(["--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "articles" in payload and "videos" in payload


def test_the_publish_index_reads_the_real_snapshots():
    """真的仓库里的 567 条快照，一条都不能漏。

    别的用例把快照目录指到临时目录——**路径写错时它们照样绿**。
    这一条对着真仓库：漏掉任何一个平台的目录，站点就会把
    「已经发过的」当成「没发过」。
    """
    records = publish_index.read_outbox()
    assert sum(len(v) for v in records.values()) == 567, (
        f"读到 {sum(len(v) for v in records.values())} 条快照，应为 567"
    )
