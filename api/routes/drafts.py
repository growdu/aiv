"""草稿箱的路由。

**草稿箱是平台唯一的写点**（全局约束 4）：
「保存」写 `drafts/`，「过审」把草稿**复制**进母稿层。

**界面上不给直接写 `docs/` 或 `video/` 的入口**——一条都没有。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import coordinates
from ..services import drafts
from ..services.paths import (
    DRAFTS_DIR,
    DOCS_DIR,
    EPISODES_DIR,
    REPO_ROOT,
    TIERS,
    VIDEO_DRAFT_PREFIX,
    DraftUnit,
    list_draft_units,
)

router = APIRouter(prefix="/api/drafts", tags=["drafts"])

#: 哪些形态这一版**不给过审按钮**（规格 §九 的 Q2 / Q3）。
#: 索引页照抄会造站内死链，bundle 稿要引用解析器。
NOT_PROMOTABLE = {
    "index": "索引页照抄会造站内死链，这一版不过审",
    "bundle": "bundle 稿要引用解析器，这一版不过审",
}


class CreateBody(BaseModel):
    kind: str
    draft_id: str
    title: str = ""


class WriteBody(BaseModel):
    files: dict[str, str]


def _unit_view(unit: DraftUnit) -> dict:
    """一个草稿单元给界面看的样子。"""
    reason = NOT_PROMOTABLE.get(unit.kind, "")
    return {
        "kind": unit.kind,
        "draft_id": unit.draft_id,
        "path": str(unit.path),
        "files": list(unit.files),
        "promotable": not reason,
        "reason": reason,
    }


# ⚠️ **`/api/drafts/draft` 必须注册在 `/{draft_id:path}` 之前**——
# 否则 `{draft_id:path}` 会把它吃掉（「draft」正好是一个合法的 id）。
@router.post("/draft")
def ai_draft():
    """AI 起草——**这一版没做**。

    返回 501 而不是 404：它**不是**「没有这条路径」，是「说好了要做，
    还没做」。
    """
    raise HTTPException(status_code=501,
                        detail="AI 起草这一版还没做：先手写稿子，或用 POST /api/drafts 建一个单元")


@router.get("/options")
def draft_options():
    """坐标选项：界面做下拉框要用的两棵树。

    **并集**：草稿箱里的分类与母稿层里的分类都要能选——
    只在草稿箱里的是「还没写」，只在母稿层里的是「已经过了审」。

    **只返回目录名**——站名、品牌名、平台名一个都没有。
    """
    return {
        "document": {
            "categories": coordinates.document_tree(DRAFTS_DIR, DOCS_DIR),
        },
        "episode": {
            "series": coordinates.episode_tree(
                DRAFTS_DIR / VIDEO_DRAFT_PREFIX, EPISODES_DIR),
            "tiers": list(TIERS),
        },
    }


@router.get("")
def list_drafts():
    """草稿箱里有哪些单元。

    **索引页与 bundle 稿要列**——它们存在，只是**不给过审**，
    界面上标原因。
    """
    return {"units": [_unit_view(unit) for unit in list_draft_units(DRAFTS_DIR)]}


@router.post("")
def create_draft(body: CreateBody):
    """新建一个草稿单元（文档 / 一期视频 / 骨架）。"""
    try:
        unit = drafts.create_unit(body.kind, draft_id=body.draft_id,
                                  title=body.title, root=DRAFTS_DIR)
    except drafts.DraftExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _unit_view(unit)


@router.get("/{draft_id:path}")
def get_draft(draft_id: str):
    """读一个草稿单元：文件名 → 内容。"""
    try:
        unit = drafts.find_unit(draft_id, root=DRAFTS_DIR)
    except drafts.DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    view = _unit_view(unit)
    view["contents"] = drafts.read_unit(unit)
    return view


@router.put("/{draft_id:path}")
def save_draft(draft_id: str, body: WriteBody):
    """保存——**只写草稿箱**。body 里没给的键原样不动。"""
    try:
        unit = drafts.find_unit(draft_id, root=DRAFTS_DIR)
    except drafts.DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        drafts.write_unit(unit, body.files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"draft_id": unit.draft_id, "files": list(unit.files)}


@router.post("/{draft_id:path}/promote")
def promote_draft(draft_id: str):
    """过审 = **只复制**进母稿层。

    复制之后**还要人手工做三步**（`manual_steps`）——
    门面不做，也不许假装做了。
    """
    try:
        unit = drafts.find_unit(draft_id, root=DRAFTS_DIR)
    except drafts.DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        result = drafts.promote_unit(unit, repo_root=REPO_ROOT)
    except drafts.PromoteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "kind": result.kind,
        "targets": list(result.targets),
        "overwritten": list(result.overwritten),
        "manual_steps": list(result.manual_steps),
    }
