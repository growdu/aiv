"""仓库里那份真实的能力声明，必须指向真实存在的 adapter。

契约层读的是 ``publish/capabilities/*.toml``，调度器按 ``[adapter].command``
去调 adapter 的 CLI。这两层之间**没有 import**（接缝原则，规格 §11.1），
所以「声明里写的那个 adapter 到底在不在」没有编译器替我们把关——
只能靠测试。

坏掉的典型样子：能力声明先落地，adapter 还没写；或者 adapter 挪了目录，
声明还指着旧路径。两种情况下调度器一跑就报「adapter 的包目录不存在」，
而这在出包阶段才暴露——太晚。
"""

import subprocess
import sys
from pathlib import Path

from publishkit import list_capabilities, load_capability

REPO_ROOT = Path(__file__).resolve().parents[2]

CAPABILITIES = list_capabilities()


def _git(*args: str) -> subprocess.CompletedProcess:
    """跑一条 git 命令（同 `video/pipeline/tests/test_assets_are_tracked.py` 的写法）。

    **git 二进制不在 PATH 上时，不许把异常冒出去。**
    `subprocess.run` 在那种情况下抛 `FileNotFoundError`，
    异常从这儿冒出去 = **整条守卫报错**——守卫不是「查得严」，
    是「炸了」。所以这里接住它，返回一个「失败」的结果，
    让调用方据此退回不过滤。
    """
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
        )
    except OSError as error:
        # FileNotFoundError 是 OSError 的子类——git 不在 PATH 上属于这一支。
        return subprocess.CompletedProcess(
            args=["git", *args], returncode=127, stdout="", stderr=str(error),
        )


def _ignored_directories():
    """`platforms/` 下被 git 忽略的目录（发布包等产物、`__pycache__` 之类）。

    **git 只用来排除产物目录——枚举包仍然走磁盘上的 `rglob`。**
    要是改用 `git ls-files` 去枚举包，守卫在「还没提交的挪动」面前就变瞎了：
    目录挪深了还没 `git add`，守卫照样绿。**磁盘是真相，git 只用来排除产物。**

    **两种「git 用不上」的情形都退回不过滤**（返回 ``None``），**不跳过**——
    跳过等于把这条守卫整个关掉，比误报一次更糟：

    * **git 二进制不在 PATH 上**：`_git()` 接住 `OSError`
      （`FileNotFoundError` 是它的子类），返回失败的结果；
    * **这个目录不是 git 检出**（没有 `.git`）：git 跑起来了，
      但 returncode 非零。

    这两件事以前被混成一件说，实际行为不同——现在分开了。
    """
    result = _git("ls-files", "--others", "--ignored", "--exclude-standard",
                  "--directory", "--", "platforms")
    if result.returncode != 0:
        return None

    directories = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        directories.append((REPO_ROOT / line.rstrip("/")).resolve())
    return directories


def _is_ignored(path: Path, ignored) -> bool:
    """这个候选目录是不是落在被忽略的产物目录下面。

    **守卫的两段检查（深度断言、重复包检查）共用这一个判定。**
    上一轮只给深度断言套了排除规则，重复包检查照旧裸扫——
    同一个守卫的两半，一个修了一个没修，等于没修：误报还在，
    只是报错文案从「被挪深了一层」换成了「这个包应该只有一个」，
    下一个人照样被带偏。

    ``ignored`` 是 ``None``（git 用不上）时一律不排除——退回不过滤。
    """
    if ignored is None:
        return False
    resolved = path.resolve()
    return any(resolved.is_relative_to(directory) for directory in ignored)


def test_the_repository_declares_at_least_the_four_known_platforms():
    ids = {cap.id for cap in CAPABILITIES}
    assert {"wechat", "toutiao", "channels", "bilibili"} <= ids


def test_every_declaration_points_at_an_adapter_that_exists():
    for capability in CAPABILITIES:
        package = capability.adapter_package
        assert package, f"{capability.id} 的能力声明没有 [adapter].package"

        directory = REPO_ROOT / "platforms" / package
        assert directory.is_dir(), (
            f"{capability.id} 指向的 adapter 目录不存在：{directory}"
        )


def test_every_adapter_command_names_a_module_that_exists():
    """命令是 ``python3 -m <模块>``，模块要真的在那个目录里。"""
    for capability in CAPABILITIES:
        command = capability.adapter_command
        assert command, f"{capability.id} 的能力声明没有 [adapter].command"

        module = command[-1].split(".")[0]
        directory = REPO_ROOT / "platforms" / capability.adapter_package
        candidates = [
            directory / "__init__.py",        # 压平后包目录就是 platforms/<plat>/
            directory / (module + ".py"),
        ]
        assert any(path.is_file() for path in candidates), (
            f"{capability.id} 的命令 {' '.join(command)} 指向的模块不在 {directory} 里"
        )


