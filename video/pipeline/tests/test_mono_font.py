"""等宽字体：代码块用真等宽的那一族。

**为什么代码不能凑合用比例字体**：比例字体的字宽不等，一行代码画出来
对不齐列——**缩进层级看不出来**。代码要能一眼看出哪一行属于哪一层。

**这一族怎么来的**：上游 `Noto Sans Mono CJK SC`，与正文那一族
**同版本、同授权**（SIL OFL 1.1），由 `scripts/build_font_subset.py`
从离线源（Debian 的 `fonts-noto-cjk`）里**按 PostScript 名**抽出来，
子集化、改族名成 `AIV Mono CJK SC`。

**这里守四件事**：

1. **等宽是真的等宽**——每个字符的步进相同（这是「等宽」的定义，
   不是「看起来像」）；
2. **代码块确实用它**——不混排：一段代码要么全等宽，要么全比例；
3. **量与画是同一族**——量一族、画另一族，量出来的宽度跟画出来的对不上；
4. **认不到时退回并说清楚**——不静默降级。

**等宽那族没装上时，第 2、3 条会说明原因**（skip 而不是假装绿）——
但第 1 条**只读字体文件**，不依赖装没装，所以它永远会跑。
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr

import cairo
import pytest

from pyv import draw
from pyv import fonts
from pyv.generic import gen_code

#: 拿来量步进的字符：**ASCII 可见字符 + 常见符号**。
#:
#: 为什么要带上非字母：等宽字体里 `i` 与 `W` 的步进必须一样——
#: 只测字母的话，`i` 那种窄字形的步进短一点也可能蒙混过关。
SAMPLE = ("abcdefghijklmnopqrstuvwxyz0123456789"
          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
          "(){}[]<>+-*/=_,.;:!?'\"`~@#$%^&|\\")

#: 汉字也是等宽的一部分（全角一个字宽）。
CJK_SAMPLE = "取号顺序并发事务隔离级别"

#: 拿来试画的一段代码（要能分出好几个 token，才测得出「量与画同族」）。
CODE = "SELECT id FROM t WHERE x = 1;"


def _mono_font():
    """载入内置等宽子集（fontTools 只在构建期用；这里读度量）。"""
    ttlib = pytest.importorskip("fontTools.ttLib")
    if not fonts.BUNDLED_MONO_PATH.is_file():
        pytest.skip(f"内置等宽字体不在仓库里：{fonts.BUNDLED_MONO_PATH}")
    return ttlib.TTFont(str(fonts.BUNDLED_MONO_PATH))


def _mono_advance(ctx: cairo.Context, text: str, size: float) -> float:
    """用等宽那一族量一段字的步进宽度。"""
    fonts.select_font(ctx, fonts.BUNDLED_MONO_FAMILY)
    ctx.set_font_size(size)
    return ctx.text_extents(text).x_advance


def _render_code(monkeypatch) -> list[tuple[str, float, float, str | None]]:
    """画一段代码，把每一次落笔记下来：`(文字, x, 字号, 族名)`。"""
    seen: list[tuple[str, float, float, str | None]] = []

    def recorder(ctx, s, x, y, size, color, anchor="left", bold=False,
                 alpha=1.0, family=None):
        seen.append((s, x, size, family))
        return None

    monkeypatch.setattr(draw, "text", recorder)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 360)
    ctx = cairo.Context(surface)
    gen_code.render(ctx, 0.5, 640, 360, {"content": CODE, "lang": "sql"})
    return seen


def test_every_character_has_the_same_advance():
    """**每个字符的步进相同**——这就是「等宽」的定义。

    只读字体文件（`hmtx`），**不依赖字体装没装**——所以这条
    在任何机器上都会跑。

    比例字体在这里必然红：实测 Noto Sans CJK SC 的 `'i'` 是
    285/1000 em，`'W'` 是 928/1000 em——差三倍。
    """
    font = _mono_font()
    cmap = font.getBestCmap()
    metrics = font["hmtx"].metrics
    units_per_em = font["head"].unitsPerEm

    advances = {}
    for ch in SAMPLE + CJK_SAMPLE:
        code = ord(ch)
        if code not in cmap:
            continue
        advances[ch] = metrics[cmap[code]][0]

    assert advances, "等宽字体里一个可测的字符都没有"

    # **全角与半角分开比**：等宽 CJK 字体里 ASCII 是半个汉字宽，
    # 汉字是全角——两者的步进本来就该不同。要求「全部一样」
    # 是错的判据。
    ascii_advances = {advances[ch] for ch in SAMPLE if ch in advances}
    cjk_advances = {advances[ch] for ch in CJK_SAMPLE if ch in advances}

    assert len(ascii_advances) == 1, (
        f"ASCII 字符的步进不止一个：{sorted(ascii_advances)}——"
        f"这不是等宽字体"
    )
    assert len(cjk_advances) == 1, (
        f"汉字的步进不止一个：{sorted(cjk_advances)}——这不是等宽字体"
    )

    half, full = ascii_advances.pop(), cjk_advances.pop()
    assert full == half * 2, (
        f"全角 {full} 不是半角 {half} 的两倍——等宽 CJK 字体的"
        f"半角与全角应当是 1:2"
    )
    assert units_per_em > 0


def test_the_mono_family_is_resolvable_or_says_so(monkeypatch):
    """等宽那族**认得到就用它，认不到就退回并说清楚**。

    退回不报错：没装字体的机器本来也能出片（代码对不齐列而已）。
    但**不许无声**——退回到比例字体这件事要往 stderr 出声，
    否则「为什么代码列对不齐」只能靠猜。

    **两条路都走一遍**（把「认不认得」逼成认得 / 不认得）：
    只测当前这台机器碰巧走的那条，等于没测。
    """
    # 路一：认得 → 用等宽那族
    monkeypatch.setattr(fonts, "family_resolves", lambda family: True)
    assert fonts.mono_family() == fonts.BUNDLED_MONO_FAMILY

    # 路二：认不得 → 退回比例字体，**并且出声**
    monkeypatch.setattr(fonts, "family_resolves", lambda family: False)
    fonts.reset_warnings()
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        chosen = fonts.mono_family()

    assert chosen == fonts.font_family(), (
        f"认不到等宽字体时应该退回「{fonts.font_family()}」，"
        f"实际退回到 {chosen}"
    )
    assert fonts.BUNDLED_MONO_FAMILY in buffer.getvalue(), (
        "退回到比例字体时**没有出声**——静默降级，"
        "代码为什么对不齐列只能靠猜"
    )


def test_the_code_renderer_draws_only_in_the_mono_family(monkeypatch):
    """**代码块里画的东西全都是等宽那一族**——不混排。

    一段代码要么全等宽，要么全比例。混排的代码列是歪的，
    而且**看不出来**（每一段单独看都是正常的字）。

    认不到等宽那族时这条会说明原因（skip）——那台机器本来就
    只能画比例字体。
    """
    if not fonts.mono_family_resolves():
        pytest.skip(
            f"等宽「{fonts.BUNDLED_MONO_FAMILY}」没装上"
            f"（python3 scripts/install_font.py）——"
            f"这条守不了「代码用等宽画」"
        )

    seen = _render_code(monkeypatch)
    assert seen, "一个字都没画出来——守卫瞎了"

    families = {family for _, _, _, family in seen}
    assert families == {fonts.BUNDLED_MONO_FAMILY}, (
        f"代码块里有东西不是等宽的：{families}——混排的代码列是歪的"
    )


def test_the_code_renderer_measures_with_the_same_family(monkeypatch):
    """**量与画必须是同一族**。

    量用比例字体、画用等宽字体的话，量出来的宽度跟画出来的对不上——
    表现是「空格后面的空隙不对」或者「行尾多出一截」。

    这里量的是：同一行里**相邻两段**的间距，必须等于**等宽那族**量出来
    的第一段的步进（而不是比例字体的）。
    """
    if not fonts.mono_family_resolves():
        pytest.skip(f"等宽「{fonts.BUNDLED_MONO_FAMILY}」没装上")

    seen = _render_code(monkeypatch)
    assert len(seen) >= 2, "这一帧里没有相邻的两段字——守卫瞎了"

    first_text, first_x, size, family = seen[0]
    second_text, second_x = seen[1][0], seen[1][1]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 360)
    ctx = cairo.Context(surface)
    mono = _mono_advance(ctx, first_text, size)

    # 比例那一族量出来是多少——用来证明「量错了族就会被看出来」
    proportional = None
    if fonts.family_resolves(fonts.font_family()):
        fonts.select_font(ctx, fonts.font_family())
        ctx.set_font_size(size)
        proportional = ctx.text_extents(first_text).x_advance

    gap = second_x - first_x
    assert abs(gap - mono) < 0.5, (
        f"相邻两段的间距 {gap:.2f} 与等宽步进 {mono:.2f} 对不上——"
        f"量与画不是同一族"
    )
    if proportional is not None:
        assert abs(proportional - mono) > 0.5, (
            "等宽与比例量出来的一样——这条守卫分辨不出「量错族」，"
            "换一段能分辨的字再测"
        )
        assert abs(gap - proportional) > 0.5, (
            f"相邻两段的间距 {gap:.2f} 与比例步进 {proportional:.2f} "
            f"一样——量用的是比例字体"
        )
    assert family == fonts.BUNDLED_MONO_FAMILY
    assert second_text  # 第二段不是空串
