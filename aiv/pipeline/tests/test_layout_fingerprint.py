"""跨机布局指纹守卫。

**为什么要有它**：逐像素基准在 macOS 与 Linux 之间**不可比**——
cairo 在 macOS 走 CoreText、在 Linux 走 FreeType，栅格化不同，像素必然不同。
但**轮廓、坐标与步进宽度**来自字体文件与场景代码，与栅格化无关，跨机可比。

指纹记四类量：

| 量 | 从哪来 |
| --- | --- |
| 落笔坐标 (x, y) | 场景代码里的纯算术，跨机完全一致 |
| 字号 | `fit_size` 收敛后的结果 |
| 步进宽度 `x_advance` | 字体文件的 hmtx |
| 轮廓包围盒 | `text_path` + `path_extents`，是字形轮廓不是像素 |

**容差写死字面量**，不从被测代码 import——阈值自证等于永远绿。

**实测依据**（2026-11-16，macOS / CoreText，内置子集 `AIV Sans CJK SC`）：

- cairo 量出的步进宽度 vs 从字体文件 hmtx 算出的：差 **≤ 0.056px**；
- cairo 的 `text_path` 轮廓 vs 从字体文件字形数据算出的：**逐项相等**
  （y 轴只是屏幕坐标向下、字形坐标向上的翻面）。

也就是说这两类量**直接来自字体文件**，不是栅格化的产物——换机器、
换渲染后端，数值不变。Linux 上 cairo 走 FreeType，autohinter 会把轮廓
点对齐到像素网格（单侧 ≤ 1px），所以轮廓的容差留一倍余量。

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
# 坐标与字号是**场景代码里的纯算术**（字号是 `fit_size` 收敛后的结果），
# 跨机应当完全一致；步进与轮廓**直接来自字体文件**，实测差 ≤ 0.056px
# （见模块 docstring）。

#: 坐标：场景代码里的纯算术，跨机应当完全一致。0.01px 吃浮点噪声。
COORD_TOLERANCE_PX = 0.01

#: 字号：`fit_size` 的收敛值。轮廓一致时它就是同一个数；留 1px 是为了
#: 吃「刚好贴边」时迭代次数不同带来的抖动。
SIZE_TOLERANCE = 1.0

#: 步进宽度：实测与字体文件 hmtx 差 ≤ 0.056px，取 1.0px 留约 18 倍余量。
ADVANCE_TOLERANCE_PX = 1.0

#: 轮廓包围盒：macOS 上实测与字形数据逐项相等；Linux 上 FreeType 的
#: autohinter 会把轮廓点对齐到像素网格（单侧 ≤ 1px），留一倍余量。
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
    """六期契约里的全部视觉段。"""
    for episode in episodes_mod.EPISODE_ORDER:
        contract = contract_mod.load_contract(
            AIV_ROOT / "contracts" / f"{episode}.json")
        for segment in contract.segments:
            yield episode, segment


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
        f"装上内置字体：cd aiv/pipeline && python3 scripts/install_font.py"
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
    """指纹必须覆盖六期 × 2 画幅 × 5 时刻——少一条就有一段没人守。"""
    actual = set(_fixture()["frames"])
    expected = _expected_keys()
    assert actual == expected, (
        f"指纹覆盖对不上：缺 {sorted(expected - actual)[:5]}；"
        f"多 {sorted(actual - expected)[:5]}"
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
    episode, segment = next(_segments())
    module = importlib.import_module(segment.renderer)
    drawn = fingerprint.collect_texts(
        module, segment.params, CANVASES[0][1], CANVASES[0][2], TIMES[0])
    assert drawn, f"{episode}/{segment.id} 一帧都没画出字——探针是瞎的"
    assert any("一" <= ch <= "鿿" for ch in "".join(drawn)), (
        f"只收到非汉字，拦的可能是错的东西：{drawn[:5]}"
    )
