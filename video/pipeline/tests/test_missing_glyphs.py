"""缺字判定：盖不住的字**当场报错**，不画豆腐块。

**为什么**：成片里的一段方框，观众分不清是「内容没写」还是「片子坏了」——
比一次报错难懂得多。豆腐块是**静默的失败**：画面照样生成、时长照样对。

**口径（D5）**：内置子集盖住 GB 2312-80 全集；超出的那些字**当场报错**，
并给出补救办法（把字并进子集重跑脚本）。有一条**放行开关**，
但放行时**往 stderr 出声**——可以放行，不许无声。

**这里守五件事**：

1. 纯 Python 读的 cmap 与 fontTools 读出来的一致（两套办法各写一份）；
2. 缺字**当场报错**，报得出是哪些字；
3. 报错信息**给得出补救办法**；
4. 放行开关**开着时出声**、**关着时报错**；
5. 母稿里的生僻字**画不出来就炸**（不是画成方框）。
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr

import cairo
import pytest

from pyv import draw
from pyv import fonts
from pyv.generic import gen_code

#: 上游字体有、**GB 2312-80 没有**的字（扩展 A 区）。
#:
#: 拿它当「生僻字」样本：它**真的**能画出来——只要把它并进子集重跑脚本。
#: 拿一个上游也没有的字当样本就说不清了（补救办法是「先解决上游」）。
RARE = "㐀"

#: 上游**也没有**的字（⌊ ⌋）：任何子集都画不出来。
ABSENT = "⌊"


def _surface() -> tuple[cairo.ImageSurface, cairo.Context]:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 200)
    return surface, cairo.Context(surface)


def test_the_pure_python_reader_agrees_with_fonttools():
    """**纯 Python 读的 cmap 与 fontTools 读出来的一致**。

    两套办法各写一份、互不引用：fontTools 只在构建期用，运行时这条
    读 cmap 的代码是自己写的，写错了没人拦——除非拿它跟参考实现对拍。

    参考实现是 fontTools 的 `getBestCmap()`（独立实现，不是本模块的）。
    """
    ttlib = pytest.importorskip("fontTools.ttLib")
    if not fonts.BUNDLED_REGULAR_PATH.is_file():
        pytest.skip(f"内置字体不在仓库里：{fonts.BUNDLED_REGULAR_PATH}")

    font = ttlib.TTFont(str(fonts.BUNDLED_REGULAR_PATH))
    reference = set(font.getBestCmap())

    intervals = fonts.bundled_coverage()
    mine = {code for start, end in intervals for code in range(start, end + 1)}

    assert mine == reference, (
        f"纯 Python 读出来的覆盖与 fontTools 差 "
        f"{len(mine ^ reference)} 个码位"
    )
    assert len(reference) > 7000, (
        f"内置子集只盖住 {len(reference)} 个码位——子集没重建？"
    )


def test_the_mono_family_is_covered_by_its_own_subset():
    """等宽那族**盖住的字与正文那族一样**。

    代码块画的是代码，可代码里有中文注释——中文注释画成方框，
    比代码画歪了还难看。
    """
    assert fonts.bundled_coverage(fonts.BUNDLED_MONO_FAMILY) == \
        fonts.bundled_coverage(fonts.BUNDLED_FAMILY)


def test_a_rare_character_is_reported_missing():
    """**盖不住的字要报得出来**。"""
    assert fonts.missing_chars(f"取号{RARE}顺序") == [RARE]
    assert fonts.missing_chars("取号顺序") == []


def test_control_characters_are_not_missing():
    """换行、制表**不是字形**——不算缺字。"""
    assert fonts.missing_chars("取号\n顺序\t") == []


def test_drawing_a_character_the_font_lacks_raises():
    """**画到缺字就当场报错**——不画豆腐块。"""
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs) as caught:
        draw.text(ctx, f"取号{RARE}", 10, 40, 24.0, "#000000")
    assert RARE in str(caught.value)


def test_the_error_says_how_to_fix_it():
    """**报错要给出补救办法**——只说「缺字」等于没说。"""
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs) as caught:
        draw.text(ctx, RARE, 10, 40, 24.0, "#000000")
    message = str(caught.value)
    assert "extra_chars.txt" in message, "报错没说要改哪个文件"
    assert "build_font_subset.py" in message, "报错没说要跑哪个脚本"


def test_the_opt_out_lets_it_through_but_says_so(monkeypatch):
    """**放行开关开着：放过，但出声**。

    可以放行，不许无声——不然成片里就是一段方框，没人知道为什么。
    """
    monkeypatch.setenv(fonts.ALLOW_MISSING_ENV, "1")
    fonts.reset_warnings()
    buffer = io.StringIO()
    _, ctx = _surface()
    with redirect_stderr(buffer):
        draw.text(ctx, RARE, 10, 40, 24.0, "#000000")

    said = buffer.getvalue()
    assert RARE in said, f"放行了却没出声（stderr 是空的）：{said!r}"
    assert fonts.ALLOW_MISSING_ENV in said, "出声里没说是哪条开关放行的"


def test_without_the_opt_out_the_error_still_raises(monkeypatch):
    """**没开开关就报错**——开关不是默认开的。"""
    monkeypatch.delenv(fonts.ALLOW_MISSING_ENV, raising=False)
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs):
        draw.text(ctx, RARE, 10, 40, 24.0, "#000000")


def test_a_switch_value_of_zero_does_not_allow_anything(monkeypatch):
    """`=0` 是「不放开」，不是「放开但关着」。"""
    monkeypatch.setenv(fonts.ALLOW_MISSING_ENV, "0")
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs):
        draw.text(ctx, RARE, 10, 40, 24.0, "#000000")


def test_the_code_renderer_reports_a_rare_character():
    """**母稿里的生僻字，画不出来就炸**——不是画成方框。

    走的是真实路径：内容 → 代码渲染器 → `draw.text`。
    """
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs) as caught:
        gen_code.render(ctx, 0.0, 640, 360,
                        {"content": f"SELECT 1; -- {RARE}", "lang": "sql"})
    assert RARE in str(caught.value)


def test_a_character_the_font_lacks_upstream_says_so(monkeypatch):
    """**上游也没有的字**，报错要点出「上游也得先解决」。

    拿 `⌊` 当样本：它不在 GB 2312-80 里，**上游字体也没有**——
    并进 `extra_chars.txt` 重跑脚本也还是画不出来。这时候要说的是
    「先解决上游」，不是「并进 extra_chars.txt 就行」。
    """
    assert fonts.missing_chars(ABSENT) == [ABSENT]
    _, ctx = _surface()
    with pytest.raises(fonts.MissingGlyphs) as caught:
        draw.text(ctx, ABSENT, 10, 40, 24.0, "#000000")
    assert "上游" in str(caught.value)


def test_a_rare_character_in_a_motherdoc_is_caught(tmp_path):
    """**母稿里的生僻字要被抓出来**——母稿是内容的真相，不能有画不出的字。

    走的是母稿自己的路：写一篇母稿 → 解析出块 → 看块里的字盖不盖得住。
    """
    from pyv import motherdoc

    doc = tmp_path / "母稿.md"
    doc.write_text(
        "# 母稿\n\n"
        "正文里有个生僻字。\n\n"
        "```python\n"
        f"value = '{RARE}'  # 注释里的生僻字\n"
        "```\n",
        encoding="utf-8",
    )

    mother = motherdoc.load_motherdoc(doc)
    block = motherdoc.find_block(mother, "code", 1)

    assert RARE in fonts.missing_chars(block.content), (
        "母稿代码块里的生僻字没被抓出来"
    )
