import json
from pathlib import Path

import pytest

from wechat.collection import (ArticleRef, Collection, build_categories,
                               build_collections, category_archive_url,
                               category_id_for, collection_digest,
                               load_spec, render_category_tag,
                               render_collection_index, render_collection_plan,
                               safe_name)
from wechat.slugs import slugize
from wechat.posts import Post, build_permalink


def _post(slug, title, categories, date="2026-11-09 15:00:00", category_ids=()):
    return Post(
        path=Path("/tmp") / (slug + ".md"),
        slug=slug,
        title=title,
        digest="摘要：" + title,
        permalink=build_permalink(slug),
        body="正文",
        categories=tuple(categories),
        date=date,
        category_ids=tuple(category_ids),
    )


# --- categories -------------------------------------------------------------


def test_build_categories_groups_posts_and_orders_by_size():
    posts = [
        _post("a", "A", ["数据库"]),
        _post("b", "B", ["数据库"]),
        _post("c", "C", ["集群"]),
    ]
    categories = build_categories(posts)
    assert list(categories) == ["数据库", "集群"]
    assert [ref.title for ref in categories["数据库"]] == ["A", "B"]


def test_build_categories_counts_a_post_under_every_category_it_has():
    posts = [_post("a", "A", ["数据库深入", "数据库"])]
    categories = build_categories(posts)
    assert set(categories) == {"数据库深入", "数据库"}
    assert categories["数据库"][0].slug == "a"


def test_build_categories_ignores_posts_without_a_category():
    posts = [_post("a", "A", [])]
    assert build_categories(posts) == {}


# --- category archive pages ------------------------------------------------


def test_category_archive_url_takes_the_category_unit_id():
    """分类归档地址按**分类内容单元 id** 算——共享规则去掉 `_index` 尾巴。"""
    url = category_archive_url("https://growdu.cn", "数据库深入/数据库/_index")
    assert url == "https://growdu.cn/docs/数据库深入/数据库/"


def test_category_archive_url_uses_the_shared_rule():
    """地址形状来自共享规则，不许在 adapter 里写死。"""
    import re
    from pathlib import Path
    text = Path(__file__).resolve().parents[2].joinpath(
        "wechat", "collection.py").read_text(encoding="utf-8")
    assert "url_rules" in text, "分类地址应该走共享规则（tools/url_rules.py）"
    assert not re.search(r"""['"]/docs/""", text), "分类地址不许写死 '/docs/'"


def test_category_id_for_finds_the_unit_id_of_a_category():
    """分类名 → 分类单元 id 的查表：名字在两个平行列表里对得上。"""
    posts = [_post("a", "A", ["数据库深入", "数据库"],
                   category_ids=["数据库深入/_index", "数据库深入/数据库/_index"])]
    assert category_id_for(posts, "数据库深入") == "数据库深入/_index"
    assert category_id_for(posts, "数据库") == "数据库深入/数据库/_index"
    assert category_id_for(posts, "没有这个分类") is None


def test_category_id_for_takes_the_shallowest_id_of_a_repeated_name():
    """同一个分类名落在两个互不为祖先的目录上 → 取**层级最浅**的那个。

    编译器只在**一篇之内**的目录链上去重，不跨篇——所以两个 id 都「对」。
    老代码（`build_category_paths`）取的是最浅的那个，这里保持同一口径。
    """
    posts = [
        _post("a", "A", ["数据库"], category_ids=["数据库深入/数据库/_index"]),
        _post("b", "B", ["数据库"], category_ids=["数据库/_index"]),
    ]
    assert category_id_for(posts, "数据库") == "数据库/_index"
    # 结果与文件顺序无关
    assert category_id_for(list(reversed(posts)), "数据库") == "数据库/_index"


def test_category_id_for_breaks_a_tie_by_the_id_itself():
    """同样深时按 id 字典序取小的——结果与文件顺序无关。"""
    posts = [
        _post("a", "A", ["数据库"], category_ids=["集群/_index"]),
        _post("b", "B", ["数据库"], category_ids=["数据库深入/_index"]),
    ]
    assert category_id_for(posts, "数据库") == "数据库深入/_index"
    assert category_id_for(list(reversed(posts)), "数据库") == "数据库深入/_index"


def test_slugize_replaces_spaces_with_dashes():
    """The adapter's own slug rule: spaces become dashes, Chinese is kept."""
    assert slugize("Go Web") == "Go-Web"
    assert slugize("PostgreSQL 源码修炼之路") == "PostgreSQL-源码修炼之路"


# --- the category tag ------------------------------------------------------


