"""首页第一屏的守卫：统计条在最上，学习路径铺满，正好一屏。

**背景**
------
首页是站点的门面。作者要的效果是（blog-bak 那次「首页做减法」之后定下的）：
**第一眼看到的是「这个站有多少东西」**，接着就是几条赛道——不用往下翻
就知道这站是什么规模、从哪儿开始读。

所以首页的版面是**固定的两段**：

1. **统计条**（文章数 / 总字数 / 站龄）——在最上面；
2. **学习路径面板**（赛道卡）——铺满剩下的视口。

**不搬的东西**：hero（照片 carousel、搜索框、分类徽章、打字机）、
最新文章列表、分类标签那一排。blog-bak 那次全退休了。

**入场动画也不要**：AOS 的 fade-up 会把内容整体往下挪 100px 再淡入，
那一截让页面在动画期间比视口高出一截——滚动条闪一下，内容跳一下。
一屏的版面不要这种动画。

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


@pytest.fixture(scope="module")
def home() -> str:
    if not (DIST / "index.html").exists():
        pytest.skip("还没构建（先跑 npm run build）")
    return (DIST / "index.html").read_text(encoding="utf-8")


def test_the_stats_banner_comes_first(home):
    """统计条在最上面——读者第一眼看到的应该是「这站有多少东西」。"""
    stats = home.find('class="home-stats"')
    learning = home.find('class="learning-path"')
    assert stats != -1, "首页没有统计条"
    assert learning != -1, "首页没有学习路径面板"
    assert stats < learning, "统计条不在学习路径面板前面"


def test_the_home_page_has_exactly_one_h1(home):
    """首页只有一个 h1（站名）。两三个 h1 的页面，爬虫与分享卡片都拿不准重点。"""
    headings = re.findall(r"<h1[^>]*>", home)
    assert len(headings) == 1, f"首页有 {len(headings)} 个 h1：{headings}"


def test_the_home_page_has_no_entrance_animation(home):
    """AOS 的入场动画会让一屏的版面在动画期间高出视口一截。"""
    assert "data-aos" not in home, "首页上还有 data-aos（入场动画）"


def test_the_retired_home_hero_is_gone(home):
    """hero 那一整套（照片 carousel、搜索框、分类徽章、打字机）退休了。"""
    for marker in ("home-hero", "index-cover", "carousel", "typed", "aos-init"):
        assert marker not in home, f"首页上还有「{marker}」"


def test_the_home_page_has_no_latest_posts_section(home):
    """首页没有「最新文章」列表——它归归档页。"""
    assert "recent-posts" not in home, "首页上还有最新文章列表"


def test_the_body_carries_the_one_screen_class(home):
    """一屏的版面靠 body 上的这个类（theme 的 CSS 认它）。"""
    assert 'class="home-page"' in home, "首页的 body 上没有 home-page 这个类"
