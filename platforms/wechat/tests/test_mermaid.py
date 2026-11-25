from pathlib import Path

from wechat.mdparse import parse
from wechat.mermaid import _summarize_error, mermaid_key, render_mermaid


def test_summarize_error_keeps_the_meaningful_head():
    stderr = "\nError: Evaluation failed: UnknownDiagramError: No diagram type detected\n\n    at detectType (...)\n    at other (...)\n"
    message = _summarize_error(stderr, "")
    assert message.startswith("Error: Evaluation failed")
    assert "at detectType" not in message


def test_summarize_error_falls_back_to_first_line():
    assert _summarize_error("", "something went wrong\nmore") == "something went wrong"


def test_summarize_error_handles_empty_output():
    assert _summarize_error("", "") == "mermaid-cli failed"


def test_mermaid_key_is_stable_and_position_independent():
    assert mermaid_key("graph TD;\nA-->B;") == mermaid_key("graph TD;\nA-->B;")
    assert mermaid_key("a") != mermaid_key("b")


def test_render_mermaid_collects_only_mermaid_blocks(tmp_path):
    blocks = parse("```mermaid\ngraph TD;\nA-->B;\n```\n\n```sql\nSELECT 1;\n```\n")

    def runner(source, out_file):
        out_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        return True, ""

    assets = render_mermaid(blocks, tmp_path, runner=runner)
    assert len(assets) == 1
    asset = next(iter(assets.values()))
    assert asset.png is not None
    assert asset.error is None
    assert asset.png.read_bytes().startswith(b"\x89PNG")


def test_render_mermaid_records_failure_without_raising(tmp_path):
    blocks = parse("```mermaid\nBROKEN\n```\n")

    def runner(source, out_file):
        return False, "Parse error on line 1"

    assets = render_mermaid(blocks, tmp_path, runner=runner)
    asset = next(iter(assets.values()))
    assert asset.png is None
    assert "Parse error" in asset.error


def test_render_mermaid_removes_partial_file_on_failure(tmp_path):
    blocks = parse("```mermaid\nBROKEN\n```\n")

    def runner(source, out_file):
        out_file.write_bytes(b"partial garbage")
        return False, "boom"

    assets = render_mermaid(blocks, tmp_path, runner=runner)
    asset = next(iter(assets.values()))
    assert asset.png is None
    assert not list(tmp_path.glob("*.png"))


def test_render_mermaid_reuses_cached_file(tmp_path):
    blocks = parse("```mermaid\ngraph TD;\nA-->B;\n```\n")
    calls = []

    def runner(source, out_file):
        calls.append(source)
        out_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        return True, ""

    render_mermaid(blocks, tmp_path, runner=runner)
    render_mermaid(blocks, tmp_path, runner=runner)
    assert len(calls) == 1


def test_render_mermaid_deduplicates_identical_diagrams(tmp_path):
    blocks = parse(
        "```mermaid\ngraph TD;\nA-->B;\n```\n\n"
        "```mermaid\ngraph TD;\nA-->B;\n```\n"
    )
    calls = []

    def runner(source, out_file):
        calls.append(source)
        out_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        return True, ""

    assets = render_mermaid(blocks, tmp_path, runner=runner)
    assert len(assets) == 1
    assert len(calls) == 1


def test_render_mermaid_uses_same_key_as_render_module(tmp_path):
    from wechat.render import mermaid_key as render_key

    blocks = parse("```mermaid\ngraph TD;\nA-->B;\n```\n")

    def runner(source, out_file):
        out_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        return True, ""

    assets = render_mermaid(blocks, tmp_path, runner=runner)
    key = next(iter(assets))
    assert key == render_key("graph TD;\nA-->B;")


def test_the_npx_is_looked_up_in_the_path_instead_of_guessed(tmp_path, monkeypatch):
    """npx 在 Windows 上是 npx.cmd，光写 "npx" 是拉不起来的。

    ``npx`` 这个名字要靠 PATHEXT 才能找到 .cmd，所以得真的去 PATH 里查。
    """
    import shutil

    from wechat import mermaid as mermaid_module

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["env"] = kwargs.get("env", {})
        return _Result()

    monkeypatch.setattr(mermaid_module.subprocess, "run", fake_run)

    mermaid_module.default_runner("graph TD;\nA-->B;\n", tmp_path / "out.png")

    assert captured["command"][0] == (shutil.which("npx") or "npx")


def test_the_browser_on_this_machine_is_handed_to_mermaid_cli(tmp_path, monkeypatch):
    """系统里的浏览器得给 mermaid-cli 用，别让它自己下一个 Chromium。"""
    from wechat import chrome as chrome_module
    from wechat import mermaid as mermaid_module

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Result()

    monkeypatch.setattr(mermaid_module.subprocess, "run", fake_run)

    mermaid_module.default_runner("graph TD;\nA-->B;\n", tmp_path / "out.png")

    expected = chrome_module.find_chrome()
    if expected is None:
        assert "PUPPETEER_EXECUTABLE_PATH" not in captured["env"]
    else:
        assert captured["env"]["PUPPETEER_EXECUTABLE_PATH"] == expected


def test_mermaid_cli_is_given_the_flags_chrome_needs_under_root(tmp_path, monkeypatch):
    """Chrome 以 root 跑时不带 sandbox 参数会起不来。

    mermaid-cli 通过 puppeteer 驱动 Chrome，而 puppeteer 的启动参数只从
    配置文件读——不给，浏览器就报 "Failed to launch the browser process!"，
    每张图都降级成源码块。所以命令行上必须有 ``-p``，指向一份写了
    ``--no-sandbox`` 的配置文件。
    """
    import json

    from wechat import mermaid as mermaid_module

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        return _Result()

    monkeypatch.setattr(mermaid_module.subprocess, "run", fake_run)

    mermaid_module.default_runner("graph TD;\nA-->B;\n", tmp_path / "out.png")

    command = captured["command"]
    assert "-p" in command, "mermaid-cli 没拿到 puppeteer 配置文件"
    config_path = Path(command[command.index("-p") + 1])
    assert config_path.is_file(), "puppeteer 配置文件没写出来"

    args = json.loads(config_path.read_text(encoding="utf-8"))["args"]
    assert "--no-sandbox" in args, "puppeteer 配置里没有 --no-sandbox"
    assert "--disable-dev-shm-usage" in args, (
        "容器里的 /dev/shm 常常不够大，puppeteer 配置里缺 --disable-dev-shm-usage"
    )


def test_the_puppeteer_config_is_written_next_to_the_diagram(tmp_path):
    """配置文件跟图源放一起——产物目录一清，两样一起没。"""
    from wechat import mermaid as mermaid_module

    config = mermaid_module.write_puppeteer_config(tmp_path)
    assert config.parent == tmp_path
    assert config.is_file()
