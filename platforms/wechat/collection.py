"""Category tags and collection (合集) plans.

WeChat's open API cannot create a 分类 or a 合集, and the limitation is
structural rather than a missing feature in this pipeline:

- ``draft/add`` has no category or album field.  The article payload
  offers exactly one place for a classification, and that place is the
  body text.
- ``api.weixin.qq.com`` exposes no endpoint for either.  Every
  plausible path probed against a live account answered "invalid url"
  or with an empty body.
- The page that manages 合集 lives at
  ``mp.weixin.qq.com/cgi-bin/appmsgalbummgr``.  That is a
  cookie-authenticated web route with a per-session token, not an
  ``access_token`` endpoint, and it may only hold *published* articles
  -- a draft cannot be added to a 合集.

So the platform-side relation is a human step, and this module
automates the content around it: the category tag printed on an
article, the ordered plan of articles that belong to a collection, and
the index article that leads into one.

**分类归档页的地址现在指向站点上真实存在的页面。**

``category_archive_url()`` 拼出来的是 ``{站点}/docs/<分类内容单元 id>/``——
站点现在的规则是文档页与分类页都走这一条（分类页的 id 尾巴带
``_index``，地址里那个尾巴被抹掉）。

**地址形状不在本模块写死**：全仓库只有一份规则（仓库根的
``rules/urls.json``），它的读取器是根 ``tools/url_rules.py`` 的
``doc_url()``——本模块按文件读那份规则，不自己拼前缀。

**分类名 → 分类内容单元 id 的映射来自内容编译器**：编译器
（``tools/build-content-units.py``）把每个分类名对应的那个分类内容单元 id
写进每篇稿子的 front matter（``category_ids``，与 ``categories``
**同序、同长**的两个平行列表），adapter 从那儿查。
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .render import BODY_FONT, H2_STYLE, MUTED_STYLE, css

# 共享 URL 规则住在仓库根的 tools/ 下（读取器 `url_rules.py`，规则
# `rules/urls.json`）。本模块按**文件**读它——模块之间不互相 import。
# platforms/wechat/collection.py → parents[0]=wechat、parents[1]=platforms、
# parents[2]=仓库根。
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from url_rules import doc_url  # noqa: E402

__all__ = [
    "ArticleRef",
    "Collection",
    "build_categories",
    "build_collections",
    "category_archive_url",
    "category_id_for",
    "collection_digest",
    "load_spec",
    "render_category_tag",
    "render_collection_index",
    "render_collection_plan",
    "safe_name",
]

CATEGORY_TAG_STYLE = css("font-size: 13px", "color: #888", "margin: 0 0 18px")
CATEGORY_NAME_STYLE = css("color: #3d7ea6", "font-weight: 700")
COLLECTION_ITEM_STYLE = css("margin: 0 0 14px", "padding: 0 0 12px",
                            "border-bottom: 1px solid #eef0f2")
COLLECTION_TITLE_STYLE = css("font-size: 15px", "font-weight: 700", "margin: 0 0 4px")
COLLECTION_META_STYLE = css("font-size: 12px", "color: #999", "margin: 0")
COLLECTION_LINK_STYLE = css("font-size: 12px", "color: #888", "margin: 4px 0 0",
                             "word-break: break-all")

_UNSAFE_NAME_RE = re.compile(r"[\\/:*?\"<>|]+")


@dataclass(frozen=True)
class ArticleRef:
    """One article as it appears in a category list or a collection."""

    slug: str
    title: str
    digest: str
    permalink: str
    date: str

    @property
    def label(self) -> str:
        """The date as it should be printed: ``2026-01-02``."""
        return self.date[:10]


@dataclass(frozen=True)
class Collection:
    """A named group of articles, ready to become a WeChat 合集."""

    title: str
    description: str
    articles: tuple
    categories: tuple = ()
    category_id: str = ""

    @property
    def slug(self) -> str:
        """A filesystem-safe identifier for this collection."""
        return safe_name(self.title)

    @property
    def count(self) -> int:
        return len(self.articles)

    def archive_url(self, source_url: str) -> str:
        """The page that lists this collection's articles.

        A collection that maps to a single category points at that
        category's archive page on the blog.  A curated collection
        spans several categories and has no such page, so it points at
        the blog's home page instead.
        """
        if self.category_id:
            return category_archive_url(source_url, self.category_id)
        return source_url.rstrip("/") + "/"


def safe_name(title: str) -> str:
    """Turn a collection title into a name that is safe on disk and in a URL.

    Chinese titles stay as they are -- the filesystem and the blog both
    handle UTF-8 -- but path separators and the characters Windows
    rejects have to go, or the output directory cannot be created.
    """
    cleaned = _UNSAFE_NAME_RE.sub("-", title).strip().strip(".")
    return cleaned or "collection"


def _ref(post) -> ArticleRef:
    return ArticleRef(
        slug=post.slug,
        title=post.title,
        digest=post.digest,
        permalink=post.permalink,
        date=post.date,
    )


def build_categories(posts) -> dict:
    """Group the posts by their front-matter category.

    Ordered by size, largest first, so the tag printed on an article
    leads with the category that actually describes it.
    """
    buckets = {}
    for post in posts:
        ref = _ref(post)
        for name in post.categories:
            buckets.setdefault(name, []).append(ref)
    ordered = sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))
    return {name: tuple(items) for name, items in ordered}


def category_archive_url(source_url: str, category_id: str) -> str:
    """The blog's own archive page for a category.

    The category is identified by the id of its **content unit** -- the
    one the compiler writes into the front matter as ``category_ids``.
    The address itself comes from the shared URL rule, so the shape
    lives in exactly one place in the repository.
    """
    return source_url.rstrip("/") + doc_url(category_id)


def _id_order(category_id: str) -> tuple:
    """候选分类单元 id 的排序键：层级最浅的在前，同深度按字典序。

    段数 = id 里的斜杠数 + 1（分类页的 id 尾巴都带 ``_index``），
    所以斜杠少的那个就是层级浅的那个。
    """
    return (category_id.count("/"), category_id)


def category_id_for(posts, name: str) -> str | None:
    """分类名 → 分类内容单元 id。找不到返回 None。

    同一个分类名可能落在两个**互不为祖先**的目录上：编译器只在**一篇之内**
    的目录链上去重（``if name not in categories`` 守的是这一篇自己的链），
    不跨篇——于是两个 id 都「对」。取**层级最浅**的那个（**规则本身**：与老代码
    ``build_category_paths`` 同一口径——不是「哪个页面列出文章最多」的推论），
    同深度时按 id 字典序取小的：**结果与文件顺序无关**。
    """
    candidates = []
    for post in posts:
        ids = post.category_ids
        for index, category in enumerate(post.categories):
            if category == name and index < len(ids):
                candidates.append(ids[index])
    if not candidates:
        return None
    return min(candidates, key=_id_order)


def load_spec(path: Path) -> list:
    """Read the optional collection specification.

    The file is optional: without it the collections are derived from
    the front-matter categories.  A malformed file is an error rather
    than a fallback -- the user wrote it on purpose, and silently
    publishing different groups would be worse than refusing to start.
    """
    path = Path(path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("合集配置读取失败: {} ({})".format(path, error)) from error
    if not isinstance(data, dict) or not isinstance(data.get("collections"), list):
        raise ValueError('合集配置格式错误: 需要 {"collections": [...]} 的 JSON 对象')
    return data["collections"]


def build_collections(posts, spec=None, min_articles: int = 2) -> list:
    """Build the collections.

    With a specification the collections are exactly what it says.
    Without one, every category holding at least ``min_articles``
    articles becomes a collection: a category with a single article is
    a tag, not a series.
    """
    if spec:
        return _collections_from_spec(posts, spec)
    return _collections_from_categories(posts, min_articles)


def _collections_from_categories(posts, min_articles: int) -> list:
    collections = []
    for name, refs in build_categories(posts).items():
        if len(refs) < min_articles:
            continue
        # Chronological order: a 合集 is read in sequence, so the
        # articles have to be lined up by date, not by file path.
        ordered = tuple(sorted(refs, key=lambda ref: (ref.date, ref.slug)))
        collections.append(Collection(
            title=name,
            description="「{}」分类下的 {} 篇文章。".format(name, len(refs)),
            articles=ordered,
            categories=(name,),
            category_id=category_id_for(posts, name) or "",
        ))
    return collections


def _collections_from_spec(posts, spec) -> list:
    by_slug = {post.slug: post for post in posts}
    categories_of = {post.slug: set(post.categories) for post in posts}
    collections = []
    seen_titles = set()

    for entry in spec:
        if not isinstance(entry, dict):
            raise ValueError("合集配置项必须是对象: {!r}".format(entry))

        title = str(entry.get("title") or "").strip()
        if not title:
            raise ValueError("合集配置项缺少 title")
        if title in seen_titles:
            raise ValueError("合集标题重复: {}".format(title))
        seen_titles.add(title)

        wanted = {str(name) for name in entry.get("categories", [])}
        extra = [str(slug) for slug in entry.get("slugs", [])]
        exclude = {str(slug) for slug in entry.get("exclude", [])}

        unknown = [slug for slug in extra if slug not in by_slug]
        if unknown:
            raise ValueError("合集「{}」引用了不存在的文章: {}".format(
                title, ", ".join(unknown)))

        selected = {}
        for post in posts:
            if post.slug in exclude:
                continue
            if wanted & categories_of[post.slug]:
                selected[post.slug] = _ref(post)
        for slug in extra:
            if slug not in exclude:
                selected[slug] = _ref(by_slug[slug])

        articles = sorted(selected.values(), key=lambda ref: (ref.date, ref.slug))
        if str(entry.get("order", "asc")).lower() == "desc":
            articles = list(reversed(articles))

        category_id = str(entry.get("category_id") or "").strip()
        if not category_id:
            category_id = _category_id_for_chain(posts, wanted, selected)

        collections.append(Collection(
            title=title,
            description=str(entry.get("description") or ""),
            articles=tuple(articles),
            categories=tuple(sorted(wanted)),
            category_id=category_id,
        ))

    return collections


def _category_id_for_chain(posts, wanted, selected) -> str:
    """The category unit id of a curated collection.

    The collection has no page of its own, so it borrows the one of the
    first category it covers: the unit id of that category in the
    first article that carries it.
    """
    chosen = set(selected)
    for post in posts:
        if post.slug not in chosen:
            continue
        ids = post.category_ids
        for index, category in enumerate(post.categories):
            if category in wanted and index < len(ids):
                return ids[index]
    return ""


def render_category_tag(categories) -> str:
    """Render the category line printed above an article.

    The names are plain text on purpose: WeChat strips anchors from the
    body, so a link to the category archive would not survive the
    sanitiser.  The reader gets the 「阅读原文」 link instead.
    """
    names = [str(name) for name in categories if name]
    if not names:
        return ""
    tags = " · ".join(
        '<span style="%s">%s</span>' % (CATEGORY_NAME_STYLE, html_lib.escape(name))
        for name in names
    )
    return '<p style="%s">分类 · %s</p>' % (CATEGORY_TAG_STYLE, tags)


def collection_digest(collection: Collection) -> str:
    """The summary of the index article, capped at WeChat's 120 characters."""
    text = "「{}」合集目录，共 {} 篇文章。".format(collection.title, collection.count)
    if collection.description:
        text += collection.description
    return text[:120]


