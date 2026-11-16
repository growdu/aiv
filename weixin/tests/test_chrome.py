"""The browser has to be found, and driven, the same way on every platform.

**Why this file exists.**  ``wechat.svg`` and ``wechat.mermaid`` both
need a browser, and both used to look for one in five places -- the
macOS app bundle and three Linux binaries -- and nowhere else.  On
Windows they found nothing, so every SVG was reported as an unusable
image and every mermaid diagram came back as an error.

Finding the browser is only half of the story.  A headless run that
shares the *default* Chrome profile with a Chrome that is already open
can end up doing nothing at all: it exits 0 and writes no picture.  So
every run gets its own throw-away profile, and the spelling of the
headless flag is tried in turn -- the old one first, because that is
the one this kit has always used.
"""

import os
from pathlib import Path

import pytest

from wechat import chrome as chrome_module


class _FakeResult:
    """What ``subprocess.run`` gives back."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_runner(draw_on_attempt=None, returncode=0, stderr=""):
    """A stand-in for ``subprocess.run`` that records the commands.

    *draw_on_attempt* is the number of the call that leaves a picture
    behind; the earlier calls exit 0 without drawing anything, which is
    exactly what a Chrome that shares a profile with an open window
    does.
    """
    calls = []

    def run(command, **kwargs):
        calls.append(list(command))
        if draw_on_attempt is not None and len(calls) == draw_on_attempt:
            target = next(a for a in command if a.startswith("--screenshot="))
            Path(target.split("=", 1)[1]).write_bytes(b"\x89PNG\r\n\x1a\n")
        return _FakeResult(returncode=returncode, stderr=stderr)

    return run, calls


def _screenshot_of(command):
    target = next(a for a in command if a.startswith("--screenshot="))
    return target.split("=", 1)[1]


@pytest.mark.skipif(os.name != "nt", reason="Windows 上的浏览器位置")
def test_the_browser_is_looked_for_where_windows_keeps_it():
    """Windows 上浏览器在 Program Files 底下，不是 /usr/bin。"""
    candidates = chrome_module.chrome_candidates()
    assert any(c.lower().endswith("chrome.exe") for c in candidates)
    # Edge 一直跟着 Windows 装，Chrome 没装时它能顶上。
    assert any(c.lower().endswith("msedge.exe") for c in candidates)


def test_the_browser_that_is_found_is_a_real_file():
    """找到的得是真在那儿的浏览器，不能是拼出来的路径。"""
    found = chrome_module.find_chrome()
    if found is None:
        pytest.skip("this machine has no browser")
    assert Path(found).is_file()
    assert Path(found).is_absolute()


def test_every_headless_run_gets_its_own_profile(tmp_path, monkeypatch):
    """每次无头渲染都得有自己的 profile。

    共用默认 profile 的话，无头请求可能落进已经开着的那个窗口，
    结果是退出 0，一张图也不画。
    """
    run, calls = _fake_runner(draw_on_attempt=1)
    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    ok, detail = chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert ok is True, detail
    assert len(calls) == 1
    profiles = [a for a in calls[0] if a.startswith("--user-data-dir=")]
    assert len(profiles) == 1
    assert not Path(profiles[0].split("=", 1)[1]).exists(), \
        "临时 profile 目录没被清掉"


def test_a_run_that_draws_nothing_is_tried_again_with_the_next_spelling(
        tmp_path, monkeypatch):
    """第一种写法画不出图时，要换下一种写法再试一次。"""
    run, calls = _fake_runner(draw_on_attempt=2)
    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    ok, detail = chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert ok is True, detail
    assert len(calls) == 2, "第一种写法没画出图，却没再试"
    assert "--headless=new" in calls[1]
    assert calls[0] != calls[1]


def test_the_first_spelling_is_the_one_the_kit_has_always_used(tmp_path, monkeypatch):
    """老写法排第一——以前能跑通的机器，还是走以前那条路。"""
    run, calls = _fake_runner(draw_on_attempt=1)
    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert "--headless" in calls[0]
    assert "--headless=new" not in calls[0]
    assert "--headless=old" not in calls[0]


def test_when_every_spelling_fails_the_reason_is_reported(tmp_path, monkeypatch):
    """全都失败时，要把 Chrome 说的话带出来，不能只说一句「失败了」。"""
    run, calls = _fake_runner(returncode=1, stderr="something went wrong")
    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    ok, detail = chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert ok is False
    assert "something went wrong" in detail
    assert len(calls) == len(chrome_module.HEADLESS_FLAG_VARIANTS)


def test_a_picture_that_came_out_empty_is_not_taken_for_a_picture(
        tmp_path, monkeypatch):
    """画了个 0 字节的文件不算画出来了。"""

    def run(command, **kwargs):
        Path(_screenshot_of(command)).write_bytes(b"")
        return _FakeResult(returncode=0)

    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    ok, detail = chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert ok is False
    assert detail


def test_a_missing_browser_is_said_so(tmp_path, monkeypatch):
    """浏览器压根没有时，要说清楚是没有浏览器。"""
    def run(command, **kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(chrome_module.subprocess, "run", run)

    ok, detail = chrome_module.screenshot(
        "chrome", tmp_path / "out.png", 10, 10, tmp_path / "a.svg")

    assert ok is False
    assert "chrome" in detail


def test_the_svg_renderer_and_the_browser_module_look_in_the_same_place():
    """SVG 与 mermaid 得看同一个地方——不然一个找到另一个找不到。"""
    from wechat import mermaid as mermaid_module
    from wechat import svg as svg_module

    assert svg_module._find_chrome() == chrome_module.find_chrome()
    assert mermaid_module._find_chrome() == chrome_module.find_chrome()
