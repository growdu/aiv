"""mermaid → PNG（视频线自持的一份）。

**为什么不直接用 `platforms/wechat/mermaid.py`**：层间零 import——
视频线是上游（生产母稿），平台适配器是下游（发布），
反过来 import 就把依赖方向倒过来了。

所以这里**自持一份**，做法与微信那份一致：

- 锁定 mermaid-cli **10.9.1**（与站点渲染版本一致）；
- 探测系统 Chrome（不下载自己的 Chromium）；
- 按源码 hash 磁盘缓存，重复渲染不重复跑；
- **失败是正常路径**：返回 `(ok, 原因)`，不抛异常、不静默。

两份实现的版本号与关键参数由 `tests/test_mermaid.py` **对拍**——
测试**读对方那份的源码**（`ast` 解析出常量），不 import 那个模块：
读文件是允许的跨层说话方式，import 不是。

**产物不入库**：PNG 落在 `build/mermaid/`（或 `PYV_MERMAID_CACHE` 指的地方）。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: mermaid-cli 的版本（与站点、与微信那份一致）。
MERMAID_CLI_VERSION = "10.9.1"

#: 渲染出来的宽度（像素）。视频画面 1920 宽，1080 的图留出边。
DEFAULT_WIDTH = 1080

#: 背景色（mermaid-cli 的参数）。
DEFAULT_BACKGROUND = "white"

#: 2 倍渲染，缩到画面里才不糊。
DEFAULT_SCALE = 2

#: 渲染超时（秒）。mermaid-cli 偶尔会卡住，卡住比失败更糟。
RENDER_TIMEOUT = 180

#: 缓存目录的环境变量。
ENV_CACHE = "PYV_MERMAID_CACHE"

#: 探测浏览器时按顺序找这些路径（macOS 的 app bundle 在最前）。
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

#: 找不到绝对路径时按名字找（Windows 上 Chrome 不在 /usr/bin 里）。
CHROME_NAMES = ("google-chrome", "chrome", "chromium", "msedge")

#: video/ 是 pipeline/ 的上一级：pyv/mermaid.py → pyv → pipeline → video
PIPELINE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MermaidAsset:
    """一张图：源码、渲染出来的 PNG（如果有），或者失败的原因。"""

    key: str
    source: str
    png: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.png is not None


def mermaid_key(source: str) -> str:
    """缓存键：源码内容的指纹，与它在母稿里的位置无关。"""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def cache_dir() -> Path:
    """PNG 缓存目录。

    默认 `video/pipeline/build/mermaid/`——**产物，不入库**。
    `PYV_MERMAID_CACHE` 可以指到别处（同一台机器跑多套片子时用得上）。
    """
    override = os.environ.get(ENV_CACHE, "").strip()
    if override:
        return Path(override).expanduser()
    return PIPELINE_ROOT / "build" / "mermaid"


def find_chrome() -> str | None:
    """mermaid-cli 该驱动哪个浏览器。找不到就返回 `None`（不是错误）。"""
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def summarize_error(stderr: str, stdout: str) -> str:
    """从 mermaid-cli 的输出里取出**有用的那一行**。

    mermaid-cli 报错时会跟一大段 JavaScript 栈，栈比消息长得多——
    取头不取尾：真正有用的那句在前面。
    """
    for stream in (stderr, stdout):
        for line in stream.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("Error") or "Parse error" in line:
                return line[:400]
    for stream in (stderr, stdout):
        for line in stream.split("\n"):
            if line.strip():
                return line.strip()[:400]
    return "mermaid-cli failed"


def default_runner(source: str, out_file: Path) -> tuple[bool, str]:
    """用 mermaid-cli 渲染一张图。返回 `(ok, 失败原因)`。

    **失败不抛异常**：约 8% 的图解析不出来（规格 §6.2），
    那是正常路径，调用方要拿这个原因去画面上说明白。
    """
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    source_file = out_file.with_suffix(".mmd")
    source_file.write_text(source, encoding="utf-8")

    env = dict(os.environ)
    chrome = find_chrome()
    if chrome:
        env["PUPPETEER_EXECUTABLE_PATH"] = chrome

    npx = shutil.which("npx") or "npx"
    command = [
        npx, "-y", f"@mermaid-js/mermaid-cli@{MERMAID_CLI_VERSION}",
        "-i", str(source_file),
        "-o", str(out_file),
        "-w", str(DEFAULT_WIDTH),
        "-b", DEFAULT_BACKGROUND,
        "-s", str(DEFAULT_SCALE),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, env=env, timeout=RENDER_TIMEOUT,
            encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False, "npx not found: install Node.js to render mermaid diagrams"
    except subprocess.TimeoutExpired:
        return False, f"mermaid-cli timed out after {RENDER_TIMEOUT}s"

    if result.returncode != 0 or not out_file.exists():
        return False, summarize_error(result.stderr or "", result.stdout or "")
    return True, ""


def render_one(source: str, out_dir: str | Path | None = None, *,
               runner=None) -> MermaidAsset:
    """渲染一张图。**缓存命中就不跑第二次。**

    `runner` 是给测试用的假实现：签名与 `default_runner` 一样
    （`(source, out_file) -> (ok, 原因)`）。
    """
    run = runner or default_runner
    directory = Path(out_dir) if out_dir is not None else cache_dir()
    directory.mkdir(parents=True, exist_ok=True)

    key = mermaid_key(source)
    png = directory / f"{key}.png"
    if png.exists() and png.stat().st_size > 0:
        return MermaidAsset(key=key, source=source, png=png)

    ok, error = run(source, png)
    if ok and png.exists():
        return MermaidAsset(key=key, source=source, png=png)
    if png.exists():
        png.unlink()
    return MermaidAsset(key=key, source=source, png=None, error=error)