def test_every_id_matches_its_file_name():
    for capability in CAPABILITIES:
        assert capability.path.stem == capability.id


def test_every_platform_can_be_loaded_by_id():
    for capability in CAPABILITIES:
        assert load_capability(capability.id).id == capability.id


def test_every_platform_is_importable_under_its_own_name():
    """平台目录名 = Python 包名 = 平台 id。

    压平之后 `platforms/<plat>/` 本身就是那个包，`python3 -m <plat>.cli`
    靠 cwd 在 sys.path 里找到它——目录名和包名必须是同一个词。
    """
    platforms = REPO_ROOT / "platforms"
    assert platforms.is_dir(), "platforms/ 不存在"
    for plat in ("wechat", "toutiao", "douyin", "bilibili", "channels"):
        package = platforms / plat
        assert package.is_dir(), f"platforms/{plat}/ 不存在"
        assert (package / "__init__.py").is_file(), f"platforms/{plat}/ 缺 __init__.py"
        result = subprocess.run(
            [sys.executable, "-c", f"import {plat}.cli"],
            cwd=str(platforms), capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"import {plat}.cli 失败：{result.stderr.strip()}")


def test_the_platform_dirs_keep_the_repo_root_at_the_right_depth():
    """搬家改了两处深度：内层包压平（−1 层）、tests/tools 下沉（+1 层）。

    「仓库根在哪一层」是这些目录里所有相对路径的地基——钉住它，
    免得以后再被悄悄挪走一层，而症状要等到出包时才炸。

    **这里必须从磁盘上找包，不能照着名单反推路径。**
    反推出来的断言恒真：目录真被挪走一层，守卫照样 PASS。
    所以下面扫的是 `platforms/` 下真实存在的「带 `__init__.py` 的目录」——
    挪深一层（`platforms/xx/toutiao`）它就会露出来。

    **产物目录不算。** `platforms/<plat>/out/` 里是发布包等本地产物，
    它们被 git 忽略，里面要是出现 `__init__.py`（比如某个产物是个包），
    那不是「平台被挪深了一层」——把它算进来就是**误报**，而下一个人会去查
    搬迁，没人查产物目录。

    **两段检查共用同一份排除集**（`_is_ignored`）：产物目录里冒出来的
    包既不该被判「挪深了一层」，也不该被判「这个平台有两个」。
    """
    repo_root = REPO_ROOT.resolve()
    platforms_dir = repo_root / "platforms"
    assert platforms_dir.is_dir(), "platforms/ 不存在"

    # ① 每个平台包都必须待在 platforms/ 这一层。
    #    枚举走磁盘（rglob）；git 只用来把「被忽略的产物目录」排除掉。
    ignored = _ignored_directories()
    packages = []
    for marker in platforms_dir.rglob("__init__.py"):
        package = marker.parent
        if _is_ignored(package, ignored):
            continue
        packages.append(package)
    packages.sort()

    assert packages, "platforms/ 下一个 Python 包都没有——目录结构不对"
    for package in packages:
        assert package.resolve().parents[1] == repo_root, (
            f"{package.relative_to(repo_root)}/ 的仓库根深度变了"
            "（它被挪深了一层？）"
        )

    # ② 五个平台包各自只能有一份，而且就在 platforms/ 下。
    #    同一份排除集——产物目录里的同名目录不是「第二份平台」。
    for plat in ("wechat", "toutiao", "douyin", "bilibili", "channels"):
        found = sorted(
            path for path in platforms_dir.rglob(plat)
            if path.is_dir() and (path / "__init__.py").is_file()
            and not _is_ignored(path, ignored)
        )
        assert len(found) == 1, (
            f"platforms/ 下 {plat} 这个包应该只有一个，现在找到 {len(found)} 个："
            f"{[str(p.relative_to(repo_root)) for p in found]}"
        )
        assert found[0].resolve().parents[1] == repo_root, (
            f"platforms/{plat}/ 的仓库根深度变了")

    # ③ tests/ 与 tools/ 下沉一层，仓库根对它们来说是 parents[2]。
    for package in sorted(p for p in platforms_dir.iterdir() if p.is_dir()):
        for sub in ("tests", "tools"):
            directory = package / sub
            if directory.is_dir():
                assert directory.resolve().parents[2] == repo_root, (
                    f"{package.name}/{sub}/ 的仓库根深度变了")
