"""字体解析的守卫：跨平台挑字体，且渲染代码不再硬编码 macOS 字体。"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from pyv import fonts

PIPELINE_DIR = Path(__file__).resolve().parent.parent
PYV_DIR = PIPELINE_DIR / "pyv"
AIV_ROOT = PIPELINE_DIR.parent


@pytest.fixture(autouse=True)
def _reset_cache():
    """字体解析是缓存的，改完环境变量必须清缓存，否则测的是上一轮的结果。"""
    fonts.reset_font_cache()
    yield
    fonts.reset_font_cache()


def test_resolve_font_finds_a_usable_family():
    """这台机器上必须能解析出一款中文字体（否则渲染会直接抛错）。"""
    font = fonts.resolve_font()
    assert font.resolves, f"没解析出可用字体：{font}"
    assert font.family.strip()


def _installed_copy(path: Path) -> Path | None:
    """这个字体文件在 OS 字体目录里的副本（装了才有）。"""
    for directory in (Path.home() / ".local" / "share" / "fonts",
                      Path.home() / "Library" / "Fonts",
                      Path("/usr/local/share/fonts")):
        candidate = directory / path.name
        if candidate.is_file():
            return candidate
    return None


def test_an_installed_bundled_font_counts_as_resolvable():
    """**装了就要说认得**——哪怕它的字宽跟系统默认一模一样。

    为什么这条要紧：内置子集就是 Noto Sans CJK SC 的子集，**字宽跟
    系统里那款 Noto 逐项相同**。用「宽度差 > 0.5px」判装没装，在这种
    机器上必然失手（实测同机上「AIV Sans CJK SC」与「__NoSuchFontFamily__」
    的宽度只差 **0.2px**）——于是「装了」被说成「没装」，内置子集一直
    没人用，跨机的步进也就一直对不上。

    没装（或者装的是旧版本）的机器上这条会说明原因（skip）。
    """
    import hashlib

    if not fonts.BUNDLED_REGULAR_PATH.is_file():
        pytest.skip(f"内置字体不在仓库里：{fonts.BUNDLED_REGULAR_PATH}")

    installed = _installed_copy(fonts.BUNDLED_REGULAR_PATH)
    if installed is None:
        pytest.skip(
            "内置字体没装进 OS 字体目录（跑 python3 scripts/install_font.py）"
        )

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    if sha256(installed) != sha256(fonts.BUNDLED_REGULAR_PATH):
        pytest.skip(f"装的是旧版本（{installed}），不是仓库里这一份")

    assert fonts.family_resolves(fonts.BUNDLED_FAMILY), (
        f"字体已经装在 {installed}，却说不认得「{fonts.BUNDLED_FAMILY}」——"
        f"内置子集等于没用上"
    )


def test_a_family_that_does_not_exist_is_not_resolvable():
    """**不存在的族名必须说认不得**——否则「认得」这个词就没意义了。"""
    assert not fonts.family_resolves("__NoSuchFontFamily__")


def test_environment_variable_wins(monkeypatch):
    monkeypatch.setenv(fonts.FONT_ENV, "Some Explicit Family")
    fonts.reset_font_cache()
    font = fonts.resolve_font()
    assert font.family == "Some Explicit Family"
    assert fonts.FONT_ENV in font.label


def test_macos_font_is_tried_before_linux_fonts():
    """macOS 上必须继续用 PingFang SC——否则历史成片的画面会变。"""
    macos = {c.family for c in fonts.MACOS_CANDIDATES}
    assert macos == {"PingFang SC"}
    families = [c.family for c in fonts._all_candidates()]
    assert families.index("PingFang SC") < families.index("Noto Sans CJK SC")


def test_linux_fallback_is_a_cjk_font():
    """Linux 上退到的必须是开源中文字体（PingFang 是 Apple 授权，不能分发）。"""
    families = {c.family for c in fonts.LINUX_CANDIDATES}
    assert "Noto Sans CJK SC" in families
    assert "Source Han Sans SC" in families
    for candidate in fonts.LINUX_CANDIDATES:
        assert candidate.path.startswith("/usr/share/fonts/")


def test_no_linux_candidate_points_at_apple_font():
    """Linux 候选里不能出现 /System/Library（那是 macOS 专有路径）。"""
    for candidate in fonts.LINUX_CANDIDATES:
        assert "/System/" not in candidate.path


def test_assert_font_available_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr(
        fonts, "resolve_font",
        lambda: fonts.ResolvedFont("Nope", None, "没有", False),
    )
    with pytest.raises(RuntimeError) as excinfo:
        fonts.assert_font_available()
    message = str(excinfo.value)
    assert "fonts-noto-cjk" in message
    assert fonts.FONT_ENV in message


def test_assert_font_available_passes_when_resolvable(monkeypatch):
    monkeypatch.setattr(
        fonts, "resolve_font",
        lambda: fonts.ResolvedFont("Some Family", None, "有", True),
    )
    fonts.assert_font_available()


def test_palette_delegates_to_fonts(monkeypatch):
    from pyv import palette

    called = []
    monkeypatch.setattr(fonts, "assert_font_available",
                        lambda: called.append(1))
    palette.assert_font_available()
    assert called == [1]


def _source_files() -> list[Path]:
    """**流水线**的源码：管线与脚本，不含 tests（测试自己会提到这些路径）。

    「不许硬编码 macOS 字体」那两条只扫这里——它们守的是**渲染管线**。
    素材脚本（`brand/`、`character/`）是另一回事：它们把字画进**已入库的
    素材**，不是每次出片都跑；`brand/scripts/fix_plates.py` 甚至走的是
    ffmpeg + 字体文件（带 Linux 退路），跟 cairo 的族名解析不是一回事。
    """
    out = []
    for directory in (PYV_DIR, PIPELINE_DIR / "scripts"):
        if not directory.is_dir():
            continue
        out.extend(sorted(directory.rglob("*.py")))
    return out


def _drawing_files() -> list[Path]:
    """**所有用 cairo 画字的地方**：流水线 + 素材脚本。

    「选字体必须走 `fonts.select_font`」那条扫这里——**凡是用 cairo
    画字的代码**，都要关掉 hinting，否则 Linux 上量出来的宽度跟 macOS
    对不上（素材脚本也一样：它们把字画进已入库的素材，跨机不一致就等于
    「同一份素材在两台机器上长得不一样」）。
    """
    out = []
    for directory in (PYV_DIR, PIPELINE_DIR / "scripts",
                      AIV_ROOT / "character" / "scripts",
                      AIV_ROOT / "brand" / "scripts"):
        if not directory.is_dir():
            continue
        out.extend(sorted(directory.rglob("*.py")))
    return out


def test_no_render_module_hardcodes_pingfang():
    """渲染代码不许再硬编码「PingFang SC」——换平台时会静默画成豆腐块。"""
    offenders = []
    for path in _source_files():
        if path.name == "fonts.py":
            continue          # 候选表本身当然要提这个名字
        source = path.read_text(encoding="utf-8")
        if re.search(r'"PingFang SC"|\'PingFang SC\'', source):
            offenders.append(str(path.relative_to(AIV_ROOT)))
    assert offenders == []


def test_no_module_hardcodes_apple_font_paths():
    """macOS 专有的字体路径只允许出现在 fonts.py 的候选表里。"""
    offenders = []
    pattern = re.compile(r"/System/Library/Fonts/")
    for path in _source_files():
        if path.name == "fonts.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(AIV_ROOT)))
    assert offenders == []


def test_missing_glyph_detects_a_character_the_font_lacks():
    """字体里没有的字符会被画成豆腐块，必须能识别出来。"""
    # 私有区字符，几乎所有中文字体都没有
    assert fonts.missing_glyph("\ue123")
    # 常用汉字肯定有
    assert not fonts.missing_glyph("并")


def test_font_family_matches_resolved_font():
    assert fonts.font_family() == fonts.resolve_font().family


# ------------------------------------------------- 几何只由字体文件决定
#
# **跨机版式一致的前提**：步进宽度、墨迹宽度这些量，必须是**字体文件
# 的性质**，不能掺进「栅格化后端」的因素。cairo 在 Linux 上走 FreeType，
# 默认开着 autohinter——轮廓吸附像素网格、度量取整——掺进来的就是它。


def test_the_helper_turns_hinting_off():
    """`fonts.select_font` 必须把 hinting 关掉。

    开着 hinting 时，Linux 量出来的步进跟 macOS 能差 **68px**（实测，
    2026-11-16）：墨迹宽度被取整，`fit_size` 收出来的字号跟着差 3.2px，
    整条轮廓再整体缩放。关掉之后两边逐项相等。
    """
    cairo = pytest.importorskip("cairo")
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    ctx = cairo.Context(surface)
    fonts.select_font(ctx)
    options = ctx.get_font_options()
    assert options.get_hint_style() == cairo.HINT_STYLE_NONE, (
        "hinting 还开着——Linux 上量出来的宽度会跟 macOS 对不上"
    )
    assert options.get_hint_metrics() == cairo.HINT_METRICS_OFF, (
        "度量还在取整——Linux 上量出来的步进会跟 macOS 对不上"
    )


def test_every_font_selection_goes_through_the_helper():
    """**除了 `pyv/fonts.py`，不许有地方直接调 `ctx.select_font_face`。**

    **为什么**：关 hinting 的开关跟「选哪款字体」是**同一个动作**
    （`fonts.select_font` 两件一起做）。少走一处，那处的度量就又是
    「字体文件 × 栅格化后端」的产物——跨机对不上，而且**静默**地对不上：
    画面照常出，只有跨机指纹守卫会红，而那要等到 CI 上才发现。

    判据是**结构性**的（不许绕过那个入口），不是「某段文字的宽度必须
    等于多少」——后者会被合法例外打脸。

    **扫的是所有用 cairo 画字的地方**（流水线 + 素材脚本）——素材脚本
    把字画进已入库的素材，跨机不一致就等于「同一份素材在两台机器上
    长得不一样」。
    """
    offenders = []
    for path in _drawing_files():
        relative = path.relative_to(AIV_ROOT).as_posix()
        if relative == "pipeline/pyv/fonts.py":
            continue          # 那个入口本身当然要调 select_font_face
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "select_font_face":
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == [], (
        "这些地方直接选了字体，没走 fonts.select_font——hinting 没关，"
        "跨机版式就对不上：\n  " + "\n  ".join(offenders)
    )


def test_the_measured_advance_comes_from_the_font_file():
    """cairo 量出来的步进，必须等于**从字体文件 hmtx 算出来的**步进。

    **独立复算**：一边用 cairo 量，一边用 fontTools 读字体的 hmtx——
    两套办法各写一份、互不引用。开了 hinting 时 Linux 的度量被取整，
    这两条就对不上；用的字体不对（解析到了别的族）也对不上。

    这条比「跟 macOS 抓的基准比」更硬：它不依赖任何一份基准，
    在**每台机器上**都成立。
    """
    fontTools = pytest.importorskip("fontTools.ttLib")
    cairo = pytest.importorskip("cairo")

    if not fonts.BUNDLED_REGULAR_PATH.is_file():
        pytest.skip(f"内置字体不在仓库里：{fonts.BUNDLED_REGULAR_PATH}")

    # 从字体文件里取一个汉字的字形步进。
    font = fontTools.TTFont(str(fonts.BUNDLED_REGULAR_PATH))
    units_per_em = font["head"].unitsPerEm
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    char = next(
        (ch for ch in "取号顺序" if ord(ch) in cmap), None)
    if char is None:
        pytest.skip("内置字体里没有用来测量的汉字")
    advance_units = hmtx[cmap[ord(char)]][0]
    expected = advance_units * 60.0 / units_per_em

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
    ctx = cairo.Context(surface)
    fonts.select_font(ctx, fonts.BUNDLED_FAMILY)
    ctx.set_font_size(60)
    actual = ctx.text_extents(char).x_advance

    assert abs(actual - expected) < 0.01, (
        f"「{char}」的步进 cairo 量出 {actual:.4f}，"
        f"字体文件里是 {expected:.4f}（{advance_units}/{units_per_em} em）——"
        f"差 {abs(actual - expected):.4f}px：hinting 没关，或用的不是内置字体"
    )
