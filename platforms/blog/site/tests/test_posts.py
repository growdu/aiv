"""文章这一层的守卫：地址形状与 front matter。

**背景**
------
站点的地址形状只有一处说了算：`tools/urls.py`（它读仓库根的
`rules/urls.json`，规则表不在时用同样的默认值兜底）。
`tools/build-posts.py` 把内容单元编成 hexo 的文章与目录页，
`tools/rewrite-links.mjs` 按同一张地址表重写正文里的相对链接。

**这一层守什么**
----------------

1. **地址形状**：文档 → `/docs/<id>/`；目录页 → `/docs/<目录>/`
   （`_index` 的尾巴抹掉）；视频 → `/videos/<slug>/`。
2. **文件落在哪儿**：文章在 `source/_posts/`，目录页在 `source/docs/<路径>/index.md`。
3. **front matter 齐不齐**：标题、地址、版式、描述。
4. **视频单元不进站点**（作者拍板：站上没有视频页）——但它**在地址表里**，
   正文里指向视频的相对链接要有个地址可换。

**语料是自造的**：一条用例如果依赖「仓库里曾经有过的内容」，它迟早会因为
内容被清掉而变成假红（`acceptance/README.md` §三）。所以这里在 `tmp_path`
里造自己的内容单元树。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_tool
from paths import SITE

SITE_ROOT = SITE

build_posts = load_tool("build-posts.py")
urls = load_tool("urls.py")


DOCUMENT = """---
title: 演示文档
date: 2026-01-02 10:00:00
description: 一篇演示用的文档
kind: document
categories:
  - source-tracks/demo
tags:
  - demo
---

# 演示文档

正文。
"""

CATEGORY = """---
title: 演示目录
kind: category
categories: []
tags: []
---

这个目录的引言。
"""

VIDEO = """---
title: 演示视频
date: 2026-01-03 10:00:00
kind: video
---

