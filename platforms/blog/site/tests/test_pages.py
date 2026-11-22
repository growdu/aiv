"""产物这一层的守卫：每个内容单元都有页面，站内没有死链。

**背景**
------
站点是**全量构建**的：一次构建，整站重新生成。所以「某一篇没生成出来」
这种事不会在运行期报错——它只是**悄悄不见了**。链接重写器还会把母稿里的
相对链接换成站上的地址，换对了是好事，换错了就是一个 404。

所以这两条得有人守着：

1. **每个内容单元都有一个页面**（文档 `/docs/<id>/`、目录页 `/docs/<目录>/`）；
2. **站内没有死链**——产物里每一个站内地址都真的存在。

**站上没有视频页**（作者拍板）：视频单元的地址（`/videos/<slug>/`）在
地址表里，但站内不生成那些页面。正文里指向视频的链接因此是站内死链——
这一条是**已知的后果**，不是错误：那些地址归发布层落地。
所以死链检查跳过 `/videos/`。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE
from url_shape import is_category_id

SITE_ROOT = SITE
DIST = SITE_ROOT / "dist"

#: 产物里取地址的地方。
LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')

#: 站内不生成的地址前缀：视频页由发布层落地。
DEAD_LINK_EXEMPT_PREFIXES = ("/videos/",)


@pytest.fixture(scope="module")
def dist() -> Path:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return DIST


def _unit_kinds() -> list[tuple[str, str]]:
    """内容单元 → [(单元 id, kind)]。"""
    out = []
    for path in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = path.relative_to(CONTENT_UNITS).as_posix()
        unit_id = rel.removesuffix(".md")
        if is_category_id(unit_id):
            kind = "category"
        else:
            kind = _front_matter_kind(path)
        out.append((unit_id, kind))
    return out


def _dist_target(dist: Path, url: str) -> Path:
    """站内地址 → 产物里的文件。"""
    clean = url.split("#")[0].split("?")[0]
    target = dist / clean.lstrip("/")
    if clean.endswith("/"):
        target = target / "index.html"
    elif target.is_dir():
        target = target / "index.html"
    return target


def _front_matter_kind(path: Path) -> str:
    """从 front matter 里读 kind（读不到就按文档算）。"""
    head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    match = re.search(r"^kind:\s*(\S+)\s*$", head, re.M)
    return match.group(1).strip("\"'") if match else "document"


# ── 每个内容单元都有页面 ───────────────────────────────────


def test_every_document_unit_has_a_page(dist):
    missing = []
    for unit_id, kind in _unit_kinds():
        if kind != "document":
            continue
        target = dist / "docs" / unit_id / "index.html"
        if not target.exists():
            missing.append(unit_id)
    assert not missing, f"这些内容单元没有页面：{missing}"


def test_every_category_unit_has_a_page(dist):
    missing = []
    for unit_id, kind in _unit_kinds():
        if kind != "category":
            continue
        directory = unit_id[: -len("_index")] if unit_id.endswith("_index") else unit_id
        target = dist / "docs" / directory / "index.html"
        if not target.exists():
            missing.append(unit_id)
    assert not missing, f"这些目录单元没有页面：{missing}"


def test_the_site_has_no_video_pages(dist):
    """站上没有视频页（作者拍板）。"""
    assert not (dist / "videos").exists(), "站上不该有视频页"


# ── 站内没有死链 ───────────────────────────────────────────


def test_there_are_no_dead_internal_links(dist):
    dead: list[str] = []
    for html in sorted(dist.rglob("*.html")):
        text = html.read_text(encoding="utf-8", errors="ignore")
        for match in LINK_RE.finditer(text):
            url = match.group(1)
            if not url.startswith("/") or url.startswith("//"):
                continue
            clean = url.split("#")[0].split("?")[0]
            if not clean:
                continue
            if clean.startswith(DEAD_LINK_EXEMPT_PREFIXES):
                continue
            if not _dist_target(dist, clean).exists():
                dead.append(f"{html.relative_to(dist)} → {url}")

    assert not dead, "站内死链：\n  " + "\n  ".join(sorted(set(dead)))


def test_the_fixed_pages_exist(dist):
    """导航与规范里写死的那几个页面，一个都不能少。"""
    for rel in (
        "index.html",
        "archives/index.html",
        "about/index.html",
        "all/index.html",
        "404.html",
    ):
        assert (dist / rel).exists(), f"{rel} 不在产物里"
