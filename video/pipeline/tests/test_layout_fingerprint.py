"""跨机布局指纹守卫。

**为什么要有它**：逐像素基准在 macOS 与 Linux 之间**不可比**——
cairo 在 macOS 走 CoreText、在 Linux 走 FreeType，栅格化不同，像素必然不同。
但**轮廓、坐标与步进宽度**是字体的性质，跨机可比。

指纹记四类量：

| 量 | 从哪来 |
| --- | --- |
| 落笔坐标 (x, y) | 场景代码里的纯算术，跨机完全一致 |
| 字号 | `fit_size` 收敛后的结果 |
| 步进宽度 `x_advance` | 字体文件的 hmtx |
| 轮廓包围盒 | `text_path` + `path_extents`，是字形轮廓不是像素 |

**这条守卫成立有两个前提**，都是踩过坑才补上的：

1. **hinting 必须关掉**（`pyv/fonts.py::select_font`）。
   Linux 上 cairo 走 FreeType，默认**开着** autohinter：轮廓点被吸附到
   像素网格、度量被取整。于是「步进宽度」这种本该只由字体文件决定的量，
   变成了「字体文件 × 栅格化后端」的产物——实测一行字能差 **68px**。
   关掉之后，FreeType 量出来的步进与字体文件的 hmtx **逐项相等**。

2. **粗体必须是真的 Bold 字形**（两个字重都入库）。
   只装常规字重的话，cairo 会**合成**粗体，而合成是各后端自己的做法：
   实测同一段粗体文字，两个后端的轮廓包围盒差 **3.14px**。

**容差写死字面量**，不从被测代码 import——阈值自证等于永远绿。
每个容差的实测依据见下面的「容差」一节。

**另外钉住三件事**：

1. **覆盖**：指纹的帧集合 == 六期契约的段 × 2 画幅 × 5 时刻；
2. **范围没漂**：测试里的时刻与画幅是**独立写的字面量**，与生产代码对得上；
3. **探针看得见字**：契约里每一条文案都真的被画出去过——漏掉一条
   画字路径，指纹就会少一块，而少的那块在基准与比对两侧同时消失，
   守卫看着绿、实际没守。
"""
from __future__ import annotations

import ast
import importlib
import json
import subprocess
from pathlib import Path

import pytest

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod
from pyv import fingerprint
from pyv import fonts

AIV_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = AIV_ROOT / "pipeline"
REPO_ROOT = AIV_ROOT.parent
FIXTURE = Path(__file__).parent / "fixtures" / "layout_fingerprint.json"

#: 扫的时刻。**独立取值**——不 import 生产代码。
TIMES = (0.0, 0.25, 0.5, 0.75, 1.0)

#: 两个画幅。**独立取值**。
CANVASES = (("horizontal", 1920, 1080), ("vertical", 1080, 1920))

#: 允许直接往 ctx 上画字的模块，各有理由（见下面的守卫）。
#:
#: 判据是「**这个调用画不画视频画面**」：`pyv/draw.py` 与
#: `pyv/subtitle.py` 画画面，其余三个都画在**自己的临时表面**上——
#: 量墨迹、探字形、量轮廓，都不进成片。
ALLOWED_DIRECT = {
    "pyv/draw.py",       # draw.text 的实现——文字出画面只有这一条路
    "pyv/subtitle.py",   # 字幕走 text_path（描边必须转路径），另一条路
    "pyv/inkbox.py",     # 量墨迹用的离屏表面，不进画面
    "pyv/fonts.py",      # 探字形：80×80 的临时表面，判「有没有墨」
    "pyv/fingerprint.py",  # 探针自己：量轮廓包围盒
}

#: 直接往 ctx 上画字的两个方法。绕过它们就是绕过探针。
DIRECT_DRAW = ("show_text", "text_path")

