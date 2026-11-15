#!/usr/bin/env python3
"""系列页：站上那一期的目录（``/videos/``）。

**母稿是唯一真相**：期号线从 ``source/_data/podcast_index.json`` 来
（``tools/build-podcast-index.py`` 的产物），这个脚本只把它排成一张
给人看的表——一行一期：期号、标题、钩子、时长、完整版（母稿页）、
口播稿与字幕、发到了哪些平台。

产物：

    source/videos/index.md

**地址是派生的**：完整版与口播稿页的站内地址都走
``tools/site_root.py`` 的 ``permalink``（日期 + content_id），
带挂载点前缀（主站 ``/``、镜像 ``/blog``）——不另写一份前缀拼接。

用法：

    python3 tools/build-series-page.py [--out <路径>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_root import permalink as _permalink  # noqa: E402
from site_root import rooted_path as _rooted_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "source" / "_data"
PODCAST_INDEX = DATA_DIR / "podcast_index.json"
SERIES_DIR = REPO_ROOT / "source" / "videos"

#: 系列的更新节奏。规格 §7.1：「承诺了就要兑现」。
CADENCE = "每周一期"


def read_index():
    """期号索引：上一步 ``build-podcast-index.py`` 的产物。"""
    if not PODCAST_INDEX.is_file():
        return {}
    try:
        return json.loads(PODCAST_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def link_text(text):
    """链接文字里的方括号要转义，否则 Markdown 会把它当链接语法。"""
    return text.replace("[", "\\[").replace("]", "\\]")


def platform_line(row):
    """这一期发到了哪些平台。

    发出去的给链接；只出包没发布的写成「（未发布）」——不假装已经发出去。
    """
    platforms = row.get("platforms") or []
    if not platforms:
        return "- 平台：还没发出去"
    parts = []
    for item in platforms:
        label = item.get("label") or item.get("platform_name") or item.get("platform")
        url = item.get("published_url")
        if url:
            parts.append("[{}]({})".format(label, url))
        else:
            parts.append("{}（未发布）".format(label))
    return "- 平台：" + " · ".join(parts)


def render(index):
    """系列页的 Markdown。"""
    series = index.get("series") or {}
    name = series.get("name") or "播客"
    tagline = series.get("tagline") or ""
    episodes = index.get("episodes") or []

    lines = [
        "---",
        'title: "{}"'.format(name),
        "date: 2026-01-01 00:00:00",
        "type: videos",
        "layout: page",
        "---",
        "",
        "# {}".format(name),
        "",
    ]
    if tagline:
        lines += ["> {}".format(tagline), ""]
    lines += [
        "{}。一期一条视频，**完整版是站上的长文**——"
        "讲的是公开的上游机制，不涉及任何公司内部信息。".format(CADENCE),
        "",
        "- 订阅：[播客 feed]({})（RSS 2.0，每期带旁白音频）".format(
            _rooted_path("/feed.xml")
        ),
        "",
    ]

    for row in episodes:
        label = row.get("episode_label") or "EP{}".format(row.get("episode_no"))
        title = row.get("title") or ""
        lines.append("## {} · {}".format(label, title))
        lines.append("")
        if row.get("hook"):
            lines.append("- 一句话：{}".format(row["hook"]))
        if row.get("duration_s"):
            lines.append("- 时长：{} 秒".format(round(row["duration_s"])))
        draft_title = row.get("draft_title") or title
        if row.get("date") and row.get("content_id"):
            draft_url = _permalink(row["date"], row["content_id"])
            lines.append(
                "- 完整版（长文）：[{}]({})".format(link_text(draft_title), draft_url)
            )
        if row.get("video_date") and row.get("video_content_id"):
            video_url = _permalink(row["video_date"], row["video_content_id"])
            lines.append("- [口播稿与字幕]({})".format(video_url))
        lines.append(platform_line(row))
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成系列页（source/videos/index.md）")
    parser.add_argument("--out", help="输出路径（默认 source/videos/index.md）")
    args = parser.parse_args(argv)

    index = read_index()
    episodes = index.get("episodes") or []
    if not episodes:
        # 一期都没有就别覆盖：空页面比旧页面更糟。
        print("期号索引是空的，系列页保持原样。")
        return 0

    out = Path(args.out) if args.out else SERIES_DIR / "index.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(index), encoding="utf-8")
    print("系列页：{}（{} 期）".format(out, len(episodes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
