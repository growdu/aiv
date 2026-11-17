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
    """
    repo_root = REPO_ROOT.resolve()
    for plat in ("wechat", "toutiao", "douyin", "bilibili", "channels"):
        package = (REPO_ROOT / "platforms" / plat).resolve()
        assert package.parents[1] == repo_root, f"platforms/{plat}/ 的仓库根深度变了"
        for sub in ("tests", "tools"):
            directory = package / sub
            if directory.is_dir():
                assert directory.parents[2] == repo_root, (
                    f"platforms/{plat}/{sub}/ 的仓库根深度变了")
