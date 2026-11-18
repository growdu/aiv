"""让根级（母稿 / review 层）的测试**在仓库根目录里也能跑**。

pytest 默认只把测试文件所在目录塞进 ``sys.path``；没有这一段，
``from paths import DOCS`` 之类的引用会在别的 cwd 下以「模块不存在」假红。
仓库根与 ``tools/`` 都塞进去，路径常量才有唯一来源。

层数自己数过：``tests/conftest.py`` 的 ``parents[0]=tests``、
``[1]=仓库根``。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))
