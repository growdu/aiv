import os
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: 夹具期的目录：口播稿 + 契约。格式与真的一期一样，只是内容不算数。
#:
#: **目录名就是 slug**（协议 §五）：期目录名是身份，front matter 的
#: `episode` 跟它一致。
FIXTURE_EPISODE_DIR = FIXTURES_DIR / "fixture"

#: 夹具期的 slug。
FIXTURE_EPISODE = "fixture"


@pytest.fixture
def fixture_episode_dir() -> Path:
    """夹具期的目录。"""
    return FIXTURE_EPISODE_DIR


@pytest.fixture
def fixture_episode():
    """夹具期（`pyv.episodes.Episode`）。"""
    from pyv import episodes

    return episodes.episode_at(FIXTURE_EPISODE_DIR, FIXTURE_EPISODE)
