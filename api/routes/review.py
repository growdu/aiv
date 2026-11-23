"""统一审校的路由：两条线一张表。

**信号不是门禁**（全局约束 11）：这里返回的 `gate` **只看审校记录的状态**。
命中的信号在 `signals` 里摆着给人看——**不影响**能不能过。

**两条线的表列名不一样**（`review/INDEX.md` 七列、`video/review/INDEX.md` 八列），
所以**各自解析、各自投影**到公共子集，不硬凑一张大表。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..services import commands
from ..services import review as review_service
from ..services.jobs import RUNNER, capture
from ..services.paths import DOCS_DIR, EPISODES_DIR, REPO_ROOT

router = APIRouter(prefix="/api/review", tags=["review"])

#: 两条线那张表的**第一列表头**——用它认出哪张表是要读的那张。
DOC_TABLE_HEAD = "记录"
VIDEO_TABLE_HEAD = "期号"

#: 表里的一格是 markdown 链接：`[标题](路径)`。
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _is_separator(cells: list[str]) -> bool:
    """表头下面那行 `| --- | --- |`。"""
    return bool(cells) and all(set(c) <= set("-: ") for c in cells)


def _table_rows(path: Path, head: str) -> list[list[str]]:
    """找**第一列表头是 `head`** 的表，读它下面的行。

    **别写死行号**——这两个文件是给人改的，行数会变。
    认表的办法是「**这一行的下一行是分隔行**」——
    光看第一列会认错（`review/INDEX.md` 里那张说明表就有一行以「记录」开头）。
    """
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0] != head:
            continue
        if index + 1 >= len(lines):
            continue
        following = lines[index + 1].strip()
        if not following.startswith("|"):
            continue
        if not _is_separator([c.strip() for c in following.strip("|").split("|")]):
            continue
        rows = []
        for row_line in lines[index + 2:]:
            row_stripped = row_line.strip()
            if not row_stripped.startswith("|"):
                break
            row = [c.strip() for c in row_stripped.strip("|").split("|")]
            if _is_separator(row):
                continue
            rows.append(row)
        return rows
    return []


def _int(cell: str) -> int:
    """表里的一格数字。读不出来 → 0（**不编**）。"""
    try:
        return int(cell.strip())
    except (TypeError, ValueError):
        return 0


def _link_target(cell: str) -> str:
    """`[标题](路径)` → 路径；不是链接就原样返回。"""
    match = LINK.search(cell)
    return match.group(2).strip() if match else cell.strip()


def _document_rows(repo_root: Path) -> list[dict]:
    """文档线那张表 → 公共子集。"""
    rows = []
    for cells in _table_rows(repo_root / "review" / "INDEX.md", DOC_TABLE_HEAD):
        if len(cells) < 7:
            continue
        target = _link_target(cells[0])
        doc_id = target[:-len(".md")] if target.endswith(".md") else target
        rows.append({
            "layer": "document",
            "id": doc_id,
            "title": "",
            "status": cells[2],
            "signals": _int(cells[3]),
            "pending": _int(cells[4]),
            "batch": cells[6],
        })
    return rows


def _episode_rows(repo_root: Path) -> list[dict]:
    """视频线那张表 → 公共子集。**信号是两层的和。**"""
    rows = []
    for cells in _table_rows(repo_root / "video" / "review" / "INDEX.md",
                             VIDEO_TABLE_HEAD):
        if len(cells) < 8:
            continue
        rows.append({
            "layer": "episode",
            "id": cells[1],
            "title": cells[2],
            "status": cells[3],
            "signals": _int(cells[4]) + _int(cells[5]),
            "pending": _int(cells[6]),
            "batch": cells[7],
        })
    return rows


def _empty_report(layer: str, subject_id: str, path: str, note: str,
                  repo_root: Path) -> dict:
    """命令没跑成时的那份报告：**形状一样，只是没有信号。**

    **不假装有信号，也不假装没问题**——notes 里说清楚出了什么事。
    """
    if layer == "document":
        gate = review_service.document_gate(subject_id, repo_root=repo_root)
    else:
        gate = review_service.episode_gate(subject_id, repo_root=repo_root)
    return {
        "subject": {"kind": layer, "id": subject_id, "path": path},
        "layer": layer,
        "counts": {"error": 0, "warn": 0, "info": 0},
        "signals": [],
        "notes": [note],
        "gate": gate,
    }


@router.get("/overview")
def review_overview():
    """两条线的进度表合并成一张。

    **各自解析、各自投影**——两条线的列名不一样，不硬凑。
    """
    rows = _document_rows(REPO_ROOT) + _episode_rows(REPO_ROOT)
    return {"rows": rows}


@router.post("/episodes/{episode:path}/run")
def run_episode_review(episode: str):
    """起作业跑一遍审校（文本层 + 成片层）。"""
    episode = episode.strip("/")
    if not (EPISODES_DIR / episode).is_dir():
        raise HTTPException(status_code=404, detail="没有这一期")
    steps = [commands.video_review_text(episode),
             commands.video_review_video(episode)]
    job = RUNNER.submit_steps("review", steps, key=f"review:{episode}")
    return {"job_id": job.id, "status": job.status}


@router.get("/documents/{doc_id:path}")
def review_document(doc_id: str):
    """文档流的审校：信号 + 审校记录的状态。"""
    doc_id = doc_id.strip("/")
    if not (DOCS_DIR / f"{doc_id}.md").is_file():
        raise HTTPException(status_code=404, detail="没有这一篇")
    rel = f"docs/{doc_id}.md"
    code, out = capture(commands.document_review(rel))
    if code != 0:
        return _empty_report("document", doc_id, rel,
                             f"审校命令没跑成（退出码 {code}）：{out.strip()}",
                             REPO_ROOT)
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return _empty_report("document", doc_id, rel,
                             "审校命令的输出不是 JSON", REPO_ROOT)
    return review_service.normalize_document_report(
        raw, doc_id=doc_id, path=rel, repo_root=REPO_ROOT)


@router.get("/episodes/{episode:path}")
def review_episode(episode: str):
    """视频流的审校：文本层信号 + 这一期 `review.md` 的状态。"""
    episode = episode.strip("/")
    if not (EPISODES_DIR / episode).is_dir():
        raise HTTPException(status_code=404, detail="没有这一期")
    code, out = capture(commands.video_review_text(episode))
    if code != 0:
        return _empty_report("episode", episode, f"video/episodes/{episode}",
                             f"审校命令没跑成（退出码 {code}）：{out.strip()}",
                             REPO_ROOT)
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return _empty_report("episode", episode, f"video/episodes/{episode}",
                             "审校命令的输出不是 JSON", REPO_ROOT)
    return review_service.normalize_pyv_report(
        raw, subject={"kind": "episode", "id": episode}, repo_root=REPO_ROOT)
