"""作业的路由：查一个作业、订阅它的日志。

**作业调的命令与手敲命令行逐字等价**——门面只负责起进程、收日志、
报退出码。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..services.jobs import RUNNER

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str):
    """查一个作业：状态、退出码、日志。"""
    job = RUNNER.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="没有这个作业")
    return job.to_dict()


@router.get("/{job_id}/events")
def job_events(job_id: str):
    """订阅作业的日志（SSE）。

    每条事件的 `data:` 是一个 JSON：
    `{"type": "log", "text": "…"}` 或
    `{"type": "done", "status": "…", "exit_code": …, "exit_label": "…"}`。
    """
    if RUNNER.get(job_id) is None:
        raise HTTPException(status_code=404, detail="没有这个作业")

    def stream():
        for payload in RUNNER.events(job_id):
            yield f"data: {payload}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
