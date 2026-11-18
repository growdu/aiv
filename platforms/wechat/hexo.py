"""Reuse of the site's compiler, ``platforms/blog/site/tools/sync-hexo.py``.

The converter must not re-implement anything the site build already
knows.  ``sync-hexo.py`` carries the ``slugize`` rule that turns a
category name into the URL segment the site actually serves -- a
category named 「PostgreSQL 源码修炼之路」 lives at
``/categories/.../PostgreSQL-源码修炼之路/`` and not at
``.../PostgreSQL%20源码修炼之路/``.  Copying the rule here would let
the two drift apart, so the module is loaded and its function called.

Loading is safe: every module-level statement in ``sync-hexo.py`` is a
definition, and the work happens inside ``main()`` behind an
``if __name__ == '__main__'`` guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# platforms/wechat/ 下的模块：parents[2] 就是仓库根。
# 路径常量统一从根 tools/paths.py 取——那儿是唯一出处。
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from paths import SITE_TOOLS  # noqa: E402

__all__ = ["slugize", "sync_module"]

_SYNC_PATH = SITE_TOOLS / "sync-hexo.py"

_module = None
_slugize = None


def sync_module():
    """Load the site's compiler as a module, once per process."""
    global _module
    if _module is None:
        if not _SYNC_PATH.is_file():
            raise FileNotFoundError("找不到 {}".format(_SYNC_PATH))
        spec = importlib.util.spec_from_file_location("blog_sync_hexo", _SYNC_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module = module
    return _module


def slugize(name: str, separator: str = "-") -> str:
    """Slugize a name the way the site build does."""
    global _slugize
    if _slugize is None:
        _slugize = sync_module().slugize
    return _slugize(name, separator)
