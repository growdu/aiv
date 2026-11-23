"""作业：后台跑、留日志、去重。

**作业调的命令与手敲命令行逐字等价**（反目标 A3）——所以这里只负责
「起进程、收日志、报退出码」，不负责业务。

**退出码有两层**（全局约束 10）：

- `exit_code` 是原始退出码，一个字节都不改。
- `exit_label` 是尽力而为的标签。**原始码本身有损**：
  `pyv/cli.py` 用 `1` 同时表示「用法错」和「内容错」，
  所以 `1` 的标签是 `usage-or-content`，**不是** `usage`。
  不认识的码标 `unknown`——宁可说不知道，也不编一个。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .commands import Command

#: 退出码 → 标签。**1 故意不叫 `usage`**：pyv 用它表示两件事。
EXIT_LABELS = {
    0: "ok",
    1: "usage-or-content",
    2: "precondition",
    3: "failed",
}

#: 日志环形缓冲的容量（行）。
LOG_CAPACITY = 2000


def exit_label(code: int | None) -> str:
    """给一个退出码贴标签。不认识 → `unknown`。"""
    if code is None:
        return "unknown"
    return EXIT_LABELS.get(code, "unknown")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    """一个作业。"""

    id: str
    kind: str
    status: str = "queued"          # queued | running | succeeded | failed
    exit_code: int | None = None
    exit_label: str = "unknown"
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "exit_code": self.exit_code,
            "exit_label": self.exit_label,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "log": list(self.log),
        }

    def note(self, text: str) -> None:
        """往日志里加一行。

        **作业里的 Python 步骤用它说话**（比如「这一期没有旁白」）。
        """
        self.log.append(text)


#: 一步作业。要么是一条命令，要么是一段 Python（自己往 `Job` 的日志里写）。
#: Python 步骤返回**退出码**——非零就停在那一步，后面不跑。
Step = Command | Callable[[Job], int]


class JobRunner:
    """跑作业的地方。

    **同 key 的作业不排队**：重复提交返回**正在跑的那一个**。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._by_key: dict[str, str] = {}
        self._lock = threading.Lock()
        self._counter = 0

    # ── 提交 ────────────────────────────────────────────────────────
    def submit(self, kind: str, argv: list[str], cwd: Path, *,
               key: str | None = None) -> Job:
        """起一个作业。`key` 命中在跑的作业 → 直接返回那一个。"""
        command = Command(argv=list(argv), cwd=Path(cwd), key=key or kind)
        return self.submit_steps(kind, [command], key=key)

    def submit_steps(self, kind: str, steps: list[Step], *,
                     key: str | None = None) -> Job:
        """起一个**串行**的作业：一步不成功，后面的不跑。"""
        effective_key = key or (steps[0].key if steps else kind)
        with self._lock:
            existing_id = self._by_key.get(effective_key)
            if existing_id is not None:
                existing = self._jobs.get(existing_id)
                if existing is not None and existing.status in {"queued", "running"}:
                    return existing
            self._counter += 1
            job_id = f"j-{self._counter:04d}"
            job = Job(id=job_id, kind=kind, status="queued")
            self._jobs[job_id] = job
            self._by_key[effective_key] = job_id

        thread = threading.Thread(target=self._run, args=(job, steps), daemon=True)
        thread.start()
        return job

    # ── 查询 ────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def events(self, job_id: str) -> Iterator[str]:
        """SSE 的 data 行。

        每行一个 JSON：
        - `{"type": "log", "text": "…"}` —— 一行日志
        - `{"type": "done", "status": "…", "exit_code": …, "exit_label": "…"}`
          —— 结束
        """
        seen = 0
        while True:
            job = self.get(job_id)
            if job is None:
                return
            while seen < len(job.log):
                yield json.dumps({"type": "log", "text": job.log[seen]},
                                 ensure_ascii=False)
                seen += 1
            if job.status in {"succeeded", "failed"}:
                yield json.dumps(
                    {"type": "done", "status": job.status,
                     "exit_code": job.exit_code, "exit_label": job.exit_label},
                    ensure_ascii=False)
                return
            time.sleep(0.2)

    # ── 跑 ──────────────────────────────────────────────────────────
    def _append(self, job: Job, line: str) -> None:
        with self._lock:
            job.log.append(line)
            if len(job.log) > LOG_CAPACITY:
                del job.log[: len(job.log) - LOG_CAPACITY]

    def _run(self, job: Job, steps: list[Step]) -> None:
        job.status = "running"
        try:
            for step in steps:
                code = self._run_step(job, step)
                if code != 0:
                    job.exit_code = code
                    job.status = "failed"
                    break
            else:
                job.exit_code = 0
                job.status = "succeeded"
        finally:
            job.exit_label = exit_label(job.exit_code)
            job.finished_at = _now()
            with self._lock:
                for key, job_id in list(self._by_key.items()):
                    if job_id == job.id:
                        del self._by_key[key]

    def _run_step(self, job: Job, step: Step) -> int:
        """跑一步。命令 → 起进程；Python → 直接调。"""
        if isinstance(step, Command):
            return self._run_one(job, step)
        try:
            return int(step(job))
        except Exception as exc:                      # noqa: BLE001
            # 作业里炸了要**报出来**，不能变成一句「失败了」。
            job.note(f"这一步炸了：{exc!r}")
            return 3

    def _run_one(self, job: Job, command: Command) -> int:
        """跑一条命令，逐行收日志。**不用 shell**。"""
        self._append(job, f"$ {' '.join(command.argv)}")
        try:
            process = subprocess.Popen(
                command.argv,
                cwd=str(command.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
            )
        except OSError as exc:
            self._append(job, f"起不来：{exc}")
            return 2

        assert process.stdout is not None
        for line in process.stdout:
            self._append(job, line.rstrip("\n"))
        process.wait()
        return process.returncode


#: 门面只有一个进程、一个用户——**一个共用的作业池**就够了。
RUNNER = JobRunner()


def capture(command: Command, *, timeout: float = 60.0) -> tuple[int, str]:
    """跑一条命令，**把输出收回来**。返回 `(退出码, stdout)`。

    **只给「读输出」的场合用**（审校信号）。要留日志的场合用 `JobRunner`。

    超时或起不来 → `(2, 一句人话)`——退出码 2 的意思是「前置条件没满足」。
    **不用 shell**：argv 逐个传参，期路径里的中文与空格才不会被拆词。
    """
    try:
        process = subprocess.run(
            command.argv,
            cwd=str(command.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return 2, "命令超时了"
    except OSError as exc:
        return 2, f"起不来：{exc}"
    return process.returncode, process.stdout or ""
