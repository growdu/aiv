"""mermaid → PNG：缓存、降级、以及与微信那份的对拍。

**失败是正常路径**（规格 §6.2：母稿里约 8% 的 mermaid 图解析不出来），
所以这里把失败当正常路径测：返回原因，不抛异常，不留下半个 PNG。

**两份实现要对拍**：视频线不能 import 平台层（层间零 import），
所以 `pyv/mermaid.py` 与 `platforms/wechat/mermaid.py` 各持一份，
版本号与关键参数必须一致——这份测试**读对方那份的源码**（`ast` 解析常量），
不 import 那个模块。
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from pyv import mermaid

#: video/ 是 pipeline/ 的上一级；仓库根在 video/ 的上一级。
AIV_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AIV_ROOT.parent
WECHAT_MERMAID = REPO_ROOT / "platforms" / "wechat" / "mermaid.py"


# ---- 缓存键与缓存目录 ------------------------------------------------------


def test_the_key_depends_only_on_the_source():
    """同一段源码 → 同一个键；位置变了不影响。"""
    assert mermaid.mermaid_key("graph TD\n A --> B") == \
        mermaid.mermaid_key("graph TD\n A --> B")
    assert mermaid.mermaid_key("graph TD\n A --> B") != \
        mermaid.mermaid_key("graph TD\n A --> C")
    assert len(mermaid.mermaid_key("x")) == 16


def test_the_cache_directory_is_the_build_folder_by_default(monkeypatch):
    """产物不入库：默认落在 build/ 下。"""
    monkeypatch.delenv(mermaid.ENV_CACHE, raising=False)
    assert mermaid.cache_dir() == mermaid.PIPELINE_ROOT / "build" / "mermaid"


def test_the_cache_directory_can_be_pointed_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setenv(mermaid.ENV_CACHE, str(tmp_path / "图缓存"))
    assert mermaid.cache_dir() == tmp_path / "图缓存"


# ---- 找浏览器 --------------------------------------------------------------


def test_find_chrome_returns_none_when_there_is_no_browser(monkeypatch):
    """找不到浏览器不是错误——只是「没法渲染」，调用方要拿这个去降级。"""
    monkeypatch.setattr(mermaid, "CHROME_CANDIDATES", ())
    monkeypatch.setattr(mermaid.shutil, "which", lambda name: None)
    assert mermaid.find_chrome() is None


def test_find_chrome_takes_the_first_existing_candidate(monkeypatch, tmp_path):
    fake = tmp_path / "chrome"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(mermaid, "CHROME_CANDIDATES", (str(tmp_path / "没有"),
                                                       str(fake)))
    assert mermaid.find_chrome() == str(fake)


# ---- 跑 mermaid-cli --------------------------------------------------------


def test_a_missing_npx_is_reported_not_raised(monkeypatch, tmp_path):
    """没装 Node.js 是常见环境缺失——报一句，不抛异常。"""
    def _boom(*args, **kwargs):
        raise FileNotFoundError("npx")

    monkeypatch.setattr(mermaid.subprocess, "run", _boom)
    ok, error = mermaid.default_runner("graph TD\n A --> B",
                                       tmp_path / "out.png")
    assert ok is False
    assert "npx" in error


def test_a_timeout_is_reported_not_raised(monkeypatch, tmp_path):
    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="mmdc", timeout=1)

    monkeypatch.setattr(mermaid.subprocess, "run", _boom)
    ok, error = mermaid.default_runner("graph TD\n A --> B",
                                       tmp_path / "out.png")
    assert ok is False
    assert "timed out" in error


def test_a_failed_render_leaves_no_png_behind(monkeypatch, tmp_path):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "Parse error on line 3: Unexpected token\nError: boom\n"

    monkeypatch.setattr(mermaid.subprocess, "run",
                        lambda *a, **k: _Result())
    out = tmp_path / "out.png"
    ok, error = mermaid.default_runner("graph TD\n A --> B", out)
    assert ok is False
    assert "Parse error" in error
    assert not out.exists()


def test_the_failure_message_takes_the_head_not_the_tail():
    """mermaid-cli 报错会跟一大段 JavaScript 栈——取头不取尾。"""
    stderr = ("Parse error on line 3: Unexpected token\n"
              + "    at Parser.parse (/npm/node_modules/mermaid/dist.js:1)\n"
              + "    at Parser2.parse (/npm/node_modules/mermaid/dist.js:2)\n")
    message = mermaid.summarize_error(stderr, "")
    assert message.startswith("Parse error on line 3")
    assert "at Parser" not in message


def test_a_failed_render_with_no_output_still_says_something():
    assert mermaid.summarize_error("", "") == "mermaid-cli failed"


# ---- 渲染一张图 ------------------------------------------------------------


def test_render_one_caches_by_source_hash(tmp_path):
    """同一段源码只渲染一次——重复渲染一张图要好几秒。"""
    calls = []

    def _runner(source, out_file):
        calls.append(source)
        out_file.write_bytes(b"\x89PNG")
        return True, ""

    first = mermaid.render_one("graph TD\n A --> B", tmp_path, runner=_runner)
    second = mermaid.render_one("graph TD\n A --> B", tmp_path, runner=_runner)
    assert len(calls) == 1
    assert first.png is not None and first.png.exists()
    assert second.png == first.png
    assert second.error is None


def test_a_failed_render_reports_the_reason_and_leaves_no_png(tmp_path):
    def _runner(source, out_file):
        out_file.write_bytes(b"half a file")
        return False, "Parse error on line 3"

    asset = mermaid.render_one("graph TD\n A --> B", tmp_path, runner=_runner)
    assert asset.png is None
    assert asset.error == "Parse error on line 3"
    assert asset.ok is False
    assert not list(tmp_path.glob("*.png"))


# ---- 与微信那份对拍 --------------------------------------------------------


def _constants_of(path: Path) -> dict:
    """从源码里读出模块级常量（不 import 那个模块）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                out[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


@pytest.mark.parametrize("name", [
    "MERMAID_CLI_VERSION",
    "DEFAULT_WIDTH",
    "DEFAULT_BACKGROUND",
    "DEFAULT_SCALE",
    "RENDER_TIMEOUT",
])
def test_the_wechat_implementation_uses_the_same_parameters(name):
    """两份实现的关键参数必须一样——不然两边的图长得不一样。"""
    assert WECHAT_MERMAID.is_file(), f"找不到 {WECHAT_MERMAID}"
    theirs = _constants_of(WECHAT_MERMAID)
    ours = _constants_of(Path(mermaid.__file__))
    assert name in theirs, f"微信那份里没有 {name}"
    assert ours[name] == theirs[name], (
        f"{name} 两边不一样：视频线 {ours[name]!r}，微信 {theirs[name]!r}"
    )
