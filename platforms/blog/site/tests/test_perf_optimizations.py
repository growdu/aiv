"""性能相关的几条守卫：资源本地化、重库按需加载、jQuery 同步加载。

**背景**
------
站点是**内容站**，读者多半在手机上、网不��。所以：

1. **第三方资源全部本地化**——不走 CDN。CDN 在某些网络里慢，
   而且第三方脚本随时可能改内容。
2. **重库按需加载**——prism（代码高亮）只有页面里真有代码时才加载；
   mermaid（3MB 出头）只有页面里真有 ``.mermaid`` 容器时才加载。
3. **jQuery 保持同步加载**——这是**有意的**：Materialize 的脚本在解析时
   就要用到 jQuery，给它加 ``defer`` 会在某些浏览器里炸。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from paths import SITE

SITE_ROOT = SITE
DIST = SITE_ROOT / "dist"
THEME = SITE_ROOT / "themes" / "matery"
LAYOUT = THEME / "layout"

#: 产物里不该出现的**站外资源**前缀。
#:
#: 只管**资源**（脚本、样式表、图片）：普通的链接（canonical、og、
#: 主题的版权署名）指向站外是正常的。
EXTERNAL_PREFIXES = (
    "http://",
    "https://",
    "//cdn",
    "//cdnjs",
    "//unpkg",
    "//cdnjs.cloudflare.com",
)

#: 会被当成「资源」的标签。
RESOURCE_RE = re.compile(
    r'<script[^>]+src="([^"]+)"'
    r'|<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"'
    r'|<img[^>]+src="([^"]+)"',
    re.I,
)


@pytest.fixture(scope="module")
def pages() -> list[Path]:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return sorted(DIST.rglob("*.html"))


# ── 资源本地化 ─────────────────────────────────────────────


def test_no_page_loads_a_resource_from_the_internet(pages):
    offenders = []
    for html in pages:
        text = html.read_text(encoding="utf-8", errors="ignore")
        for match in RESOURCE_RE.finditer(text):
            url = next((g for g in match.groups() if g), "")
            if url.startswith(EXTERNAL_PREFIXES):
                offenders.append(f"{html.relative_to(DIST)} → {url}")
    assert not offenders, (
        "页面里引了站外的资源（第三方资源要本地化）：\n  " + "\n  ".join(offenders)
    )


def test_the_jsdelivr_base_is_empty():
    """主题配置的 CDN 前缀是空的——空 = 从站点自己的 ``/libs/`` 出。"""
    config = (SITE_ROOT / "_config.matery.yml").read_text(encoding="utf-8")
    assert re.search(r"^jsDelivr:\s*$", config, re.M), "配置里没有 jsDelivr 这一节"
    block = config.split("jsDelivr:", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"url:\s*$", block, re.M), "jsDelivr.url 不是空的（会走 CDN）"


# ── 重库按需加载 ───────────────────────────────────────────


def test_prism_is_loaded_only_when_the_page_has_code():
    """prism 只在文章页、且页面里真有代码时才加载。"""
    layout = (LAYOUT / "layout.ejs").read_text(encoding="utf-8")
    assert "libs.js.prism" in layout, "文章页不加载 prism 了"
    assert re.search(r"is_post\(\)\s*&&\s*_hasCode", layout), (
        "prism 不再按「文章页 + 有代码」加载"
    )


def test_mermaid_is_loaded_only_when_the_page_has_a_diagram():
    """mermaid 有 3MB 出头——页面上没有图就一个字都不下载。"""
    layout = (LAYOUT / "layout.ejs").read_text(encoding="utf-8")
    assert "querySelector('.mermaid')" in layout, (
        "mermaid 不再按「页面上有 .mermaid」加载"
    )


# ── jQuery 同步加载 ───────────────────────────────────────


def test_jquery_is_loaded_synchronously():
    """jQuery 必须同步加载：Materialize 的脚本在解析时就要用它。

    给它加 ``defer`` 会在某些浏览器里炸——所以这条是钉住「有意为之」，
    不是钉住「碰巧没坏」。
    """
    head = (LAYOUT / "_partial" / "head.ejs").read_text(encoding="utf-8")
    match = re.search(r'<script[^>]*src="[^"]*jquery[^"]*"[^>]*>', head)
    assert match, "顶栏里没有加载 jQuery"
    tag = match.group(0)
    assert "defer" not in tag, "jQuery 被加上了 defer（Materialize 会炸）"
    assert "async" not in tag, "jQuery 被加上了 async（Materialize 会炸）"
