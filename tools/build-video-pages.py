#!/usr/bin/env python3
"""把视频线的口播稿变成站上的视频页。

**一期 = 一个档位目录**：``video/episodes/<系列>/<合集>/<文档>/<档位>/``。
那一行一句的口播稿与字幕表（``口播稿.md``）是这条线入库的唯一真相；
画面契约在同一个期目录里的 ``contract.json``，发布元数据在 ``publish.json``，
发布状态在 ``platforms/<平台>/outbox/*.json``。

生成的是**内容单元**（``content/units/video/<期号>.md``），不是页面：
视频和文章走同一套渲染、同一个 permalink、同一条「已发布到」通道。
这也补上了规格 §9.3 说的那句话——站点是内容谱系的根，而视频此前
在站上零呈现（video widget 关着、菜单无入口）。

期从哪来：**扫目录**。期根下面四层，末层是档位（``short``/``mid``/``full``），
就是一个期——**目录就是登记表**，不另建一份映射表（两个地方各记一遍就会漂）。
口径与 ``video/pipeline/pyv/episodes.py`` 是同一套。

**还没有期是合法状态**：一条期都没有时生成 0 个内容单元，不是错。

生成物是派生产物：``content/units/video/`` 每次构建现生成（与 ``sync-hexo.py``
的产物一个待遇）。

用法：

    python3 tools/build-video-pages.py

产物：

    content/units/video/<期号>.md    每期一个内容单元

**合集页（``platforms/blog/site/source/videos/index.md``）不由这个脚本写**：它由
``platforms/blog/site/tools/build-series-page.py`` 生成——那一页是**系列页**，按期号排，
每期带钩子、时长与完整版（母稿页）的链接，数据来自期号索引
（母稿是唯一真相）。一个文件一个写入者。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 根 tools/ 的脚本：parents[1] 就是仓库根。
# 路径常量统一从根 tools/paths.py 取——那儿是唯一出处。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from paths import CONTENT_UNITS, REPO_ROOT, SITE_DATA  # noqa: E402

AIV_ROOT = REPO_ROOT / "video"
EPISODES_DIR = AIV_ROOT / "episodes"
PLATFORMS_DIR = REPO_ROOT / "platforms"
POSTS_DIR = CONTENT_UNITS

#: 一期的坐标：期根往下四层 `系列/合集/文档/档位`。
EP_DEPTH = 4
#: 末层是档位——只有这三个名字算期目录。
TIERS = ("short", "mid", "full")
SCRIPT_NAME = "口播稿.md"
CONTRACT_NAME = "contract.json"
PUBLISH_NAME = "publish.json"

CATEGORY = "视频"


def site_author():
    """站点的作者名——从站点身份文件读，不写死。

    **框架层不许写死站名**：身份在 ``platforms/blog/site/data/site.json``，
    改那一个文件就够。读不到就用 ``author`` 键，再读不到就空着
    （空着也不会让构建炸——身份是站点的事，不是这一行视频页的事）。
    """
    path = SITE_DATA / "site.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("author") or data.get("name") or "").strip()


def read_episodes():
    """磁盘上的每一期：期路径 → 期目录。

    **坐标就是接口**：期根 ``video/episodes/`` 往下四层
    ``系列/合集/文档/档位``，末层是档位名——**一期 = 一个档位目录**。
    目录里有一份 ``口播稿.md`` 才算一期（没有母稿的目录不是期）。

    这里不查任何登记表，也不解析 Makefile：**目录就是登记表**。
    """
    if not EPISODES_DIR.is_dir():
        return {}
    episodes = {}
    for path in sorted(EPISODES_DIR.rglob("*")):
        if not path.is_dir():
            continue
        rel = path.relative_to(EPISODES_DIR)
        if len(rel.parts) != EP_DEPTH or rel.parts[-1] not in TIERS:
            continue
        if not (path / SCRIPT_NAME).is_file():
            continue
        episodes[rel.as_posix()] = path
    return episodes


def parse_front_matter(text):
    """Split the flat ``key: value`` front matter a script file carries.

    The format is the same one ``sync-hexo.py`` writes: flat scalars only.
    """
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fields = {}
    for line in match.group(1).split("\n"):
        if ":" not in line or line.startswith(" "):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields, match.group(2)


def read_outbox():
    """Every publish snapshot, keyed by (content_id, platform).

    The snapshots live in each platform's own directory
    (``platforms/<platform>/outbox/``), so every one of those directories
    is read -- **missing one hides an episode that was already sent**.
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
            if isinstance(content_id, str) and isinstance(platform, str):
                records[(content_id, platform)] = data
    return records


def permalink(date_text, slug):
    """The site's permalink for one content unit.

    Mirrors the site's permalink rule (``:year/:month/:day/:title/``): the
    date comes from the front matter, the title part is the path under
    ``source/_posts``.
    """
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_text or "")
    if not match:
        # 没有日期就没有年/月/日，但路径形状不变。
        return f"/{slug}/"
    year, month, day = match.groups()
    return f"/{year}/{month}/{day}/{slug}/"


