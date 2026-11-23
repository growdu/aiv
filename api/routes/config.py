"""配置：站名、简介、导航、品牌名。

**前端不写死任何身份**（全局约束 2）——它从这里拿。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services import identity

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config():
    """站点身份 + 品牌身份。"""
    return {"site": identity.site_identity(),
            "brand": identity.brand_identity()}
