"""产物的路由：按 `artifact_id` 取一个文件。

**不合格的 id 一律 404**——不 403。403 等于告诉调用者「这个路径存在」。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.artifacts import resolve_artifact
from ..services.paths import REPO_ROOT

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

#: 按后缀给 Content-Type。**不认识的后缀给通用的那个**——
#: 浏览器下载就下载，不猜。
CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


@router.get("/{artifact_id:path}")
def get_artifact(artifact_id: str):
    """取一个产物文件。"""
    path = resolve_artifact(artifact_id, repo_root=REPO_ROOT)
    if path is None:
        raise HTTPException(status_code=404, detail="没有这个产物")
    return FileResponse(
        path,
        media_type=CONTENT_TYPES.get(path.suffix.lower(),
                                     "application/octet-stream"),
    )
