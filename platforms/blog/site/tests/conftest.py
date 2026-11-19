"""让站点自己的测试**在站点目录里也能跑**。

pytest 默认只把测试文件所在目录塞进 ``sys.path``；没有这一段，
``from paths import CONTENT_UNITS`` 之类的引用会在别的 cwd 下以「模块不存在」假红。
仓库根与 ``tools/`` 都塞进去，路径常量才有唯一来源。

层数自己数过：``platforms/blog/site/tests/conftest.py`` 的
``parents[0]=tests``、``[1]=site``、``[2]=blog``、``[3]=platforms``、``[4]=仓库根``。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))