口播稿。
"""


@pytest.fixture()
def units(tmp_path, monkeypatch) -> Path:
    """在 `tmp_path` 里造一棵内容单元树，返回它的根。"""
    root = tmp_path / "units"
    (root / "source-tracks" / "demo" / "getting-started").mkdir(parents=True)
    (root / "source-tracks" / "demo" / "_index.md").write_text(CATEGORY, encoding="utf-8")
    (root / "source-tracks" / "demo" / "getting-started" / "hello.md").write_text(
        DOCUMENT, encoding="utf-8"
    )
    (root / "video").mkdir(parents=True)
    (root / "video" / "demo-ep.md").write_text(VIDEO, encoding="utf-8")

    docs = tmp_path / "docs"
    docs.mkdir()

    monkeypatch.setattr(build_posts, "CONTENT_UNITS", root)
    monkeypatch.setattr(build_posts, "DOCS", docs)
    monkeypatch.setattr(build_posts, "POSTS_DIR", tmp_path / "site" / "source" / "_posts")
    monkeypatch.setattr(build_posts, "PAGES_DIR", tmp_path / "site" / "source" / "docs")
    monkeypatch.setattr(build_posts, "DATA_DIR", tmp_path / "site" / "source" / "_data")
    monkeypatch.setattr(build_posts, "IMAGES_DIR", tmp_path / "site" / "source" / "images")
    return root


@pytest.fixture()
def built(units):
    posts, pages, url_map, images, kinds = build_posts.build_all()
    return {
        "posts": posts,
        "pages": pages,
        "urls": url_map,
        "images": images,
        "kinds": kinds,
    }


def _front_matter(text: str) -> dict:
    import yaml

    assert text.startswith("---\n")
    raw = text.split("\n---", 1)[0][4:]
    return yaml.safe_load(raw) or {}


# ── 地址形状 ───────────────────────────────────────────────


def test_a_document_gets_a_docs_url(built):
    url = built["urls"]["source-tracks/demo/getting-started/hello"]
    assert url == "/docs/source-tracks/demo/getting-started/hello/"


def test_a_category_page_gets_the_directory_url(built):
    url = built["urls"]["source-tracks/demo/_index"]
    assert url == "/docs/source-tracks/demo/"


def test_a_video_unit_keeps_its_own_address(built):
    """视频没有站内页面，但地址表里得有它——正文里的链接要有个地址可换。"""
    assert built["urls"]["video/demo-ep"] == "/videos/demo-ep/"


def test_url_rules_are_the_only_source_of_truth():
    """地址形状由 `tools/urls.py` 决定，别的工具不许自己拼一遍。"""
    assert urls.unit_url("a/b", "document") == "/docs/a/b/"
    assert urls.unit_url("a/_index", "category") == "/docs/a/"
    assert urls.unit_url("video/x", "video") == "/videos/x/"


# ── 文件落在哪儿 ───────────────────────────────────────────


def test_documents_become_posts_and_categories_become_pages(built):
    assert set(built["posts"]) == {"source-tracks/demo/getting-started/hello"}
    assert set(built["pages"]) == {"source-tracks/demo/_index"}


def test_a_category_page_lands_in_the_docs_tree(units, tmp_path):
    posts, pages, url_map, images, kinds = build_posts.build_all()
    build_posts.write_all(posts, pages, url_map, images)
    target = tmp_path / "site" / "source" / "docs" / "source-tracks" / "demo" / "index.md"
    assert target.exists(), "目录页没落在 source/docs/<路径>/index.md"


# ── 视频不进站点 ───────────────────────────────────────────


def test_video_units_do_not_become_pages(built):
    assert "video/demo-ep" not in built["posts"]
    assert "video/demo-ep" not in built["pages"]
    assert built["kinds"].get("video") == 1


# ── front matter ───────────────────────────────────────────


def test_a_post_carries_the_fields_the_site_needs(built):
    fm = _front_matter(built["posts"]["source-tracks/demo/getting-started/hello"])
    assert fm["title"] == "演示文档"
    assert fm["layout"] == "post"
    assert fm["permalink"] == "/docs/source-tracks/demo/getting-started/hello/"
    assert fm["description"] == "一篇演示用的文档"
    assert fm["date"] is not None


def test_a_category_page_uses_the_directory_layout(built):
    fm = _front_matter(built["pages"]["source-tracks/demo/_index"])
    assert fm["layout"] == "docs-index"
    assert fm["permalink"] == "/docs/source-tracks/demo/"


def test_the_body_is_copied_verbatim(built):
    """正文一个字都不改——这一层只做 front matter 的改写与拷贝。"""
    text = built["posts"]["source-tracks/demo/getting-started/hello"]
    body = text.split("\n---\n", 1)[1]
    assert body.strip().endswith("正文。")
    assert "演示文档" in body  # 母稿里的 H1 还在（摘 H1 是渲染层的事）


# ── 图片 ───────────────────────────────────────────────────


def test_images_are_copied_and_stale_ones_are_pruned(units, tmp_path):
    """撤掉的图片不许留在产物里。

    源稿删了一张图，产物里就得没有它——不然站上会挂着一张
    「已经没有对应文章」的图片，而构建日志还在说「图片 0 张」，
    看起来一切正常。**图片跟文章走同一个规矩：撤掉的不许留在磁盘上。**
    """
    docs = tmp_path / "docs"
    (docs / "source-tracks" / "demo").mkdir(parents=True)
    (docs / "source-tracks" / "demo" / "keep.png").write_bytes(b"kept")

    images_dir = tmp_path / "site" / "source" / "images"
    stale = images_dir / "source-tracks" / "old" / "stale.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")

    posts, pages, url_map, images, kinds = build_posts.build_all()
    build_posts.write_all(posts, pages, url_map, images)

    assert (images_dir / "source-tracks" / "demo" / "keep.png").read_bytes() == b"kept"
    assert not stale.exists()
    assert not stale.parent.exists()  # 空目录也不留
