"""渲染失败不许静悄悄：产物里不许有空页面，目录页必须列得出自己的子级。

**背景**
------
Hexo 渲染一个 layout 抛异常时，**不会让构建失败**：它记一条 ERROR，
然后把这一页写成 **0 字节的空文件**。构建照样报「N files generated」，
退出码是 0。于是「目录页不见了」这件事，在 CI 与本地都看不见——
直到有人去点那个链接。

真踩过：目录页的 layout 里写了 `(site.posts || []).concat(...)`，
而 `site.posts` 在 Hexo 里是 **Query**（warehouse 的查询对象），不是数组，
它没有 `concat`。渲染抛 TypeError → 页面 0 字节 → 目录页静悄悄地没了。
`docs/` 里没有内容时压根没有目录页，所以这个洞一直没人看见。

所以这里钉两条：

1. **产物里没有空页面**——每个 `.html` 都得有内容（症状层）。
2. **目录页列得出自己的直接子级**——症状层的第二道：
   就算页面不是空的，链接算错了也是断的（语义层）。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE
from url_shape import doc_url, is_category_id

SITE_ROOT = SITE
DIST = SITE_ROOT / "dist"


@pytest.fixture(scope="module")
def dist() -> Path:
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return DIST


def _unit_ids() -> list[str]:
    """内容单元的 id（相对 `content/units/`，不带 .md）。"""
    return [
        path.relative_to(CONTENT_UNITS).as_posix()[: -len(".md")]
        for path in sorted(CONTENT_UNITS.rglob("*.md"))
    ]


def test_no_generated_page_is_empty(dist):
    """每个生成出来的页面都得有内容。

    0 字节的 HTML 是 Hexo 渲染失败的症状——构建不失败，页面却是空的。
    """
    empty = [
        html.relative_to(dist).as_posix()
        for html in sorted(dist.rglob("*.html"))
        if html.stat().st_size == 0
    ]
    assert not empty, f"这些页面是空文件（渲染失败了）：{empty}"


def test_every_generated_page_looks_like_html(dist):
    """每个页面都得是完整的一页（有 `<html`），不是半截。"""
    broken = []
    for html in sorted(dist.rglob("*.html")):
        text = html.read_text(encoding="utf-8", errors="ignore")
        if "<html" not in text:
            broken.append(html.relative_to(dist).as_posix())
    assert not broken, f"这些页面不是完整的 HTML：{broken}"


def test_category_pages_link_to_their_direct_children(dist):
    """目录页得列得出自己这一层的入口。

    「直接子级」= 地址在本页底下、且只深一层：文章与子目录的门面都算。
    深两层的归各自的目录页管——目录是分层的，不是一口气摊平。
    """
    unit_ids = _unit_ids()
    missing: list[str] = []
    for unit_id in unit_ids:
        if not is_category_id(unit_id):
            continue
        directory = unit_id[: -len("_index")] if unit_id.endswith("_index") else unit_id
        prefix = directory + "/"
        page = dist / "docs" / directory / "index.html"
        if not page.exists():
            missing.append(f"{unit_id}（页面本身不存在）")
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        for child in unit_ids:
            if not child.startswith(prefix):
                continue
            # 只深一层：前缀后面不能再有斜杠。
            if "/" in child[len(prefix) :]:
                continue
            url = doc_url(child)
            if f'href="{url}"' not in text:
                missing.append(f"{unit_id} → {child}（{url}）")
    assert not missing, "目录页没列出自己的子级：\n  " + "\n  ".join(missing)
