"""URL 级重定向机制的守卫。

**这张表是什么**：键是旧地址，值是新地址。赛道改名、文章搬家之后，
旧地址不会自己消失——这张表是「旧地址搬去哪儿了」的**唯一真相**。

**为什么要有守卫**：站点对未知路径返回 **HTTP 200 + 首页**，
所以「旧 URL 有跳转」这件事**不会靠 404 暴露**。写错一条（少了斜杠、
指回自己、盖掉一个还活着的页面），从外面看站点照常跑，只有点那个旧链接
的人会发现不对。

四条规矩，各有一条用例盯着：

1. 两端都是站内完整路径（以 `/` 开头、以 `/` 结尾）；
2. 旧地址不许还挂着一个活着的页面——**那不是跳转，是自相矛盾**；
3. 跳转页必须带**显式** ``permalink:``（hexo 对页面也认这个字段，
   少了它页面就落在它在 ``source/`` 里的位置，旧地址上什么都不会有）；
4. 表里删掉的条目，产物里不许留残留。
"""
import json
import subprocess
from pathlib import Path

import pytest

from conftest import load_tool
from url_shape import unit_url

REPO_ROOT = Path(__file__).resolve().parents[4]
SITE = REPO_ROOT / "platforms/blog/site"
TABLE = SITE / "data" / "url-redirects.json"
CONTENT_UNITS = REPO_ROOT / "content" / "units"
LEARNING_RULES = SITE / "data" / "learning-path.json"

build_posts = load_tool("build-posts.py")


# --- 表本身 ----------------------------------------------------------------


