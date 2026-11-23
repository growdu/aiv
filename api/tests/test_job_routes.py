"""作业的路由：查作业、订阅日志。"""
from __future__ import annotations

import sys
import time

from api.services.jobs import RUNNER


def _wait(job_id):
    for _ in range(400):
        job = RUNNER.get(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("作业没在预期时间内结束")


def test_an_unknown_job_is_404(client):
    assert client.get("/api/jobs/j-9999").status_code == 404


def test_a_job_is_listed_with_its_log(client, tmp_path):
    job = RUNNER.submit("probe", [sys.executable, "-c", "print('你好')"], tmp_path)
    done = _wait(job.id)

    body = client.get(f"/api/jobs/{job.id}").json()
    assert body["id"] == job.id
    assert body["status"] == "succeeded"
    assert body["exit_code"] == 0
    assert body["exit_label"] == "ok"
    assert any("你好" in line for line in body["log"])


def test_the_events_route_streams_sse(client, tmp_path):
    job = RUNNER.submit("probe", [sys.executable, "-c", "print('一行')"], tmp_path)
    with client.stream("GET", f"/api/jobs/{job.id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        chunks = []
        for chunk in response.iter_text():
            chunks.append(chunk)
            if '"type": "done"' in "".join(chunks):
                break
    text = "".join(chunks)
    assert "data: " in text
    assert '"type": "log"' in text