def test_render_category_tag_lists_every_category():
    html = render_category_tag(["数据库", "集群"])
    assert "数据库" in html
    assert "集群" in html


def test_render_category_tag_is_empty_without_categories():
    assert render_category_tag([]) == ""
    assert render_category_tag(()) == ""


def test_render_category_tag_carries_no_class_attribute():
    html = render_category_tag(["数据库"])
    assert "class=" not in html
    assert "<style" not in html


def test_render_category_tag_escapes_the_category_name():
    html = render_category_tag(['<script>"x"'])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --- collections -----------------------------------------------------------


def test_build_collections_derives_one_collection_per_category():
    posts = [
        _post("a", "A", ["数据库"]),
        _post("b", "B", ["数据库"]),
        _post("c", "C", ["集群"]),
    ]
    collections = build_collections(posts)
    assert [c.title for c in collections] == ["数据库"]
    assert collections[0].count == 2


def test_build_collections_skips_a_category_with_a_single_article():
    posts = [_post("a", "A", ["集群"]), _post("b", "B", ["数据库"]),
             _post("c", "C", ["数据库"])]
    collections = build_collections(posts)
    assert "集群" not in [c.title for c in collections]


def test_build_collections_honours_the_minimum_article_count():
    posts = [_post("a", "A", ["集群"]), _post("b", "B", ["集群"])]
    assert build_collections(posts, min_articles=3) == []
    assert len(build_collections(posts, min_articles=2)) == 1


def test_build_collections_carries_the_category_id():
    """合集记住的是**分类内容单元 id**，不是 hexo 归档路径。"""
    posts = [
        _post("a", "A", ["数据库深入", "数据库"],
              category_ids=["数据库深入/_index", "数据库深入/数据库/_index"]),
        _post("b", "B", ["数据库深入", "数据库"],
              category_ids=["数据库深入/_index", "数据库深入/数据库/_index"]),
    ]
    collection = build_collections(posts)[0]
    assert collection.category_id == "数据库深入/数据库/_index"
    assert collection.archive_url("https://growdu.cn") == \
        "https://growdu.cn/docs/数据库深入/数据库/"


def test_build_collections_reads_a_specification():
    posts = [
        _post("a", "A", ["数据库"], date="2026-01-01 00:00:00"),
        _post("b", "B", ["数据库"], date="2026-02-01 00:00:00"),
        _post("c", "C", ["集群"], date="2026-03-01 00:00:00"),
    ]
    spec = [{"title": "数据库精选", "description": "挑几篇",
             "categories": ["数据库"], "exclude": ["b"]}]
    collections = build_collections(posts, spec)
    assert len(collections) == 1
    assert collections[0].title == "数据库精选"
    assert collections[0].description == "挑几篇"
    assert [ref.slug for ref in collections[0].articles] == ["a"]


def test_build_collections_reads_the_category_id_from_a_specification():
    """合集配置里的键是 `category_id`——拼错就落回 fallback。

    键名写错时 `_category_id_for_chain` 的 fallback 照样给得出一个 id，
    所以这条用例专门钉住**键名**。
    """
    posts = [
        _post("a", "A", ["数据库"], date="2026-01-01 00:00:00"),
        _post("b", "B", ["数据库"], date="2026-02-01 00:00:00"),
    ]
    spec = [{"title": "数据库精选", "categories": ["数据库"],
             "category_id": "数据库/_index"}]
    collection = build_collections(posts, spec)[0]
    assert collection.category_id == "数据库/_index"
    assert collection.archive_url("https://growdu.cn") == \
        "https://growdu.cn/docs/数据库/"


def test_build_collections_adds_extra_articles_from_a_specification():
    posts = [
        _post("a", "A", ["数据库"], date="2026-01-01 00:00:00"),
        _post("b", "B", ["集群"], date="2026-02-01 00:00:00"),
    ]
    spec = [{"title": "混合", "categories": ["数据库"], "slugs": ["b"]}]
    collections = build_collections(posts, spec)
    assert [ref.slug for ref in collections[0].articles] == ["a", "b"]


def test_build_collections_orders_articles_by_date():
    posts = [
        _post("b", "B", ["数据库"], date="2026-02-01 00:00:00"),
        _post("a", "A", ["数据库"], date="2026-01-01 00:00:00"),
    ]
    collections = build_collections(posts)
    assert [ref.slug for ref in collections[0].articles] == ["a", "b"]


