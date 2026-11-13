import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "weixin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "weixin"))

SOURCE_POSTS = REPO_ROOT / "source" / "_posts"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    """Keep the developer's own credentials out of every test.

    A real ``WX_APPID`` in the developer's shell, or a real
    ``weixin/secrets.json``, must never change what a test does -- and
    must never be sent to a test's fake server.  Tests that need
    credentials set their own.
    """
    monkeypatch.delenv("WX_APPID", raising=False)
    monkeypatch.delenv("WX_APPSECRET", raising=False)
    monkeypatch.delenv("WX_SOURCE_URL", raising=False)
    monkeypatch.delenv("WX_COVER", raising=False)


@pytest.fixture(autouse=True)
def isolated_outbox(monkeypatch, tmp_path_factory):
    """Point the outbox snapshot at a temporary directory.

    发布状态快照的默认位置是仓库里的 ``publish/outbox/``——那是要入库的
    幂等键，不是测试的沙箱。测试写进去会污染工作树（头条号那边有一条
    守卫测试专门抓这个），所以这里把它挪到临时目录。
    """
    outbox = tmp_path_factory.mktemp("outbox")
    monkeypatch.setenv("PUBLISH_OUTBOX_DIR", str(outbox))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def source_posts() -> Path:
    return SOURCE_POSTS
