"""让这个模块的测试**在模块目录里也能跑**。

pytest 默认只把测试文件所在目录塞进 ``sys.path``；没有这一段，
``cd platforms/blog/site && python3 -m pytest tests/`` 就找不到仓库根的
``tools``，测试会以「模块不存在」假红。仓库根塞进去，模块才真是自足的。

层数自己数过：``platforms/blog/site/tests/conftest.py`` 的
``parents[0]=tests``、``[1]=site``、``[2]=blog``、``[3]=platforms``、
``[4]=仓库根``——**是 4，不是 3**。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))
