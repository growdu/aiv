"""Cross-platform exclusive file locks.

**Why this module exists.**  The publish ledger and the material cache are
single files that every writer reads in full and writes back in full.  Two
writers doing that at the same moment lose each other's entries, and a
draft that is in the box but missing from the ledger is created a second
time on the next run -- the one failure the whole idempotency exists to
prevent.

``fcntl`` is the obvious tool for that, but it only exists on Unix.  On
Windows the obvious replacement, ``msvcrt.locking``, is **not** one:

- it locks a byte range, and the range has to exist -- an empty file
  cannot be locked at all;
- the lock belongs to the *process*, so a second thread of the same
  process cannot take the same range and just fails, which turns the
  "two writers" case into a spin instead of a wait;
- reading a byte somebody else locked raises ``PermissionError`` instead
  of returning the data.

So Windows gets a **named mutex** instead.  A mutex is exactly what
``flock`` is used for here: it is released when the holder dies (the next
waiter gets ``WAIT_ABANDONED`` and carries on), it is shared by every
process on the machine that uses the same name, and it is owned by a
*thread*, so two threads of one process wait for each other properly.

Callers just write::

    with locking_module.exclusive(lock_path):
        ...
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path

__all__ = ["exclusive"]


if os.name == "nt":
    import ctypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # HANDLE is a pointer: the default ctypes return type (c_int) would
    # truncate it on a 64-bit Windows and every call would fail with an
    # invalid handle.
    _kernel32.CreateMutexW.restype = ctypes.c_void_p
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                       ctypes.c_wchar_p]
    _kernel32.WaitForSingleObject.restype = ctypes.c_int
    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.ReleaseMutex.restype = ctypes.c_int
    _kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_ABANDONED = 0x00000080
    _WAIT_FAILED = 0xFFFFFFFF
    _INFINITE = 0xFFFFFFFF

    def _mutex_name(path: Path) -> str:
        """A machine-wide name for one lock file.

        The path is hashed, so two lock files never share a mutex and one
        lock file always gets the same one -- whatever the working
        directory is.
        """
        digest = hashlib.sha256(
            str(path.resolve()).encode("utf-8")).hexdigest()
        # "Local\\" keeps the mutex inside the current session, so two
        # logged-in users do not share one.
        return "Local\\wechat-lock-" + digest[:24]

    @contextmanager
    def _windows_exclusive(path: Path):
        # The lock file itself stays, so the tool's layout does not
        # change; its content is never used.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        handle = _kernel32.CreateMutexW(None, False, _mutex_name(path))
        if not handle:
            raise OSError("CreateMutexW failed for {}".format(path))
        try:
            waited = _kernel32.WaitForSingleObject(handle, _INFINITE)
            if waited not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
                # WAIT_ABANDONED means the previous holder died while
                # holding it: we own it now, so that is not an error.
                raise OSError(
                    "WaitForSingleObject failed for {}".format(path))
            try:
                yield
            finally:
                _kernel32.ReleaseMutex(handle)
        finally:
            _kernel32.CloseHandle(handle)

else:
    import fcntl

    @contextmanager
    def _unix_exclusive(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive(path: str | Path):
    """Hold an exclusive lock on *path* for the duration of the block."""
    target = Path(path)
    if os.name == "nt":
        with _windows_exclusive(target):
            yield
    else:
        with _unix_exclusive(target):
            yield
