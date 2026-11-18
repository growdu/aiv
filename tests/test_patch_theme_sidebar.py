"""patch-theme.py 里，侧栏模板只有**一份**。

以前 patcher 里存着侧栏模板的抄本（一段三引号包着的 ``sidebar_ejs = ...``），
跟主题文件 ``layout.ejs`` 里真正生效的那份早就对不上了——抄本少了折叠开关
（``onclick="toggleSidebar('cat')"``）和定义 ``window.toggleSidebar`` 的那段脚本。

今天那份抄本注入不进去（主题的 layout.ejs 自己就带着 cat-sidebar，护栏挡着），
所以今天没有**可见**的后果。但哪天它注入进去了，侧栏就再也折叠不了，
而构建不会报错、测试也不会红。

一份抄本 = 两处真相 = 迟早漂。所以这里断的是：抄本不许再存在，
留下的那一份（主题里生效的那份）必须带着折叠开关。
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "platforms" / "blog" / "site"
THEME = SITE / "themes" / "matery"
PATCH_THEME = SITE / "tools" / "patch-theme.py"
LAYOUT_EJS = THEME / "layout" / "layout.ejs"


def _sandboxed_site(tmp_path):
    """在临时目录里搭一份**同构的仓库骨架**，把 patcher 指到它。

    patcher 的主题目录来自 ``tools/paths.py`` 里的 ``SITE_THEMES``。
    路径常量集中之后它就不再随 cwd 走了——直接在仓库里跑 patcher 会改
    真主题（真主题是 git 跟踪的）。所以这里把 ``tools/paths.py``、
    ``tools/site_root.py`` 与 patcher 一起复制到临时目录里那份同构的骨架下：

    - ``paths.py`` 按自己的位置算仓库根（``parents[1]``），于是整套常量
      自然落在临时目录里；
    - 骨架的目录深度跟仓库一致（``<root>/platforms/blog/site/...``），
      脚本里写死的 ``parents[4]`` 也照样对得上。

    ``paths.py`` import 时会断言仓库根下有 ``docs/`` 与 ``platforms/``，
    所以那个空目录也得先建出来。
    """
    root = tmp_path
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "tools").mkdir(parents=True, exist_ok=True)
    for name in ("paths.py", "site_root.py"):
        shutil.copy2(REPO_ROOT / "tools" / name, root / "tools" / name)

    site = root / "platforms" / "blog" / "site"
    (site / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PATCH_THEME, site / "tools" / "patch-theme.py")
    shutil.copytree(THEME, site / "themes" / "matery")
    shutil.copytree(SITE / "theme-assets", site / "theme-assets")
    return site


def test_the_patcher_keeps_no_second_copy_of_the_sidebar():
    """patcher 里不许再存一份侧栏模板。

    抄的那份早就跟主题里生效的那份对不上了（少了折叠开关）。
    """
    text = PATCH_THEME.read_text(encoding="utf-8")

    assert 'sidebar_ejs = """' not in text, (
        "patch-theme.py 里还存着第二份侧栏模板——它已经跟主题里生效的那份对不上了"
    )


def test_the_sidebar_that_stays_in_the_theme_can_still_be_collapsed():
    """留下的那一份（主题里生效的那份）必须带着折叠开关。

    少了 ``onclick`` 就是点标题没反应；少了 ``window.toggleSidebar`` 的定义
    就是点了直接抛错。两者都只在浏览器里才看得见。
    """
    layout = LAYOUT_EJS.read_text(encoding="utf-8")

    assert "toggleSidebar('cat')" in layout, "分类导航的标题上没有折叠开关"
    assert "toggleSidebar('hot')" in layout, "最多阅读的标题上没有折叠开关"
    assert "window.toggleSidebar=" in layout, "侧栏里没有定义 window.toggleSidebar"


def test_running_the_patcher_leaves_the_sidebar_alone(tmp_path):
    """跑一遍 patcher，主题里的侧栏还是**那一份**。

    patcher 是在站点的主题目录上跑的，所以在临时目录里搭一份同构的骨架、
    把主题的拷贝放进去再跑它——跑完侧栏应该还在原处、还带着折叠开关、
    而且**只有一份**。
    """
    site = _sandboxed_site(tmp_path)
    theme_copy = site / "themes" / "matery"

    result = subprocess.run(
        [sys.executable, str(site / "tools" / "patch-theme.py")],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, "patch-theme.py 跑挂了：\n{}\n{}".format(
        result.stdout, result.stderr
    )

    layout = (theme_copy / "layout" / "layout.ejs").read_text(encoding="utf-8")
    assert layout.count('<div class="cat-sidebar">') == 1, (
        "侧栏被塞了不止一份（分类导航出现 {} 次）".format(
            layout.count('<div class="cat-sidebar">')
        )
    )
    assert layout.count('<div class="hot-sidebar">') == 1, (
        "侧栏被塞了不止一份（最多阅读出现 {} 次）".format(
            layout.count('<div class="hot-sidebar">')
        )
    )
    assert "toggleSidebar('cat')" in layout, "跑完 patcher，折叠开关没了"
