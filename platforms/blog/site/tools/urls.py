"""站点这一侧的 URL 形状规则。

**形状只有一份**。读仓库根的 `rules/urls.json`（那是全仓库的规则表，
根 `tools/url_rules.py` 是它的另一个读取器）。规则表不在 = 仓库不完整，
直接报错，不拿默认值兜底（默认值就是第二份真相）。

**单元 id 是什么**：内容单元相对 `content/units/` 的路径，不带 `.md`。
两处形状要在拼地址时抹掉：

- 分类页的 id 尾巴带 `_index` → 地址是它所在目录 + 文档前缀；
- 视频单元的 id 开头带 `video/` → 地址是视频前缀 + slug。

**不 percent-encode**：拼出来的地址逐字照抄单元 id。

用法::

    from urls import unit_url
    unit_url("source-tracks/postgresql/x", "document")
    unit_url("source-tracks/postgresql/_index", "category")
    unit_url("video/row-lock", "video")
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# tools/urls.py → parents[0]=tools, parents[1]=site, parents[4]=仓库根
SITE = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]

#: 全仓库的规则表。
RULES_FILE = REPO_ROOT / "rules" / "urls.json"

REQUIRED_KEYS = (
    "version",
    "doc_prefix",
    "video_prefix",
    "video_id_prefix",
    "category_suffix",
    "trailing_slash",
)


@lru_cache(maxsize=1)
def load_rules() -> dict:
    """读规则表。缺失或坏掉的规则表都不许悄悄兜底——报错。"""
    if not RULES_FILE.exists():
        raise FileNotFoundError(f"规则表不在：{RULES_FILE}")
    try:
        rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"规则表不是合法 JSON：{RULES_FILE}：{exc}") from exc
    missing = [k for k in REQUIRED_KEYS if k not in rules]
    if missing:
        raise ValueError(f"规则表缺键：{'、'.join(missing)}（{RULES_FILE}）")
    return rules


def strip_video_prefix(unit_id: str) -> str:
    """去掉视频单元 id 的 `video/` 前缀。"""
    prefix = load_rules()["video_id_prefix"]
    if unit_id.startswith(prefix):
        return unit_id[len(prefix) :]
    return unit_id


def strip_category_suffix(unit_id: str) -> str:
    """去掉分类页 id 的 `_index` 尾巴。"""
    suffix = load_rules()["category_suffix"]
    if unit_id.endswith(suffix):
        return unit_id[: -len(suffix)]
    return unit_id


def unit_url(unit_id: str, kind: str = "document") -> str:
    """内容单元 id → 站点上的地址。

    - 视频单元 → `video_prefix` + 去掉前缀的 id；
    - 分类页（`_index` 结尾）→ `doc_prefix` + 去掉后缀的目录；
    - 其余 → `doc_prefix` + 原样的 id。
    """
    rules = load_rules()
    if kind == "video" or unit_id.startswith(rules["video_id_prefix"]):
        slug = strip_video_prefix(unit_id)
        return f"{rules['video_prefix']}{slug}/"
    if unit_id.endswith(rules["category_suffix"]):
        directory = strip_category_suffix(unit_id)
        directory = directory.rstrip("/")
        return f"{rules['doc_prefix']}{directory}/" if directory else rules["doc_prefix"]
    return f"{rules['doc_prefix']}{unit_id}/"


def doc_url(unit_id: str) -> str:
    """文档单元 id → 地址（分类页的 `_index` 也会被抹掉）。"""
    return unit_url(unit_id, "document")


def video_url(unit_id: str) -> str:
    """视频单元 id → 地址。"""
    return unit_url(unit_id, "video")


def track_url(track_id: str) -> str:
    """赛道 id → 学习流页地址。"""
    return f"/learning/{track_id}/"
