#!/usr/bin/env python3
"""播客 feed：RSS 2.0，带 ``<enclosure>``。

**成片 mp4 不在站点托管**；**旁白 mp3 在站点托管**（发布架构 §八.1 的更正）。
RSS 的 ``<enclosure>`` 必须是自己域名下的**稳定音频直链**——B站 / 视频号
都不提供能直接放进 ``<enclosure>`` 的音频地址，所以站点承担「文字 + 音频」
的永久副本，视频流量仍然导给平台。

产物：

    source/feed.xml              RSS 2.0（/feed.xml）
    source/audio/<期号>.mp3       旁白音频的站点副本

**数据源**：``source/_data/podcast_index.json``（期号线，母稿是唯一真相）
与 ``video/narration_<期号>.mp3``（旁白，入库）。

**地址是派生的**：条目链接走 ``tools/site_root.py`` 的 ``permalink``，
音频地址走 ``absolute_url``（域名 + 站内路径，挂载点前缀只加一次）。

用法：

    python3 tools/build-podcast-feed.py [--out <路径>]
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_root import absolute_url as _absolute_url  # noqa: E402
from site_root import permalink as _permalink  # noqa: E402
from site_root import site_url as _site_url  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "source" / "_data"
PODCAST_INDEX = DATA_DIR / "podcast_index.json"
AIV_ROOT = REPO_ROOT / "video"
AUDIO_DIR = REPO_ROOT / "source" / "audio"

#: feed 里的条目数上限。与 ``atom.xml`` 的 ``limit: 20`` 一致。
LIMIT = 20

#: 音频在站上的路径前缀（站点托管的旁白 mp3）。
AUDIO_PREFIX = "audio"

#: 旁白音频在仓库里的文件名模板。
NARRATION_TEMPLATE = "narration_{}.mp3"

#: guid 的前缀。**必须稳定**：重发同一期不能变成新条目。
GUID_PREFIX = "growdu.cn/podcast"


def read_index():
    """期号索引：``build-podcast-index.py`` 的产物。"""
    if not PODCAST_INDEX.is_file():
        return {}
    try:
        return json.loads(PODCAST_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def narration_path(slug):
    """一期旁白音频在仓库里的位置。"""
    return AIV_ROOT / NARRATION_TEMPLATE.format(slug)


def publish_audio(slug):
    """把旁白 mp3 复制到站点托管的目录。

    返回 ``(站内路径, 字节数)``；没有这一期的旁白就返回 ``None``。
    """
    source = narration_path(slug)
    if not source.is_file():
        return None
    target_dir = AUDIO_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return "/" + AUDIO_PREFIX + "/" + target.name, target.stat().st_size


def rfc822(date_text):
    """``YYYY-MM-DD`` → RFC 822（RSS 的 ``<pubDate>`` 要这个格式）。"""
    try:
        moment = datetime.strptime(date_text[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        moment = datetime(1970, 1, 1)
    return moment.strftime("%a, %d %b %Y 00:00:00 +0800")


def render_item(row, audio):
    """一期的 ``<item>``。"""
    label = row.get("episode_label") or "EP{}".format(row.get("episode_no"))
    title = "{} · {}".format(label, row.get("title") or "")
    link = _absolute_url(_permalink(row["date"], row["content_id"]))
    description = row.get("hook") or ""
    enclosure = ""
    if audio:
        audio_path, size = audio
        enclosure = (
            '      <enclosure url="{}" length="{}" type="audio/mpeg"/>'.format(
                _absolute_url(audio_path), size
            )
        )
    return "\n".join(
        [
            "    <item>",
            "      <title>{}</title>".format(escape(title)),
            "      <link>{}</link>".format(escape(link)),
            '      <guid isPermaLink="false">{}/{}</guid>'.format(
                GUID_PREFIX, escape(row.get("episode") or "")
            ),
            "      <pubDate>{}</pubDate>".format(rfc822(row.get("video_date"))),
            "      <description>{}</description>".format(escape(description)),
            enclosure,
            "    </item>",
        ]
    )


def render_feed(index):
    """整个 feed。"""
    series = index.get("series") or {}
    name = series.get("name") or "播客"
    tagline = series.get("tagline") or ""
    episodes = list(index.get("episodes") or [])
    # 新的在前（期号升序 → 倒过来）。
    episodes.reverse()
    episodes = episodes[:LIMIT]

    items = []
    for row in episodes:
        audio = publish_audio(row.get("episode") or "")
        items.append(render_item(row, audio))

    channel_link = _absolute_url("/") or "/"
    self_link = _absolute_url("/feed.xml")
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"'
        ' xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        "  <channel>",
        "    <title>{}</title>".format(escape(name)),
        "    <link>{}</link>".format(escape(channel_link)),
        "    <description>{}</description>".format(escape(tagline)),
        "    <language>zh-cn</language>",
        "    <lastBuildDate>{}</lastBuildDate>".format(now),
        '    <atom:link href="{}" rel="self" type="application/rss+xml"/>'.format(
            escape(self_link)
        ),
        "    <itunes:author>growdu</itunes:author>",
        "    <itunes:explicit>false</itunes:explicit>",
        "    <itunes:subtitle>{}</itunes:subtitle>".format(escape(tagline)),
        "    <itunes:summary>{}</itunes:summary>".format(escape(tagline)),
    ]
    lines += items
    lines += ["  </channel>", "</rss>", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成播客 feed（source/feed.xml）")
    parser.add_argument("--out", help="输出路径（默认 source/feed.xml）")
    args = parser.parse_args(argv)

    index = read_index()
    episodes = index.get("episodes") or []
    if not episodes:
        print("期号索引是空的，feed 保持原样。")
        return 0

    out = Path(args.out) if args.out else REPO_ROOT / "source" / "feed.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_feed(index), encoding="utf-8")
    print("播客 feed：{}（{} 期）".format(out, len(episodes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
