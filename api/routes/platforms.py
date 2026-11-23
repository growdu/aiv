"""平台能力：各平台能收什么、限额多少、自动化到哪一档。

**平台名不写死**（全局约束 2）——这里只把文件里的内容端出去。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import identity

router = APIRouter(prefix="/api", tags=["platforms"])


@router.get("/platforms")
def get_platforms():
    """各平台的能力声明 + 发布规格。"""
    return {"platforms": identity.platform_capabilities()}
