"""Find a Chromium-family browser and drive it headless.

Two parts of this kit need a browser: the SVG rasteriser
(``wechat/svg.py``) and the mermaid renderer (``wechat/mermaid.py``).
Both used to look for Chrome in the same five places -- the macOS app
bundle and three Linux binaries -- so on a Windows machine neither
could find anything and both gave up on their own.

Finding the browser is only half of it.  The headless command line has
to match the browser in front of it:

- ``--headless`` alone is not enough everywhere.  Chrome 132 dropped
  the old headless mode, and a headless run that shares the *default*
  profile with a Chrome that is already open can end up doing nothing
  at all: it exits 0 and writes no picture.
- So every run gets its own throw-away ``--user-data-dir``, and the
  spelling of the flag is tried in the order the installed browser
  understands.  The first spelling is the one this kit has always
  used, so a machine that worked before still takes exactly that path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

__all__ = ["find_chrome", "screenshot", "RENDER_TIMEOUT"]

RENDER_TIMEOUT = 60

# The browsers on macOS and Linux, in the order they are preferred.
_POSIX_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

# Windows keeps its browsers under Program Files, and the folder name
# differs between a 64-bit and a 32-bit install, so every known root
# is tried.  Edge is here because Windows ships it and it takes the
# same command line; it is only reached when Chrome is not installed.
_WINDOWS_ROOTS = ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
_WINDOWS_RELATIVE = (
    ("Google", "Chrome", "Application", "chrome.exe"),
    ("Microsoft", "Edge", "Application", "msedge.exe"),
)

# The spellings of the headless flag, oldest first.  "--headless" is
# what this kit has always used and still works on Chrome 157; the
# other two are the explicit names of the old and the new mode, which
# is what a browser that has dropped one of them wants to see.
HEADLESS_FLAG_VARIANTS = (
    ("--headless",),
    ("--headless=new",),
    ("--headless=old",),
)


def chrome_candidates() -> tuple:
    """Every path a browser may live at, in the order they are tried."""
    candidates = list(_POSIX_CANDIDATES)
    if os.name == "nt":
        for root in _WINDOWS_ROOTS:
            base = os.environ.get(root)
            if not base:
                continue
            for relative in _WINDOWS_RELATIVE:
                candidates.append(os.path.join(base, *relative))
    return tuple(candidates)


def find_chrome() -> str | None:
    """The browser on this machine, or ``None`` when there is none."""
    for candidate in chrome_candidates():
        if Path(candidate).exists():
            return candidate
    return None


@contextmanager
def _private_profile():
    """A throw-away profile directory for one headless run.

    Chrome is left alone -- it never touches the real profile -- and a
    run that shares the default profile with an open Chrome window can
    quietly do nothing instead of drawing the picture.
    """
    directory = tempfile.mkdtemp(prefix="wechat-chrome-")
    try:
        yield directory
    finally:
        # Chrome may still hold a file or two on Windows; the profile is
        # throw-away, so a leftover is not worth an error.
        shutil.rmtree(directory, ignore_errors=True)


def screenshot(chrome: str, target: Path, width: int, height: int,
               source: Path, timeout: int = RENDER_TIMEOUT) -> tuple:
    """Draw *source* with a headless browser and save it as *target*.

    Returns ``(ok, detail)``.  ``detail`` is the reason when ``ok`` is
    false, and empty when the picture was written.
    """
    target = Path(target)
    uri = Path(source).resolve().as_uri()
    failures = []

    for flags in HEADLESS_FLAG_VARIANTS:
        with _private_profile() as profile:
            command = [chrome]
            command.extend(flags)
            command.extend([
                "--user-data-dir={}".format(profile),
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--default-background-color=FFFFFFFF",
                "--screenshot={}".format(target),
                "--window-size={},{}".format(width, height),
                uri,
            ])
            try:
                result = subprocess.run(
                    command, capture_output=True, timeout=timeout,
                    encoding="utf-8", errors="replace")
            except FileNotFoundError:
                return False, "找不到 Chrome: {}".format(chrome)
            except subprocess.TimeoutExpired:
                failures.append("{} 超时（{} 秒）".format(
                    " ".join(flags), timeout))
                continue

        if target.is_file() and target.stat().st_size > 0:
            return True, ""

        lines = (result.stderr or result.stdout or "").strip().splitlines()
        detail = lines[-1][:200] if lines else "没有输出"
        failures.append("{} 返回 {} —— {}".format(
            " ".join(flags), result.returncode, detail))

    return False, "; ".join(failures)
