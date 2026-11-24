"""中文字体解析：跨平台挑一款能用的中文字体。

macOS 自带 `PingFang SC`；Linux 上没有等价物——PingFang 是 Apple 的授权
字体，**不能随仓库分发**。Linux 上退到开源的 `Noto Sans CJK SC` /
`Source Han Sans SC`（思源黑体）。

**代价**：同一段文字在 macOS 与 Linux 上渲染出的像素不一样（字形不同）。
文案、字幕内容一字不变，视觉上仍是同一套现代无衬线黑体。
验收口径按「视觉等价」而不是「逐像素一致」，见《形象与音色规范》。

选中的字体族名由 `font_family()` 统一给出——渲染代码不要再各自硬编码
`PingFang SC`，否则换平台时会静默画成豆腐块。

优先级：

1. `AIV_FONT_FAMILY` 环境变量（显式指定族名，最高优先级）
2. 已知路径上的字体文件——**macOS 的 PingFang 排在 Linux 的 Noto 前面**，
   这样在 macOS 上出来的画面与历史版本逐像素一致
3. `fontconfig`（Linux 上 cairo 就是靠它按族名解析字体）：问它要一款
   支持中文（`:lang=zh`）的字体
4. 都没有 → 抛错，报错信息里给出安装命令
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 环境变量：显式指定字体族名（CI、特殊机器用）
FONT_ENV = "AIV_FONT_FAMILY"

#: 内置字体的族名。
#:
#: **必须唯一**：跟系统里任何字体重名，fontconfig 就会在两份之间二选一，
#: 机器之间就不一致了。子集由 `scripts/build_font_subset.py` 生成
#: （上游 Noto Sans CJK SC，SIL OFL 1.1，允许随软件分发）。
#:
#: **两个字重共用这一个族名**：Regular 与 Bold 是同一个族的两面，
#: 操作系统靠 name ID 1（族名）相同、ID 2（子族名）不同把它们认成
#: 一族。族名分开的话，`select_font_face(family, ..., BOLD)` 在两个
#: 平台上挑到的就不是同一个字体。
BUNDLED_FAMILY = "AIV Sans CJK SC"

#: **等宽**那一族的族名（代码块用）。
#:
#: **为什么代码块不能凑合用比例字体**：比例字体的字宽不等，
#: 一行代码画出来对不齐列——代码要能一眼看出缩进层级。
#:
#: 同样必须唯一——跟系统里任何字体重名，fontconfig 就在两份之间
#: 二选一，机器之间就不一致了。
BUNDLED_MONO_FAMILY = "AIV Mono CJK SC"

#: 内置字体文件在仓库里的位置。
#:
#: **两个字重都要在**：只装 Regular 的时候，cairo 会**合成**粗体——
#: CoreText 合成一套、FreeType 合成另一套。实测（2026-11-16）：同一段
#: 粗体文字，两个后端量出来的轮廓包围盒差 **3.14px**。合成粗体是各
#: 后端自己的做法，不是字体文件的性质。
BUNDLED_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
BUNDLED_REGULAR_PATH = BUNDLED_DIR / "AIVSansCJKSC-Regular.otf"
BUNDLED_BOLD_PATH = BUNDLED_DIR / "AIVSansCJKSC-Bold.otf"
BUNDLED_MONO_PATH = BUNDLED_DIR / "AIVMonoCJKSC-Regular.otf"
BUNDLED_PATHS = (BUNDLED_REGULAR_PATH, BUNDLED_BOLD_PATH, BUNDLED_MONO_PATH)

INSTALL_HINT = (
    "装一套中文字体：\n"
    "  内置字体（推荐：两台机器用同一份，跨机版式一致）：\n"
    "    cd video/pipeline && python3 scripts/install_font.py\n"
    "  Debian/Ubuntu: sudo apt-get install -y fonts-noto-cjk\n"
    "  Fedora/RHEL:  sudo dnf install google-noto-sans-cjk-fonts\n"
    "  Arch:         sudo pacman -S noto-fonts-cjk\n"
    "  或自带字体：把 NotoSansCJK-Regular.ttc 放进 "
    "~/.local/share/fonts/ 后跑 fc-cache -f"
    "\n也可以用 " + FONT_ENV + "=<族名> 显式指定字体族。"
)

# 探测不到字形时的探针字符（Unicode 私有区，字体一般没有）
_MISSING_GLYPH = "\ue000"


#: 已经说过的提醒（**同一件事只说一次**）。
#:
#: 为什么：批渲染时每一帧都会调 `mono_family()`，不合并的话，一段
#: 一分钟的片子能喊上千遍同一句话——那是噪音，不是提醒。
_WARNED: set[str] = set()


def _warn_once(message: str) -> None:
    """往 stderr 说一声，**同一句话只说一次**。"""
    if message in _WARNED:
        return
    _WARNED.add(message)
    print(message, file=sys.stderr)


def reset_warnings() -> None:
    """把「已经说过」清空——让下一句提醒重新说一遍（测试用）。"""
    _WARNED.clear()


@dataclass(frozen=True)
class FontCandidate:
    """一个候选字体：文件路径 → cairo 用的字体族名。"""

    path: str
    family: str
    label: str


@dataclass(frozen=True)
class ResolvedFont:
    """挑中的那款字体。"""

    family: str
    path: str | None
    label: str
    resolves: bool


# ---- macOS：系统自带 PingFang SC ----------------------------------------

MACOS_CANDIDATES = (
    FontCandidate("/System/Library/Fonts/PingFang.ttc",
                  "PingFang SC", "PingFang SC（macOS 自带）"),
    FontCandidate("/System/Library/Fonts/PingFang SC.ttc",
                  "PingFang SC", "PingFang SC（macOS 自带）"),
)

# macOS 新版把 PingFang 放进可下载资产目录，文件名带哈希，需 glob
MACOS_ASSET_GLOB = (
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/*/AssetData/PingFang.ttc"
)

# ---- Linux：开源中文字体 --------------------------------------------------

LINUX_CANDIDATES = (
    FontCandidate("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "Noto Sans CJK SC", "Noto Sans CJK SC（fonts-noto-cjk）"),
    FontCandidate("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
                  "Noto Sans CJK SC", "Noto Sans CJK SC（fonts-noto-cjk）"),
    FontCandidate("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                  "Noto Sans CJK SC", "Noto Sans CJK SC（fonts-noto-cjk）"),
    FontCandidate("/usr/share/fonts/opentype/noto/NotoSansCJK-VF.ttc",
                  "Noto Sans CJK SC", "Noto Sans CJK SC（可变字重）"),
    FontCandidate("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
                  "Source Han Sans SC", "思源黑体 Source Han Sans SC"),
    FontCandidate("/usr/share/fonts/truetype/source-han-sans/SourceHanSansSC-Regular.otf",
                  "Source Han Sans SC", "思源黑体 Source Han Sans SC"),
)

# 自己装到 home / /usr/local 下的
USER_FONT_GLOBS = (
    "~/.local/share/fonts/**/NotoSansCJK*",
    "~/.local/share/fonts/**/SourceHanSansSC*",
    "~/.fonts/**/NotoSansCJK*",
    "~/.fonts/**/SourceHanSansSC*",
    "/usr/local/share/fonts/**/NotoSansCJK*",
    "/usr/local/share/fonts/**/SourceHanSansSC*",
)

# fontconfig 兜底时优先问这些族名
FALLBACK_FAMILIES = (
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    "WenQuanYi Zen Hei",
)


def _expand(patterns: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for pattern in patterns:
        out.extend(sorted(glob.glob(os.path.expanduser(pattern), recursive=True)))
    return out


def _all_candidates() -> list[FontCandidate]:
    """所有候选，按优先级排。

    **仓库内置的子集排第一**：两台机器装同一份字体文件，跨机的
    步进宽度与收字号结果才一致（实测同一份文件下 CoreText 与 FreeType
    的步进差 ≤ 0.45px）。没装内置字体就落到系统字体上——那是退路，
    不是首选。
    """
    candidates: list[FontCandidate] = [
        FontCandidate(str(BUNDLED_REGULAR_PATH), BUNDLED_FAMILY,
                      "AIV Sans CJK SC（仓库内置子集）"),
    ]
    candidates.extend(MACOS_CANDIDATES)
    candidates.extend(
        FontCandidate(path, "PingFang SC", "PingFang SC（macOS 可下载资产）")
        for path in _expand((MACOS_ASSET_GLOB,))
    )
    candidates.extend(LINUX_CANDIDATES)
    candidates.extend(
        FontCandidate(path, "Noto Sans CJK SC", "Noto Sans CJK SC（用户自装）")
        for path in _expand(USER_FONT_GLOBS)
    )
    return candidates


def _cairo():
    """惰性取 cairo 模块。

    cairo 是原生扩展：导入它要装 libcairo。字体解析（列字体、问
    fontconfig）用不上它，所以只有真的要量文字时才 import——本模块
    导入时不拖上这个依赖。
    """
    import cairo

    return cairo


def _resolved_width(family: str, sample: str = "并行解码") -> float:
    """cairo 实际解析该字体族后的文本宽度。"""
    cairo = _cairo()

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    ctx = cairo.Context(surface)
    select_font(ctx, family)
    ctx.set_font_size(40)
    return ctx.text_extents(sample).width


@lru_cache(maxsize=1)
def _fc_families() -> frozenset[str] | None:
    """系统里 fontconfig 认得的**所有**族名。

    **fontconfig 不可用时返回 `None`**（macOS 上没有 `fc-list`）——
    调用方据此退回宽度判定。

    **为什么不用 `fc-list :family=X` 过滤**：那走的是 pattern 匹配，
    族名里的 `*` `?` 会被当通配符。列全量再精确比对，没有这种坑。
    """
    exe = shutil.which("fc-list")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "--format=%{family}\\n"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        for name in line.split(","):
            name = name.strip()
            if name:
                names.add(name)
    return frozenset(names)


def family_resolves(family: str) -> bool:
    """这个族名能不能被 cairo 解析出来（而不是静默回退到默认字体）。

    **两种判法，按系统选**：

    - **fontconfig 在场（Linux）**：直接问它「这个族名在不在」。
      **不能只看宽度**——本仓库内置的子集就是 Noto Sans CJK SC 的子集，
      与系统里那款 Noto 的字宽**逐项相同**。宽度比法在这里必然失手：
      实测同机上「AIV Sans CJK SC」与「__NoSuchFontFamily__」的宽度
      只差 **0.2px**（门槛是 0.5px），于是「装没装」判不出来——
      **没装的会被当成装了的（用了系统 Noto 却以为用了内置子集），
      装了的反而被当成没装**（内置子集明明在位却一直没人用）。
    - **没有 fontconfig（macOS）**：退回宽度判定。那边的默认字体是
      PingFang SC，与内置子集的字宽差得开，宽度比法有效。
    """
    families = _fc_families()
    if families is not None:
        return family in families

    try:
        fallback = _resolved_width("__NoSuchFontFamily__")
        return abs(_resolved_width(family) - fallback) > 0.5
    except Exception:
        return False


def bold_face_resolves(family: str | None = None) -> bool:
    """粗体用的是**真的 Bold 字形**，还是后端**合成**出来的。

    **怎么判**：看步进。**合成粗体不改步进**——CoreText 与 FreeType
    合成出来的字形轮廓不一样，但步进都还是原来那个 Regular 的步进。
    所以：

    - 粗体的步进 == 常规的步进 → 用的是合成粗体；
    - 粗体的步进 != 常规的步进 → 用的是真的 Bold 字形。

    实测（Noto Sans CJK SC）：Bold 的 'A' 是 641/1000 em，Regular 的是
    608/1000 em——差得开，一眼就能分辨。

    **为什么要在意**：合成粗体是**各后端自己的做法**，两个平台合成出来
    的不一样（实测轮廓包围盒差 3.14px）。于是「几何只由字体文件决定」
    这条前提在粗体上不成立，跨机版式就对不上。
    """
    cairo = _cairo()

    face = family if family else font_family()
    try:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        ctx = cairo.Context(surface)
        select_font(ctx, face, bold=False)
        ctx.set_font_size(44)
        regular = ctx.text_extents("A").x_advance
        select_font(ctx, face, bold=True)
        ctx.set_font_size(44)
        bold = ctx.text_extents("A").x_advance
    except Exception:
        return False
    return abs(bold - regular) > 0.5


def mono_family() -> str:
    """给**代码块**用的字体族名。

    **等宽那族认不到就退回比例字体，并把这件事说清楚**——代码块
    画出来对不齐列，人一眼能看出来，但「为什么对不齐」不该靠猜。

    退回时不报错：比例字体照样能画，只是列对不齐。**报错会让整条
    流水线在没装字体的机器上停摆**，而那台机器本来也能出片。

    认得到的时候一律用等宽那族——**不混排**：一段代码要么全等宽，
    要么全比例。
    """
    if family_resolves(BUNDLED_MONO_FAMILY):
        return BUNDLED_MONO_FAMILY

    fallback = font_family()
    _warn_once(
        f"等宽字体「{BUNDLED_MONO_FAMILY}」认不到"
        f"（装了吗：python3 scripts/install_font.py），"
        f"代码块退回比例字体「{fallback}」——列会对不齐。",
    )
    return fallback


def mono_family_resolves() -> bool:
    """等宽那族认不认得（不退回、不出声）。"""
    return family_resolves(BUNDLED_MONO_FAMILY)


def _fc_chinese_families() -> list[str]:
    """问 fontconfig 要支持中文的字体族名（Linux 上 cairo 靠它解析）。"""
    exe = shutil.which("fc-list")
    if not exe:
        return []
    try:
        proc = subprocess.run(
            [exe, ":lang=zh", "family"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    families: list[str] = []
    for line in proc.stdout.splitlines():
        for name in line.split(","):
            name = name.strip()
            if name and name not in families:
                families.append(name)
    return families


@lru_cache(maxsize=1)
def resolve_font() -> ResolvedFont:
    """挑一款可用的中文字体。找不到就返回 resolves=False 的占位结果。"""
    env = os.environ.get(FONT_ENV, "").strip()
    if env:
        return ResolvedFont(env, None, f"{env}（{FONT_ENV} 指定）",
                            family_resolves(env))

    for candidate in _all_candidates():
        if not os.path.exists(candidate.path):
            continue
        # **文件在 ≠ cairo 认得**：内置字体躺在仓库里，但没装进 OS 的
        # 字体目录，cairo 照样找不到它（macOS 走 CoreText，不认
        # fontconfig 目录）。认不得就接着找下一个候选——
        # 早先这里是「第一个存在的文件就赢」，于是内置字体明明还没装，
        # 整条渲染链却直接报「找不到中文字体」，连系统的 Noto 都用不上。
        if not family_resolves(candidate.family):
            continue
        return ResolvedFont(
            candidate.family, candidate.path, candidate.label, True,
        )

    # fontconfig 兜底：先问已知族名，再问系统里任何一款支持中文的字体
    tried: list[str] = []
    for family in list(FALLBACK_FAMILIES) + _fc_chinese_families():
        if family in tried:
            continue
        tried.append(family)
        if family_resolves(family):
            return ResolvedFont(family, None, f"{family}（fontconfig）", True)

    return ResolvedFont(MACOS_CANDIDATES[0].family, None,
                        "未找到中文字体", False)


def reset_font_cache() -> None:
    """改完环境变量或装完字体后，让下一次解析重新探测。"""
    resolve_font.cache_clear()
    # **族名清单也要重新读**：装完字体之后系统里多了一个族，
    # 清单还是旧的就会说「认不得」。
    _fc_families.cache_clear()


def font_family() -> str:
    """给 `ctx.select_font_face()` 用的字体族名。"""
    return resolve_font().family


def select_font(ctx, family: str | None = None, *, bold: bool = False) -> None:
    """把 ctx 的字体设成**要画/要量的那一个**，并且**关掉 hinting**。

    **所有地方都必须走这个函数**——直接调 `ctx.select_font_face` 的地方
    一律视为 bug（有守卫盯着，见 `tests/test_fonts.py`）。
    理由是下面这段：

    **hinting 会让「几何」不再是字体文件的性质。** cairo 在 Linux 上走
    FreeType，默认**开着** autohinter：轮廓点被吸附到像素网格，度量被
    取整。于是「步进宽度」「墨迹宽度」这些本该只由字体文件决定的量，
    在 Linux 上变成了「字体文件 × 栅格化后端」的产物。

    实测（2026-11-16，Linux / FreeType vs macOS / CoreText，同一份字体
    文件）：开着 hinting 时，一行字的步进能差 **68px**——因为墨迹宽度
    被取整，`fit_size` 收出来的字号跟着差 3.2px，整条轮廓再整体缩放。
    关掉之后，步进与轮廓包围盒逐项相等。

    **关掉 hinting 对 macOS 是空操作**：CoreText 后端本来就不做 hinting
    （实测同一段文字在开/关两种设置下量出来的 advance、墨迹宽、轮廓
    包围盒**逐项相等**）——所以单是这一项，既有的像素基准不用重录。

    `family` 不给就用当前解析到的族名；给了就用那个（墨迹测量有时要
    量一个别的族）。
    """
    cairo = _cairo()

    options = cairo.FontOptions()
    options.set_hint_style(cairo.HINT_STYLE_NONE)
    options.set_hint_metrics(cairo.HINT_METRICS_OFF)
    ctx.set_font_options(options)

    ctx.select_font_face(
        family if family else font_family(),
        cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )


def assert_font_available() -> None:
    """字体不可用时立即失败，避免跨机渲染出豆腐块。"""
    font = resolve_font()
    if font.resolves:
        return
    raise RuntimeError(
        f"找不到可用的中文字体（当前族名 {font.family}），拒绝渲染"
        f"（避免输出豆腐块）。\n"
        f"装一套开源中文字体即可：\n{INSTALL_HINT}\n"
        f"也可以用 {FONT_ENV}=<族名> 显式指定字体族。"
    )


def missing_glyph(ch: str) -> bool:
    """这个字符在当前字体里是不是画不出来（会变成豆腐块）。"""
    cairo = _cairo()

    def pixels(text: str) -> bytes:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 80, 80)
        ctx = cairo.Context(surface)
        select_font(ctx)
        ctx.set_font_size(40)
        ctx.set_source_rgb(0, 0, 0)
        ctx.move_to(4, 40)
        ctx.show_text(text)
        surface.flush()
        return bytes(surface.get_data())

    return pixels(ch) == pixels(_MISSING_GLYPH)


# ---- 缺字判定（D5：盖不住的那些字当场报错） ----------------------------

#: 放行缺字的环境变量。
#:
#: **放行时必须往 stderr 出声**——「不静默」的底线是：可以放行，不许无声。
ALLOW_MISSING_ENV = "AIV_ALLOW_MISSING_GLYPHS"

#: 认可「放行」的值（其余一律当没设）。
ALLOW_MISSING_VALUES = ("1", "true", "yes", "on")

#: 内置子集文件 → 族名（查 cmap 用）。
BUNDLED_FAMILY_FILES = {
    BUNDLED_FAMILY: BUNDLED_REGULAR_PATH,
    BUNDLED_MONO_FAMILY: BUNDLED_MONO_PATH,
}


class MissingGlyphs(RuntimeError):
    """字体盖不住要画的字。

    **当场报，不画豆腐块**：豆腐块在成片里是「一段没有人声的旁白配着一屏
    方框」，观众看不懂是内容的问题还是片子的问题。
    """


def _format4_intervals(data: bytes, base: int) -> list[tuple[int, int]]:
    """cmap 格式 4（BMP）盖住的码位区间。

    **逐个码位查一遍**：只有映射到**真字形**的才算盖住——映射到
    `.notdef`（0）的码位画出来是豆腐块。
    """
    seg_count = int.from_bytes(data[base + 6:base + 8], "big") // 2
    end_base = base + 14
    start_base = end_base + seg_count * 2 + 2
    delta_base = start_base + seg_count * 2
    range_base = delta_base + seg_count * 2

    intervals: list[tuple[int, int]] = []
    for index in range(seg_count):
        end = int.from_bytes(data[end_base + index * 2:end_base + index * 2 + 2],
                             "big")
        start = int.from_bytes(
            data[start_base + index * 2:start_base + index * 2 + 2], "big")
        if start > end or start == 0xFFFF:
            continue
        delta = int.from_bytes(
            data[delta_base + index * 2:delta_base + index * 2 + 2],
            "big", signed=True)
        range_offset = int.from_bytes(
            data[range_base + index * 2:range_base + index * 2 + 2], "big")

        run_start: int | None = None
        for code in range(start, min(end, 0xFFFE) + 1):
            if range_offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                at = range_base + index * 2 + range_offset + (code - start) * 2
                if at + 2 > len(data):
                    glyph = 0
                else:
                    glyph = int.from_bytes(data[at:at + 2], "big")
                    if glyph:
                        glyph = (glyph + delta) & 0xFFFF
            if glyph:
                if run_start is None:
                    run_start = code
            elif run_start is not None:
                intervals.append((run_start, code - 1))
                run_start = None
        if run_start is not None:
            intervals.append((run_start, min(end, 0xFFFE)))
    return intervals


def _format12_intervals(data: bytes, base: int) -> list[tuple[int, int]]:
    """cmap 格式 12（可扩到 U+10FFFF）盖住的码位区间。

    格式 12 的字形号在每组里**连续**，所以一组里只有**第一个**码位可能
    映射到 `.notdef`（起始字形号是 0 时）——不用逐个码位查。
    """
    groups = int.from_bytes(data[base + 12:base + 16], "big")
    intervals: list[tuple[int, int]] = []
    for index in range(groups):
        at = base + 16 + index * 12
        start = int.from_bytes(data[at:at + 4], "big")
        end = int.from_bytes(data[at + 4:at + 8], "big")
        first_glyph = int.from_bytes(data[at + 8:at + 12], "big")
        if start > end:
            continue
        if first_glyph == 0:
            start += 1
            if start > end:
                continue
        intervals.append((start, end))
    return intervals


def _merge_intervals(intervals: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """区间排序并合并（相邻的接起来）。"""
    if not intervals:
        return ()
    ordered = sorted(intervals)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _parse_cmap(data: bytes) -> tuple[tuple[int, int], ...]:
    """cmap 表 → 盖住的码位区间。"""
    count = int.from_bytes(data[2:4], "big")
    intervals: list[tuple[int, int]] = []
    for index in range(count):
        at = 4 + index * 8
        sub = int.from_bytes(data[at + 4:at + 8], "big")
        fmt = int.from_bytes(data[sub:sub + 2], "big")
        if fmt == 4:
            intervals.extend(_format4_intervals(data, sub))
        elif fmt == 12:
            intervals.extend(_format12_intervals(data, sub))
    return _merge_intervals(intervals)


@lru_cache(maxsize=4)
def _read_coverage(path: str) -> tuple[tuple[int, int], ...]:
    """读一个字体文件的 cmap，返回它盖住的码位区间。

    **纯 Python，不引 fontTools**：fontTools 只在**构建期**用（生成与
    校验子集）。运行时多一个依赖，就多一份「装不上」的风险。
    """
    file_path = Path(path)
    with file_path.open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12:
            raise ValueError(f"{file_path} 不是字体文件（头太短）")
        table_count = int.from_bytes(header[4:6], "big")
        handle.seek(12)
        directory = handle.read(16 * table_count)
        offset = length = None
        for index in range(table_count):
            entry = directory[index * 16:(index + 1) * 16]
            if entry[:4] == b"cmap":
                offset = int.from_bytes(entry[8:12], "big")
                length = int.from_bytes(entry[12:16], "big")
                break
        if offset is None or length is None:
            raise ValueError(f"{file_path} 里没有 cmap 表")
        handle.seek(offset)
        data = handle.read(length)
    return _parse_cmap(data)


def bundled_coverage(family: str | None = None) -> tuple[tuple[int, int], ...]:
    """内置子集盖住的码位区间（按族名选文件）。"""
    path = BUNDLED_FAMILY_FILES.get(family or BUNDLED_FAMILY,
                                    BUNDLED_REGULAR_PATH)
    return _read_coverage(str(path))


def covers(intervals: tuple[tuple[int, int], ...], code: int) -> bool:
    """码位在不在这些区间里（二分）。"""
    low, high = 0, len(intervals) - 1
    while low <= high:
        mid = (low + high) // 2
        start, end = intervals[mid]
        if code < start:
            high = mid - 1
        elif code > end:
            low = mid + 1
        else:
            return True
    return False


def missing_chars(text: str, family: str | None = None) -> list[str]:
    """text 里**内置子集盖不住**的字（按出现顺序，不重复）。

    **为什么按内置子集判，而不是按当前这台机器解析到的族**：内置子集是
    **入库的事实**（它盖住 GB 2312-80 全集，是 CI 里跑得动的判据）。
    当前机器恰好用着系统字体、盖得更多，不代表入库的资产盖得住——
    换台机器、换个 CI runner 就画成豆腐块。

    **控制字符不算缺**（换行、制表不是字形）。
    """
    intervals = bundled_coverage(family)
    missing: list[str] = []
    for ch in text:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            continue
        if covers(intervals, ord(ch)):
            continue
        if ch not in missing:
            missing.append(ch)
    return missing


def _allow_missing() -> bool:
    """放行开关开了没有。"""
    return os.environ.get(ALLOW_MISSING_ENV, "").strip().lower() \
        in ALLOW_MISSING_VALUES


def check_glyphs(text: str, family: str | None = None) -> None:
    """画之前查缺字。

    - **缺了当场报错**（`MissingGlyphs`）：报出是哪些字，并给出补救办法；
    - 设了 `AIV_ALLOW_MISSING_GLYPHS=1` 就放行，但**往 stderr 出声**
      （可以放行，不许无声）。
    """
    missing = missing_chars(text, family)
    if not missing:
        return

    if _allow_missing():
        _warn_once(
            f"字体盖不住 {len(missing)} 个字（{''.join(missing[:20])}）——"
            f"按 {ALLOW_MISSING_ENV} 放行，画出来是豆腐块。"
        )
        return

    listed = "".join(missing[:20]) + ("…" if len(missing) > 20 else "")
    raise MissingGlyphs(
        f"字体盖不住要画的 {len(missing)} 个字：{listed}\n"
        f"当场报错，不画豆腐块。\n"
        f"补救：把用到的字并进 assets/fonts/extra_chars.txt，重跑\n"
        f"  python3 scripts/build_font_subset.py\n"
        f"重建子集（上游字体本身没有的字，要先解决上游）。\n"
        f"确实要放过：设 {ALLOW_MISSING_ENV}=1（会往 stderr 出声）。"
    )

