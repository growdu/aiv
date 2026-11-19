"""站点配置的守卫：**框架层不许认识任何站点**。

**背景**
------
站点是一个**通用框架**：规则在框架里，身份在使用者手里。
站点的名字、简介、首页首屏、导航、页脚都在 `data/site.json`；
使用者改那一个文件，站点就是他的了。

这类「通用化」最容易烂在两处：

1. **框架里漏写死一个名字**。改配置没改全，页脚还挂着旧站名——
   这类漏最难发现，因为它编译得过去、测试也过得去。
2. **配置指向不存在的页面**。导航里写了个 `/foo/`，可没有这个页面——
   读者点进去是 404。

**这一层守的**
------------
1. 配置本身是齐的、类型对、导航项不重名。
2. **框架源码里不出现站点名**（站名从配置里读，再回头去源码里搜）。
3. 导航项指向的页面在构建产物里真的存在。
4. 模块开关与产物一致：学习流关着，就一个学习流页面都不该有。

跑法（站点模块自己的验收）::

    cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from paths import SITE, SITE_DATA

CONFIG_FILE = SITE_DATA / "site.json"
DIST = SITE / "dist"
SRC = SITE / "src"
CONTENT_DIR = SITE / "content"

#: 源码里要扫的扩展名。`src/content/` 是内容单元的副本（使用者的内容），
#: 不在扫描范围内——那里出现站名是应该的。
SCAN_SUFFIXES = (".astro", ".ts", ".mjs", ".css")

#: 框架认识的模块（站点配置里 `feature` 只能写这些）。
KNOWN_FEATURES = {"learning_path"}


@pytest.fixture(scope="module")
def config():
    if not CONFIG_FILE.exists():
        pytest.fail(f"站点配置不存在：{CONFIG_FILE}")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compiled_learning():
    path = SITE_DATA / "learning-path.compiled.json"
    if not path.exists():
        pytest.skip("学习流数据不存在（先跑 npm run compile）")
    return json.loads(path.read_text(encoding="utf-8"))


# ── 配置本身 ─────────────────────────────────────────────


def test_config_has_the_identity_fields(config):
    for key in ("name", "description", "home", "nav", "footer"):
        assert key in config, f"站点配置里缺 {key}"
    assert isinstance(config["name"], str) and config["name"].strip(), "站名不能为空"
    assert isinstance(config["description"], str) and config["description"].strip()


def test_home_fields(config):
    home = config.get("home") or {}
    for key in ("title", "lead", "sub"):
        assert isinstance(home.get(key), str), f"home.{key} 得是字符串"
    actions = home.get("actions")
    assert isinstance(actions, list), "home.actions 得是列表"
    for action in actions:
        assert action.get("label"), "首页按钮得有 label"
        assert str(action.get("href", "")).startswith("/"), "首页按钮的 href 得是站内地址"


def test_nav_keys_are_unique(config):
    keys = [item.get("key") for item in config.get("nav") or []]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"导航里有重名的 key：{dupes}"
    for item in config.get("nav") or []:
        assert item.get("label"), "导航项得有 label"
        assert str(item.get("href", "")).startswith("/"), "导航项的 href 得是站内地址"


def test_nav_features_are_known(config):
    """导航项声明的 `feature` 得是框架认识的模块——否则那项永远出不来。"""
    for item in config.get("nav") or []:
        feature = item.get("feature")
        if feature is None:
            continue
        assert feature in KNOWN_FEATURES, f"导航项 {item.get('key')} 依赖不存在的模块 {feature}"


def test_about_page_exists():
    """关于页的正文由使用者写；缺了它，页面会退到兜底，但不该悄无声息。"""
    about = CONTENT_DIR / "about.md"
    assert about.exists(), f"关于页正文不存在：{about}"
    text = about.read_text(encoding="utf-8")
    assert "title:" in text.split("---")[1] if text.startswith("---") else "title:" in text, (
        "关于页的 front matter 里得有 title"
    )


# ── 框架层不许认识站点 ───────────────────────────────────


def test_framework_source_does_not_mention_the_site(config):
    """站名只许出现在配置与使用者内容里，不许出现在框架源码里。

    **这条是「通用」这件事本身的可执行定义**：改站名不用改代码。
    """
    site_name = config["name"]
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in SCAN_SUFFIXES:
            continue
        if "content" in path.relative_to(SRC).parts:
            continue  # 内容单元的副本：使用者的内容
        text = path.read_text(encoding="utf-8", errors="ignore")
        if site_name and site_name.lower() in text.lower():
            offenders.append(str(path.relative_to(SITE)))
    assert not offenders, (
        f"框架源码里出现了站名「{site_name}」——它只该在 data/site.json 里：{offenders}"
    )


# ── 产物与配置要对得上 ───────────────────────────────────


def _dist_target(url: str) -> Path:
    path = url.split("#")[0].split("?")[0]
    candidate = DIST / path.strip("/")
    if candidate.suffix == "":
        candidate = candidate / "index.html"
    return candidate


def test_nav_targets_exist(config, compiled_learning):
    """导航里写了的地址，构建产物里得有那个页面。

    带着 `feature` 的导航项例外：那个模块关着时，这一项本来就不出现，
    对应的页面也不生成。
    """
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    learning_on = compiled_learning.get("enabled", True)
    missing = []
    for item in config.get("nav") or []:
        if item.get("feature") == "learning_path" and not learning_on:
            continue
        target = _dist_target(item["href"])
        if not target.exists():
            missing.append(f"{item['key']} → {item['href']}")
    assert not missing, "导航指向了不存在的页面：\n" + "\n".join(missing)


def test_learning_pages_match_the_module_switch(compiled_learning):
    """学习流关着 → 一个学习流页面都不生成；开着 → 总览页必须在。"""
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    enabled = compiled_learning.get("enabled", True)
    index = DIST / "learning" / "index.html"
    if enabled:
        assert index.exists(), "学习流开着，总览页却没生成"
    else:
        leftover = sorted(str(p.relative_to(DIST)) for p in (DIST / "learning").rglob("*.html"))
        assert not leftover, "学习流关着，却还有这些学习流页面：\n" + "\n".join(leftover)


def test_disabled_module_is_not_linked(compiled_learning):
    """模块关着，页面里就不该有指向它的链接（导航、首页按钮都算）。"""
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    if compiled_learning.get("enabled", True):
        pytest.skip("学习流开着，这条只管关掉的时候")
    home = DIST / "index.html"
    if not home.exists():
        pytest.skip("没有首页")
    html = home.read_text(encoding="utf-8", errors="ignore")
    assert '/learning/' not in html, "学习流关着，首页却还链着 /learning/"


def test_no_dead_links_in_the_nav_bar(config):
    """顶栏与页脚的链接都得在产物里存在（框架自己生成的，不许指向空处）。"""
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    home = DIST / "index.html"
    if not home.exists():
        pytest.skip("没有首页")
    html = home.read_text(encoding="utf-8", errors="ignore")
    hrefs = set(re.findall(r'href="(/[^"#?]*)"', html))
    dead = sorted(h for h in hrefs if not _dist_target(h).exists())
    assert not dead, f"首页上的站内链接指向不存在的页面：{dead}"