def test_the_redirect_table_exists_and_is_a_mapping():
    """表得在，而且得是个对象——键是旧地址，值是新地址。"""
    assert TABLE.is_file(), f"重定向表不在：{TABLE}"
    data = json.loads(TABLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_the_redirect_table_is_tracked_by_git():
    """它是一份真相，不是构建产物——构建产物在 `source/redirects/` 里。"""
    out = subprocess.run(
        ["git", "ls-files", "--error-unmatch",
         "platforms/blog/site/data/url-redirects.json"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "重定向表必须入库"


def test_both_ends_are_complete_site_paths():
    """两端都以 `/` 开头、以 `/` 结尾。

    少一个斜杠的后果很具体：`/learning/postgresql` 会被当成**文件**
    而不是目录，服务器少一个尾斜杠就 301 过去——多一次跳转。
    """
    for old_url, new_url in json.loads(TABLE.read_text(encoding="utf-8")).items():
        assert old_url.startswith("/") and old_url.endswith("/"), old_url
        assert new_url.startswith("/") and new_url.endswith("/"), new_url


def test_a_url_never_redirects_to_itself():
    for old_url, new_url in json.loads(TABLE.read_text(encoding="utf-8")).items():
        assert old_url != new_url, old_url


# --- 活着的地址 ------------------------------------------------------------


def _live_urls() -> set[str]:
    """站上现在**有页面**的地址集合。

    三处：文章与目录页（从内容单元算）、学习流页（从规则表算）、
    以及那两个手写的页面（关于页与归档页）。
    """
    live = {"/about/", "/all/"}
    if CONTENT_UNITS.is_dir():
        for path in sorted(CONTENT_UNITS.rglob("*.md")):
            unit_id = path.relative_to(CONTENT_UNITS).as_posix()[: -len(".md")]
            head = path.read_text(encoding="utf-8").split("---")
            kind = "document"
            if len(head) > 2:
                for line in head[1].splitlines():
                    if line.strip().startswith("kind:"):
                        kind = line.split(":", 1)[1].strip()
            if kind == "video":
                continue  # 视频单元不进站点，站上没有它的页面
            live.add(unit_url(unit_id, kind))
    if LEARNING_RULES.is_file():
        rules = json.loads(LEARNING_RULES.read_text(encoding="utf-8"))
        live.add("/learning/")
        for track in rules.get("tracks", []):
            live.add(f"/learning/{track['id']}/")
    return live


def test_a_redirect_must_not_target_a_url_that_is_still_alive():
    """**旧地址必须已经是空的**。

    一个还活着的地址上再放一个跳转页，hexo 会让两个页面抢同一个路由——
    后写的赢，而先写的那个**静悄悄地不见了**。这不是「跳转失效」，
    是「一个页面凭空消失」。
    """
    live = _live_urls()
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    for old_url in table:
        assert old_url not in live, (
            f"{old_url} 上还有活着的页面——这条跳转会盖掉它。"
            f"先把那个页面搬走，再加这条。"
        )


# --- 跳转页 ----------------------------------------------------------------


def _page(old_url: str, new_url: str) -> str:
    return build_posts.redirect_page(old_url, new_url)


def _front_matter(text: str) -> dict:
    assert text.startswith("---\n")
    end = text.index("\n---", 3)
    import yaml
    return yaml.safe_load(text[3:end])


def test_a_redirect_page_carries_an_explicit_permalink():
    """**显式 permalink 是必须的**。

    hexo 的页面处理（``processor/asset.js``）把 ``data.permalink`` 直接
    当成页面地址；少了它，页面就落在它在 ``source/`` 里的位置，
    旧地址上什么都不会有——而且**不报错**，只是那个地址没有跳转。
    """
    fm = _front_matter(_page("/learning/old-track/", "/learning/new-track/"))
    assert fm["permalink"] == "/learning/old-track/"


def test_a_redirect_page_points_at_the_new_url():
    text = _page("/learning/old-track/", "/learning/new-track/")
    assert '<meta http-equiv="refresh" content="0; url=/learning/new-track/">' in text
    # 兜底：meta refresh 被浏览器策略挡掉时，页面上还有一个能点的链接。
    assert '<a href="/learning/new-track/">' in text


def test_a_redirect_page_is_not_in_the_sitemap():
    """旧地址不该被当成「站上有的内容」告诉搜索引擎。"""
    fm = _front_matter(_page("/learning/old-track/", "/learning/new-track/"))
    assert fm["sitemap"] is False


def test_a_redirect_page_does_not_wear_the_site_chrome():
    """跳转页是给浏览器读的，不要套主题的框。"""
    fm = _front_matter(_page("/learning/old-track/", "/learning/new-track/"))
    assert fm["layout"] is False


# --- 形状不对的表：当场报错 --------------------------------------------------


@pytest.mark.parametrize("table", [
    {"/learning/old-track": "/learning/new-track/"},     # 旧地址少尾斜杠
    {"/learning/old-track/": "/learning/new-track"},      # 新地址少尾斜杠
    {"learning/old-track/": "/learning/new-track/"},      # 旧地址少首斜杠
    {"/learning/old-track/": "/learning/old-track/"},     # 指回自己
    {"/": "/learning/new-track/"},                        # 旧地址是站点根
])
def test_a_malformed_table_is_refused_loudly(table):
    """一份写坏的重定向表 = 旧地址没人接 = 链接悄悄 404。

    这比构建失败更坏——构建失败会有人看见。所以**当场报错**，
    不悄悄跳过那一条。
    """
    with pytest.raises(ValueError):
        build_posts.redirect_pages(table)


# --- 写盘与清理 ------------------------------------------------------------


def test_writing_the_pages_puts_them_under_the_redirect_directory(tmp_path, monkeypatch):
    """跳转页落一个专门的目录——整目录是构建产物，一条忽略规则就够。"""
    monkeypatch.setattr(build_posts, "REDIRECT_DIR", tmp_path / "redirects")
    count = build_posts.write_url_redirects(
        {"/learning/old-track/": "/learning/new-track/"})
    assert count == 1
    written = tmp_path / "redirects" / "learning" / "old-track" / "index.md"
    assert written.is_file()
    assert "url=/learning/new-track/" in written.read_text(encoding="utf-8")


def test_a_stale_redirect_page_is_removed(tmp_path, monkeypatch):
    """表里删掉的条目，产物里不许留残留（跟文章同一个道理）。"""
    monkeypatch.setattr(build_posts, "REDIRECT_DIR", tmp_path / "redirects")
    build_posts.write_url_redirects(
        {"/learning/old-track/": "/learning/new-track/",
         "/learning/older-track/": "/learning/new-track/"})
    build_posts.write_url_redirects(
        {"/learning/old-track/": "/learning/new-track/"})
    assert not (tmp_path / "redirects" / "learning" / "older-track").exists()
    assert (tmp_path / "redirects" / "learning" / "old-track" / "index.md").is_file()


def test_the_check_mode_notices_a_stale_page(tmp_path, monkeypatch):
    monkeypatch.setattr(build_posts, "REDIRECT_DIR", tmp_path / "redirects")
    build_posts.write_url_redirects({"/learning/old-track/": "/learning/new-track/"})
    build_posts.write_url_redirects({})
    problems = build_posts.check_url_redirects({"/learning/old-track/": "/learning/new-track/"})
    assert any("older" in p or "old-track" in p for p in problems)


# --- 产物不入库 ------------------------------------------------------------


def test_the_redirect_pages_are_not_tracked_by_git():
    """跳转页是构建产物——它们由那张表编出来，不许进 git。

    进 git 就有两份真相：表改了、页面忘了改，站点照旧跳到旧地方，
    而 git 里看不出任何差别。
    """
    out = subprocess.run(
        ["git", "check-ignore", "-q",
         "platforms/blog/site/source/redirects/learning/old-track/index.md"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "跳转页的落点必须在 .gitignore 里"
