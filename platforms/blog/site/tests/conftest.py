"""让站点自己的测试**在站点目录里也能跑**。

pytest 默认只把测试文件所在目录塞进 ``sys.path``；没有这一段，
``from paths import CONTENT_UNITS`` 之类的引用会在别的 cwd 下以「模块不存在」假红。
仓库根与 ``tools/`` 都塞进去，路径常量才有唯一来源。

层数自己数过：``platforms/blog/site/tests/conftest.py`` 的
``parents[0]=tests``、``[1]=site``、``[2]=blog``、``[3]=platforms``、``[4]=仓库根``。

另外给一条 ``load_tool()``：站点自己的工具是**脚本**（文件名带连字符，
不是合法的模块名），测试要用它们的函数时走这条路加载。
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))


def load_tool(name: str):
    """按文件名加载站点自己的工具脚本。

    ``name`` 是 ``tools/`` 下的文件名（带 ``.py``）。

    **为什么不用 import**：这些脚本的名字带连字符（``build-posts.py``），
    不是合法的 Python 模块名，``import`` 不了。
    """
    path = Path(__file__).resolve().parents[1] / "tools" / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
