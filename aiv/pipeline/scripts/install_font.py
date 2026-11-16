#!/usr/bin/env python3
"""把内置字体装进 OS 的字体目录，让 cairo 找得到它。

**为什么不能只把字体放在仓库里。** 实测（2026-11-16）：

- cairo 在 macOS 上走 CoreText，**不认 fontconfig 目录**——把字体放进
  `~/.local/share/fonts/` 后 `fc-list` 找得到，cairo 的 `select_font_face`
  找不到（宽度回落到 `.notdef`）。
- cairo 在 Linux 上走 fontconfig，要 `fc-cache -f` 才认新装的字体。

所以字体必须装进**两边的 OS 都认的那个目录**：

| 平台 | 装到 | 额外步骤 |
| --- | --- | --- |
| macOS | `~/Library/Fonts/` | CoreText 自动拾取 |
| Linux | `~/.local/share/fonts/` | `fc-cache -f` |

幂等：已安装且 sha256 相同 → 跳过。

用法：

    python3 scripts/install_font.py            # 装
    python3 scripts/install_font.py --check    # 只看状态，不装
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from pyv import fonts  # noqa: E402

FONT_SOURCE = PIPELINE_ROOT / "assets" / "fonts" / "AIVSansCJKSC-Regular.otf"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_dir() -> Path:
    """这个平台认的字体目录。"""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Fonts"
    if system == "Linux":
        base = Path.home() / ".local" / "share" / "fonts"
        return base
    # 其他平台（Windows 等）没有可移植的装法，只能靠 AIV_FONT_FAMILY
    return Path.home() / ".local" / "share" / "fonts"


def install() -> int:
    if not FONT_SOURCE.is_file():
        print(f"内置字体不在仓库里：{FONT_SOURCE}")
        print("先跑 scripts/build_font_subset.py 生成")
        return 1

    directory = target_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FONT_SOURCE.name

    source_sha = sha256_of(FONT_SOURCE)
    if target.is_file() and sha256_of(target) == source_sha:
        print(f"已安装（sha256 一致）：{target}")
    else:
        shutil.copyfile(FONT_SOURCE, target)
        print(f"已安装：{target}")

    if platform.system() == "Linux":
        fc_cache = shutil.which("fc-cache")
        if fc_cache:
            subprocess.run([fc_cache, "-f"], check=False)
            print("已刷新 fontconfig 缓存（fc-cache -f）")
        else:
            print("找不到 fc-cache——字体可能要等下次 fc-cache 才生效")

    return _wait_until_resolved()


def _wait_until_resolved() -> int:
    """等 cairo 认得新装的字体。

    **macOS 上要等**：CoreText 维护自己的字体清单，刚放进
    `~/Library/Fonts/` 的字体不会立刻可见——实测装完立刻查，
    cairo 还是回落到 PingFang。Linux 上 `fc-cache -f` 是同步的，
    一般立刻就好。
    """
    for attempt in range(6):
        if fonts.family_resolves(fonts.BUNDLED_FAMILY):
            print(f"cairo 认得「{fonts.BUNDLED_FAMILY}」了")
            return 0
        if attempt < 5:
            time.sleep(1.0)
    print(
        "装好了，但 cairo 还没认得——macOS 的 CoreText 字体清单要一会儿"
        "才刷新（Linux 上跑 fc-cache -f 就好）。过几秒再跑一次：\n"
        f"  python3 {Path(__file__).name} --check"
    )
    return 1


def check() -> int:
    """字体装没装、cairo 认不认。"""
    directory = target_dir()
    target = directory / FONT_SOURCE.name
    installed = target.is_file()
    same = installed and sha256_of(target) == sha256_of(FONT_SOURCE)
    resolved = fonts.family_resolves(fonts.BUNDLED_FAMILY)

    print(f"字体文件    {FONT_SOURCE}")
    print(f"安装目标    {target}")
    print(f"已安装      {'是' if installed else '否'}"
          f"{'（sha256 一致）' if same else ''}")
    print(f"cairo 解析  {'认得' if resolved else '认不得'}「{fonts.BUNDLED_FAMILY}」")
    print(f"当前在用    {fonts.font_family()}")

    if resolved:
        print("OK 内置字体已就位")
        return 0
    print("还没装好——跑 python3 scripts/install_font.py")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="安装内置字体")
    parser.add_argument("--check", action="store_true", help="只看状态，不装")
    args = parser.parse_args()
    if args.check:
        return check()
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