def render_collection_index(collection: Collection, source_url: str) -> str:
    """Render the index article that leads into a collection.

    The article links are printed as text, not as anchors: WeChat
    removes anchors that point outside the account, so a clickable link
    to an article is not available.  The one link that survives is
    「阅读原文」, which the publisher points at the blog's own category
    archive.
    """
    root = source_url.rstrip("/")
    parts = []

    if collection.description:
        parts.append('<p style="%s">%s</p>' % (
            BODY_FONT, html_lib.escape(collection.description)))
    parts.append('<p style="%s">共 %d 篇，按发布时间排列。</p>' % (
        MUTED_STYLE, collection.count))

    for index, ref in enumerate(collection.articles, 1):
        parts.append((
            '<section style="%s">'
            '<p style="%s">%d. %s</p>'
            '<p style="%s">%s</p>'
            '<p style="%s">%s</p>'
            '</section>'
        ) % (
            COLLECTION_ITEM_STYLE,
            COLLECTION_TITLE_STYLE, index, html_lib.escape(ref.title),
            COLLECTION_META_STYLE,
            html_lib.escape(ref.label + ("　" + ref.digest if ref.digest else "")),
            COLLECTION_LINK_STYLE,
            html_lib.escape(root + ref.permalink),
        ))

    return "".join(parts)


