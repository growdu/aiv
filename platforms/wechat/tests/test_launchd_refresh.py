"""Tests for the launchd template that refreshes the existing draft box.

This job is the second one launchd runs for this tool: the auto-draft
job only handles new documents, this one pushes the already-drafted
corpus to the current pipeline version. It runs on its own, so the
arguments it carries are worth pinning down — the ``--limit`` is what
keeps the round inside the daily call budget, and the label is what
tells the two jobs apart in ``launchctl list``.
"""
import plistlib
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[1] / "deploy" / "launchd-refresh.plist.template"
)


def _load() -> dict:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = (text.replace("__PYTHON__", "/usr/bin/python3")
                .replace("__REPO__", "/repo")
                .replace("__HOME__", "/home/me"))
    return plistlib.loads(text.encode("utf-8"))


def test_the_job_has_the_expected_label():
    assert _load()["Label"] == "com.growdu.weixin.refresh-drafts"


def test_the_job_refreshes_the_existing_drafts():
    """``batch`` re-pushes what is already in the draft box; the limit
    keeps one round inside the daily call budget.
    """
    args = _load()["ProgramArguments"]
    assert args[-4:] == ["wechat.cli", "batch", "--limit", "100"]


def test_the_job_runs_inside_the_platforms_directory():
    config = _load()
    assert config["WorkingDirectory"].endswith("/platforms")
    assert config["EnvironmentVariables"]["PYTHONPATH"].endswith("/platforms")


def test_the_log_goes_to_the_library_logs_folder():
    config = _load()
    assert config["StandardOutPath"].endswith("/Library/Logs/weixin-refresh-drafts.log")
    assert config["StandardErrorPath"] == config["StandardOutPath"]


def test_the_schedule_runs_every_six_hours():
    slots = _load()["StartCalendarInterval"]
    assert [(slot["Hour"], slot["Minute"]) for slot in slots] == [
        (0, 30),
        (6, 30),
        (12, 30),
        (18, 30),
    ]


def test_the_template_is_committed():
    """A template that is missing from the package cannot be installed."""
    assert TEMPLATE.is_file()
