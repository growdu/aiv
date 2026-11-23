"""文档流的路由：列母稿、读母稿、重建、看真页面。

**读的是母稿层（`docs/`）**——那才是内容真相。草稿在另一条路上
（`drafts.py`）。

**不提供任何写母稿的入口**（全局约束 4）：写只有两个去处——
草稿箱（`PUT /api/drafts/…`）与「过审」（`POST /api/drafts/…/promote`）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import commands, frontmatter, preview
from ..services.jobs import RUNNER
from ..services.paths import DOCS_DIR

router = APIRouter(prefix="/api/documents", tags=["documents"])

#: 母稿层里**保留名**——模块说明文档，不是稿子（编译器也跳过它）。
RESERVED_NAMES = ("README.md",)


def _doc_path(doc_id: str):
    """把文档 id 变成母稿里的路径。越界 → 404。"""
    clean = doc_id.strip("/")
    if not clean or ".." in clean.split("/"):
        raise HTTPException(status_code=404, detail="没有这一篇")
    path = (DOCS_DIR / f"{clean}.md").resolve()
    if DOCS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="没有这一篇")
    return path


def _listing():
    """列母稿里的稿子：id / path / title。"""
    out = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        if path.name in RESERVED_NAMES:
            continue
        rel = path.relative_to(DOCS_DIR).as_posix()
        doc_id = rel[: -len(".md")]
        text = path.read_text(encoding="utf-8")
        out.append({"id": doc_id, "path": f"docs/{rel}",
                    "title": frontmatter.title(text, path.stem)})
    return out


@router.get("")
def list_documents():
    """母稿层里有哪些稿子。"""
    return {"documents": _listing()}


@router.get("/{doc_id:path}/preview")
def preview_document(doc_id: str):
    """这一篇在 dev server 上的地址。

    **dev server 没跑就现起一个**（站点是本地的，起它不花钱）。
    起不来就明说，**不给一个永远 404 的 iframe**。
    """
    _doc_path(doc_id)          # 不存在 → 404
    running, hint = preview.ensure_site_server()
    return {"url": preview.site_preview_url(doc_id),
            "running": running,
            "hint": hint}


#: 重建的三步。**次序不能换**（见 `rebuild_document` 的说明）。
#: 测试把它换成一条无害命令——真跑一次站点构建要几分钟。
REBUILD_STEPS = (
    commands.document_units_rebuild(),
    commands.video_units_rebuild(),
    commands.site_build(),
)


@router.post("/{doc_id:path}/rebuild")
def rebuild_document(doc_id: str):
    """重建：文档内容单元 → 视频内容单元 → 站点。

    **三步串行，次序不能换**：视频单元必须在文档单元之后
    （学习流的规则表按 id 归类，视频单元晚一步出现就会「漏归类」）。
    """
    _doc_path(doc_id)
    job = RUNNER.submit_steps("rebuild", list(REBUILD_STEPS),
                              key=f"rebuild:{doc_id}")
    return {"job_id": job.id, "status": job.status}


@router.get("/{doc_id:path}")
def get_document(doc_id: str):
    """读一篇母稿：正文原文 + front matter 里的标题。"""
    path = _doc_path(doc_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="没有这一篇")
    text = path.read_text(encoding="utf-8")
    rel = f"docs/{path.relative_to(DOCS_DIR.resolve()).as_posix()}"
    return {"id": doc_id.strip("/"), "path": rel,
            "title": frontmatter.title(text, path.stem),
            "content": text}
