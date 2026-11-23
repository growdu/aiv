"""身份从缝里读，**不写死**（全局约束 2）。

- 站名、简介、导航 → `platforms/blog/site/data/site.json`
- 品牌名、片头副标题 → `video/config.toml` 的 `[brand]`
- 平台能力 → 各平台目录里的 `capability.toml` + `publish-spec.json`
- 出包快照 → 各平台目录里的 `outbox/*.json`

**不 import `publish/publishkit/`**（规格 D12）：能力声明是**数据文件**，
读它，不 import。也不 import 各平台的包——那些是别的层。

**这一层不发明默认值。** 读不到就少一个键，不拿一个假的名字顶上。
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .paths import PLATFORMS_DIR, REPO_ROOT, SITE_DIR

#: 站点的身份文件。
SITE_CONFIG = SITE_DIR / "data" / "site.json"

#: 视频线的身份文件（品牌段在里面）。
BRAND_CONFIG = REPO_ROOT / "video" / "config.toml"

#: 站点身份**只取这几个键**——`note` 那种说明字段不端出去。
SITE_KEYS = ("name", "tagline", "description", "nav", "url")

#: 品牌身份只取这几个键。
BRAND_KEYS = ("name", "tagline", "token", "site")

#: 平台能力取这几个键（`limits` / `media` 是两张子表）。
CAPABILITY_KEYS = ("id", "name", "kind", "automation", "review", "tiers",
                   "verified", "limits", "media")

#: 出包快照的**公共子集**——各平台快照的键数不一样
#: （有的九个键、有的是十个），只投影这几个。
OUTBOX_COMMON = ("platform", "status", "reason", "updated_at",
                 "content_id", "title", "published_url")


def _read_json(path: Path):
    """读 JSON。读不到或不是 JSON → `None`。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_toml(path: Path) -> dict:
    """读 TOML。读不到 → `{}`。"""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def site_identity() -> dict:
    """站名 / 简介 / 导航 / 地址。**读不到就少几个键**。"""
    data = _read_json(SITE_CONFIG)
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in SITE_KEYS if key in data}


def brand_identity() -> dict:
    """品牌名 / 片头副标题 / 品牌词 / 落版地址。"""
    data = _read_toml(BRAND_CONFIG)
    brand = data.get("brand")
    if not isinstance(brand, dict):
        return {}
    return {key: brand[key] for key in BRAND_KEYS if key in brand}


def platform_capabilities() -> list[dict]:
    """各平台的能力声明。

    **扫目录**——有 `capability.toml` 的才算一个平台。
    `id` **以文件里的为准**，不拿目录名当 id（两者可能不同）。
    """
    out = []
    for directory in sorted(PLATFORMS_DIR.iterdir()):
        if not directory.is_dir():
            continue
        capability = directory / "capability.toml"
        if not capability.is_file():
            continue
        data = _read_toml(capability)
        item = {key: data[key] for key in CAPABILITY_KEYS if key in data}
        spec_path = directory / "publish-spec.json"
        item["spec"] = _read_json(spec_path) if spec_path.is_file() else None
        out.append(item)
    return sorted(out, key=lambda item: str(item.get("id", "")))


def outbox_snapshots() -> list[dict]:
    """各平台的出包快照，**只投影公共子集**。

    缺了的键就缺着——**不补默认值**：补出来的 `published_url: null`
    与「还没发」是两回事。
    """
    out = []
    for directory in sorted(PLATFORMS_DIR.iterdir()):
        outbox = directory / "outbox"
        if not outbox.is_dir():
            continue
        for path in sorted(outbox.glob("*.json")):
            data = _read_json(path)
            if not isinstance(data, dict):
                continue
            out.append({key: data[key] for key in OUTBOX_COMMON if key in data})
    return sorted(out, key=lambda item: (str(item.get("platform", "")),
                                         str(item.get("content_id", ""))))
