"""出包状态：各平台的快照，**投影成公共子集**。

各平台快照的键数不一样（有的九个键、有的是十个）——
这里只端出公共的那几个，前端一张表就能看全。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import identity

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.get("/outbox")
def get_outbox():
    """全部出包快照。"""
    return {"snapshots": identity.outbox_snapshots()}