# ---------------------------------------------------------------- 容差
#
# **全部写死字面量，不从被测代码 import**——阈值从被测代码取，等于自证，
# 永远是绿的。
#
# **每个数字都来自实测**（2026-11-16，真实 Linux/FreeType 容器 vs
# macOS/CoreText，同一份内置字体文件、hinting 已关、两个字重都是真字形）：
#
# | 量 | 实测最大差 | 容差 | 余量 |
# | --- | --- | --- | --- |
# | 落笔坐标 x / y | 0.000 | 0.01 | 纯算术，跨机完全一致 |
# | 字号 | 0.027 | 0.2 | 约 7 倍 |
# | 步进宽度 | 0.812 | 2.0 | 约 2.5 倍 |
# | 轮廓包围盒 | 0.711 | 2.0 | 约 2.8 倍 |
#
# **坐标为什么能是 0.000**：落笔点是场景代码里的纯算术，跟字体无关。
#
# **步进与轮廓那 0.8px 从哪来**：FreeType **严格照字体文件的 hmtx 走**
# （实测：ASCII 全部字形，cairo 量出来的步进与 hmtx 逐项相等）；CoreText
# 对**少数拉丁字形**会多给几个 em 单位（实测 'A' +8、'V' +10、'Y' +13、
# 'f' +5，单位是 1/1000 em）。字体文件本身是自洽的（字形轮廓里的宽度与
# hmtx 逐项相等），所以这是 CoreText 侧的差异。
#
# 它落在字形串里会累积：'HEAP_XMAX_KEYSHR_LOCK'（两个 'A'）在 50.75px
# 上差 0.812px——就是这个 8/1000 em × 2 × 字号。
#
# **字号那 0.027px** 是上面那点墨迹宽度差透过 `fit_size` 的收敛传下来
# 的——墨迹右沿差 0.4px，收出的字号差 0.027px。
#
# **这两个容差还能抓什么**：字号差 2px（42→44）会让步进差十几 px；
# 坐标挪 3px 会被 0.01 的坐标容差抓住。真实回归远大于上面这些余量。

#: 坐标：场景代码里的纯算术，跨机应当完全一致。0.01px 吃浮点噪声。
COORD_TOLERANCE_PX = 0.01

#: 字号：`fit_size` 的收敛值。实测跨机差 ≤ 0.027px（墨迹宽度差的连带），
#: 留 0.2px 约 7 倍余量。字号是这条守卫最灵的判据——换字体导致的收字号
#: 变化动辄好几 px。
SIZE_TOLERANCE = 0.2

#: 步进宽度：FreeType 严格照 hmtx 走，CoreText 对少数拉丁字形多给几个
#: em 单位，实测跨机最大差 0.812px。取 2.0px 留约 2.5 倍余量。
ADVANCE_TOLERANCE_PX = 2.0

#: 轮廓包围盒：同一个来源（那几个字形的墨迹右沿跟着挪），实测最大差
#: 0.711px。取 2.0px 留约 2.8 倍余量。
OUTLINE_TOLERANCE_PX = 2.0

#: 每一项的字段与它的容差，顺序与 `fingerprint.FIELDS` 对齐。
CHECKS = (
    ("x", 0, COORD_TOLERANCE_PX),
    ("y", 1, COORD_TOLERANCE_PX),
    ("size", 2, SIZE_TOLERANCE),
    ("advance", 3, ADVANCE_TOLERANCE_PX),
    ("x0", 4, OUTLINE_TOLERANCE_PX),
    ("y0", 5, OUTLINE_TOLERANCE_PX),
    ("x1", 6, OUTLINE_TOLERANCE_PX),
    ("y1", 7, OUTLINE_TOLERANCE_PX),
)


def _segments():
    """磁盘上各期契约里的全部视觉段。"""
    for slug in episodes_mod.known_eps():
        path = episodes_mod.contract_path(slug)
        if not path.is_file():
            continue
        contract = contract_mod.load_contract(path)
        for segment in contract.segments:
            yield slug, segment


def _expected_keys() -> set[str]:
    return {
        f"{episode}/{segment.id}/{canvas}@{t}"
        for episode, segment in _segments()
        for canvas, _, _ in CANVASES
        for t in TIMES
    }


def _fixture() -> dict:
    assert FIXTURE.is_file(), (
        f"布局指纹基准不在：{FIXTURE}——"
        f"跑 scripts/capture_layout_fingerprint.py 抓一份"
    )
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _need_bundled_font() -> None:
    """指纹只在「同一份字体文件」下可比。

    用别的字体，步进宽度与轮廓都对不上——那时候红的是「字体不同」，
    不是「版式坏了」，报错会指错方向。所以直接跳过并说清楚。
    """
    family = fonts.font_family()
    if family == fonts.BUNDLED_FAMILY:
        return
    pytest.skip(
        f"当前在用的字体是「{family}」，不是内置的那份"
        f"「{fonts.BUNDLED_FAMILY}」——指纹只在同一份字体文件下可比。"
        f"装上内置字体：cd video/pipeline && python3 scripts/install_font.py"
    )


