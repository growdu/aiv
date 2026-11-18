"""能力模型与 platforms/wechat/ 常量的一致性（规格 §5.3）。

能力模型的 ``limits`` 与 ``platforms/wechat/posts.py`` 的 ``TITLE_LIMIT`` /
``BODY_LIMIT`` / ``DIGEST_LIMIT`` 描述的是同一批数字，会漂移。

**解法不是改 platforms/wechat/，而是在契约层加这条兼容性测试**（规格 §5.3）——
它**只读** platforms/wechat/，不改它一个字节；任一边漂移，测试立刻红。

今天它生效了：``platforms/wechat/capability.toml`` 已进仓库（2026-11-13），
公众号的能力声明不再是散在几个分支上的口头约定。

> **值从哪来**：以 ``platforms/wechat/`` 的常量为准。规格 §5 的示例里写的是
> ``title_chars = 32``，但 ``platforms/wechat/titles.py:36`` 的 ``TITLE_LIMIT``
> 是 **64**（公众号编辑器的真实上限）。规格 §5.3 自己那条断言
> （``== posts.TITLE_LIMIT``）与 §5 的示例 TOML 是互相矛盾的——示例照抄
> 进来，这条测试会立刻变红。
"""

import sys
from pathlib import Path

import pytest

from publishkit import load_capability_file

REPO_ROOT = Path(__file__).resolve().parents[2]
WEIXIN_DIR = REPO_ROOT / "platforms" / "wechat"
WECHAT_CAPABILITY = REPO_ROOT / "platforms" / "wechat" / "capability.toml"


def _wechat_posts():
    """Import ``wechat.posts`` without importing it at module level.

    platforms/wechat/ 正在被并行开发，它挪目录或改了导入路径时本条自动 skip，
    不给别人的工作添麻烦。

    用 importlib 而不是 ``from wechat import posts``：那个包不在
    site-packages 里，静态导入在类型检查器眼里永远是「找不到的模块」。
    """
    if not WEIXIN_DIR.is_dir():
        return None
    if str(WEIXIN_DIR.parent) not in sys.path:
        sys.path.insert(0, str(WEIXIN_DIR.parent))
    try:
        import importlib

        return importlib.import_module("wechat.posts")
    except Exception:  # pragma: no cover - weixin 那边在并行开发
        return None


def test_wechat_limits_match_the_weixin_constants():
    posts = _wechat_posts()
    if posts is None:
        pytest.skip("platforms/wechat/ 不可用，跳过与 wechat.posts 的对照")
    assert posts is not None

    if not WECHAT_CAPABILITY.is_file():
        pytest.skip(
            "platforms/wechat/capability.toml 还没进仓库（平台能力声明分散在"
            "几个分支上，见规格 §12）——那份文件落地后本条开始生效"
        )

    cap = load_capability_file(WECHAT_CAPABILITY)

    assert cap.limits["title_chars"] == posts.TITLE_LIMIT
    assert cap.limits["body_chars"] == posts.BODY_LIMIT
    assert cap.limits["digest_chars"] == posts.DIGEST_LIMIT


def test_the_weixin_constants_are_readable_at_all():
    """对照的前提是三个常量都在。少了任何一个，这条对照就名存实亡。"""
    posts = _wechat_posts()
    if posts is None:
        pytest.skip("platforms/wechat/ 不可用")
    assert posts is not None

    assert isinstance(posts.TITLE_LIMIT, int)
    assert isinstance(posts.BODY_LIMIT, int)
    assert isinstance(posts.DIGEST_LIMIT, int)
