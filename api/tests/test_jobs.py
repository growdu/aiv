"""作业：后台跑、留日志、去重。"""
from __future__ import annotations

import sys
import time

from api.services.jobs import EXIT_LABELS, JobRunner, exit_label


def _wait(runner, job_id):
    for _ in range(400):
        job = runner.get(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("作业没在预期时间内结束")


def test_exit_one_is_not_called_a_usage_error():
    """pyv 用 1 同时表示「用法错」和「内容错」——标错就是撒谎。"""
    assert exit_label(1) == "usage-or-content"
    assert exit_label(0) == "ok"
    assert exit_label(2) == "precondition"
    assert exit_label(3) == "failed"
    assert exit_label(99) == "unknown"


def test_the_exit_table_matches_the_capability_files():
    """api 不 import 契约层（D12），但**数字**必须与各平台的 [exit] 表一致。"""
    import tomllib

    from api.services.paths import PLATFORMS_DIR

    checked = 0
    for cap in sorted(PLATFORMS_DIR.glob("*/capability.toml")):
        data = tomllib.loads(cap.read_text(encoding="utf-8"))
        table = data.get("exit") or {}
        if not table:
            continue
        checked += 1
        assert table.get("ok") == 0
        assert table.get("usage") == 1
        assert table.get("precondition") == 2
        assert table.get("failed") == 3
        assert EXIT_LABELS[table["usage"]] == "usage-or-content"
    assert checked, "应该至少有一个平台声明了 [exit]"


def test_a_job_runs_and_collects_its_log(tmp_path):
    runner = JobRunner()
    job = runner.submit("probe", [sys.executable, "-c", "print('你好')"], tmp_path)
    done = _wait(runner, job.id)
    assert done.status == "succeeded"
    assert done.exit_code == 0
    assert done.exit_label == "ok"
    assert any("你好" in line for line in done.log)


def test_a_failing_job_reports_its_exit_code(tmp_path):
    runner = JobRunner()
    job = runner.submit("probe", [sys.executable, "-c", "raise SystemExit(2)"], tmp_path)
    done = _wait(runner, job.id)
    assert done.status == "failed"
    assert done.exit_code == 2
    assert done.exit_label == "precondition"


def test_resubmitting_the_same_key_returns_the_running_job(tmp_path):
    """同一期连点两次「出片」——只能有一个 make 在跑。"""
    runner = JobRunner()
    argv = [sys.executable, "-c", "import time; time.sleep(2)"]
    first = runner.submit("build", argv, tmp_path, key="ep-1")
    second = runner.submit("build", argv, tmp_path, key="ep-1")
    assert second.id == first.id


def test_a_new_key_starts_a_new_job(tmp_path):
    runner = JobRunner()
    argv = [sys.executable, "-c", "import time; time.sleep(2)"]
    first = runner.submit("build", argv, tmp_path, key="ep-1")
    second = runner.submit("build", argv, tmp_path, key="ep-2")
    assert second.id != first.id


def test_the_argv_is_passed_as_a_list_not_a_shell_string(tmp_path):
    """期路径含中文与空格——拼 shell 字符串会被拆词。"""
    runner = JobRunner()
    job = runner.submit("probe",
                        [sys.executable, "-c",
                         "import sys; print(sys.argv[1])", "系列/合集/文档/short"],
                        tmp_path)
    done = _wait(runner, job.id)
    assert "系列/合集/文档/short" in "\n".join(done.log)


def test_serial_steps_stop_at_the_first_failure(tmp_path):
    from api.services.commands import Command

    runner = JobRunner()
    marker = tmp_path / "second-ran"
    steps = [
        Command(argv=[sys.executable, "-c", "raise SystemExit(3)"],
               cwd=tmp_path, key="s1"),
        Command(argv=[sys.executable, "-c",
                      f"open({str(marker)!r}, 'w').write('x')"],
               cwd=tmp_path, key="s2"),
    ]
    job = runner.submit_steps("rebuild", steps)
    done = _wait(runner, job.id)
    assert done.exit_code == 3
    assert not marker.exists()
