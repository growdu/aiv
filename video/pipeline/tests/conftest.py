import os
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: 夹具期的**期根**：夹具期就摆在这个根下面，形状跟真的一样——
#: 四层（系列 / 合集 / 文档 / 档位）。
FIXTURE_ROOT = FIXTURES_DIR

#: 夹具期的期路径（相对期根，四层）。
#:
#: **目录就是身份**：front matter 的 `episode` 记的是**文档路径**
#: （三层，去掉档位），`tier` 记的是档位，`episode_number` 才是期号。
FIXTURE_EPISODE = "演示系列/演示合集/夹具文档/short"

#: 夹具期的期目录。
FIXTURE_EPISODE_DIR = FIXTURE_ROOT / FIXTURE_EPISODE


@pytest.fixture
def fixture_episode_dir() -> Path:
    """夹具期的目录。"""
    return FIXTURE_EPISODE_DIR


@pytest.fixture
def fixture_episode():
    """夹具期（`pyv.episodes.Episode`）。"""
    from pyv import episodes

    return episodes.episode_at(FIXTURE_EPISODE_DIR, FIXTURE_EPISODE)
