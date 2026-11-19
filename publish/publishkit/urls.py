"""契约层按共享规则拼地址。

**规则只有一份**：仓库根的 `rules/urls.json`。这个模块是它在**契约层**
的读取器——本包里的脚本从这里取 URL 形状，不自己写死前缀。

⚠️ **方向**：本包**不许** import 根 `tools/`（反过来也不许）。
两层之间的接缝是**文件**（那份 JSON），不是 import——
共享规则是数据，不是代码。

**仓库根从哪来**：环境变量 `PUBLISH_REPO`（部署模板里已有这个变量），
取不到就按本文件的目录层级推（`publish/publishkit/urls.py` 往上两级）。

**口径**（与站点 `platforms/blog/site/src/lib/urls.ts` 逐字相同）：

- 单元 id 是内容单元相对 `content/units/` 的路径（不带 `.md`）；
- 分类页的 id 尾巴带 `_index`、视频的 id 开头带 `video/`——
  那是**内容单元里的形状**，不是 URL 里的形状，这里负责抹掉；
- **不 percent-encode**：拼出来的地址逐字照抄单元 id。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import PublishKitError


class RulesError(PublishKitError, ValueError):
    """规则文件不合法（缺键、不是一个对象……）。

    既是契约层的错误（`except PublishKitError` 兜得住），
    也是 `ValueError`（规则文件坏了属于「值不对」）——
    两个身份都要，调用方才好写。
    """


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
    """规则文件的路径。

    仓库根优先取环境变量 `PUBLISH_REPO`（部署模板里已有），
    取不到按本文件的目录层级推。
    """
    env = os.environ.get("PUBLISH_REPO")
    if env:
        return Path(env).resolve() / "rules" / "urls.json"
    # publish/publishkit/urls.py → parents[0]=publishkit, [1]=publish, [2]=仓库根
    return Path(__file__).resolve().parents[2] / "rules" / "urls.json"


def load_rules(path: str | Path | None = None) -> dict:
    """读规则文件，返回它的内容。

    少任何一个必需键就抛 `RulesError`（它也是 `ValueError`），
    消息里写清缺哪个键——规则文件坏了要立刻知道，
    而不是拼出半个对的地址。
    """
    target = Path(path) if path is not None else rules_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RulesError(f"规则文件不是合法的 JSON：{target}（{exc}）") from exc
    if not isinstance(data, dict):
        raise RulesError(f"规则文件不是一个对象：{target}")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise RulesError(f"规则文件缺键：{', '.join(missing)}（{target}）")
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


def doc_url(unit_id: str) -> str:
    """文档（或分类页）在站上的地址。"""
    rules = load_rules()
    return _join(rules["doc_prefix"], _strip_category_suffix(unit_id, rules), rules)


def video_url(unit_id: str) -> str:
    """视频在站上的地址。"""
    rules = load_rules()
    return _join(rules["video_prefix"], _strip_video_prefix(unit_id, rules), rules)


def unit_url(unit_id: str, kind: str) -> str:
    """内容单元在站上的地址。`kind` 决定它走哪一条前缀。"""
    if kind == "video":
        return video_url(unit_id)
    return doc_url(unit_id)
