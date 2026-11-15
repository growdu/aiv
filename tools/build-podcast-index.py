#!/usr/bin/env python3
"""期号索引：母稿页上那一块的全部数据。

**母稿是唯一真相**（发布架构 §一 不变量一）：期号字段写在
``docs/<分类>/<名>.md`` 的 front matter 里，由 ``tools/sync-hexo.py``
透传进 ``source/_posts/``。这个脚本只做一件事——把**编译产物**里那些
带 ``episode:`` 的内容单元汇总成一张表，给主题 partial 消费。

它读的是 ``source/_posts/``（**编译产物**，构建期现生成），所以它必须
在 ``sync-hexo.py`` 之后跑；平台链接与视频页地址来自
``source/_data/publish_index.json``（上一步生成）。

产物：

    source/_data/podcast_index.json    主题 partial 消费的数据源

**地址是派生的，不是抄来的**：母稿页地址 = content_id + 内容单元的
date，走 ``tools/site_root.py`` 的 ``permalink``——那是站点构建层自己
的规则实现，不另写一份。存进 JSON 的是**不带挂载点前缀**的站内路径，
主题用 ``url_for()`` 补前缀（主站 ``/``，镜像 ``/blog``）。

用法：

    python3 tools/build-podcast-index.py [--out <路径>]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_root import permalink as _permalink  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = REPO_ROOT / "source" / "_posts"
DATA_DIR = REPO_ROOT / "source" / "_data"
PUBLISH_INDEX = DATA_DIR / "publish_index.json"

#: 系列的一句话定位。规格 §7.1 系列页的口径。
#:
#: 系列名本身**不写在这里**——它由六期母稿的 ``series`` 字段决定
#: （母稿是唯一真相）。这里只写这句定位文案。
SERIES_TAGLINE = "数据库内核机制，讲到源码那一行"

#: 视频内容单元的目录。视频页是独立内容单元（``tools/build-video-pages.py``
#: 生成），期号页是母稿页——两者内容不同，地址也不同。
VIDEO_PREFIX = "video/"

#: 平台在期号区块里的说法。规格 §4.2 第 2 行：「在 B站看 / 在视频号看 /
#: 在抖音看」。
#:
#: 这是**期号区块的显示口径**，与 ``build-publish-index.py`` 的
#: ``PLATFORM_NAMES``（发布索引里的规范名）是两件事：那边叫「哔哩哔哩」，
#: 这边要说人话「在 B站看」。没列进来的平台退回规范名。
PLATFORM_LABELS = {
    "bilibili": "B站",
    "channels": "视频号",
    "douyin": "抖音",
}


def parse_front_matter(text):
    """Split the flat ``key: value`` front matter.

    形状是 ``sync-hexo.py`` 写出来的那种：扁平标量 + 单层列表。
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields = {}
    list_key = None
    for line in text[4:end].split("\n"):
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            if list_key is not None:
                fields.setdefault(list_key, []).append(stripped[2:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value:
            fields[key] = value.strip('"')
            list_key = None
        else:
            list_key = key
            fields[key] = []
    return fields, text[end + 4:]


def read_episode_posts():
    """每一期母稿：content_id -> 期号字段。

    只有带 ``episode:`` 的内容单元才算一期——普通文章不进期号线。
    """
    episodes = {}
    if not POSTS_DIR.is_dir():
        return episodes
    for path in sorted(POSTS_DIR.rglob("*.md")):
        content_id = path.relative_to(POSTS_DIR).with_suffix("").as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fields, _body = parse_front_matter(text)
        slug = fields.get("episode")
        if not slug:
            continue
        date_text = fields.get("date", "")
        episodes[slug] = {
            "episode": slug,
            "episode_no": _as_int(fields.get("episode_no")),
            "draft_title": fields.get("title") or path.stem,
            "hook": fields.get("episode_hook", ""),
            "duration_s": _as_float(fields.get("episode_duration_s")),
            "license": fields.get("episode_license", ""),
            "subtitle": fields.get("episode_subtitle", ""),
            "series": fields.get("series", ""),
            "content_id": content_id,
            "date": date_text[:10],
            "url": _permalink(date_text, content_id, root=""),
            "sources": fields.get("episode_sources", []) or [],
            "repro": fields.get("episode_repro", []) or [],
        }
    return episodes


def _as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def read_publish_index():
    """发布索引：上一步 ``build-publish-index.py`` 的产物。"""
    if not PUBLISH_INDEX.is_file():
        return {}
    try:
        return json.loads(PUBLISH_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_video_date(slug):
    """视频内容单元的日期。

    视频页是独立内容单元（``tools/build-video-pages.py`` 生成的），
    它的地址要由 **日期 + content_id** 派生，所以这里得把日期也带上——
    站点构建层的规则是 ``tools/site_root.py`` 的 ``permalink``，
    不另写一份前缀拼接。
    """
    path = POSTS_DIR / VIDEO_PREFIX / (slug + ".md")
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    fields, _body = parse_front_matter(text)
    return fields.get("date", "")[:10]


def platform_label(item):
    """期号区块里的平台说法。"""
    platform = item.get("platform") or ""
    return PLATFORM_LABELS.get(platform, item.get("platform_name") or platform)


def build_index():
    """期号索引：六期的身份、内容事实与去向。"""
    episodes = read_episode_posts()
    publish = read_publish_index()
    videos = publish.get("videos", {}) or {}

    rows = []
    missing_video_page = []

    for slug, episode in episodes.items():
        video = videos.get(VIDEO_PREFIX + slug) or {}
        video_url = video.get("url") or ""
        if not video_url:
            missing_video_page.append(slug)
        platforms = []
        for item in video.get("platforms", []) or []:
            entry = dict(item)
            entry["label"] = platform_label(item)
            platforms.append(entry)
        row = dict(episode)
        # 期号标题用**口播稿的标题**（期号的身份），不是母稿的文章标题
        # ——母稿标题就在页面顶上，再写一遍是噪音。
        # 母稿标题另存一份：系列页要用它当「完整版」的链接文字。
        row["title"] = video.get("title") or episode["draft_title"]
        # 期号标签（EP01）在这里定一次：主题、系列页、检查器都用它，
        # 三处各拼一遍「EP」+ 补零，早晚拼歪。
        row["episode_label"] = (
            "EP{:02d}".format(row["episode_no"]) if row["episode_no"] else ""
        )
        row["video_content_id"] = VIDEO_PREFIX + slug if video else ""
        row["video_url"] = video_url
        row["video_date"] = read_video_date(slug)
        row["platforms"] = platforms
        rows.append(row)

    # 期号在前：期号页的区块与系列页都按期号顺序排。
    rows.sort(key=lambda item: (item["episode_no"] is None, item["episode_no"] or 0))

    series_name = ""
    for row in rows:
        if row.get("series"):
            series_name = row["series"]
            break

    published = sum(
        1
        for row in rows
        for item in row["platforms"]
        if item.get("published_url")
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "series": {"name": series_name, "tagline": SERIES_TAGLINE},
        "episodes": rows,
        "stats": {
            "episodes": len(rows),
            "published_links": published,
            "missing_video_page": missing_video_page,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成期号索引（source/_data/podcast_index.json）")
    parser.add_argument("--out", help="输出路径（默认 source/_data/podcast_index.json）")
    args = parser.parse_args(argv)

    payload = build_index()
    out = Path(args.out) if args.out else DATA_DIR / "podcast_index.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "期号索引：{} 期，涉及 {} 个已发布链接。".format(
            payload["stats"]["episodes"], payload["stats"]["published_links"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
