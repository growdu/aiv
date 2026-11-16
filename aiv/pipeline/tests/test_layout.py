"""版式层：常量必须与现状一字不差。

**这层的价值是「搬运」不是「规范化」**：改一个数值就是改画面，
逐像素基准会红。所以每一条都写死字面量断言——常量一旦漂，
这里立刻抓住，而不是等到重录基准时才发现。

**横版的取值不许统一。** 现状里左边距有 0.06 也有 0.07、标题基线有
0.15 也有 0.16。这些「不整齐」是历史事实，不是待清理的债：
统一了就改画面。所以这里断言的是**每一个具体取值**，不是「它们应该一样」。
"""
from __future__ import annotations

import pytest

from pyv import layout
from pyv import scene_layout


# ---- 竖版：与旧的 scene_layout 完全等价 --------------------------------


def test_vertical_layout_matches_the_legacy_module():
    """`layout.V` 与旧的 `scene_layout` 必须完全等价。

    26 个场景还没迁到新版式层，它们用的仍是 `scene_layout`——
    它转发到 `layout.V`，所以这两个必须一字不差。
    """
    assert layout.V.MARGIN_X == scene_layout.MARGIN_X
    assert layout.V.TITLE_Y == scene_layout.TITLE_Y
    assert layout.V.CONTENT_TOP == scene_layout.CONTENT_TOP
    assert layout.V.CONTENT_BOTTOM == scene_layout.CONTENT_BOTTOM
    assert layout.V.RAIL_RIGHT == scene_layout.RAIL_RIGHT
    assert layout.V.TITLE_SIZE == scene_layout.TITLE_SIZE
    assert layout.MIN_SIZE == scene_layout.MIN_SIZE


def test_vertical_geometry_is_unchanged():
    """竖版的几何量逐个钉死（像素来自设计文档 §三）。"""
    assert layout.V.content_width(1080) == pytest.approx(1080 * 0.94 - 120)
    assert layout.V.content_left(1080) == pytest.approx(1080 * 0.06)
    assert layout.V.content_right(1080) == pytest.approx(
        1080 * 0.06 + 1080 * 0.94 - 120)
    assert layout.V.content_top_px(1920) == pytest.approx(1920 * 0.130)
    assert layout.V.content_bottom_px(1920) == pytest.approx(1920 * 0.700)
    # 字幕带 1393 与内容区下沿 1344 之间留 49px
    assert 1920 * 0.700 <= 1393 - 49 + 1e-9


def test_vertical_title_position_is_unchanged():
    """标题基线 0.075 × 1920 = 144px（设计文档 §三）。"""
    assert layout.V.TITLE_Y == 0.075
    assert layout.V.TITLE_Y * 1920 == pytest.approx(144)


# ---- 横版：取值来自横版现状，一个都不许动 ------------------------------


def test_horizontal_constants_are_unchanged():
    """横版的画幅级取值。

    - 标题字号 60：三处一致（s02_serial / s03_cores / s04_parallel）
    - 标题基线 0.15：两处 0.15、一处 0.16，默认取众数
    - 左边距 0.06：仓库里 56 处
    - 说明行基线 0.86、字号 44：s02_serial 与 s04_parallel 一致
    """
    assert layout.H.WIDTH == 1920
    assert layout.H.HEIGHT == 1080
    assert layout.H.TITLE_SIZE == 60
    assert layout.H.TITLE_Y == 0.15
    assert layout.H.MARGIN_X == 0.06
    assert layout.H.CAPTION_Y == 0.86
    assert layout.H.CAPTION_SIZE == 44
    assert layout.H.CONTENT_TOP == 0.25
    assert layout.H.RAIL_RIGHT == 0


def test_horizontal_geometry_is_unchanged():
    """横版不叠平台 UI，内容区就是去掉左边距后的全部宽度。"""
    assert layout.H.content_left(1920) == pytest.approx(1920 * 0.06)
    assert layout.H.content_width(1920) == pytest.approx(1920 * 0.94)
    assert layout.H.content_right(1920) == pytest.approx(1920)
    assert layout.H.content_top_px(1080) == pytest.approx(1080 * 0.25)


# ---- 两档的差别是刻意的 ------------------------------------------------


def test_the_two_canvases_differ_where_it_matters():
    """竖版收字号、横版不收——这是刻意的差别，不是待清理的债。

    竖版每一行都要过 `fit_size`（「宁可字小一点，也不能出框」）；
    横版历来直接画字。统一成一种就是改画面。
    """
    assert layout.V.FITS_TEXT is True
    assert layout.H.FITS_TEXT is False


def test_for_canvas_picks_by_aspect_ratio():
    """判据只看高宽比，不认画布名字——以后加 4:5 之类的档，场景不用改。"""
    assert layout.for_canvas(1920, 1080) is layout.H
    assert layout.for_canvas(1080, 1920) is layout.V
    # 4:5 这类将来才有的档：高 > 宽就按竖版处理
    assert layout.for_canvas(1080, 1350) is layout.V
    assert layout.for_canvas(1080, 900) is layout.H


# ---- 结构：不许把绘制函数绑死在导入时 ----------------------------------


def test_layout_draws_through_the_draw_module():
    """版式层必须走 `draw.<函数>` 的模块属性访问。

    **为什么**：`tests/test_scene_overlap.py` 靠给 `draw.text` 打桩来
    记录画面上画过的字。层里如果 `from pyv.draw import text` 绑在导入时，
    打桩就拦不住——守卫会悄悄变成「什么都看不见」，从此再也没人发现
    画面里字压住了字。
    """
    import pyv.layout as layout_module

    for name in ("text", "arrow", "rounded_rect", "stroke_rect"):
        assert not hasattr(layout_module, name), (
            f"layout 绑定了 {name}——打桩拦不住，元素级守卫会瞎掉"
        )
