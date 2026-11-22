import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "platforms") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "platforms"))

SOURCE_POSTS = REPO_ROOT / "source" / "_posts"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    """Keep the developer's own credentials out of every test.

    A real ``WX_APPID`` in the developer's shell, or a real
    ``platforms/wechat/secrets.json``, must never change what a test does -- and
    must never be sent to a test's fake server.  Tests that need
    credentials set their own.
    """
    monkeypatch.delenv("WX_APPID", raising=False)
    monkeypatch.delenv("WX_APPSECRET", raising=False)
    monkeypatch.delenv("WX_COVER", raising=False)
    # 站点地址：夹具**注入**一个，而不是把它删掉。公众号的「阅读原文」
    # 需要它——没有它就退 2（缺前置条件），整个套件会整片变红。
    # setenv 顺带把开发者本机真设的 ``SITE_URL`` 盖掉：那个值也不该
    # 改写任何一条用例。域名取 ``https://growdu.cn``——与这套件今天用的
    # 硬编码默认值是同一个，那些断言前后都成立。
    monkeypatch.setenv("SITE_URL", "https://growdu.cn")


@pytest.fixture(autouse=True)
def isolated_outbox(monkeypatch, tmp_path_factory):
    """Point the outbox snapshot at a temporary directory.

    发布状态快照的默认位置是仓库里的 ``platforms/wechat/outbox/``——那是要入库的
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
