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
import shutil
import sys
import tempfile
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

#: **粗体那一面**的上游。
#:
#: **为什么必须把粗体也入库**：只装 Regular 的时候，cairo 会**合成**粗体
#: ——CoreText 合成一套、FreeType 合成另一套。实测（2026-11-16）：
#: 同一段粗体文字，两个后端量出来的轮廓包围盒差 **3.14px**。合成粗体是
#: 各后端自己的做法，不是字体文件的性质，于是「几何只由字体文件决定」
#: 这条前提在粗体上不成立。
#:
#: 装上真的 Bold 之后，同样的对比差降到 **0.36px**。
UPSTREAM_BOLD_SHA256 = (
    "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a"
)
UPSTREAM_BOLD_URLS = (
    "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@Sans2.004/"
    "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf",
    "https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/"
    "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf",
)
UPSTREAM_BOLD_URL = UPSTREAM_BOLD_URLS[0]

#: **等宽**那一面的上游（代码块用）。
#:
#: 上游 sha256 **没钉**：这台机器连不上 CDN（实测 jsdelivr 与
#: raw.githubusercontent 都超时），钉不出来就不假装钉了——
#: 等宽那面的来源靠下面的离线源钉住。
MONO_UPSTREAM_URLS = (
    "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@Sans2.004/"
    "Sans/Mono/OTF/SimplifiedChinese/NotoSansMonoCJKsc-Regular.otf",
    "https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/"
    "Sans/Mono/OTF/SimplifiedChinese/NotoSansMonoCJKsc-Regular.otf",
)

#: **离线源**：Debian 的 `fonts-noto-cjk` 20220127 包。
#:
#: **为什么要有离线源**：上游 CDN 在很多机器上连不上（实测这台机器
#: jsdelivr 与 raw.githubusercontent 都超时），子集脚本必须有一条
#: 不联网的路。
#:
#: **为什么是它**：20220127 这个包里的面报的是
#: `Version 2.004;hotconv 1.0.118;makeotfexe 2.5.65603`——
#: 与台账里钉住的上游 OTF **同一个上游构建**（实测：同一字符集重建的
#: 子集，与入库的那份**逐字 outline 相同、advance 相同**）。
#:
#: **别拿本机装的那份当源**：Debian buster 的 `fonts-noto-cjk` 是
#: **2.001**（`Version 2.001;hotconv 1.0.107`）——`'A'` 的步进差
#: 1/1000 em（608 vs 607），`'中'` 的左边距差 4/1000 em。
#: 字形一换，版面就变，逐像素基准全红。所以脚本会先验字形
#: （见 `verify_source`），版本串对不上直接拒绝。
OFFLINE_SOURCE = {
    "package": "fonts-noto-cjk",
    "version": "20220127+repack1-1",
    "url": ("https://deb.debian.org/debian/pool/main/f/fonts-noto-cjk/"
            "fonts-noto-cjk_20220127+repack1-1_all.deb"),
    "sha256": "4a2515eb6db3978b897fef9709ed0d2b1f4c6c4df4d83d6c4ef65f71f1b1f502",
    "ttc": {
        "Regular": "NotoSansCJK-Regular.ttc",
        "Bold": "NotoSansCJK-Bold.ttc",
    },
    "version_string": "Version 2.004;hotconv 1.0.118;makeotfexe 2.5.65603",
}

#: 授权：SIL Open Font License 1.1，允许随软件分发。
LICENSE = "SIL Open Font License 1.1"
LICENSE_URL = "https://github.com/notofonts/noto-cjk/blob/Sans2.004/LICENSE"

#: 内置族名。**必须唯一**——跟系统里任何字体重名，fontconfig 就会在
#: 两份之间二选一，机器之间就不一致了。
#:
#: **两个字重共用一个族名**：Regular 与 Bold 是**同一个族的两面**
#: （name ID 1 相同，ID 2 分别是 Regular / Bold）。这样 cairo 的
#: `select_font_face(family, ..., BOLD)` 在两个平台上都解析到同一份
#: 粗体字形；族名不同的话，两个平台挑到的就不是同一个字体。
FAMILY = "AIV Sans CJK SC"

