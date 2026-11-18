"""组件层：形状与几何的单元测试。

组件的**绝对位置**随调用方变，所以不比逐像素；比的是**不变量**：
块排必须等分、网格必须按行、箭头必须指向目标、组件里不许出现契约文案。

**组件不许写死契约文案**这条是硬的：文案归契约，组件里出现字面量
就等于绕过了 `tests/test_contract.py` 的 AST 守卫。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import cairo
import pytest

from pyv import components
from pyv import contract as contract_mod

AIV_ROOT = Path(__file__).resolve().parents[2]


def _ctx(w: int = 800, h: int = 600):
    """透明底画布。返回 (surface, ctx)——取像素要靠 surface。

    **不刷白底**：刷了之后 alpha 恒为 255，「有没有墨」就分不出来了。
    透明底的 alpha=0 就是「没画过」。
    """
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    return surface, ctx


def _has_ink(surface, x: int, y: int) -> bool:
    """(x, y) 那一像素有没有墨。"""
    surface.flush()
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    offset = y * stride + x * 4
    return data[offset + 3] != 0


# ---- 几何 --------------------------------------------------------------


def test_cols_width_divides_the_total_evenly():
    """等分公式：每列 = (总宽 - (列数-1) × 间隙) / 列数。"""
    assert components.cols_width(600, 3, gap=20) == pytest.approx(
        (600 - 2 * 20) / 3)


def test_row_fills_the_total_width_exactly():
    """n 个块 + (n-1) 个间隙正好铺满总宽——不多不少。"""
    boxes = components.row(100.0, 600.0, 3, gap=20)
    assert len(boxes) == 3
    widths = [w for _, w in boxes]
    assert widths[0] == widths[1] == widths[2]
    assert sum(widths) + 20.0 * 2 == pytest.approx(600.0)
    # 第一个块从 x 起，最后一个块的右缘落在总宽末端
    assert boxes[0][0] == 100.0
    assert boxes[-1][0] + boxes[-1][1] == pytest.approx(700.0)


def test_column_fills_the_total_height_exactly():
    """一列同理：铺满总高。"""
    boxes = components.column(50.0, 300.0, 2, gap=40)
    assert len(boxes) == 2
    heights = [h for _, h in boxes]
    assert heights[0] == heights[1]
    assert sum(heights) + 40.0 == pytest.approx(300.0)
    assert boxes[-1][0] + boxes[-1][1] == pytest.approx(350.0)


def test_row_and_column_of_zero_is_empty():
    """数量为 0 时返回空，不许除零。"""
    assert components.row(0.0, 100.0, 0) == []
    assert components.column(0.0, 100.0, 0) == []


def test_steps_keeps_the_given_size():
    """定尺寸定步长：块的大小是给定的，不铺满总宽。"""
    boxes = components.steps(10.0, 20.0, 30.0, 40.0, 3, step_x=50.0)
    assert len(boxes) == 3
    assert all(b[2] == 30.0 and b[3] == 40.0 for b in boxes)
    assert boxes[1][0] == 60.0


def test_grid_fills_row_by_row_and_leaves_the_last_row_short():
    """网格按行排，末行不满就空着——不补虚位。

    s03_cores 竖版的七个小块就是 4+3 两行。
    """
    boxes = components.grid(0.0, 0.0, 50.0, 60.0, 7, 4, gap_x=14, gap_y=20)
    assert len(boxes) == 7
    assert boxes[0][:2] == (0.0, 0.0)
    assert boxes[3][:2] == (3 * 64, 0.0)
    assert boxes[4][:2] == (0.0, 80.0)
    # 末行只有三个：第七个在第二行第三列
    assert boxes[6][:2] == (2 * 64, 80.0)


# ---- 形状 --------------------------------------------------------------


def test_block_draws_inside_its_bounds():
    """块画在给的矩形里。"""
    surface, ctx = _ctx()
    components.block(ctx, 100.0, 100.0, 200.0, 120.0, fill="#2B4C7E")
    assert _has_ink(surface, 150, 150), "块内部应该有墨"
    assert not _has_ink(surface, 50, 50), "块外面不该有墨"
    assert not _has_ink(surface, 400, 300), "块外面不该有墨"


# ---- 箭头 --------------------------------------------------------------


def test_arrow_v_points_downward():
    """竖箭头：箭头翼在尖端那端，不在起点那端。

    `draw.arrow` 从 (x1,y1) 到 (x2,y2) 画一条杆，再在**尖端**张开两翼
    （默认 head=24、翼与杆夹角 150°，所以竖直向下时两翼落在
    (x±12, y2-20.8) 附近）。
    """
    surface, ctx = _ctx()
    components.arrow_v(ctx, 400.0, 100.0, 300.0, color="#2B4C7E")
    # 翼在尖端上方张开
    assert _has_ink(surface, 388, 279), "箭头翼应该在尖端那一端"
    assert _has_ink(surface, 412, 279), "箭头翼应该在尖端那一端"
    # 起点只有杆，没有翼
    assert not _has_ink(surface, 388, 100), "起点不该有箭头翼"
    assert not _has_ink(surface, 412, 100), "起点不该有箭头翼"


def test_arrow_h_points_rightward():
    """横箭头：翼在尖端那端（右边），不在起点那端（左边）。"""
    surface, ctx = _ctx()
    components.arrow_h(ctx, 200.0, 100.0, 300.0, color="#2B4C7E")
    assert _has_ink(surface, 279, 188), "箭头翼应该在尖端那一端"
    assert _has_ink(surface, 279, 212), "箭头翼应该在尖端那一端"
    assert not _has_ink(surface, 100, 188), "起点不该有箭头翼"
    assert not _has_ink(surface, 100, 212), "起点不该有箭头翼"


# ---- 结构 --------------------------------------------------------------


def _contract_copy() -> set[str]:
    """六期契约里出现过的所有文案。"""
    copy: set[str] = set()

    def walk(node):
        if isinstance(node, str):
            if len(node) >= 2:
                copy.add(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    for path in sorted(contract_mod.CONTRACTS_DIR.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return copy


def test_components_do_not_hardcode_contract_copy():
    """组件里不许出现契约文案——文案归契约。

    这条是从 `tests/test_contract.py` 的 AST 守卫延伸过来的：那条扫场景
    模块，这条扫组件层。组件是场景的公共部分，文案漏进来影响面更大。
    """
    source = Path(components.__file__).read_text(encoding="utf-8")
    literals = {
        node.value for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    leaks = sorted(literals & _contract_copy())
    assert not leaks, f"组件里写死了契约文案：{leaks}"


def test_components_draws_through_the_draw_module():
    """组件必须走 `draw.<函数>` 的模块属性访问。

    **为什么**：`tests/test_scene_overlap.py` 靠给 `draw.text` / `draw.arrow`
    打桩来记录画面上画过的字与箭头。组件如果 `from pyv.draw import arrow`
    绑在导入时，打桩就拦不住——守卫会悄悄变成「什么都看不见」，
    再也没有人发现画面里箭头穿过了字。
    """
    for name in ("text", "arrow", "rounded_rect", "stroke_rect"):
        assert not hasattr(components, name), (
            f"components 绑定了 {name}——打桩拦不住，元素级守卫会瞎掉"
        )
