"""The package has to import on every platform a developer uses.

**Why this file exists.**  ``fcntl`` only exists on Unix.  When
``wechat.state`` imported it at module level, the whole test suite stopped
being *collectable* on Windows: five modules raised ``ModuleNotFoundError``
while pytest was still collecting, so not a single assertion ran.  A
suite that cannot be collected is not a suite -- it is a comment.

So the rule is written down where it can be checked:

- no module may import a Unix-only module;
- the one module that has to (the lock) must do it behind a platform
  branch, not at the top of the file;
- asking whether a process is alive must not kill it (``os.kill(pid, 0)``
  is ``TerminateProcess`` on Windows).
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
LOCKING = PACKAGE / "locking.py"

# Modules that only exist on Unix.  Importing one of them at module
# level takes the whole package down on Windows.
UNIX_ONLY = ("fcntl", "pwd", "grp", "termios", "resource", "syslog", "tty",
             "pty", "select", "poll", "posix", "linux", "darwin")


def _imports(path: Path) -> set[str]:
    """The top-level module names that *path* imports."""
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("name", UNIX_ONLY)
def test_no_module_imports_a_unix_only_module(name):
    """除了锁模块，谁都不许碰 Unix-only 的模块。

    锁模块必须碰 ``fcntl``（Unix 上就是它），但它得在平台分支里碰。
    """
    offenders = sorted(
        path.name for path in PACKAGE.rglob("*.py")
        if path != LOCKING and name in _imports(path))
    assert not offenders, (
        "{} 里有模块 import 了 {}：Windows 上整个套件收集不起来"
        .format(offenders, name))


def test_the_lock_module_only_imports_fcntl_behind_a_platform_branch():
    """锁模块的 ``fcntl`` 必须在平台分支里，不是在文件头上。

    文件头的 import 是**无条件**执行的——Windows 上照样会炸。
    """
    tree = ast.parse(LOCKING.read_text(encoding="utf-8"))
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    guarded.update(alias.name.split(".")[0]
                                  for alias in child.names)
    top_level = _imports(LOCKING)
    assert "fcntl" not in top_level, "fcntl 回到了文件头，Windows 上直接炸"
    assert "fcntl" in guarded, "锁模块里找不到被平台分支护住的 fcntl"


def test_asking_whether_a_process_is_alive_does_not_kill_it():
    """问「这个 pid 还活着吗」不该把被问的那个进程杀掉。

    ``os.kill(pid, 0)`` 是 Unix 的问法。Windows 上 ``os.kill`` 映射到
    ``TerminateProcess``——问一句就把人家杀了。
    """
    from wechat.cli import _pid_alive

    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert _pid_alive(sleeper.pid) is True
        assert sleeper.poll() is None, "问活性的动作把那个进程杀了"
    finally:
        sleeper.kill()
        sleeper.wait()


def test_a_pid_that_is_not_running_is_reported_as_dead():
    """pid 不在时要说死——锁在崩溃后留下的 pid 得能被接管。"""
    from wechat.cli import _pid_alive

    assert _pid_alive(999999) is False


def test_the_lock_works_on_this_platform():
    """这台机器上锁要真的能拿住——Windows 走互斥量，Unix 走 flock。"""
    from wechat import locking

    with locking.exclusive(Path(os.environ.get("TEMP", "/tmp")) / "wechat-lock-probe.lock"):
        pass
