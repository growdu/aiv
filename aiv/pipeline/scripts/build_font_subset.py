#!/usr/bin/env python3
"""生成内置字体子集。

**为什么要内置字体**：三条实测出来的事实决定的。

1. cairo 在 macOS 上走 CoreText、**不认 fontconfig 目录**——把字体放在
   仓库里或 fontconfig 目录里，cairo 根本找不到它。字体必须装进 OS
   认的字体目录（macOS `~/Library/Fonts/`，Linux `~/.local/share/fonts/`）。
2. 跨 OS 逐像素一致**做不到**（CoreText ≠ FreeType），但**布局一致**做得到：
   同一份字体文件给出同一组步进宽度（实测两者相差 ≤ 0.45px），
   `fit_size` 收出同一个字号，文字不会出框。
3. 仓库实际用到的字符只有一千多个——整份 16.4MB 的字体没必要进仓库。

所以：**一份可分发的字体（OFL 1.1）按仓库用到的字符子集化，入库**，
两台机器装同一份文件 → 跨机布局一致。

用法：

    python3 scripts/build_font_subset.py                  # 从上游下载并生成
    python3 scripts/build_font_subset.py --from FILE      # 用已下载的上游文件

上游文件必须与台账里钉的 sha256 一致——否则拒绝生成。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AIV_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

# ---- 上游：钉死版本与 sha256 ---------------------------------------------
#
# 用 2.004 而不是最新的 main：Debian/Ubuntu 的 fonts-noto-cjk 就是 2.004，
# CI 上装的是它，macOS 上装的也是它。钉在同一个版本上，系统字体与内置
# 子集的**字形完全一致**，换机器不会因为字体版本漂掉而改版式。
#
# **实测**：上游这份文件与本机 `~/Library/Fonts/NotoSansCJKsc-Regular.otf`
# 字节完全一致（sha256 都是 2c76254f…）。
UPSTREAM_SHA256 = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
UPSTREAM_VERSION = "2.004"

#: 下载源。第一个是 CDN（实测 3.6MB/s），第二个是 GitHub 原始地址
#: （实测很慢，会断）。**内容一样**，sha256 核对过。
UPSTREAM_URLS = (
    "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@Sans2.004/"
    "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
    "https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/"
    "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
)
UPSTREAM_URL = UPSTREAM_URLS[0]

#: 授权：SIL Open Font License 1.1，允许随软件分发。
LICENSE = "SIL Open Font License 1.1"
LICENSE_URL = "https://github.com/notofonts/noto-cjk/blob/Sans2.004/LICENSE"

#: 内置族名。**必须唯一**——跟系统里任何字体重名，fontconfig 就会在
#: 两份之间二选一，机器之间就不一致了。
FAMILY = "AIV Sans CJK SC"
PS_NAME = "AIVSansCJKSC-Regular"

FONT_DIR = PIPELINE_ROOT / "assets" / "fonts"
SUBSET_PATH = FONT_DIR / "AIVSansCJKSC-Regular.otf"
MANIFEST_PATH = FONT_DIR / "SOURCE.json"


#: 画字模块：这些模块里的字符串字面量会经 cairo 画到画面上。
#:
#: **为什么按模块列，而不是扫整个仓库**：整个 `pyv/` 里有一大半模块
#: 只往终端上打字（doctor、cli、align、persona、timeline……），它们的中文
#: 永远不上画面。把它们也收进子集，就得为「只出现在终端里的字」留字形。
#:
#: 实测踩到的三例（上游 Noto Sans CJK SC 里**根本没有**这些字形）：
#:
#: - `pyv/fonts.py` 的探针字符 `U+E000`（探测字形缺失用的哨兵）
#: - `tests/test_bgm.py` 的替换符 `U+FFFD`（断言「文档里不该有它」）
#: - `scripts/redgreen_check.py` 的读音样本 `ŋ`（TTS 载荷，不是画面）
#:
#: 素材脚本（`brand/`、`character/`）也不在内：它们往素材上写的是
#: ASCII 品牌词「growdu」，已被 ASCII 段覆盖；散文 docstring 不进字体。
DRAWING_MODULES = (
    "pipeline/pyv/scenes/*.py",
    "pipeline/pyv/subtitle.py",
    "pipeline/pyv/layout.py",
    "pipeline/pyv/components.py",
    "pipeline/pyv/scene_layout.py",
)


def _string_literals(source: str) -> list[str]:
    """源码里所有**不是 docstring** 的字符串字面量。

    **用 ast，不用正则**：正则扫原始文本会跨过引号边界，把注释里
    的字符也捞进来（实测 bgm.py 的一句注释里的 `✗` 就被捞到了），
    于是子集里混进根本不会上画面的符号。

    **排除 docstring**：docstring 是给人看的散文，不是画面文案。
    场景模块的 docstring 写得很长（每个模板一大段），里面提到但
    **没有真画出来**的符号（例如「排队那一格画一个叉」——那个叉是
    用线条画的，不依赖字体）会混进子集。
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        head = body[0]
        if (isinstance(head, ast.Expr)
                and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)):
            docstrings.add(id(head.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def _is_drawable(ch: str) -> bool:
    """这个字符会不会出现在画面（或已入库的素材）上。

    排除两类：

    - **控制字符**（ord < 32）：换行、制表符；
    - **变体选择符**（U+FE00–U+FE0F、U+E0100–U+E01EF）：它们只修饰前面
      的字符，本身永远不画。字幕稿里的 `⚠️` 就带一个 U+FE0F——它不是
      字形，是格式修饰符。
    """
    code = ord(ch)
    if code < 32:
        return False
    if 0xFE00 <= code <= 0xFE0F:
        return False
    if 0xE0100 <= code <= 0xE01EF:
        return False
    return True


def repo_charset() -> set[str]:
    """仓库里会被画到画面上的字符。

    **这个提取逻辑与 `tests/test_font_subset.py` 里的那份是独立复算的**
    （两边各写一份，故意不共用代码）——共用一份的话，提取逻辑写错了
    两边一起错，缺字守卫就永远绿着。

    来源：

    1. 六期契约 JSON 里的所有字符串——**画面文案的唯一来源**
    2. 六份字幕稿的全部字符（字幕是烧进画面的，宁可多收）
    3. **画字模块**里的字符串字面量（见 `DRAWING_MODULES`）——
       场景里写死的少量文案（比如那个问号）在这里
    4. 基础 ASCII 与常用中英标点

    **不含** `pyv/` 下的其余模块（doctor、cli、align、persona……）——
    那些只往终端上打字，不往画面上画。
    """
    chars: set[str] = set()

    def add(text: str) -> None:
        chars.update(ch for ch in text if _is_drawable(ch))

    def walk(node) -> None:
        if isinstance(node, str):
            add(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    for path in sorted((AIV_ROOT / "contracts").glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))

    for path in sorted(AIV_ROOT.glob("字幕-*.md")):
        add(path.read_text(encoding="utf-8"))

    for pattern in DRAWING_MODULES:
        for path in sorted(AIV_ROOT.glob(pattern)):
            for literal in _string_literals(path.read_text(encoding="utf-8")):
                add(literal)

    add("".join(chr(i) for i in range(32, 127)))
    add("　·—…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*")
    return chars


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_upstream(target: Path) -> Path:
    """下载上游字体并核对 sha256。

    多个源按顺序试——GitHub 的原始地址实测很慢会断，CDN 快得多。
    **内容一样**，sha256 核对过才收。
    """
    errors: list[str] = []
    for url in UPSTREAM_URLS:
        print(f"下载上游字体：{url}")
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                target.write_bytes(response.read())
        except Exception as exc:  # noqa: BLE001 - 网络错误一律换下一个源
            errors.append(f"{url} → {exc}")
            continue
        actual = sha256_of(target)
        if actual == UPSTREAM_SHA256:
            return target
        target.unlink()
        errors.append(f"{url} → sha256 不符（{actual}）")
    raise SystemExit(
        "所有下载源都没拿到可用的上游文件：\n  "
        + "\n  ".join(errors)
        + "\n可以自己下载一份再传 --from：\n  "
        + "\n  ".join(UPSTREAM_URLS)
    )


def build(source: Path, charset: set[str]) -> None:
    """子集化并改族名。"""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    # **hinting 必须留着**：cairo 的步进宽度受 hinting 影响，
    # 丢掉它两边算出来的字号会不一样，布局就不一致了。
    options.hinting = True
    options.desubroutinize = False
    options.drop_tables = []
    options.glyph_names = False

    font = subset.load_font(str(source), options)
    name = font["name"]
    for name_id, value in ((1, FAMILY), (2, "Regular"), (3, PS_NAME),
                           (4, FAMILY), (6, PS_NAME), (16, FAMILY), (17, "Regular")):
        name.setName(value, name_id, 3, 1, 0x409)
    name.setName(FAMILY, 1, 1, 0, 0)

    subsetter = subset.Subsetter(options)
    subsetter.populate(text="".join(sorted(charset)))
    subsetter.subset(font)

    # **先落临时文件，验完再搬正位。**
    #
    # 早先这里是「先写 SUBSET_PATH，再验 cmap」——验不过就直接抛错，
    # 于是仓库里留下一个**新的字体文件配一份旧的台账**：文件对不上
    # sha256，台账里的 `chars` 也还是上一次的数量。半成品的组合比
    # 什么都没有更难查。
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    staged = SUBSET_PATH.with_suffix(".otf.staged")
    subset.save_font(font, str(staged), options)

    # **子集必须真的盖住每一个字**：子集化可能因为某些字符没有字形
    # 而静默丢掉它们——那正是「画出来是豆腐块」的来源。
    check = TTFont(str(staged))
    cmap = check.getBestCmap()
    missing = sorted(ch for ch in charset if ord(ch) not in cmap)
    if missing:
        staged.unlink()
        raise SystemExit(
            f"子集缺 {len(missing)} 个字：{missing[:20]}\n"
            f"上游字体里没有这些字形——换个来源或把这些字挪出画面。"
        )

    staged.replace(SUBSET_PATH)


def write_manifest(charset: set[str]) -> None:
    manifest = {
        "family": FAMILY,
        "postscript_name": PS_NAME,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "upstream": UPSTREAM_URL,
        "version": UPSTREAM_VERSION,
        "sha256": UPSTREAM_SHA256,
        "subset_sha256": sha256_of(SUBSET_PATH),
        "subset_bytes": SUBSET_PATH.stat().st_size,
        "chars": len(charset),
        "note": (
            "按仓库实际用到的字符子集化。**字符集由 "
            "`scripts/build_font_subset.py` 从仓库自动提取**，"
            "不手工维护——`tests/test_font_subset.py` 独立复算一遍，"
            "对不上就红。\n"
            "上游钉在 2.004：Debian/Ubuntu 的 fonts-noto-cjk 就是这个版本，"
            "系统字体与内置子集的字形一致。"
        ),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成内置字体子集")
    parser.add_argument("--from", dest="source", default=None,
                        help="用这份本地文件当上游（必须是上游原版，sha256 要对得上）")
    args = parser.parse_args()

    charset = repo_charset()
    print(f"仓库用到的字符：{len(charset)} 个")

    if args.source:
        source = Path(args.source)
        actual = sha256_of(source)
        if actual != UPSTREAM_SHA256:
            raise SystemExit(
                f"这份文件的 sha256 与台账不符：\n"
                f"  期望 {UPSTREAM_SHA256}\n"
                f"  实际 {actual}"
            )
        print(f"用本地上游：{source}")
    else:
        source = fetch_upstream(FONT_DIR / "_upstream.otf")

    build(source, charset)
    write_manifest(charset)

    if source.name == "_upstream.otf":
        source.unlink()

    print(f"已生成 {SUBSET_PATH}（{SUBSET_PATH.stat().st_size} 字节）")
    print(f"台账 {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
