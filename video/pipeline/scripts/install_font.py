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

#: 要装进 OS 字体目录的内置字体文件（两个字重）。
FONT_SOURCES = fonts.BUNDLED_PATHS


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
    missing = [path for path in FONT_SOURCES if not path.is_file()]
    if missing:
        for path in missing:
            print(f"内置字体不在仓库里：{path}")
        print("先跑 scripts/build_font_subset.py 生成")
        return 1

    directory = target_dir()
    directory.mkdir(parents=True, exist_ok=True)

    for source in FONT_SOURCES:
        target = directory / source.name
        source_sha = sha256_of(source)
        if target.is_file() and sha256_of(target) == source_sha:
            print(f"已安装（sha256 一致）：{target}")
        else:
            shutil.copyfile(source, target)
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

    **两个字重都要认得**：认得 Regular 不等于认得 Bold——粗体没认到
    的话，cairo 会**合成**一份，两个平台的合成方式还不一样（实测轮廓
    差 3.14px）。所以这里查的是「粗体能不能量出 Bold 的步进」。
    """
    for attempt in range(6):
        if fonts.family_resolves(fonts.BUNDLED_FAMILY):
            print(f"cairo 认得「{fonts.BUNDLED_FAMILY}」了")
            if fonts.bold_face_resolves():
                print("粗体也认得了（用真的 Bold 字形，不是合成的）")
                return 0
            print("粗体还没认到——cairo 会合成粗体，跨机版式会对不上")
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
    resolved = fonts.font_family()

    print(f"字体文件    {', '.join(str(p) for p in FONT_SOURCES)}")
    print(f"安装目标    {directory}")
    for source in FONT_SOURCES:
        target = directory / source.name
        installed = target.is_file()
        same = installed and sha256_of(target) == sha256_of(source)
        print(f"  {source.name:<28} 已安装 {'是' if installed else '否'}"
              f"{'（sha256 一致）' if same else ''}")
    print(f"cairo 解析  {'认得' if fonts.family_resolves(fonts.BUNDLED_FAMILY) else '认不得'}"
          f"「{fonts.BUNDLED_FAMILY}」")
    print(f"粗体        {'认得（真的 Bold 字形）' if fonts.bold_face_resolves() else '认不得——会合成粗体'}")
    print(f"当前在用    {resolved}")

    if fonts.family_resolves(fonts.BUNDLED_FAMILY) and fonts.bold_face_resolves():
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
