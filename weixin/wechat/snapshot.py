"""outbox 状态快照：公众号这一侧的公开状态。

**为什么要它**：发布层的幂等键是 ``publish/outbox/`` 里那份快照
（规格 §7.1）。微信 adapter 原来把发布状态写在自己机器上的
``weixin/out/state.json``，那份文件**不入库**——换台机器、或者清一次
工作目录，「这篇发过没有」就没人知道了。

所以公众号也把状态写进 outbox：契约层、站点发布索引、以及别的平台
都看同一个地方。

**只含公开信息**：access_token、AppSecret 永不入库。

形状与头条号那份一致（文档类平台的形状），字段由
``publish/tests/test_reader_agreement.py`` 盯着两边不漂。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["OUTBOX_DIR", "snapshot_name", "write_snapshot", "outbox_dir_from_env"]

#: 仓库里那份 outbox 目录（与 publish/capabilities、publish/outbox 同级）。
OUTBOX_DIR = Path(__file__).resolve().parents[2] / "publish" / "outbox"

#: 快照的字段就是这些，多一个少一个都会被契约测试抓住。
SNAPSHOT_KEYS = (
    "content_id",
    "platform",
    "kind",
    "status",
    "automation",
    "title",
    "published_url",
    "package_dir",
    "updated_at",
    "reason",
    "retryable",
)


def outbox_dir_from_env() -> Path:
    """快照写到哪：环境变量优先，其次仓库里那份。

    调度器调 adapter 时会带上 ``PUBLISH_OUTBOX_DIR``（规格 §5.4：
    状态目录要能配，因为调度器与 adapter 可能不在同一个工作目录）。
    """
    value = os.environ.get("PUBLISH_OUTBOX_DIR")
    return Path(value) if value else OUTBOX_DIR


def snapshot_name(content_id: str, platform: str = "wechat") -> str:
    """快照的文件名：``<压平后的 content_id>__<platform>.json``。

    content_id 形如 ``database/demo``，压平后是 ``database-demo``——
    目录分隔符换成横杠，文件名里不留斜杠。
    """
    flat = content_id.replace("/", "-").replace("\\", "-")
    return f"{flat}__{platform}.json"


def _now() -> datetime:
    """当前时间（UTC）。

    单独拎成一个函数，是为了让测试能控制它——``datetime`` 是不可变
    类型，patch 不了它的 ``now``。
    """
    return datetime.now(timezone.utc)


def write_snapshot(
    path: str | Path,
    *,
    content_id: str,
    status: str,
    title: str,
    reason: str = "",
    published_url: str | None = None,
    package_dir: str = "",
    automation: str = "api_draft",
    retryable: bool = False,
) -> Path:
    """写一份状态快照。

    **每次都重写**：调度器靠「快照的 mtime 变了没有」判断 adapter 的
    成功是不是真的落盘了幂等键（规格 §7.1）。内容没变就不重写的话，
    调度器会把它判成「结果未知」并转人工——那是误报。

    写文件失败会抛 ``OSError``：快照没落盘就等于这次发布没有凭据，
    不能假装成功。
    """
    out = Path(path)
    payload = {
        "content_id": content_id,
        "platform": "wechat",
        "kind": "document",
        "status": status,
        "automation": automation,
        "title": title,
        "published_url": published_url,
        "package_dir": package_dir,
        "updated_at": _now().isoformat(timespec="seconds"),
        "reason": reason,
        "retryable": retryable,
    }
    assert set(payload) == set(SNAPSHOT_KEYS), "快照字段与契约不一致"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out