def rewrite_links(body, script_to_permalink):
    """Point sibling episode links at their site pages.

    ``./字幕-结构化DDL.md`` becomes the permalink of that episode's page.
    Links that have no published counterpart (the topic library, the module
    READMEs) keep their text but lose the link — a dead link on the site is
    worse than plain text.
    """
    def replace(match):
        target = match.group(1)
        url = script_to_permalink.get(target)
        if url:
            return f"]({url})"
        return "]"

    return re.sub(r"\]\(([^)]+)\)", replace, body)


def read_publish_meta(ep_dir):
    """这一期的发布元数据（期目录里的 ``publish.json``）。

    **它是母版标题的出处**（视频发布契约 §4.3：「这一期的标题（母版标题）。
    各平台文案默认从这里派生」）。画面契约（同目录的 ``contract.json``）里的
    title 是**画面标题**，两者不必相同。

    所以站上的视频页用母版标题：那一期在 B站/视频号叫什么，站内就叫什么。
    """
    path = ep_dir / PUBLISH_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def build_page(episode, ep_dir, outbox, content_id):
    """Build one content unit. Returns ``(title, date, markdown)``."""
    script_file = ep_dir / SCRIPT_NAME
    fields, body = parse_front_matter(script_file.read_text(encoding="utf-8"))

    contract_file = ep_dir / CONTRACT_NAME
    contract = {}
    if contract_file.is_file():
        contract = json.loads(contract_file.read_text(encoding="utf-8"))

    meta = read_publish_meta(ep_dir)
    # 母版标题优先：那一期在平台上叫什么，站内就叫什么。
    title = meta.get("title") or contract.get("title") or fields.get("title") or episode
    date = fields.get("date") or "1970-01-01"
    description = meta.get("description") or ""

    platforms = sorted(
        platform
        for (cid, platform) in outbox
        if cid == content_id
    )

    front_matter = [
        "---",
        f'title: "{title}"',
        f"date: {date}",
        f"author: {site_author()}",
        "categories:",
        f"  - {CATEGORY}",
        "tags:",
        f"  - {CATEGORY}",
        f"  - {episode}",
        "kind: video",
    ]
    if platforms:
        front_matter.append("platforms:")
        for platform in platforms:
            front_matter.append(f"  - {platform}")
    front_matter.append("---")

    return title, date, "\n".join(front_matter) + "\n\n" + body.lstrip("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-video-pages",
        description="把视频线的口播稿生成成站上的视频内容单元。",
    )
    parser.parse_args(argv)

    episodes = read_episodes()
    outbox = read_outbox()

    posts_dir = POSTS_DIR / "video"
    posts_dir.mkdir(parents=True, exist_ok=True)

    if not episodes:
        # **还没有期是合法状态**：一条期都没有，生成 0 个单元，不是错。
        print("还没有期：video/episodes/ 下没有期目录，生成 0 个视频内容单元")
        print("合集页（系列页）由 platforms/blog/site/tools/build-series-page.py 生成")
        return 0

    # 先算出每期口播稿对应的站内地址：兄弟期之间的链接要指向这些地址。
    script_to_permalink = {}
    episode_meta = {}
    for episode, ep_dir in sorted(episodes.items()):
        script_file = ep_dir / SCRIPT_NAME
        fields, _body = parse_front_matter(script_file.read_text(encoding="utf-8"))
        date = fields.get("date") or "1970-01-01"
        # 内容单元的身份是**期号**（front matter 的 episode_number）——
        # 播放顺序那一串。期路径会随目录重排变，期号是站上认得的那个。
        content_id = fields.get("episode_number") or episode.replace("/", "-")
        url = permalink(date, f"video/{content_id}")
        # 兄弟期之间的链接：相对期根的路径与带 ./ 的写法都认。
        rel = script_file.relative_to(EPISODES_DIR).as_posix()
        script_to_permalink[f"./{rel}"] = url
        script_to_permalink[rel] = url
        episode_meta[episode] = (ep_dir, date, url, content_id)

    pages = []
    for episode, (ep_dir, date, url, content_id) in sorted(episode_meta.items()):
        title, _date, markdown = build_page(episode, ep_dir, outbox, content_id)
        body_start = markdown.index("---", 4) + 3
        front, body = markdown[:body_start], markdown[body_start:]
        body = rewrite_links(body, script_to_permalink)
        path = posts_dir / f"{content_id}.md"
        path.write_text(front + body, encoding="utf-8")

        platforms = sorted(
            platform for (cid, platform) in outbox if cid == content_id
        )
        pages.append((episode, title, date, url, platforms))

    print("生成视频内容单元 {} 个：{}".format(
        len(pages), "、".join(episode for episode, *_ in pages)
    ))
    print("合集页（系列页）由 platforms/blog/site/tools/build-series-page.py 生成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