# ---------------------------------------------------------------- 覆盖与范围


def test_the_fingerprint_fixture_is_tracked():
    """指纹基准必须入库——否则别的机器上 clone 完就没有它。

    基准是**入库的事实**（这一版的版式长什么样），不是本地产物。
    """
    relative = FIXTURE.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{relative} 没被 git 跟踪——别的机器 clone 完就没有基准了"
    )


def test_the_fingerprint_covers_every_segment_and_canvas():
    """指纹必须覆盖每段 × 2 画幅 × 5 时刻——少一条就有一段没人守。

    两条判据：

    1. **时刻齐全**：基准里每一段 × 每个画幅，五个时刻一个都不能少
       （少抓一个时刻，那一段有一段没人守）。
    2. **磁盘上的期都盖住了**：期目录里的每一段都要在基准里——
       新加一期忘了重抓指纹，这条就红。
    """
    frames = _fixture()["frames"]
    actual = set(frames)

    moments: dict[tuple[str, str, str], set[str]] = {}
    for key in actual:
        episode, segment, canvas_at = key.split("/")
        canvas, _, moment = canvas_at.partition("@")
        moments.setdefault((episode, segment, canvas), set()).add(moment)
    wanted = {str(t) for t in TIMES}
    incomplete = {
        "/".join(key): sorted(wanted - times)
        for key, times in moments.items()
        if wanted - times
    }
    assert not incomplete, f"指纹少了时刻：{sorted(incomplete)[:5]}"

    expected = _expected_keys()
    assert expected <= actual, (
        f"指纹覆盖对不上：缺 {sorted(expected - actual)[:5]}"
    )


def test_the_fingerprint_scope_has_not_drifted():
    """测试里的时刻与画幅是**独立写的**——那就钉住它跟生产代码一致。

    两边各写一份、故意不共用代码：共用一份的话，范围改了守卫跟着改，
    守卫就永远绿。这里断言它们一致——不一致就红，提醒人改两边。
    """
    assert TIMES == fingerprint.TIMES, (
        f"采集用的时刻 {fingerprint.TIMES} 与这里写的 {TIMES} 对不上"
    )
    assert CANVASES == fingerprint.CANVASES, (
        f"采集用的画幅 {fingerprint.CANVASES} 与这里写的 {CANVASES} 对不上"
    )


def test_the_fixture_was_captured_with_the_bundled_font():
    """基准必须是拿内置字体抓的——用别的字体抓，基准没有意义。"""
    capture = _fixture()["capture"]
    assert capture["font"] == fonts.BUNDLED_FAMILY, (
        f"基准是用「{capture['font']}」抓的，不是内置的那份"
        f"「{fonts.BUNDLED_FAMILY}」——重抓："
        f"python3 scripts/capture_layout_fingerprint.py"
    )


# ---------------------------------------------------------------- 比对


def test_the_layout_fingerprint_matches():
    """每个量都在容差内。超了就报出是哪一期哪一段哪个量差多少。"""
    _need_bundled_font()
    frames = _fixture()["frames"]
    findings: list[str] = []
    # 每个量各差多少——第一行就要能看出「是哪一类量出的问题」。
    worst: dict[str, float] = {}
    for episode, segment in _segments():
        module = importlib.import_module(segment.renderer)
        for canvas, width, height in CANVASES:
            for t in TIMES:
                key = f"{episode}/{segment.id}/{canvas}@{t}"
                expected = frames[key]
                actual = fingerprint.collect_segment(
                    module, segment.params, width, height, t)
                if len(actual) != len(expected):
                    findings.append(
                        f"{key} 文字数 {len(actual)} != 基准 {len(expected)}")
                    continue
                for index, (want, got) in enumerate(zip(expected, actual)):
                    for name, slot, tolerance in CHECKS:
                        diff = abs(want[slot] - got[slot])
                        if diff > tolerance:
                            worst[name] = max(worst.get(name, 0.0), diff)
                            findings.append(
                                f"{key} 第 {index} 个文字的 {name}："
                                f"{got[slot]:.2f} vs 基准 {want[slot]:.2f}"
                                f"（差 {diff:.2f} > {tolerance}）")
    # **第一行必须自带诊断信息**：CI 只摘报错的第一行（`grep '^FAILED'`），
    # 后面那些细节在流水线注解里看不到。差在哪一类量、差多少、差在哪
    # 一次，都得在这一行里说清楚。
    breakdown = "、".join(
        f"{name} 差 {diff:.2f}px" for name, diff in
        sorted(worst.items(), key=lambda kv: -kv[1])
    ) or "无"
    assert not findings, (
        f"布局指纹对不上：{len(findings)} 项超容差（{breakdown}）\n  "
        + "\n  ".join(findings[:40])
    )


