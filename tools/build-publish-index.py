#!/usr/bin/env python3
"""汇总发布状态，产出站点用的发布索引。

**站点是内容谱系的根**（发布架构 §9.3）：一篇文章页要能回答「这篇还发到了
哪些平台」，一个视频页要能回答「这期发到哪了」。答案在各平台的
``platforms/<平台>/outbox/`` 里——那是发布层的幂等键，本工具把它汇总成
站点能消费的形状。

产物：

    source/_data/publish_index.json    主题 partial 消费的数据源
    source/_posts/_published.md        （不生成，见下）

**只读不写发布状态**：本工具不改 ``platforms/<平台>/outbox/``，它只是把那些
快照读出来拼成一张表。真相永远在快照里。

用法：

    python3 tools/build-publish-index.py

退出码：0 = 生成成功；2 = 用法或环境错误。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORMS_DIR = REPO_ROOT / "platforms"
POSTS_DIR = REPO_ROOT / "source" / "_posts"
DATA_DIR = REPO_ROOT / "source" / "_data"

# 平台的中文名。索引里放中文名，主题 partial 直接用，不在模板里做映射。
PLATFORM_NAMES = {
    "wechat": "微信公众号",
    "toutiao": "今日头条",
    "channels": "微信视频号",
    "bilibili": "哔哩哔哩",
    "youtube": "YouTube",
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


def permalink_of(content_id, date_text):
    """站内的文章地址，与站点的 permalink 规则一致。

    规则是 ``:year/:month/:day/:title/``，而 ``:title`` 是内容单元相对
    ``source/_posts`` 的路径去后缀——也就是 content_id 本身。
    """
    # 日期形如 "2026-07-27 15:48:27"：只取日期那三段。
    day_text = (date_text or "").split(" ")[0]
    parts = day_text.split("-")
    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
        year, month, day = parts[0], parts[1], parts[2]
    else:
        year, month, day = "1970", "01", "01"
    return f"/{year}/{month}/{day}/{content_id}/"


def read_posts():
    """Every content unit: content_id -> (title, url, kind)."""
    posts = {}
    if not POSTS_DIR.is_dir():
        return posts
    for path in sorted(POSTS_DIR.rglob("*.md")):
        content_id = path.relative_to(POSTS_DIR).with_suffix("").as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fields, _body = parse_front_matter(text)
        title = fields.get("title") or path.stem
        posts[content_id] = {
            "title": title,
            "url": permalink_of(content_id, fields.get("date", "")),
            "kind": fields.get("kind", "post"),
        }
    return posts


def read_outbox():
    """Every publish snapshot, keyed by content_id.

    The snapshots live in each platform's own directory
    (``platforms/<platform>/outbox/``), so every one of those directories
    is read -- **missing one hides an article that was already sent**.
    """
    records = {}
    if not PLATFORMS_DIR.is_dir():
        return records
    for directory in sorted(PLATFORMS_DIR.glob("*/outbox")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            content_id = data.get("content_id")
            platform = data.get("platform")
            if not isinstance(content_id, str) or not isinstance(platform, str):
                continue
            records.setdefault(content_id, []).append({
                "platform": platform,
                "platform_name": PLATFORM_NAMES.get(platform, platform),
                "status": data.get("status", "unknown"),
                "published_url": data.get("published_url"),
                "reason": data.get("reason", ""),
                "updated_at": data.get("updated_at", ""),
            })
    return records


def match_content_id(content_id, posts):
    """Find the content unit a snapshot belongs to.

    视频快照的 content_id 是期号（``row-lock``），而视频的内容单元在
    ``source/_posts/video/row-lock.md``——所以除了精确匹配，还要按文件名
    兜一次（只认内容单元 basename 相同的那一个，不猜）。
    """
    if content_id in posts:
        return content_id
    matches = [key for key in posts if key.rsplit("/", 1)[-1] == content_id]
    if len(matches) == 1:
        return matches[0]
    return None


def build_index():
    posts = read_posts()
    outbox = read_outbox()

    articles = {}
    videos = {}
    unmatched = []

    for content_id, entries in sorted(outbox.items()):
        target = match_content_id(content_id, posts)
        if target is None:
            unmatched.append(content_id)
            continue
        post = posts[target]
        record = {
            "content_id": target,
            "title": post["title"],
            "url": post["url"],
            "kind": post["kind"],
            "platforms": sorted(entries, key=lambda item: item["platform"]),
        }
        if post["kind"] == "video":
            videos[target] = record
        else:
            articles[target] = record

    published = sum(
        1
        for entries in outbox.values()
        for entry in entries
        if entry["published_url"]
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "articles": articles,
        "videos": videos,
        "stats": {
            "articles": len(articles),
            "videos": len(videos),
            "platforms": len({entry["platform"] for entries in outbox.values()
                              for entry in entries}),
            "published": published,
            "unmatched": unmatched,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-publish-index",
        description="汇总各平台 outbox 的发布状态，产出站点用的发布索引。",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DATA_DIR / "publish_index.json",
        help="索引文件路径（默认：source/_data/publish_index.json）",
    )
    args = parser.parse_args(argv)

    if not POSTS_DIR.is_dir():
        print(
            f"找不到 {POSTS_DIR}：先跑 python3 tools/sync-hexo.py 产出内容单元。",
            file=sys.stderr,
        )
        return 2

    index = build_index()
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    stats = index["stats"]
    print(
        "发布索引：{} 篇文章 + {} 期视频，涉及 {} 个平台。".format(
            stats["articles"], stats["videos"], stats["platforms"]
        )
    )
    if stats["unmatched"]:
        print(
            "有 {} 条快照没找到对应的内容单元：{}".format(
                len(stats["unmatched"]), "、".join(stats["unmatched"])
            ),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
