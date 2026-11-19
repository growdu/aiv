"""构建产物的守卫：每个单元都有页面，站内没有死链。

**背景**
------
站点是静态产物——链接错了不会报错，只会让读者点到一个 404。
这个测试把构建产物爬一遍：把每个 HTML 里的站内链接都取出来，
挨个核对目标文件在不在。

**它守的两条**
--------
1. 每个内容单元都有对应的页面（内容上了站，却在导航里找不到，比 404 更糟）。
2. 站内链接不指向不存在的页面。

**跑法**（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q

没构建过就跳过——这个测试要的是产物，不是源码。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from paths import CONTENT_UNITS, SITE

DIST = SITE / "dist"

HREF = re.compile(r'href="(/[^"#?]*)"')


def _unit_ids() -> list[tuple[str, str]]:
    """(kind, id) 列表，id 是相对 content/units/ 的路径（不带 .md）。"""
    out = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        unit_id = rel.removesuffix(".md")
        if unit_id.endswith("/_index") or unit_id == "_index":
            kind = "category"
        else:
            kind = _front_matter_kind(path)
        out.append((kind, unit_id))
    return out


def _front_matter_kind(path: Path) -> str:
    """从 front matter 里读 kind（读不到就按文档算）。"""
    head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    match = re.search(r"^kind:\s*(\S+)\s*$", head, re.M)
    return match.group(1).strip("\"'") if match else "document"


def _url_for(kind: str, unit_id: str) -> str:
    """单元 → 站上地址（与 src/lib/urls.ts 同一套规则）。"""
    if kind == "video":
        return f"/videos/{unit_id.removeprefix('video/')}/"
    if kind == "category":
        return "/docs/" + unit_id.removesuffix("/_index") + "/"
    return f"/docs/{unit_id}/"


def _target_of(url: str) -> Path | None:
    """站内地址 → dist 里的文件（找不到就返回 None）。"""
    path = unquote(urlsplit(url).path)
    if path == "/":
        return DIST / "index.html"
    candidate = DIST / path.lstrip("/")
    if candidate.is_dir():
        return candidate / "index.html"
    if candidate.suffix == "":
        return candidate / "index.html"
    return candidate


@pytest.fixture(scope="module")
def dist_pages() -> list[Path]:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return sorted(DIST.rglob("*.html"))


def test_every_unit_has_a_page(dist_pages):
    missing = []
    for kind, unit_id in _unit_ids():
        url = _url_for(kind, unit_id)
        target = _target_of(url)
        if target is None or not target.exists():
            missing.append(f"{kind}:{unit_id} → {url}")
    assert not missing, "这些内容单元没有对应页面：\n" + "\n".join(missing)


def test_video_units_have_a_page(dist_pages):
    """视频单元走 /videos/<slug>/，跟文档不是一个前缀。"""
    videos = [uid for kind, uid in _unit_ids() if kind == "document" and uid.startswith("video/")]
    missing = []
    for unit_id in videos:
        url = _url_for("video", unit_id)
        target = _target_of(url)
        if target is None or not target.exists():
            missing.append(url)
    assert not missing, "这些视频没有页面：\n" + "\n".join(missing)


def test_no_dead_internal_links(dist_pages):
    dead: dict[str, set[str]] = {}
    for page in dist_pages:
        html = page.read_text(encoding="utf-8", errors="ignore")
        for href in HREF.findall(html):
            if href.startswith("/_astro/") or href.startswith("/js/") or href.startswith("/images/"):
                continue  # 构建产物与静态资源，另有其责
            target = _target_of(href)
            if target is None or not target.exists():
                dead.setdefault(href, set()).add(str(page.relative_to(DIST)))
    assert not dead, "这些站内链接指向不存在的页面：\n" + "\n".join(
        f"{url}  ←  {', '.join(sorted(pages))}" for url, pages in sorted(dead.items())
    )