#: **等宽**那一族的族名（代码块用）。
#:
#: 同样必须唯一——跟系统里任何字体重名，fontconfig 就会二选一。
MONO_FAMILY = "AIV Mono CJK SC"

FONT_DIR = PIPELINE_ROOT / "assets" / "fonts"
MANIFEST_PATH = FONT_DIR / "SOURCE.json"

#: 要生成的三面。
#:
#: `style` 写进 name ID 2（子族名）——操作系统靠它把两面认成同一族。
#:
#: `source_ps` 是**上游 TTC 里那个面的 PostScript 名**：离线源按名字找面，
#: **不按下标**——下标是打包顺序，Debian 与 notofonts 的排法不一定一样，
#: 按下标取会取到别的语言面（JP / KR / TC / HK）。
FACES = (
    {
        "style": "Regular",
        "family": FAMILY,
        "file": "AIVSansCJKSC-Regular.otf",
        "postscript_name": "AIVSansCJKSC-Regular",
        "source_ps": "NotoSansCJKsc-Regular",
        "ttc": "Regular",
        "upstream_urls": UPSTREAM_URLS,
        "upstream_sha256": UPSTREAM_SHA256,
    },
    {
        "style": "Bold",
        "family": FAMILY,
        "file": "AIVSansCJKSC-Bold.otf",
        "postscript_name": "AIVSansCJKSC-Bold",
        "source_ps": "NotoSansCJKsc-Bold",
        "ttc": "Bold",
        "upstream_urls": UPSTREAM_BOLD_URLS,
        "upstream_sha256": UPSTREAM_BOLD_SHA256,
    },
    {
        # 等宽那面：**代码块用**。比例字体排的代码对不齐行。
        #
        # **没有钉上游 sha256**：这台机器连不上 CDN（jsdelivr 与
        # raw.githubusercontent 都超时），钉不出来就不假装钉——
        # 这一面走离线源（Debian 包），钉在 `offline_source` 上。
        "style": "Regular",
        "family": MONO_FAMILY,
        "file": "AIVMonoCJKSC-Regular.otf",
        "postscript_name": "AIVMonoCJKSC-Regular",
        "source_ps": "NotoSansMonoCJKsc-Regular",
        "ttc": "Regular",
        "upstream_urls": MONO_UPSTREAM_URLS,
        "upstream_sha256": "",
    },
)



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
#: 素材脚本（`character/`）不在内：它们往素材上写的是 ASCII 品牌词
#: （取值见 `video/config.toml` 的 `[brand].token`），已被 ASCII 段覆盖；
#: 散文 docstring 不进字体。
#:
#: 但 **`brand/scripts/render_brand.py` 在内**：它把品牌片的中文文案
#: （「深入数据库 · 分享技术之美」「感谢观看」「把踩过的坑写成方法」……）
#: 直接画到画面上。它不在列表里的实测后果就是品牌片出现豆腐块
#: （「⊠入数据库 · 分享技术之⊠」——「深」「美」两个字不在子集里）。
#: **素材脚本要分两类看**：只写 ASCII 的不进，写中文上画面的必须进。
DRAWING_MODULES = (
    "pipeline/pyv/scenes/*.py",
    "pipeline/pyv/generic/*.py",
    "pipeline/pyv/subtitle.py",
    "pipeline/pyv/layout.py",
    "pipeline/pyv/components.py",
    "pipeline/pyv/scene_layout.py",
    "brand/scripts/render_brand.py",
)

