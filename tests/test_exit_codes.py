"""跨模块只验接口：**五个 adapter 的退出码必须等于契约层定的那张表。**

这条用例**只验接口**——契约层那张表在不在、五份能力声明与它一致吗、
公众号那个读取器在不在。

**不验 adapter 真的按那张表返回码**：那是行为，行为断言住在**各 adapter
自己的套件里**（验收按模块拆开，根套件不 import 五个 adapter）。
"""
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "publish"))

PLATFORMS = ("toutiao", "wechat", "douyin", "bilibili", "channels")


def test_the_contract_layer_defines_the_four_codes():
    from publishkit import exit_codes
    assert exit_codes.CANONICAL == {"ok": 0, "usage": 1, "precondition": 2, "failed": 3}


def test_every_platform_declares_the_same_exit_codes():
    from publishkit import exit_codes
    for platform in PLATFORMS:
        path = REPO_ROOT / "platforms" / platform / "capability.toml"
        table = tomllib.loads(path.read_text(encoding="utf-8")).get("exit")
        assert table == exit_codes.CANONICAL, f"{platform} 的退出码与契约层不一致"


def test_the_wechat_adapter_has_a_capability_reader():
    """公众号原来没有 capability.toml 的读取器——本 Task 补上。"""
    assert (REPO_ROOT / "platforms" / "wechat" / "capability.py").is_file()
