"""站点测试里的 URL 形状：**从仓库根那份规则文件推导**。

生产方（`src/lib/rules.ts`）读的是 `rules/urls.json`——
构建时由 Vite 内联进产物。校验方（这些测试）读的是**同一个文件**。

⚠️ **为什么不是 import 生产的那个模块**：那是跨层（Python ↔ TypeScript），
而且规则文件本身就在**仓库根**，两层都够得着。
共享的是**数据**，不是代码——这条约束在四份读取器上都成立。

口径与 `tools/url_rules.py`（根工具层的读取器）、`publish/publishkit/urls.py`
（契约层的读取器）**逐字相同**：

- 单元 id 是内容单元相对 `content/units/` 的路径（不带 `.md`）；
- 分类页的 id 尾巴带分类页后缀、视频的 id 开头带视频前缀——
  那是**内容单元里的形状**，不是 URL 里的形状，这里负责抹掉；
- **不 percent-encode**：拼出来的地址逐字照抄单元 id。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# platforms/blog/site/tests/ → parents[4] 是仓库根
REPO_ROOT = Path(__file__).resolve().parents[4]
RULES_FILE = REPO_ROOT / "rules" / "urls.json"


@lru_cache(maxsize=1)
def rules() -> dict:
    """规则文件的内容。"""
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def strip_video_prefix(unit_id: str) -> str:
    """去掉单元 id 开头的视频前缀。"""
    prefix = rules()["video_id_prefix"]
    if prefix and unit_id.startswith(prefix):
        return unit_id[len(prefix):]
    return unit_id


def strip_category_suffix(unit_id: str) -> str:
    """去掉单元 id 结尾的分类页后缀。"""
    suffix = rules()["category_suffix"]
    if not suffix:
        return unit_id
    tail = "/" + suffix
    if unit_id.endswith(tail):
        return unit_id[:-len(tail)]
    return unit_id


def is_category_id(unit_id: str) -> bool:
    """这个 id 是不是分类页。"""
    suffix = rules()["category_suffix"]
    if not suffix:
        return False
    return unit_id.endswith("/" + suffix) or unit_id == suffix


def is_video_id(unit_id: str) -> bool:
    """这个 id 是不是视频（id 开头带视频前缀）。"""
    prefix = rules()["video_id_prefix"]
    return bool(prefix) and unit_id.startswith(prefix)


def doc_url(unit_id: str) -> str:
    """文档（或分类页）在站上的地址。"""
    data = rules()
    tail = strip_category_suffix(unit_id)
    if not tail:
        return data["doc_prefix"]
    return data["doc_prefix"] + tail + ("/" if data["trailing_slash"] else "")


def video_url(unit_id: str) -> str:
    """视频在站上的地址。"""
    data = rules()
    tail = strip_video_prefix(unit_id)
    if not tail:
        return data["video_prefix"]
    return data["video_prefix"] + tail + ("/" if data["trailing_slash"] else "")


def unit_url(unit_id: str, kind: str) -> str:
    """内容单元在站上的地址。`kind` 决定它走哪一条前缀。"""
    if kind == "video":
        return video_url(unit_id)
    return doc_url(unit_id)