def render_collection_plan(collection: Collection, source_url: str) -> str:
    """Render the checklist used to fill the 合集 in the backend.

    The backend's "添加已有内容" picker searches published articles by
    title, so the checklist lists exactly what has to be ticked and in
    which order.  It is the one artefact that turns a collection from a
    plan into a real 合集.
    """
    root = source_url.rstrip("/")
    lines = [
        "# 合集「{}」勾选清单".format(collection.title),
        "",
    ]
    if collection.description:
        lines.extend([collection.description, ""])
    lines.extend([
        "文章数：{}".format(collection.count),
        "",
        "## 勾选顺序",
        "",
    ])
    for index, ref in enumerate(collection.articles, 1):
        lines.append("{}. [ ] {}".format(index, ref.title))
        lines.append("   - 日期：{}".format(ref.label))
        lines.append("   - 原文：{}{}".format(root, ref.permalink))
    lines.extend([
        "",
        "## 后台操作",
        "",
        "1. 登录 mp.weixin.qq.com → 内容与互动 → 合集 → 新建合集",
        "2. 名称填「{}」，简介与封面按需填写".format(collection.title),
        "3. 点「添加已有内容」，按上面的顺序逐条勾选（只列得出已发表的文章）",
        "4. 排序与上面的顺序保持一致，开启「连续阅读」",
        "5. 保存，合集会自动显示在公众号主页",
        "",
    ])
    return "\n".join(lines)
