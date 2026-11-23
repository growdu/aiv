"""api/ 的测试夹具。**夹具只造语料，不依赖仓库里现有的内容**——
依赖「仓库里曾经有过的内容」的用例，迟早会因为内容被清掉而变成假红。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