def test_build_collections_can_order_articles_the_other_way():
    posts = [
        _post("a", "A", ["数据库"], date="2026-01-01 00:00:00"),
        _post("b", "B", ["数据库"], date="2026-02-01 00:00:00"),
    ]
    spec = [{"title": "倒序", "categories": ["数据库"], "order": "desc"}]
    collections = build_collections(posts, spec)
    assert [ref.slug for ref in collections[0].articles] == ["b", "a"]


def test_build_collections_rejects_a_specification_with_an_unknown_article():
    posts = [_post("a", "A", ["数据库"])]
    spec = [{"title": "错的", "categories": ["数据库"], "slugs": ["nope"]}]
    with pytest.raises(ValueError) as error:
        build_collections(posts, spec)
    assert "nope" in str(error.value)


def test_build_collections_rejects_a_specification_without_a_title():
    posts = [_post("a", "A", ["数据库"])]
    with pytest.raises(ValueError):
        build_collections(posts, [{"categories": ["数据库"]}])


def test_build_collections_rejects_two_collections_with_the_same_title():
    posts = [_post("a", "A", ["数据库"])]
    spec = [{"title": "同名", "categories": ["数据库"]},
            {"title": "同名", "categories": ["数据库"]}]
    with pytest.raises(ValueError):
        build_collections(posts, spec)


# --- the specification file ------------------------------------------------


def test_load_spec_returns_nothing_when_the_file_is_absent(tmp_path):
    assert load_spec(tmp_path / "absent.json") == []


def test_load_spec_reads_the_collections(tmp_path):
    path = tmp_path / "collections.json"
    path.write_text(json.dumps({"collections": [{"title": "X"}]}), encoding="utf-8")
    assert load_spec(path) == [{"title": "X"}]


def test_load_spec_rejects_a_malformed_file(tmp_path):
    path = tmp_path / "collections.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_spec(path)


def test_load_spec_rejects_a_file_with_the_wrong_shape(tmp_path):
    path = tmp_path / "collections.json"
    path.write_text(json.dumps({"collections": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_spec(path)


# --- the index article -----------------------------------------------------


def _collection():
    return Collection(
        title="数据库",
        description="两篇数据库文章。",
        articles=(
            ArticleRef("a", "文章一", "摘要一", "/2026/01/01/a/", "2026-01-01 00:00:00"),
            ArticleRef("b", "文章二", "摘要二", "/2026/01/02/b/", "2026-01-02 00:00:00"),
        ),
        categories=("数据库",),
        category_id="数据库/_index",
    )


def test_render_collection_index_lists_every_article_with_its_url():
    html = render_collection_index(_collection(), "https://growdu.cn")
    assert "文章一" in html
    assert "文章二" in html
    assert "https://growdu.cn/2026/01/01/a/" in html
    assert "https://growdu.cn/2026/01/02/b/" in html


def test_render_collection_index_is_accepted_by_wechat():
    """No class attribute, no anchor, no script: the body has to survive."""
    html = render_collection_index(_collection(), "https://growdu.cn")
    assert "class=" not in html
    assert "<a " not in html
    assert "<script" not in html
    assert "<style" not in html


def test_render_collection_index_escapes_the_article_title():
    collection = Collection(
        title="X", description="",
        articles=(ArticleRef("a", "<b>标题</b>", "", "/2026/01/01/a/", "2026-01-01"),),
    )
    html = render_collection_index(collection, "https://growdu.cn")
    assert "<b>标题</b>" not in html
    assert "&lt;b&gt;" in html


def test_collection_digest_stays_within_the_limit():
    collection = Collection(
        title="很长的名字" * 20,
        description="简介" * 60,
        articles=(),
    )
    assert len(collection_digest(collection)) <= 120


# --- the backend checklist -------------------------------------------------


def test_render_collection_plan_lists_the_articles_in_order():
    plan = render_collection_plan(_collection(), "https://growdu.cn")
    assert "1. [ ] 文章一" in plan
    assert "2. [ ] 文章二" in plan
    assert "https://growdu.cn/2026/01/01/a/" in plan


def test_render_collection_plan_explains_the_backend_steps():
    plan = render_collection_plan(_collection(), "https://growdu.cn")
    assert "appmsgalbummgr" in plan or "合集" in plan
    assert "添加已有内容" in plan


# --- names -----------------------------------------------------------------


def test_safe_name_removes_path_separators():
    assert "/" not in safe_name("a/b")
    assert "\\" not in safe_name("a\\b")


def test_safe_name_keeps_chinese_titles_readable():
    assert safe_name("数据库深入") == "数据库深入"


def test_safe_name_never_returns_an_empty_name():
    assert safe_name("///") != ""
