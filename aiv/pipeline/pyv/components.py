"""可复用的画面组件。

组件只做两件事：**画一个东西**，或者**算一组几何**。它们不做的事同样重要：

- **不写死契约文案。** 文案归契约，`tests/test_contract.py` 的 AST 守卫
  会抓住回流的字面量。
- **不替场景决定字号收不收。** 收不收是这一档画幅的事（横版历来直接
  画字，竖版每行都过 `fit_size`），组件替场景做主就会改画面。

**为什么值得抽出来。** 「等分一排块」「等分一列」「定步长的一串小块」
这几套排布原先在每个场景里各写一遍：s02_serial 的五个积压块、s03_cores
的七个小块、s04_parallel 的并行分支，同一个公式各写各的。抽出来之后，
改一次排布规则只改一处。

**绘制调用一律走 `draw.<函数>` 的模块属性访问**（不是 `from pyv.draw import
rounded_rect`）——`tests/test_scene_overlap.py` 靠给 `draw.arrow` 打桩来
记录画面上画过的箭头，模块属性访问在调用时才解析，打桩才拦得住。
"""
from __future__ import annotations

import cairo

from pyv import draw


# ---------------------------------------------------------------- 形状


def block(ctx: cairo.Context, x: float, y: float, w: float, h: float, *,
           fill: str, radius: float = 18, alpha: float = 1.0) -> None:
    """一个圆角块。"""
    draw.rounded_rect(ctx, x, y, w, h, radius, fill, alpha)


# ---------------------------------------------------------------- 几何


def cols_width(total_w: float, cols: int, gap: float = 0.0) -> float:
    """`cols` 列等分总宽：每列宽 = (总宽 - (列数-1) × 间隙) / 列数。"""
    if cols <= 0:
        raise ValueError(f"列数必须为正，实际 {cols}")
    return (total_w - gap * (cols - 1)) / cols


def row(x: float, total_w: float, count: int, *,
        gap: float = 0.0) -> list[tuple[float, float]]:
    """等分一排：返回每个块的 `(x, w)`。

    宽度按 `cols_width` 算，所以 `count` 个块 + `count-1` 个间隙正好铺满
    `total_w`。
    """
    if count <= 0:
        return []
    width = cols_width(total_w, count, gap)
    return [(x + i * (width + gap), width) for i in range(count)]


def column(y: float, total_h: float, count: int, *,
           gap: float = 0.0) -> list[tuple[float, float]]:
    """等分一列：返回每个块的 `(y, h)`。"""
    if count <= 0:
        return []
    height = cols_width(total_h, count, gap)
    return [(y + i * (height + gap), height) for i in range(count)]


def steps(x: float, y: float, w: float, h: float, count: int, *,
          step_x: float = 0.0, step_y: float = 0.0) -> list[tuple[float, float, float, float]]:
    """定尺寸、定步长的一串块：返回每个块的 `(x, y, w, h)`。

    与 `row`/`column` 的区别：**块的大小是给定的，不铺满总宽**。
    两种排布在场景里都出现过：s03_cores 横版的七个小块是定尺寸定步长，
    s02_serial 竖版的五个积压块是等分铺满。
    """
    return [
        (x + i * step_x, y + i * step_y, w, h)
        for i in range(count)
    ]


def grid(x: float, y: float, w: float, h: float, count: int, cols: int, *,
         gap_x: float = 0.0, gap_y: float = 0.0) -> list[tuple[float, float, float, float]]:
    """网格：按行排，每行 `cols` 个。返回每个块的 `(x, y, w, h)`。

    末行不满就空着——不补虚位。s03_cores 竖版的七个小块就是 4+3 两行。
    """
    return [
        (x + (i % cols) * (w + gap_x), y + (i // cols) * (h + gap_y), w, h)
        for i in range(count)
    ]


# ---------------------------------------------------------------- 箭头


def arrow_v(ctx: cairo.Context, x: float, y1: float, y2: float, *,
            color: str, width: float = 8.0, head: float = 24.0) -> None:
    """竖向箭头：从 `y1` 指向 `y2`（`y2` 大就是向下）。"""
    draw.arrow(ctx, x, y1, x, y2, color, width, head)


def arrow_h(ctx: cairo.Context, y: float, x1: float, x2: float, *,
            color: str, width: float = 8.0, head: float = 24.0) -> None:
    """横向箭头：从 `x1` 指向 `x2`（`x2` 大就是向右）。"""
    draw.arrow(ctx, x1, y, x2, y, color, width, head)