#: **GB 2312-80** 的汉字区与符号区全集。
#:
#: **为什么按标准算，而不是按「仓库用到的字符」算**：母稿不在仓库里。
#: 仓库里那篇母稿（`docs/distributed/foundations/`）有 597 个不同的字，
#: 其中 **120 个不在**按仓库算出来的子集里——照仓库算，母稿画出来
#: 一半是豆腐块，而且**画面照样生成、时长照样对**，没有任何报错。
#:
#: GB 2312-80 是一份**可引用的事实**：汉字区 6763 字（一级 3755 +
#: 二级 3008）+ 符号区。现代汉语用字的一级字表覆盖 99.7%。
#:
#: 代价是子集变大：6763 字 ≈ 3.4 MB/面（见 `assets/fonts/SOURCE.json`）。
#: 换来的是「母稿里的字画得出来」这条判据在 CI 里可查。
GB2312_LEAD = 0xA1
GB2312_TRAIL = 0xA1
GB2312_LEAD_MAX = 0xFE
GB2312_TRAIL_MAX = 0xFE


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

    1. 各期契约 JSON 里的所有字符串——**画面文案的唯一来源**
    2. 各期口播稿的全部字符（字幕是烧进画面的，宁可多收）
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

    for path in sorted((AIV_ROOT / "episodes").glob("*/contract.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))

    for path in sorted((AIV_ROOT / "episodes").glob("*/口播稿.md")):
        add(path.read_text(encoding="utf-8"))

    for pattern in DRAWING_MODULES:
        for path in sorted(AIV_ROOT.glob(pattern)):
            for literal in _string_literals(path.read_text(encoding="utf-8")):
                add(literal)

    add("".join(chr(i) for i in range(32, 127)))
    add("　·—–…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*")
    return chars


def standard_charset() -> set[str]:
    """**GB 2312-80 全集** + ASCII + 常用标点。

    母稿的汉字来自 `docs/`，那不在本仓库的字符集口径里——
    按标准算才盖得住（理由见 `GB2312_LEAD` 那段注释）。
    """
    chars = {chr(i) for i in range(32, 127)}
    for lead in range(GB2312_LEAD, GB2312_LEAD_MAX + 1):
        for trail in range(GB2312_TRAIL, GB2312_TRAIL_MAX + 1):
            try:
                chars.add(bytes((lead, trail)).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    chars.update("　·—–…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*")
    return chars


def extra_chars() -> set[str]:
    """**GB 2312-80 之外、但要能画出来的字**（`assets/fonts/extra_chars.txt`）。

    **为什么有这样一个文件**：子集的底子是 GB 2312-80 全集，那是一份
    **标准**，母稿的常用字全在里面。但标准盖不住全部——数学符号
    （`⌊` `⌋`）、生僻人名、emoji，母稿里真的会出现。

    **这些字不能画成豆腐块**：豆腐块没人看得出来，而画面照样生成、
    时长照样对，没有任何报错。缺字守卫（`pyv/fonts.py` 的
    `missing_chars`）会当场报错并指出是哪些字——**补救办法就是
    把它们加到这个文件里，重跑本脚本**。

    **为什么是文件而不是写死在脚本里**：这是**数据**，不是逻辑。
    """
    path = FONT_DIR / "extra_chars.txt"
    if not path.is_file():
        return set()
    chars: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        chars.update(stripped)
    return chars


def charset() -> set[str]:
    """要子集化的字符集：**标准全集 ∪ 仓库用到的字符 ∪ 额外的字**。

    仓库那一半不多，但要有——仓库里画字的模块（场景、字幕、品牌片）
    写的字必须在子集里。
    """
    return standard_charset() | repo_charset() | extra_chars()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_face_from_ttc(ttc_path: Path, postscript_name: str,
                         out_dir: Path) -> Path:
    """从 TTC 里按 **PostScript 名** 抽出那个面，存成临时 OTF。

    **不按下标取**：下标是打包顺序，Debian 与 notofonts 的排法不一定
    一样（Debian 的 `NotoSansCJK-Regular.ttc` 里 SC 在第 3 位，
    notofonts 的 OTF 根本不是 TTC）——按下标取会取到别的语言面
    （JP / KR / TC / HK），字形全不一样。

    抽出来的文件落在 `out_dir`（临时目录）里——**不落在 TTC 旁边**：
    离线源目录可能是只读的系统目录，也可能被别人共用。
    """
    from fontTools.ttLib import TTCollection

    collection = TTCollection(str(ttc_path), lazy=False)
    for font in collection.fonts:
        if font["name"].getDebugName(6) == postscript_name:
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{postscript_name}.otf"
            # **时间戳不许重算**：`TTFont.save` 默认把 `head.modified`
            # 改成「现在」。抽出这一步重算一次，子集化那一步就不重算，
            # 出来的文件照样每次都不一样——**重建不可复现**。
            # 留着 TTC 里那个面的原始时间戳，同一份源 → 同一个 sha256。
            font.recalcTimestamp = False
            font.save(str(target))
            return target
    available = sorted(
        font["name"].getDebugName(6) or "?" for font in collection.fonts)
    raise SystemExit(
        f"{ttc_path} 里没有 {postscript_name} 这个面。\n"
        f"里面只有：{available}")


def _outline(font, glyph_name: str):
    """一个字形的轮廓（用来逐字比对两个字体是不是同一份字形）。"""
    from fontTools.pens.recordingPen import RecordingPen

    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    return pen.value


def verify_source(face: dict, source_font) -> None:
    """**用本地源之前先验它**：版本串 + 与已入库子集逐字一致。

    **为什么版本串不够**：Debian buster 那个 `fonts-noto-cjk` 是 2.001，
    版本号也写着「Noto Sans CJK」——但它的 `'A'` 步进是 607/1000 em，
    钉住的上游是 608/1000 em。**一个字宽差 1/1000 em，整版都会移**，
    逐像素基准全红。所以还要比字形。

    **比的是什么**：共有字符的 **outline**（轮廓点）与 **advance**
    （步进）逐字相同。差一个点或差一个单位都不行。

    没有已入库的同族子集可比（第一次生成等宽那面）时，只验版本串。
    """
    version_string = source_font["name"].getDebugName(5)
    expected = OFFLINE_SOURCE["version_string"]
    if version_string != expected:
        raise SystemExit(
            f"源字体的版本串是 {version_string!r}，台账钉住的是 {expected!r}。\n"
            f"**版本对不上就不能用**——实测 2.001 与 2.004 的字宽差 "
            f"1/1000 em，版面会整体移位，逐像素基准会全红。\n"
            f"要用的源见台账的 offline_source。")

    bundled = FONT_DIR / face["file"]
    if not bundled.is_file():
        print(f"  （{face['file']} 还没有入库，这一面只验版本串）")
        return

    from fontTools.ttLib import TTFont

    current = TTFont(str(bundled))
    current_cmap = current.getBestCmap()
    source_cmap = source_font.getBestCmap()
    shared = sorted(set(current_cmap) & set(source_cmap))
    if not shared:
        return
    current_metrics = current["hmtx"].metrics
    source_metrics = source_font["hmtx"].metrics
    for code in shared:
        old_name = current_cmap[code]
        new_name = source_cmap[code]
        if current_metrics[old_name] != source_metrics[new_name]:
            raise SystemExit(
                f"源与已入库子集在 U+{code:04X} 上步进不一致："
                f"{current_metrics[old_name]} vs {source_metrics[new_name]}——"
                f"这不是同一个上游构建的字体，换源会改版面")
        if _outline(current, old_name) != _outline(source_font, new_name):
            raise SystemExit(
                f"源与已入库子集在 U+{code:04X} 上轮廓不同——"
                f"这不是同一个上游构建的字体，换源会改版面")
    print(f"  字形核对通过：{len(shared)} 个共有字符逐字相同")


def fetch_upstream(target: Path, urls: tuple[str, ...],
                  expected_sha256: str) -> Path:
    """下载上游字体并核对 sha256。

    多个源按顺序试——GitHub 的原始地址实测很慢会断，CDN 快得多。
    **内容一样**，sha256 核对过才收。
    """
    errors: list[str] = []
    for url in urls:
        print(f"下载上游字体：{url}")
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                target.write_bytes(response.read())
        except Exception as exc:  # noqa: BLE001 - 网络错误一律换下一个源
            errors.append(f"{url} → {exc}")
            continue
        actual = sha256_of(target)
        if actual == expected_sha256:
            return target
        target.unlink()
        errors.append(f"{url} → sha256 不符（{actual}）")
    raise SystemExit(
        "所有下载源都没拿到可用的上游文件：\n  "
        + "\n  ".join(errors)
        + "\n可以自己下载一份再传 --from：\n  "
        + "\n  ".join(urls)
    )


def build(source: Path, charset: set[str], face: dict) -> Path:
    """子集化并改族名。

    **两个字重用的是同一个族名**（name ID 1），只有子族名（ID 2）与
    PostScript 名（ID 6）不同——操作系统据此把它们认成同一族的两面。
    """
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
    # **时间戳不许重算**：fontTools 默认把 `head.modified` 改成「现在」，
    # 于是同一份源重跑一次脚本，出来的文件 sha256 就不同——台账里记的
    # `subset_sha256` 每次都得重写，**重建不可复现**。留着源里的时间戳，
    # 同一份源 → 同一份文件 → 同一个 sha256。
    options.recalc_timestamp = False

    style = face["style"]
    ps_name = face["postscript_name"]
    family = face["family"]
    full_name = family if style == "Regular" else f"{family} {style}"

    font = subset.load_font(str(source), options)
    name = font["name"]
    for name_id, value in ((1, family), (2, style), (3, ps_name),
                           (4, full_name), (6, ps_name), (16, family),
                           (17, style)):
        name.setName(value, name_id, 3, 1, 0x409)
    name.setName(family, 1, 1, 0, 0)

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
    subset_path = FONT_DIR / face["file"]
    staged = subset_path.with_suffix(".otf.staged")
    subset.save_font(font, str(staged), options)

    # **子集必须真的盖住每一个字**：子集化可能因为某些字符没有字形
    # 而静默丢掉它们——那正是「画出来是豆腐块」的来源。
    check = TTFont(str(staged))
    cmap = check.getBestCmap()
    missing = sorted(ch for ch in charset if ord(ch) not in cmap)
    if missing:
        staged.unlink()
        raise SystemExit(
            f"子集（{style}）缺 {len(missing)} 个字：{missing[:20]}\n"
            f"上游字体里没有这些字形——换个来源或把这些字挪出画面。"
        )

    staged.replace(subset_path)
    return subset_path


def write_manifest(charset: set[str], faces: list[dict],
                   offline: dict) -> None:
    manifest = {
        "family": FAMILY,
        "mono_family": MONO_FAMILY,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "version": UPSTREAM_VERSION,
        "chars": len(charset),
        "charset": (
            "ASCII + **GB 2312-80 全集**（汉字区 6763 字 + 符号区）+ "
            "常用标点 + 仓库用到的字符。\n"
            "**按标准算，不按仓库内容算**：母稿（`docs/`）不在本仓库的"
            "字符集口径里，按仓库算出来的子集盖不住母稿的汉字——"
            "实测仓库里那篇母稿有 120 个字不在按仓库算的子集里。"
        ),
        "faces": faces,
        "offline_source": offline,
        "note": (
            "按**标准**（GB 2312-80 全集）加仓库用到的字符子集化。"
            "**字符集由 `scripts/build_font_subset.py` 算出来**，"
            "不手工维护——`tests/test_font_subset.py` 独立复算一遍，"
            "对不上就红。\n"
            "上游钉在 2.004：Debian/Ubuntu 的 fonts-noto-cjk 就是这个版本，"
            "系统字体与内置子集的字形一致。\n"
            "**两个字重都是真的字形**：只装 Regular 的话，cairo 会用各后端"
            "自己的办法合成粗体，两个后端合成出来的不一样（实测轮廓差 "
            "3.14px）。\n"
            "**另有一族等宽**（代码块用）：上游的 Noto Sans Mono CJK SC，"
            "同版本同授权。\n"
            "**离线源**：上游 CDN 连不上的机器，用 `offline_source` 那个 "
            "Debian 包——脚本会先验字形（outline 与 advance 逐字相同），"
            "对不上直接拒绝（2.001 那种源会被挡住：字宽差 1/1000 em，"
            "版面会整体移位）。"
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
    parser.add_argument("--from-bold", dest="source_bold", default=None,
                        help="用这份本地文件当粗体上游")
    parser.add_argument(
        "--from-ttc", dest="ttc_dir", default=None,
        help="用这个目录里的 TTC 当离线源（Debian 的 fonts-noto-cjk 20220127 "
             "解包后的目录；里面含 sans 与 mono 两族，按 PostScript 名找面）")
    args = parser.parse_args()

    chars = charset()
    print(f"字符集：{len(chars)} 个"
          f"（GB 2312-80 全集 {len(standard_charset())} + 仓库的 "
          f"{len(repo_charset())}）")

    face_records = []
    offline_record = dict(OFFLINE_SOURCE)
    temp_dir = Path(tempfile.mkdtemp(prefix="aiv-font-src-"))
    try:
        for face in FACES:
            style = face["style"]
            urls = face["upstream_urls"]
            expected = face["upstream_sha256"]

            if args.ttc_dir:
                ttc_path = Path(args.ttc_dir) / OFFLINE_SOURCE["ttc"][face["ttc"]]
                if not ttc_path.is_file():
                    raise SystemExit(
                        f"离线源目录里没有 {ttc_path.name}：{ttc_path}\n"
                        f"台账钉的离线源是 "
                        f"{OFFLINE_SOURCE['package']} {OFFLINE_SOURCE['version']}"
                        f"（{OFFLINE_SOURCE['url']}）")
                source = extract_face_from_ttc(
                    ttc_path, face["source_ps"], temp_dir)
                print(f"离线源：{ttc_path.name} 里的 {face['source_ps']}")
                from fontTools.ttLib import TTFont

                verify_source(face, TTFont(str(source)))
            elif args.source and style == "Regular" and expected:
                source = Path(args.source)
                actual = sha256_of(source)
                if actual != expected:
                    raise SystemExit(
                        f"这份文件的 sha256 与台账不符：\n"
                        f"  期望 {expected}\n"
                        f"  实际 {actual}"
                    )
                print(f"用本地上游：{source}")
            elif args.source_bold and style == "Bold" and expected:
                source = Path(args.source_bold)
                actual = sha256_of(source)
                if actual != expected:
                    raise SystemExit(
                        f"粗体上游的 sha256 与台账不符：\n"
                        f"  期望 {expected}\n"
                        f"  实际 {actual}"
                    )
                print(f"用本地上游：{source}")
            else:
                if not expected:
                    raise SystemExit(
                        f"{face['file']} 没有钉住的上游 sha256，"
                        f"只能走离线源：--from-ttc")
                source = fetch_upstream(
                    FONT_DIR / f"_upstream_{face['postscript_name']}.otf",
                    urls, expected)

            subset_path = build(source, chars, face)
            record = {
                "style": style,
                "family": face["family"],
                "file": face["file"],
                "postscript_name": face["postscript_name"],
                "upstream": urls[0],
                "subset_sha256": sha256_of(subset_path),
                "subset_bytes": subset_path.stat().st_size,
            }
            if expected:
                record["source"] = "upstream"
                record["upstream_sha256"] = expected
            else:
                # 这一面没有钉住的上游 sha256（上游 CDN 连不上）——
                # 来源钉在**离线源**上：Debian 包的 sha256 + TTC 文件名
                # + 里面的面名。台账里不写空的 sha256 充数。
                record["source"] = "offline_source"
                record["source_postscript_name"] = face["source_ps"]
                record["source_ttc"] = OFFLINE_SOURCE["ttc"][face["ttc"]]
            face_records.append(record)
            print(f"已生成 {subset_path}（{subset_path.stat().st_size} 字节）")

            if source.name.startswith("_upstream_"):
                source.unlink()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    write_manifest(chars, face_records, offline_record)
    print(f"台账 {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
