"""集成测试的假仓库：把站点构建链的落点重定向到临时目录。

站点构建链搬进 ``platforms/blog/site/`` 之后，``sync-hexo.py`` 的落点
全是**绝对**路径（统一从根 ``tools/paths.py`` 取）。测试要在临时目录里
造一份语料跑一遍它，就得把那几个落点重定向过去——否则它会去改**真的**
仓库（内容单元仓库 ``content/units/``、站点源目录
``platforms/blog/site/source/``）。

假仓库的形状照着真仓库摆：

===========================  ==================================
``<root>/docs/``             母稿
``<root>/content/units/``    内容单元仓库（平台无关）
``<root>/platforms/blog/site/source/``   站点私有的源目录
``<root>/platforms/blog/site/_config.yml``  站点配置
===========================  ==================================

``run_sync()`` 跑的是**仓库里那一份真的** ``sync-hexo.py``——只是把它的
落点指到临时目录。跑之前有一道安全阀：脚本算出来的每个落点都必须落在
假仓库里，有一个落在外面就当场退出（宁可不跑，也不许写进真仓库）。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 站点这一平台的家（构建链搬过来之后的地址）。
SITE = REPO_ROOT / "platforms" / "blog" / "site"

#: 站点这一平台的脚本。
SYNC_SCRIPT = SITE / "tools" / "sync-hexo.py"

#: 站点自己的主题配置（sync 用它生成关于页）。
MATERY_CONFIG = SITE / "_config.matery.yml"

#: 根 tools/ —— 平台无关的工具住这儿（``paths.py`` / ``site_root.py``）。
ROOT_TOOLS = REPO_ROOT / "tools"


def content_units_dir(root: Path) -> Path:
    """假仓库里的内容单元仓库（平台无关，所有平台共用的那一半）。"""
    return root / "content" / "units"


def site_source_dir(root: Path) -> Path:
    """假仓库里站点私有的源目录（hexo 的 ``source_dir``）。"""
    return root / "platforms" / "blog" / "site" / "source"


def build_corpus(root: Path, drafts) -> None:
    """造一份母稿语料，外加 sync-hexo.py 要读的配置。"""
    for rel, text in drafts.items():
        path = root / "docs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # sync-hexo.py 用 _config.matery.yml 生成关于页；缺了它脚本会中断。
    # 站点搬了家，配置跟着搬——所以它躺在站点那一侧。
    site_dir = root / "platforms" / "blog" / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(MATERY_CONFIG, site_dir / "_config.matery.yml")
    # 兜底：脚本要是按「当前目录下的相对路径」找这份配置，也能找到。
    shutil.copy(MATERY_CONFIG, root / "_config.matery.yml")


#: 在子进程里跑的包装脚本：重定向落点 → 加载 sync-hexo.py → 跑 main()。
#:
#: **先加载后校验**：模块加载完、main() 还没跑的时候检查它的落点，
#: 有一个落在假仓库之外就当场退出——宁可不跑，也不许写进真仓库。
_WRAPPER = r'''
import importlib.util
import sys
from pathlib import Path

script, tools_dir = sys.argv[1], sys.argv[2]
root = Path(sys.argv[3]).resolve()

sys.path.insert(0, tools_dir)
import paths

# 落点重定向到假仓库——真仓库的内容单元与站点源目录不许被测试碰。
paths.DOCS = str(root / "docs")
paths.CONTENT_UNITS = str(root / "content" / "units")
paths.SITE_SOURCE = str(root / "platforms" / "blog" / "site" / "source")
paths.SITE_CONFIG = str(root / "platforms" / "blog" / "site" / "_config.yml")

spec = importlib.util.spec_from_file_location("sync_hexo_under_test", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# 安全阀：脚本算出来的落点必须都在假仓库里。
for name in ("DOCS", "SRC", "POSTS", "IMGS"):
    value = getattr(module, name, None)
    if value is None:
        sys.exit("sync-hexo.py 上没有 {} 这个落点常量".format(name))
    resolved = Path(value).resolve()
    if resolved != root and root not in resolved.parents:
        sys.exit("sync-hexo.py 的 {} 落在假仓库之外：{}".format(name, resolved))

module.main()
'''


def run_sync(root: Path) -> None:
    """在假仓库 ``root`` 上真跑一遍 sync-hexo.py。"""
    # **解码必须显式。** `text=True` 会按 `locale.getpreferredencoding()`
    # 解码（中文 Windows 是 cp936），而子进程输出的是 UTF-8——
    # 两边对不上就会在读取线程里炸出 UnicodeDecodeError，`stdout` 变 None。
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _WRAPPER,
            str(SYNC_SCRIPT),
            str(ROOT_TOOLS),
            str(root),
        ],
        # cwd 落在假仓库里：脚本里的 git 调用（取文章的日期）在非仓库目录里
        # 会失败，于是退回固定日期——语料没有 git 历史，日期才是确定的。
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert result.returncode == 0, "sync-hexo.py 失败：\n{}\n{}".format(
        result.stdout, result.stderr
    )
