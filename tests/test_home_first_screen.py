"""首屏不该是一张风景照。

**背景**：首页的第一屏是 ``_partial/index-cover`` 渲染的一个 Materialize
carousel——首张 ``about-cover`` 铺着主题默认的模糊橙树照片，上面是打字机、
口号「技术·学习·实践·人生·哲学」和四个统计。``my.css`` 里由
``patch-theme.py`` 注入的 ``RESPONSIVE-HERO-FIX`` 段把它撑到
``min-height: calc(100vh - 64px)``。

**后果**：统计条、学习路径、三个 tab 全部落在首屏之外。一个技术博客的第一
印象是「风景摄影 + 五词口号」，爬虫和分享卡片拿到的也是那张风景照。

**这里断言的是行为契约**：

1. 首页不再渲染那个 cover carousel；
2. 新的 ``home-hero`` 排在统计条**之前**——首屏要真的有内容，
   而不是把内容推到折线以下；
3. 首屏不是全屏的（全屏 = 还是在卖风景）；
4. 首屏带的是**站点定位**（读 ``config.home_hero_lead`` 那句短话，没配
   就退回 ``config.description``），不是一句硬编码的口号；首屏也不再有一行
   重复分类清单的小标签——那 9 个徽章已经列过一遍了；
5. 首屏有三篇代表作，而且代表作清单来自 ``data/featured.json``
   （作者可维护的文件），不是硬编码在模板里的标题。

另外两条是给 ``patch-theme.py`` 的：它曾经拥有那段 hero CSS，也曾经往
hero partial 里注入统计块和打字机。hero 换掉之后，这两样都得跟着走——
CSS 要**从 my.css 里剥掉**（不能只是不再注入，留下来的死规则照样
占着 100vh），注入目标要改成新的 ``home-hero.ejs``。

放在根级 ``tests/``，随 ``site-guard.yml`` 进 CI。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
THEME = REPO / "themes" / "matery"
LAYOUT = THEME / "layout"
PARTIAL = LAYOUT / "_partial"

INDEX_EJS = LAYOUT / "index.ejs"
HOME_CONTENT = PARTIAL / "home-content.ejs"
HOME_HERO = PARTIAL / "home-hero.ejs"
MY_CSS = THEME / "source" / "css" / "my.css"
TECH_CSS = THEME / "source" / "css" / "tech.css"
LAYOUT_EJS = LAYOUT / "layout.ejs"
MAIN_STYLE = PARTIAL / "main-style.ejs"
PATCH_THEME = REPO / "tools" / "patch-theme.py"
SYNC_HEXO = REPO / "tools" / "sync-hexo.py"
FEATURED_JSON = REPO / "data" / "featured.json"


def _read(path: Path) -> str:
    assert path.is_file(), "找不到 {}".format(path)
    return path.read_text(encoding="utf-8")


# --- 1. cover carousel 不再被渲染 ------------------------------------------


def test_the_homepage_no_longer_renders_the_cover_carousel():
    """首页不再渲染 ``_partial/index-cover``。

    断言的是**调用点没了**，不是「partial 文件还在」——文件可以留在仓库里
    （主题自带的），只要没人渲染它。
    """
    index = _read(INDEX_EJS)

    assert "_partial/index-cover" not in index, (
        "index.ejs 还在渲染 index-cover —— 全屏照片首屏没去掉"
    )


def test_the_cover_carousel_css_is_gone_from_the_patched_stylesheet():
    """``my.css`` 里不再有 ``.index-cover`` 的规则。

    ``my.css`` 由 ``patch-theme.py`` 拥有。hero 换掉之后，那段
    ``RESPONSIVE-HERO-FIX`` 规则（``min-height: calc(100vh - 64px)``）
    成了死代码——但死代码还在，就说明「首屏仍然占满一屏」这件事没有真的
    被处理掉，下次有人改主题样式时它会莫名其妙地生效。
    """
    css = _read(MY_CSS)

    assert "RESPONSIVE-HERO-FIX" not in css, (
        "my.css 里还留着 RESPONSIVE-HERO-FIX 段 —— 那段规则把首屏撑到 100vh"
    )
    assert ".index-cover" not in css, "my.css 里还留着 .index-cover 规则"


# --- 2. 首屏有内容，且排在统计条之前 ---------------------------------------


def test_the_hero_comes_before_the_stats_banner():
    """``home-hero`` 必须在 ``stats-banner`` 之前。

    首屏的价值在于「上面有东西」。如果 hero 排在统计条之后，那
    访客第一眼看到的仍然是统计数字，而不是这个站是什么。
    """
    content = _read(HOME_CONTENT)

    hero_at = content.find("home-hero")
    stats_at = content.find("stats-banner")

    assert hero_at != -1, "home-content.ejs 里没有渲染 home-hero"
    assert stats_at != -1, "home-content.ejs 里没有 stats-banner（结构变了？）"
    assert hero_at < stats_at, "home-hero 必须排在 stats-banner 之前"


# --- 3. 首屏不是全屏的 ------------------------------------------------------


def test_the_hero_is_not_full_screen():
    """``home-hero`` 不能是 100vh。

    首屏全屏 = 所有内容还是在折线以下，只是把照片换了个内容。

    注释先剥掉再扫：tech.css 里写着「别用 100vh」的那句说明本身含有这个
    词，把它算成一条违规规则，就等于逼着文档不许提这件事。
    """
    assert TECH_CSS.is_file(), "找不到 themes/matery/source/css/tech.css"

    css = re.sub(r"/\*.*?\*/", "", _read(TECH_CSS), flags=re.S)

    hero_blocks = re.findall(r"\.home-hero[^{]*\{[^}]*\}", css)
    assert hero_blocks, "tech.css 里没有 .home-hero 的样式"

    for block in hero_blocks:
        assert "100vh" not in block, (
            ".home-hero 不该是 100vh —— 那样内容还是全在折线以下：{}".format(block)
        )


# --- 4. 首屏带的是站点定位 ---------------------------------------------------


def test_the_hero_carries_the_site_positioning_sentence():
    """首屏的定位句读 ``config.description``。

    ``config.description`` 现在是一句具体的技术描述（「技术学习实践，
    涵盖数据库内核（PostgreSQL/openGauss）、分布式系统、高性能网络
    （DPDK/VPP）等工程实践……」）。硬编码一句口号等于把它复制一份，
    改配置时两处会对不上。
    """
    hero = _read(HOME_HERO)

    assert "config.description" in hero, (
        "home-hero.ejs 应当读 config.description 当定位句"
    )


def test_the_hero_lead_is_a_short_sentence_and_not_the_seo_description():
    """首屏那句大标题是**短句**，不是 SEO 用的那句长描述。

    ``config.description`` 是给搜索引擎看的（九十多个字、顿号串），
    当大标题读着像关键词堆砌，占掉四行。而那行 13px 的小标签
    （「技术·学习·实践·人生·哲学」）列的又是下面 9 个徽章里的同一批东西。

    所以：短句单独放一个配置项 ``home_hero_lead``，长句留给 meta。
    """
    hero = _read(HOME_HERO)
    config = _read(REPO / "_config.yml")

    assert "config.home_hero_lead" in hero, (
        "home-hero.ejs 应当读 config.home_hero_lead 当首屏大标题"
    )
    assert "home_hero_lead:" in config, "_config.yml 里应当有 home_hero_lead 这一句"

    lead = re.search(r"^home_hero_lead:\s*(.+)$", config, re.M)
    assert lead, "_config.yml 里读不出 home_hero_lead 的值"
    value = lead.group(1).strip().strip("'\"")
    assert value, "home_hero_lead 不能是空的"
    assert len(value) <= 24, (
        "首屏大标题要是一句话，不是一段话：{}（{} 个字）".format(value, len(value))
    )


def test_the_hero_lead_falls_back_to_the_description_when_it_is_not_configured():
    """没配 ``home_hero_lead`` 时退回 ``config.description``，那一格不空着。"""
    hero = _read(HOME_HERO)

    assert re.search(r"config\.home_hero_lead\s*\|\|\s*config\.description", hero), (
        "home-hero.ejs 的 h1 应当是 config.home_hero_lead || config.description"
    )


def test_the_hero_does_not_repeat_the_category_list_as_an_eyebrow():
    """首屏不再有一行「技术·学习·实践·人生·哲学」的小标签。

    它列的就是下面那 9 个徽章里的同一批东西，留着是同一句话出现两遍。

    注释里提到 ``config.subtitle`` 不算——那是解释「为什么删了它」，
    所以先剥掉 ``<%# ... %>`` 注释块再查。
    """
    hero = re.sub(r"<%#.*?%>", "", _read(HOME_HERO), flags=re.S)

    assert "config.subtitle" not in hero, "首屏不该再有一行重复分类清单的小标签"


def test_the_built_home_page_shows_the_short_lead():
    """构建产物里，h1 是那句短句——不是 SEO 的长描述。

    对着 ``public/index.html`` 查，不是对着模板查：模板对了、产物没对，
    中间隔着的正是 sync-hexo 和 patch-theme 那两步。
    """
    built = REPO / "public" / "index.html"
    if not built.is_file():
        import pytest

        pytest.skip("还没构建（public/index.html 不存在）")

    html = built.read_text(encoding="utf-8")
    m = re.search(r'<h1 class="home-hero__lead">(.*?)</h1>', html, re.S)
    assert m, "首页的 h1 不见了"
    lead = m.group(1).strip()

    config = _read(REPO / "_config.yml")
    m2 = re.search(r"^home_hero_lead:\s*(.+)$", config, re.M)
    assert m2, "_config.yml 里没有 home_hero_lead"
    expect = m2.group(1).strip().strip("'\"")
    assert lead == expect, "首页 h1 是「{}」，配置里写的是「{}」".format(lead, expect)
    assert len(lead) <= 24, "首页 h1 太长了：{}".format(lead)
    assert "home-hero__eyebrow" not in html, "首页还有那行重复分类清单的小标签"
    assert "技术·学习·实践·人生·哲学" not in html, (
        "首页还在显示那行「技术·学习·实践·人生·哲学」"
    )


# --- 5. 三篇代表作，来自可维护的数据文件 ------------------------------------


def test_the_hero_shows_three_curated_posts_from_the_data_file():
    """首屏的三篇代表作来自 ``data/featured.json``。

    清单必须在数据文件里：作者要能改它，而不用去改模板。
    """
    assert FEATURED_JSON.is_file(), "找不到 data/featured.json"

    data = json.loads(FEATURED_JSON.read_text(encoding="utf-8"))
    hero = data.get("hero")
    assert isinstance(hero, list), "featured.json 里应当有 hero 列表"
    assert len(hero) == 3, "首屏应当有 3 篇代表作，实际 {}".format(len(hero))

    template = _read(HOME_HERO)
    assert "site.data.featured" in template or "site.data['featured']" in template, (
        "home-hero.ejs 应当读 site.data.featured 来取代表作"
    )


def test_the_hero_can_match_the_slugs_against_a_real_permalink():
    """首屏的清单匹配必须能从文章的真实 permalink 里认出那条 slug。

    文章的 ``post.path`` 形如 ``2026/08/18/db/postgresql/learning-path/
    03-query-pipeline/`` —— **没有前导斜杠**（``url_for`` 之后才有）。
    早先的正则要求有前导斜杠，于是三张卡一张都渲染不出来：构建不报错、
    页面只是少三张卡，肉眼很容易看漏。

    这里从模板里把那条正则抠出来，用真实的 permalink 形态跑一遍 ——
    两种形态（有前导斜杠 / 没有）都要能认出 slug。
    """
    template = _read(HOME_HERO)

    m = re.search(r"\.match\((/.*?/)\)", template)
    assert m, "home-hero.ejs 里找不到匹配 permalink 的正则"

    # 去掉正则字面量的首尾斜杠，JS 的转义 `\/` 在 Python 里同样成立。
    py_pattern = m.group(1)[1:-1].replace("\\/", "/")

    slug = "db/postgresql/learning-path/03-query-pipeline"
    for path in (
        "2026/08/18/{}/".format(slug),
        "/2026/08/18/{}/".format(slug),
    ):
        got = re.search(py_pattern, path)
        assert got is not None, "正则认不出 permalink：{}".format(path)
        assert got.group(1).rstrip("/") == slug, (
            "正则从 {} 里认出的不是清单里那条 slug：{}".format(path, got.group(1))
        )


def test_the_featured_entries_point_at_real_posts():
    """清单里的每一条都对应一篇真实存在的文章。

    清单是手写的，文章会改名、会删。指着一个不存在的 slug，
    首屏就少一张卡——而构建不会报错。

    对着 ``docs/`` 查，不是 ``source/_posts/``：后者是 gitignore 的构建
    产物，而 CI 的 site-guard **不跑** sync-hexo.py——在那边查，
    这条测试就成了「本地绿、CI 红」。
    """
    data = json.loads(FEATURED_JSON.read_text(encoding="utf-8"))
    docs_root = REPO / "docs"

    for group in ("hero", "featured"):
        for slug in data.get(group, []):
            assert (
                (docs_root / (slug + ".md")).is_file()
                or (docs_root / slug / "index.md").is_file()
            ), "featured.json 的 {} 指向不存在的文章：{}".format(group, slug)


def test_the_sync_copies_the_featured_file_into_the_hexo_data_dir():
    """``sync-hexo.py`` 要把 ``data/featured.json`` 复制到 ``source/_data/``。

    ``source/`` 是 gitignore 的，仓库根的 ``data/`` 才是真相；
    hexo 的 ``site.data`` 机制读的是 ``source/_data/``。少这一步，
    ``site.data.featured`` 就是 undefined，首屏一张卡都渲染不出来。
    """
    sync = _read(SYNC_HEXO)

    assert "featured.json" in sync, "sync-hexo.py 里没有提到 featured.json"
    assert re.search(r"_data", sync), "sync-hexo.py 没有写 _data 目录"


# --- 6. patch-theme.py 的两处跟着走 -----------------------------------------


def test_the_patcher_no_longer_owns_the_hero_css():
    """``patch-theme.py`` 不再注入 ``RESPONSIVE-HERO-FIX``。

    只停止注入不够：my.css 里已经有一段了（见上面那条测试）。
    两边都要管。
    """
    patcher = _read(PATCH_THEME)

    assert "RESPONSIVE-HERO-FIX" not in patcher, (
        "patch-theme.py 还在注入 RESPONSIVE-HERO-FIX —— hero 换掉了它也该退休"
    )


def test_the_patcher_strips_the_hero_css_it_used_to_inject():
    """patcher 要有「把已注入的那段从 my.css 里剥掉」的逻辑。

    只停止注入的话，仓库里的 my.css 会永远留着旧段——本地构建一次、
    CI 构建一次，两边的 my.css 就不一样了。
    """
    patcher = _read(PATCH_THEME)

    assert re.search(r"re\.sub|subn\(", patcher), "patch-theme.py 里没有替换逻辑"
    assert "my.css" in patcher, "patch-theme.py 没有动过 my.css"


def test_the_patcher_injects_the_hero_block_into_the_new_partial():
    """hero 的统计/打字机/徽章要注入到 ``home-hero.ejs``。

    以前这段是注入到 ``bg-cover-content.ejs`` / ``index-cover.ejs`` /
    ``bg-cover.ejs`` 里的。hero 换掉之后如果不改注入目标，这块内容
    就跟着消失——首页少了四个统计和那行打字机。
    """
    patcher = _read(PATCH_THEME)

    assert "home-hero.ejs" in patcher, (
        "patch-theme.py 的注入目标里没有 home-hero.ejs"
    )


def test_the_hero_stylesheet_is_linked_from_the_layout():
    """``tech.css`` 要在页面里被引进来。

    主题的 CSS 链接集中在 ``_partial/main-style.ejs``（``layout.ejs`` 只
    include 它），所以断言落在那个文件上。

    新建了 CSS 文件但没 link，页面会安静地没有样式——不报错，只是不好看。
    """
    main_style = _read(MAIN_STYLE)

    assert "tech.css" in main_style, "main-style.ejs 没有引用 tech.css"
