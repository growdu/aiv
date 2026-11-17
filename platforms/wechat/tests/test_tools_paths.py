"""`platforms/wechat/tools/` 这四个脚本**曾经一个都跑不起来**。

目录从 `weixin/` 搬进 `platforms/`、内层包压平之后，这四个脚本的
`sys.path.insert` 全部指错了地方：

* 三个脚本插的是 `ROOT / "weixin"`——那个目录**已经不存在**了；
* `check-drafts.py` 插的是 `WECHAT_ROOT` 自己（= `platforms/wechat/`），
  但 `sys.path` 要能找到的是**包 `wechat`**，包住在 `platforms/wechat/`，
  所以 path 上该有的是 `platforms/`。

**而 484 条 wechat 测试全绿**——因为它们一条都没碰过 `tools/`。
「测试全绿」不等于「工具能跑」：这条盲区就是这么漏过去的。

所以这里补三条守卫：

1. **四个脚本在 import 阶段不炸。** 探针是
   `runpy.run_path(script, run_name="probe")`——它执行模块级的
   `sys.path.insert` 与 `from wechat.xxx import ...`，但**不会**跑 `main()`
   （所以不碰网络、不读凭据）。
   探针**跑在子进程里**：进程内的 `sys.path` 上已经有 `platforms/`
   （conftest 插的），在进程内探针就永远绿，压根抓不住这条 bug。
   子进程的 `sys.path` 只有脚本自己的那一行说了算——那才是真话。
2. **`tools/` 下没有任何脚本还提到 `weixin` 这个目录名**（静态扫，命中就是漏）。
3. **`prune-empty-drafts.py` 的两个默认值**指向
   `platforms/wechat/out` 与 `platforms/wechat/secrets.json`
   （用 AST 读，不用正则猜）。
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "platforms" / "wechat" / "tools"

#: 这四个脚本都在 `tools/` 下，都靠 `sys.path.insert` 才 import 得到 `wechat`。
SCRIPTS = (
    "check-drafts.py",
    "measure-brand.py",
    "measure-length.py",
    "prune-empty-drafts.py",
)

#: 探针的代码：执行模块体，但不触发 `if __name__ == "__main__"`。
PROBE = "import runpy, sys; runpy.run_path(sys.argv[1], run_name='probe')"


def _probe(script: Path) -> subprocess.CompletedProcess:
    """在**干净的**子进程里跑探针。

    清掉 `PYTHONPATH`：父进程带着它，探针就可能在**脚本没插对**的情况下
    靠环境变量捡到包——那就白测了。cwd 放在仓库根：那里没有 `wechat/`
    这个包目录，脚本只有靠自己那一行 `sys.path.insert` 才找得到。
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-c", PROBE, str(script)],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
    )


def test_every_tool_can_be_loaded_without_blowing_up():
    """四个脚本都能被 import 起来。

    之前它们全是坏的：插进 `sys.path` 的目录里没有 `wechat` 这个包，
    一跑就是 `ModuleNotFoundError: No module named 'wechat'`。
    """
    for name in SCRIPTS:
        script = TOOLS_DIR / name
        assert script.is_file(), f"tools/{name} 不见了"

        result = _probe(script)
        assert result.returncode == 0, (
            f"tools/{name} 在 import 阶段就炸了：\n{result.stderr.strip()}"
        )


def test_no_tool_still_mentions_the_old_directory_name():
    """`tools/` 下不许再出现 `weixin` 这个目录名。

    静态扫：这一条不依赖子进程，任何漏改都逃不掉。
    """
    offenders = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "weixin" in text:
            offenders.append(path.name)

    assert not offenders, (
        "tools/ 下这些脚本还在引用已删除的 weixin/ 目录：{}"
        .format("、".join(offenders))
    )


def _argument_default(script_name: str, option: str):
    """读出 argparse 里某个选项的**默认值表达式**。

    用 AST 而不是正则：默认值是 `ROOT / "platforms" / "wechat" / "out"`
    这样的表达式，正则猜不出它到底拼了什么。
    """
    tree = ast.parse((TOOLS_DIR / script_name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (isinstance(function, ast.Attribute)
                and function.attr == "add_argument"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != option:
            continue
        for keyword in node.keywords:
            if keyword.arg == "default":
                return keyword.value
    return None


def _path_parts(node) -> list:
    """把默认值表达式里的路径片段取出来（按**源码顺序**）。

    `ROOT / "platforms" / "wechat" / "out"` → `["platforms", "wechat", "out"]`。

    `ast.walk` 是广度优先，出来的顺序不是源码顺序——所以按
    `(lineno, col_offset)` 排一下。
    """
    if node is None:
        return []
    constants = [n for n in ast.walk(node)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    constants.sort(key=lambda n: (n.lineno, n.col_offset))
    return [n.value for n in constants]


def test_the_prune_tool_defaults_to_the_new_layout():
    """`prune-empty-drafts.py` 的两个默认值要跟着搬家走。

    这两个默认值以前指着 `weixin/out` 与 `weixin/secrets.json`——
    目录一搬，它们就指向空处；而 help 文本却已经写着
    「默认 platforms/wechat/out」——**说法变了行为没变**。
    """
    out_default = _argument_default("prune-empty-drafts.py", "--out-dir")
    assert out_default is not None, "prune-empty-drafts.py 里没有 --out-dir 选项"
    assert _path_parts(out_default) == ["platforms", "wechat", "out"], (
        "--out-dir 的默认值还指着旧目录：{}".format(ast.unparse(out_default))
    )

    secrets_default = _argument_default("prune-empty-drafts.py", "--secrets-file")
    assert secrets_default is not None, (
        "prune-empty-drafts.py 里没有 --secrets-file 选项")
    assert _path_parts(secrets_default) == ["platforms", "wechat", "secrets.json"], (
        "--secrets-file 的默认值还指着旧目录：{}"
        .format(ast.unparse(secrets_default))
    )