# ---------------------------------------------------------------- 探针没瞎


def test_the_drawing_path_goes_through_draw_text():
    """**场景不许直接调 `ctx.show_text` / `ctx.text_path`。**

    **为什么**：元素级遮挡守卫与布局指纹守卫都是靠拦 `draw.text`
    才知道「画面上画了哪些字」的。谁绕过 `draw.text` 直接往 ctx 上画，
    那些字就**同时从守卫的视野里消失**——基准里没有、比对时也没有，
    守卫看着绿，实际少守了一块。

    探针那边已经处理了「别名」这一层（`pyv/fingerprint.py` 扫
    `sys.modules`，凡是把 `draw.text` 别名成自己 `text` 属性的模块
    都拦），所以场景里 `from pyv.draw import text` 是允许的；
    **直接调 ctx 上的绘制方法才是绕过**。

    **允许的三处**，各有理由：

    - `pyv/draw.py`——`draw.text` 的实现，文字出画面只有这一条路；
    - `pyv/subtitle.py`——字幕走 `text_path`（描边必须转路径），
      那是另一条路，字幕的字形守卫单独管；
    - `pyv/inkbox.py`——量墨迹用的离屏表面，不进画面。
    """
    offenders: list[str] = []
    for path in sorted(PIPELINE_ROOT.glob("pyv/**/*.py")):
        relative = path.relative_to(PIPELINE_ROOT).as_posix()
        if relative in ALLOWED_DIRECT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr in DIRECT_DRAW:
                offenders.append(
                    f"{relative}:{node.lineno} 直接调了 ctx.{func.attr}()")
    assert not offenders, (
        "这些地方绕过了 draw.text，探针拦不到它们画出来的字：\n  "
        + "\n  ".join(offenders)
    )


def test_every_segment_shows_its_title():
    """**每一段的标题都要真的在画面上**——这是探针拦对了的证据。

    指纹记的是「每一行字的坐标与宽度」。万一探针拦错了东西（比如
    拦成了另一个模块的），指纹会整齐地少一大块，而比对时两边一样
    少——守卫照样绿。标题是每一段都画的东西，拿它当「探针真的
    拦到了这一段的画字」的证据。
    """
    _need_bundled_font()
    missing: list[str] = []
    for episode, segment in _segments():
        module = importlib.import_module(segment.renderer)
        drawn: list[str] = []
        for canvas, width, height in CANVASES:
            for t in TIMES:
                drawn.extend(fingerprint.collect_texts(
                    module, segment.params, width, height, t))
        title = segment.params.get("title")
        if isinstance(title, str) and title and title not in drawn:
            missing.append(f"{episode}/{segment.id} 的标题 {title!r} 没被画出去")
    assert not missing, "探针没拦到标题：\n  " + "\n  ".join(missing[:20])


def test_the_probe_can_see_a_text():
    """**守卫自己得会报警**——探针坏了就只是一段永远绿的代码。"""
    _need_bundled_font()
    segments = list(_segments())
    if not segments:
        pytest.skip("磁盘上没有期，没有段可探")
    episode, segment = segments[0]
    module = importlib.import_module(segment.renderer)
    drawn = fingerprint.collect_texts(
        module, segment.params, CANVASES[0][1], CANVASES[0][2], TIMES[0])
    assert drawn, f"{episode}/{segment.id} 一帧都没画出字——探针是瞎的"
    assert any("一" <= ch <= "鿿" for ch in "".join(drawn)), (
        f"只收到非汉字，拦的可能是错的东西：{drawn[:5]}"
    )
