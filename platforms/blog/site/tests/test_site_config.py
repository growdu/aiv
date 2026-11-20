"""「通用」这件事本身的守卫。

**背景**
------
站点框架是**给使用者用的**，不是一个具体站点的实现。所以框架源码里
不许出现任何一个实例身份：站名、站点地址、人设、账号。

**为什么这条最要紧**
--------------------
反目标里写着「框架里漏写死一个实例名」——这类漏**编译得过去、测试也过得去**：
页面照样出得来，只是页脚还挂着上一个站的名字。换一个使用者接手时，
那个名字会一路跟着走，直到有人想起来改。

所以它得有一条机器守着的守卫，而不是靠人记得。

**扫什么**
--------
- `themes/`（主题树）、`scripts/`（hexo 过滤器）、`tools/`（站点工具）、
  两份配置模板、`source/` 里手写的那些文件；
- 身份**不在**这些地方：它在 `data/site.json`（唯一的身份源），
  投影到 `source/_data/site.json`（生成物）与 `_config.yml`（生成物）。

**扫的是「身份文件里那个名字」，不是「某个字面量」**：把站名换成别的，
守卫照样有效——它守的是**关系**（框架里不该有身份），不是某一个人的名字。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paths import SITE

SITE_ROOT = SITE
IDENTITY_FILE = SITE_ROOT / "data" / "site.json"
THEME_DIR = SITE_ROOT / "themes"
SCRIPTS_DIR = SITE_ROOT / "scripts"
TOOLS_DIR = SITE_ROOT / "tools"
SOURCE_DIR = SITE_ROOT / "source"
DIST = SITE_ROOT / "dist"

#: 身份文件里必须有的字段。少一个就是身份没写全——报错，不猜。
REQUIRED_KEYS = ("name", "tagline", "description", "start_date", "nav", "footer")

#: 扫的时候跳过的目录与文件。
SKIP_DIRS = {"node_modules", "dist", "_data", "_posts", "images", "lib", "learning", "about"}
SKIP_FILES = {"site.json"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot"}

#: 这两个文件**本来就是身份的投影**（`tools/apply-site-config.py` 生成的）：
#: robots.txt 里的 sitemap 地址、manifest 里的站名与简介，都是身份派生的。
#: 它们是生成物（不入库），身份就在那儿是对的。
SKIP_PATHS = {"source/robots.txt", "source/manifest.json"}


@pytest.fixture(scope="module")
def identity() -> dict:
    if not IDENTITY_FILE.exists():
        pytest.skip("身份文件不存在")
    return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))


def _framework_files() -> list[Path]:
    """框架源码里的所有文本文件。"""
    roots = [
        THEME_DIR,
        SCRIPTS_DIR,
        TOOLS_DIR,
        SOURCE_DIR,
    ]
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name in SKIP_FILES or path.suffix.lower() in SKIP_SUFFIXES:
                continue
            if str(path.relative_to(SITE_ROOT)) in SKIP_PATHS:
                continue
            out.append(path)
    return out


# ── 身份文件本身 ───────────────────────────────────────────


def test_identity_has_all_required_fields(identity):
    missing = [key for key in REQUIRED_KEYS if key not in identity]
    assert not missing, f"身份文件缺字段：{'、'.join(missing)}"


def test_nav_keys_are_unique(identity):
    keys = [item.get("key") for item in identity.get("nav") or []]
    assert len(keys) == len(set(keys)), f"导航项的 key 重复：{keys}"


def test_every_nav_item_has_a_label_and_a_href(identity):
    for item in identity.get("nav") or []:
        assert item.get("label"), f"导航项缺 label：{item}"
        assert item.get("href"), f"导航项缺 href：{item}"


# ── 框架里不许有实例身份 ───────────────────────────────────


def test_the_site_name_appears_nowhere_in_the_framework(identity):
    """站名（还有站点地址）不许出现在框架源码里。"""
    name = str(identity.get("name") or "")
    url = str(identity.get("url") or "")
    needles = [n for n in (name, url) if n]

    assert needles, "身份文件里没有站名，守卫就没东西可守"

    hits: list[str] = []
    for path in _framework_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for needle in needles:
            if needle in text:
                hits.append(f"{path.relative_to(SITE_ROOT)}：写着「{needle}」")

    assert not hits, (
        "框架源码里出现了实例身份（框架是给使用者用的，身份只该在 "
        "data/site.json 里）：\n  " + "\n  ".join(hits)
    )


def test_identity_lives_in_exactly_one_place():
    """身份只该有一份源：`data/site.json`。"""
    sources = [
        path
        for path in SITE_ROOT.rglob("site.json")
        if path.is_file()
        and "node_modules" not in path.parts
        and path.name == "site.json"
    ]
    relative = {str(path.relative_to(SITE_ROOT)) for path in sources}
    # `source/_data/site.json` 是投影（生成物），`data/site.json` 才是源。
    allowed = {"data/site.json", "source/_data/site.json"}
    assert relative <= allowed, f"身份文件多了一份：{relative - allowed}"


# ── 导航指向的页面真的存在 ─────────────────────────────────


def _dist_path(href: str) -> Path:
    """站内地址 → 产物里的文件。"""
    clean = href.split("#")[0].split("?")[0]
    if clean.endswith("/"):
        return DIST / clean.lstrip("/") / "index.html"
    return DIST / clean.lstrip("/")


@pytest.mark.skipif(not DIST.exists(), reason="还没构建（先跑 npm run build）")
def test_every_nav_target_exists_in_the_build(identity):
    missing = []
    for item in identity.get("nav") or []:
        href = str(item.get("href") or "")
        if not href.startswith("/"):
            continue
        target = _dist_path(href)
        if not target.exists():
            missing.append(f"{item.get('label')} → {href}")
    assert not missing, "导航指着不存在的页面：\n  " + "\n  ".join(missing)


@pytest.mark.skipif(not DIST.exists(), reason="还没构建（先跑 npm run build）")
def test_the_home_page_exists():
    assert (DIST / "index.html").exists(), "首页不在产物里"
