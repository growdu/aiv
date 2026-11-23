"""这个 adapter 自己的 slug 规则。

**规则是谁的**：本模块的。它以前不是——早先 `wechat/hexo.py` 用
`importlib` 去加载站点的 `sync-hexo.py`，只为了借用它里面的 `slugize`。
那个脚本在 2026-11-18 站点重做（hexo → Astro）时删掉了，规则留在了这里。
（站点 2026-11-20 又换回 Hexo + matery，但那是**重写**过的一套，没把这个脚本搬回来。）

**规则没变**：搬过来的是一个字都没改的实现，跟被删掉的那个脚本逐字一致
（NFKD 归一化 → 去掉组合记号 → 去掉控制字符 → 特殊字符折叠成分隔符 →
分隔符去重 → 去掉首尾分隔符）。所以同样的名字仍然得到同样的 URL 片段：

    slugize("Go Web")                    == "Go-Web"
    slugize("PostgreSQL 源码修炼之路")    == "PostgreSQL-源码修炼之路"
    slugize("Hello, World!")             == "Hello-World"

⚠️ **这是 adapter 的规则，不是站点的规则。** 站点自己的 URL 规则在
`platforms/blog/site/tools/urls.py` 里（读全仓库唯一那份 `rules/urls.json`），
只有一处，两边不要互相模仿。
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["slugize"]

_R_CONTROL = re.compile(r"[\u0000-\u001f]")
_R_SPECIAL = re.compile(r'[\s~`!@#$%^&*()\-_+=[\]{}|\\;:"\'<>,.?/]+')


def slugize(name: str, separator: str = "-") -> str:
    """把一个名字变成 URL 片段。

    「Go Web」→「Go-Web」，「PostgreSQL 源码修炼之路」→「PostgreSQL-源码修炼之路」。
    中文不转写、不小写——只有空白与标点被折叠成分隔符。
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _R_CONTROL.sub("", s)
    s = _R_SPECIAL.sub(separator, s)
    s = re.sub(re.escape(separator) + "{2,}", separator, s)
    s = re.sub("^" + re.escape(separator) + "+|" + re.escape(separator) + "+$", "", s)
    return s
