"""共享 URL 规则（根工具层的读取器）。

**规则只有一份**：仓库根的 `rules/urls.json`。这个模块是它的**读取器**——
根 `tools/` 里的脚本从这里取 URL 形状，不自己写死前缀。

⚠️ **方向**：`publish/publishkit/` **不许** import 本模块，本模块也**不许**
import `publish/publishkit/`。两层之间的接缝是**文件**（那份 JSON），
不是 import——共享规则是数据，不是代码。

**为什么叫 `url_rules` 而不是 `rules`**：仓库根有个 `rules/` **目录**
（规则文件自己住那儿）。模块名跟目录同名，谁在 `sys.path` 上靠前谁赢——
那是隐式依赖。换个名字就没有这个雷。

**层间关系**：平台层与站点工具（`platforms/blog/cli.py`、
`platforms/blog/site/tools/build-activity.py`）读**这一份**；
根 `tools/` **不反向** import 平台层。

**口径**（与站点 `platforms/blog/site/src/lib/urls.ts` 逐字相同）：

- 单元 id 是内容单元相对 `content/units/` 的路径（不带 `.md`）；
- 分类页的 id 尾巴带 `_index`、视频的 id 开头带 `video/`——
  那是**内容单元里的形状**，不是 URL 里的形状，这里负责抹掉；
- **不 percent-encode**：拼出来的地址逐字照抄单元 id。

用法（根 `tools/` 已经在 `sys.path` 上的前提下）::

    from url_rules import unit_url
    unit_url("video/row-lock", "video")   # '/videos/row-lock/'
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# tools/url_rules.py → parents[0]=tools, parents[1]=仓库根
REPO_ROOT = Path(__file__).resolve().parents[1]

#: 规则文件在仓库根的那一个文件。
RULES_FILE = REPO_ROOT / "rules" / "urls.json"

#: 规则里**必须**有的键。少一个就是规则文件坏了——宁可不拼地址，
#: 也不要拼出一个错的地址（错的地址是一批死链，坏掉的文件只是构建失败）。
REQUIRED_KEYS = (
    "version",
    "doc_prefix",
    "video_prefix",
    "video_id_prefix",
    "category_suffix",
    "trailing_slash",
)


def rules_path() -> Path:
    """规则文件的路径。"""
    return RULES_FILE


def load_rules(path: str | Path | None = None) -> dict:
    """读规则文件，返回它的内容。

    少任何一个必需键就抛 `ValueError`（消息里写清缺哪个键）——
    规则文件坏了的时候要立刻知道，而不是拼出半个对的地址。

    读不到文件也抛 `ValueError`（消息里写清是哪个路径），
    不让裸的 `FileNotFoundError` 冒出来——两层之间的错误口径要一致。
    """
    target = Path(path) if path is not None else rules_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"读不到规则文件：{target}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"规则文件不是合法的 JSON：{target}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ValueError(f"规则文件不是一个对象：{target}")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"规则文件缺键：{', '.join(missing)}（{target}）")
    return data


def _strip_video_prefix(unit_id: str, rules: dict) -> str:
    """去掉单元 id 开头的视频前缀（`video/`）。"""
    prefix = rules["video_id_prefix"]
    if prefix and unit_id.startswith(prefix):
        return unit_id[len(prefix):]
    return unit_id


def _strip_category_suffix(unit_id: str, rules: dict) -> str:
    """去掉单元 id 结尾的分类页后缀（`/_index`）。"""
    suffix = rules["category_suffix"]
    if not suffix:
        return unit_id
    tail = "/" + suffix
    if unit_id.endswith(tail):
        return unit_id[:-len(tail)]
    return unit_id


def _join(prefix: str, tail: str, rules: dict) -> str:
    """前缀 + 单元 id 的尾巴，尾巴为空时就是前缀本身。"""
    if not tail:
        return prefix
    return prefix + tail + ("/" if rules["trailing_slash"] else "")


#: 拼地址要读规则文件，读盘 + 解析 JSON 都不便宜——同一轮构建里
#: 规则文件不会变，缓存一份即可（变了要重跑构建，这是本来就有的纪律）。
@lru_cache(maxsize=1)
def _cached_rules() -> dict:
    return load_rules()


@lru_cache(maxsize=1024)
def doc_url(unit_id: str) -> str:
    """文档（或分类页）在站上的地址。"""
    rules = _cached_rules()
    return _join(rules["doc_prefix"], _strip_category_suffix(unit_id, rules), rules)


@lru_cache(maxsize=1024)
def video_url(unit_id: str) -> str:
    """视频在站上的地址。"""
    rules = _cached_rules()
    return _join(rules["video_prefix"], _strip_video_prefix(unit_id, rules), rules)


def unit_url(unit_id: str, kind: str) -> str:
    """内容单元在站上的地址。`kind` 决定它走哪一条前缀。"""
    if kind == "video":
        return video_url(unit_id)
    return doc_url(unit_id)
