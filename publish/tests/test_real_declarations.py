"""仓库里那份真实的能力声明，必须指向真实存在的 adapter。

契约层读的是 ``publish/capabilities/*.toml``，调度器按 ``[adapter].command``
去调 adapter 的 CLI。这两层之间**没有 import**（接缝原则，规格 §11.1），
所以「声明里写的那个 adapter 到底在不在」没有编译器替我们把关——
只能靠测试。

坏掉的典型样子：能力声明先落地，adapter 还没写；或者 adapter 挪了目录，
声明还指着旧路径。两种情况下调度器一跑就报「adapter 的包目录不存在」，
而这在出包阶段才暴露——太晚。
"""

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

        directory = REPO_ROOT / package
        assert directory.is_dir(), (
            f"{capability.id} 指向的 adapter 目录不存在：{directory}"
        )


def test_every_adapter_command_names_a_module_that_exists():
    """命令是 ``python3 -m <模块>``，模块要真的在那个目录里。"""
    for capability in CAPABILITIES:
        command = capability.adapter_command
        assert command, f"{capability.id} 的能力声明没有 [adapter].command"

        module = command[-1].split(".")[0]
        directory = REPO_ROOT / capability.adapter_package
        candidates = [
            directory / module / "__init__.py",
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
