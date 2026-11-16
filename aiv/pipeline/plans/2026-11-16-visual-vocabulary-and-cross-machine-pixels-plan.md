# 视觉词汇扩容 + 跨机像素一致：实施计划

> **配套设计**：`aiv/pipeline/plans/2026-11-16-visual-vocabulary-and-cross-machine-pixels-design.md`
>
> **执行方式**：本会话内逐任务执行（inline）。每个任务一笔提交，提交后用隔离
> worktree 跑一遍全量测试，确认该 commit 自身是绿的。

**目标**：把视觉词汇从「每个场景自己造轮子」扩成共用层；把逐像素回归锁的覆盖面
从 6/36 段补到 36/36 段；把跨机一致性从「靠人看」变成「有守卫」。

**架构**：新增 `pyv/layout.py`（画幅级版式常量与绘制入口）与 `pyv/components.py`
（块/块排/带/网格/箭头）；新增 `pyv/pipeline/scripts/build_font_subset.py` 与
`install_font.py`；基准 fixture 从「按模块」改成「按段」；新增跨机布局指纹守卫。

**技术栈**：Python 3.11 / cairo 1.29 / ffmpeg / fontTools 4.25 / pytest。

## 全局约束

- **每一笔提交都必须配套单元测试 + 集成测试，且全量测试通过。**
- **每一笔提交必须在只含该 commit 内容的干净检出上独立跑通全量测试**
  （用 `git worktree add --detach` 建隔离 worktree 验，不依赖后续 commit）。
- **不改变任何已渲染画面**：任务 1、2 结束时，六期 36 段的逐像素基准必须全绿
  （唯一例外：任务 3 换了字体，基准在那笔提交里**重录**，并写明原因）。
- **文案不许回流代码**：`tests/test_contract.py` 的 AST 守卫对 `components.py`
  同样生效——组件里不得出现契约文案的字面量。
- **参数缺失当场报错**：组件的必填参数用 `pyv.params.Params` / `check_required`。
- **守卫阈值写死字面量**：容差不许从被测代码 import（自证 = 永远绿）。
- **横版层是「搬运」不是「规范化」**：迁移时坐标值一个都不许改。
- 新增/修改的文件用 UTF-8，注释与文档字符串用中文（与仓库现状一致）。

---

## 文件结构（先定边界，再写任务）

| 文件 | 职责 | 状态 |
| --- | --- | --- |
| `aiv/pipeline/pyv/layout.py` | 画幅级版式常量 + 两个画幅实例 + 绘制入口 | 新建 |
| `aiv/pipeline/pyv/components.py` | 可复用的画面组件（块/块排/带/网格/箭头） | 新建 |
| `aiv/pipeline/pyv/fingerprint.py` | 布局指纹的采集（采集脚本与测试共用一份） | 新建 |
| `aiv/pipeline/pyv/scene_layout.py` | 竖版版式的兼容层，转发到 `layout.V` | 改 |
| `aiv/pipeline/pyv/fonts.py` | 字体候选顺序（内置字体优先） | 改 |
| `aiv/pipeline/pyv/doctor.py` | 多一条：内置字体装没装 | 改 |
| `aiv/pipeline/scripts/capture_scene_baseline.py` | 抓 36 段 × 3 时刻的基准 | 改 |
| `aiv/pipeline/scripts/build_font_subset.py` | 提字符集 → 子集化 → 重命名 | 新建 |
| `aiv/pipeline/scripts/install_font.py` | 把内置字体装进 OS 字体目录 | 新建 |
| `aiv/pipeline/scripts/capture_layout_fingerprint.py` | 抓布局指纹 | 新建 |
| `aiv/pipeline/tests/fixtures/scene_baseline.json` | 逐像素基准（108 帧） | 重录 |
| `aiv/pipeline/tests/fixtures/layout_fingerprint.json` | 跨机布局指纹 | 新建 |
| `aiv/pipeline/assets/fonts/` | 内置字体子集 + 出处台账 | 新建 |

---

### Task 1：逐像素基准覆盖全部 36 段

**接口**：
- 产出：`tests/fixtures/scene_baseline.json` 的 `frames` 键从 18 条变 108 条，
  键格式从 `<renderer>@<t>` 变 `<episode>/<segment_id>/<renderer>@<t>`。
- 消费：Task 2 的迁移等价性、Task 3 的重录。

- [ ] **Step 1：先写失败的测试**

改 `aiv/pipeline/tests/test_contract.py`：

```python
#: 基准抓取的时刻。抓基准脚本与测试必须用同一份，否则键对不上。
BASELINE_TIMES = (0.0, 0.45, 0.9)


def _baseline_key(episode: str, segment, t: float) -> str:
    """基准的键：期号 + 段 id + 渲染器 + 时刻。

    **必须带期号**：`s01_intro` 与 `s06_outro` 六期都在用，而每期的
    `params` 不同（标题文案不同）→ 画面不同 → 哈希不同。只按渲染器
    存一份，后五期的画面就永远比不到。
    """
    return f"{episode}/{segment.id}/{segment.renderer}@{t}"


def _expected_baseline_keys(all_contracts) -> set[str]:
    return {
        _baseline_key(episode, segment, t)
        for episode, contract in all_contracts.items()
        for segment in contract.segments
        for t in BASELINE_TIMES
    }
```

新增两条测试：

```python
def test_the_baseline_covers_every_segment(all_contracts):
    """基准必须覆盖六期契约里的每一段——少一段就有一条画面没人守。

    这条**不依赖字体**：基准里有没有某一段是文件内容的事，与当前机器
    用哪款字体无关。所以它直接读 fixture，不走会 skip 的 `baseline_frames`。
    """
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    actual = set(data["frames"])
    expected = _expected_baseline_keys(all_contracts)
    assert actual == expected, (
        f"基准覆盖对不上：缺 {sorted(expected - actual)[:5]}；"
        f"多 {sorted(actual - expected)[:5]}"
    )


def test_the_baseline_covers_every_scene_module(all_contracts):
    """基准里的渲染器集合必须等于目录里的场景模块集合。

    照 `tests/test_scene_overlap.py::test_every_scene_module_is_covered`
    的写法：集合相等，不是子集。新加一个模块却没进任何一期契约，
    基准就扫不到它——守卫覆盖不到的那部分，坏了也不会红。
    """
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    in_baseline = {
        key.split("/")[2].split("@")[0] for key in data["frames"]
    }
    on_disk = {
        path.stem for path in (Path(__file__).parent.parent / "pyv" / "scenes").glob("*.py")
        if path.stem != "__init__"
    }
    assert in_baseline == on_disk, (
        f"基准没盖住全部场景模块：目录有基准没有 {sorted(on_disk - in_baseline)}；"
        f"基准有目录没有 {sorted(in_baseline - on_disk)}"
    )
```

把原来的 `test_contract_driven_rendering_is_pixel_identical` 改成遍历六期：

```python
def test_contract_driven_rendering_is_pixel_identical(all_contracts, monkeypatch,
                                                      baseline_frames):
    _without_mascot(monkeypatch)
    baseline = baseline_frames
    for episode, contract in all_contracts.items():
        for segment in contract.segments:
            for t in BASELINE_TIMES:
                key = _baseline_key(episode, segment, t)
                assert key in baseline, f"基准里没有 {key}"
                actual = _scene_frame_hash(segment.renderer, segment.params, t)
                assert actual == baseline[key], f"{key} 的画面变了：文案搬进契约不该动到画面"
```

并把原来那条写死 18 的断言改掉：

```python
# 原来：assert len(baseline["frames"]) == 18, "6 个场景 × 3 个时间点"
# 改成（条数由契约推导，加期不用改这里，但漏抓会红）：
assert len(baseline["frames"]) == len(_expected_baseline_keys(all_contracts))
```

- [ ] **Step 2：跑测试确认它红**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_contract.py -q
```

预期：FAIL——`test_the_baseline_covers_every_segment` 报「缺 …」（基准只有 18 条，
期望 108 条）。

- [ ] **Step 3：改抓基准脚本**

改 `aiv/pipeline/scripts/capture_scene_baseline.py`：

```python
from pyv import contract as contract_mod  # noqa: E402
from pyv import episodes as episodes_mod  # noqa: E402
from pyv import fonts  # noqa: E402
from pyv.palette import COLORS, hex_to_rgb  # noqa: E402

AIV_ROOT = PIPELINE_ROOT.parent
TIMES = (0.0, 0.45, 0.9)
BASELINE = PIPELINE_ROOT / "tests" / "fixtures" / "scene_baseline.json"


def _all_segments():
    """六期契约里的全部视觉段。

    **按段抓，不按模块抓**：同一个渲染器在不同期用的 `params` 不同
    （`s01_intro` / `s06_outro` 六期都在用，标题文案各期不同），
    画面不同 → 哈希不同 → 必须按 (期号, 段) 各存一份。
    """
    for episode in episodes_mod.EPISODE_ORDER:
        contract = contract_mod.load_contract(
            AIV_ROOT / "contracts" / f"{episode}.json")
        for segment in contract.segments:
            yield episode, segment


def frame_key(episode: str, segment, t: float) -> str:
    return f"{episode}/{segment.id}/{segment.renderer}@{t}"
```

`main()` 的循环改成：

```python
    frames: dict[str, str] = {}
    for episode, segment in _all_segments():
        for t in TIMES:
            key = frame_key(episode, segment, t)
            frames[key] = frame_hash(segment.renderer, segment.params, t)
            print(f"  {key}  {frames[key][:16]}")
```

- [ ] **Step 4：重录基准**

```bash
cd aiv/pipeline && python3 scripts/capture_scene_baseline.py
```

预期输出末行：`已写入 …（108 帧）`。

- [ ] **Step 5：跑测试确认它绿**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_contract.py -q
```

预期：全绿。

- [ ] **Step 6：全量测试**

```bash
cd aiv/pipeline && python3 -m pytest tests/ -q
```

预期：`1000 passed, 15 skipped`（条数会变，因为多了两条测试）。

- [ ] **Step 7：提交**

```bash
git add aiv/pipeline/scripts/capture_scene_baseline.py \
        aiv/pipeline/tests/test_contract.py \
        aiv/pipeline/tests/fixtures/scene_baseline.json
git commit -m "feat(aiv): 逐像素基准覆盖全部 36 个视觉段

基准原来只有 18 帧（pg-parallel-decode 的 6 段 × 3 时刻），
目录里有 26 个场景模块、六期共 36 段——覆盖率 23%。
新增场景模块基准扫不到，改坏画面没人拦。

键从「<渲染器>@<时刻」改成「<期号>/<段 id>/<渲染器>@<时刻>」：
s01_intro 与 s06_outro 六期都在用，每期 params 不同、画面不同，
只按渲染器存一份，后五期永远比不到。

另加两条覆盖声称守卫：基准的段集合 == 六期契约的段集合，
基准的渲染器集合 == 目录里的场景模块集合。条数由契约推导，
以后加期不用改断言，但漏抓会红。"
```

- [ ] **Step 8：隔离 worktree 验这笔 commit 自身**

```bash
git worktree add --detach /tmp/aiv-verify-task1 HEAD
cd /tmp/aiv-verify-task1/aiv/pipeline && python3 -m pytest tests/ -q
git worktree remove /tmp/aiv-verify-task1
```

预期：全绿。**不通过就不要往下走**——后面的任务会依赖这个基准。

---

### Task 2：版式层（layout.py）+ 组件层（components.py）+ 迁三个代表场景

**接口**：
- `pyv/layout.py` 产出：

```python
class CanvasLayout:
    """一个画幅的版式常量与共用绘制入口。"""

    def __init__(self, name: str, width: int, height: int, *,
                 margin_x: float, title_size: float, title_y: float,
                 content_top: float, content_bottom: float,
                 rail_right: float) -> None: ...

    # 画幅级常量
    NAME: str
    WIDTH: int
    HEIGHT: int
    MARGIN_X: float
    TITLE_SIZE: float
    TITLE_Y: float
    CONTENT_TOP: float
    CONTENT_BOTTOM: float
    RAIL_RIGHT: float

    # 画幅级绘制入口
    def title(self, ctx, text_value: str, w: int, h: int,
              *, size: float | None = None, color: str = COLORS["primary"],
              bold: bool = True, alpha: float = 1.0) -> None: ...
    def line(self, ctx, s: str, x: float, y: float, max_width: float,
             size: float, color: str, *, bold: bool = False,
             alpha: float = 1.0, anchor: str = "left") -> None: ...
    def content_width(self, w: int | None = None) -> float: ...
    def content_left(self, w: int | None = None) -> float: ...
    def content_right(self, w: int | None = None) -> float: ...
    def content_top_px(self, h: int | None = None) -> float: ...
    def content_bottom_px(self, h: int | None = None) -> float: ...
```

两个实例：`layout.H`（1920×1080）与 `layout.V`（1080×1920）。

- `pyv/components.py` 产出：

```python
def block(ctx, x, y, w, h, *, fill: str, label: str | None = None,
          label_size: float = 40, label_color: str = "#FFFFFF",
          radius: float = 18, bold: bool = False,
          align: str = "center", alpha: float = 1.0,
          text_ratio: float = 0.82) -> None: ...
def block_row(ctx, items, x, y, total_w, h, *, gap: float = 20,
              fill: str | Sequence[str] = "#F6AD55", ...) -> list[tuple[float, float, float, float]]: ...
def band(ctx, x, y, w, h, *, fill: str, label: str | None = None,
         label_size: float = 48, label_color: str = "#FFFFFF", ...) -> None: ...
def matrix(ctx, cells, x, y, w, h, *, cols: int, rows: int, ...) -> None: ...
def arrow_v(ctx, x, y1, y2, *, color: str, width: float = 8.0, head: float = 24.0) -> None: ...
def arrow_h(ctx, y, x1, x2, *, color: str, width: float = 8.0, head: float = 24.0) -> None: ...
```

- [ ] **Step 1：先写失败的测试（组件层）**

新建 `aiv/pipeline/tests/test_components.py`：

```python
"""组件层：形状与约束的单元测试。

组件的**绝对位置**随调用方变，所以不比逐像素；比的是**形状不变量**：
块内文字的轮廓必须落在块内、块排必须等分、箭头必须指向目标。
"""
from __future__ import annotations

import cairo
import pytest

from pyv import components
from pyv import fonts


def _ctx(w: int = 800, h: int = 600):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    return ctx


def _ink(ctx, s, x, y, size, bold=False):
    """这行字的轮廓包围盒（与栅格化无关，跨平台可比）。"""
    ctx.select_font_face(fonts.font_family(), cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.new_path()
    ctx.move_to(x, y)
    ctx.text_path(s)
    x0, y0, x1, y1 = ctx.path_extents()
    ctx.new_path()
    return x0, y0, x1, y1


def test_block_keeps_its_label_inside_the_block():
    """块里的字不许出框——出框在渲染图上一眼看不出来。"""
    ctx = _ctx()
    bx, by, bw, bh = 100.0, 100.0, 300.0, 120.0
    components.block(ctx, bx, by, bw, bh, fill="#2B4C7E",
                     label="解码线程", label_size=40)
    # 组件把标签画在块中央偏上：基线 = by + bh/2 + 字号*0.35
    baseline = by + bh / 2 + 40 * 0.35
    x0, y0, x1, y1 = _ink(ctx, "解码线程", bx + bw / 2, baseline, 40)
    assert x0 >= bx and x1 <= bx + bw
    assert y0 >= by and y1 <= by + bh


def test_block_row_divides_the_width_evenly():
    """块排必须等分：n 个块 + (n-1) 个间隙 = 总宽。"""
    ctx = _ctx()
    boxes = components.block_row(
        ctx, ["a", "b", "c"], 100.0, 100.0, 600.0, 80.0, gap=20.0)
    assert len(boxes) == 3
    widths = [b[2] for b in boxes]
    assert widths[0] == widths[1] == widths[2]
    total = sum(widths) + 20.0 * 2
    assert total == pytest.approx(600.0)


def test_arrow_v_points_downward():
    """竖箭头必须从 y1 指向 y2（y2 更大 = 向下）。"""
    ctx = _ctx()
    components.arrow_v(ctx, 400.0, 100.0, 300.0, color="#2B4C7E")
    # 箭头杆在 x=400 上；检查 y=300 附近有墨、y=100 附近没有杆身
    data = bytes(ctx.get_data())
    stride = ctx.get_stride()

    def has_ink(y: int) -> bool:
        row = data[y * stride:(y + 1) * stride]
        return any(row[3::4])

    assert has_ink(300)
    assert not has_ink(100)


def test_components_do_not_hardcode_contract_copy():
    """组件里不许写死契约文案——文案归契约，AST 守卫会抓。"""
    import ast
    from pathlib import Path

    source = Path(components.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in ("解码线程", "输出", "并行", "growdu"), (
                f"组件里写死了文案：{node.value!r}"
            )
```

- [ ] **Step 2：跑测试确认它红**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_components.py -q
```

预期：FAIL——`ModuleNotFoundError: No module named 'pyv.components'`。

- [ ] **Step 3：写 `pyv/layout.py`**

新建文件，类与两个实例按上面「接口」段的签名写。**取值必须精确等于现状**：

- `layout.V`：`margin_x=0.06, title_size=68, title_y=0.075, content_top=0.130,
  content_bottom=0.700, rail_right=120`（与现有 `scene_layout` 的常量一字不差）
- `layout.H`：`margin_x=0.06, title_size=60, title_y=0.145,
  content_top=0.145, content_bottom=0.86, rail_right=0`

`layout.V` 的 `title()` 行为必须与现有 `scene_layout.title()` 完全一致：
左对齐、x = `w * MARGIN_X`、基线 `h * TITLE_Y`、最大宽 `content_width(w)`、
字号 `TITLE_SIZE`、bold。

- [ ] **Step 4：跑测试确认 layout 的常量与现状一致**

新建 `aiv/pipeline/tests/test_layout.py`：

```python
"""版式层：常量必须与现状一字不差。

**这层的价值是「搬运」不是「规范化」**：改一个数值就是改画面，
逐像素基准会红。所以每一条都写死字面量断言——常量一旦漂，
这里立刻抓住，而不是等到重录基准时才发现。
"""
from __future__ import annotations

import pytest

from pyv import layout, scene_layout


def test_vertical_layout_matches_the_legacy_module():
    """`layout.V` 与旧的 `scene_layout` 必须完全等价。"""
    assert layout.V.MARGIN_X == scene_layout.MARGIN_X
    assert layout.V.TITLE_Y == scene_layout.TITLE_Y
    assert layout.V.CONTENT_TOP == scene_layout.CONTENT_TOP
    assert layout.V.CONTENT_BOTTOM == scene_layout.CONTENT_BOTTOM
    assert layout.V.RAIL_RIGHT == scene_layout.RAIL_RIGHT
    assert layout.V.TITLE_SIZE == scene_layout.TITLE_SIZE


def test_vertical_geometry_is_unchanged():
    """竖版的几何量逐个钉死。"""
    assert layout.V.content_width(1080) == pytest.approx(1080 * 0.94 - 120)
    assert layout.V.content_left(1080) == pytest.approx(1080 * 0.06)
    assert layout.V.content_right(1080) == pytest.approx(1080 * 0.06 + 1080 * 0.94 - 120)
    assert layout.V.content_top_px(1920) == pytest.approx(1920 * 0.130)
    assert layout.V.content_bottom_px(1920) == pytest.approx(1920 * 0.700)


def test_horizontal_geometry_is_unchanged():
    """横版的几何量逐个钉死（取自迁移前的现状值）。"""
    assert layout.H.WIDTH == 1920 and layout.H.HEIGHT == 1080
    assert layout.H.content_left(1920) == pytest.approx(1920 * 0.06)
    assert layout.H.content_width(1920) == pytest.approx(1920 * 0.94)
```

- [ ] **Step 5：写 `pyv/components.py`**

新建文件，按「接口」段的签名实现。约束：

- 组件**只画一个东西**，位置由调用方给；
- 组件内的文字走 `layout` 的 `line()`（即 `fit_size` 收字号）；
- 组件里**不得出现契约文案字面量**；
- `block()` 的标签基线：`by + bh/2 + label_size * 0.35`（居中时），
  左边距 `bw * 0.09`（与迁移场景现状一致，迁移时按现状校准）。

- [ ] **Step 6：跑组件测试确认它绿**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_components.py tests/test_layout.py -q
```

预期：全绿。

- [ ] **Step 7：把 `scene_layout.py` 改成兼容层**

保留现有公开名字（`TITLE_Y` / `CONTENT_TOP` / `CONTENT_BOTTOM` / `MARGIN_X` /
`RAIL_RIGHT` / `TITLE_SIZE` / `MIN_SIZE` / `fit_size` / `line` / `title` /
`content_*`），实现转发到 `layout.V` 与 `pyv.scene_layout` 现有的 `fit_size`。
**转发必须逐字保持现有行为**——26 个未迁移的场景还在用它。

- [ ] **Step 8：迁三个代表场景（像素必须不变）**

按顺序迁，每迁一个立刻跑基准：

```bash
cd aiv/pipeline && python3 -m pytest tests/test_contract.py -q
```

迁移对象与验收：

| 场景 | 用到的组件 | 验收 |
| --- | --- | --- |
| `pyv/scenes/s02_serial.py` | `block` / `block_row` / `arrow_v` | 该段 3 帧哈希不变 |
| `pyv/scenes/s03_cores.py` | `block_row` | 该段 3 帧哈希不变 |
| `pyv/scenes/s04_parallel.py` | `band` / `arrow_v` | 该段 3 帧哈希不变 |

迁移规则（**硬约束**）：

- **坐标值一个都不许改**。组件的位置参数用迁移前的原值；
- 文字的字号、颜色、字重、alpha 全部照搬；
- 圆角半径照搬；
- 箭头只把「手算坐标」换成组件函数，**端点值照搬**；
- 画完立刻跑基准，红了就回退这一处。

迁移过程中若发现组件 API 表达不了某个形状 → **加组件，不要在场景里手画**。

- [ ] **Step 9：跑全量测试**

```bash
cd aiv/pipeline && python3 -m pytest tests/ -q
```

预期：全绿，**且基准一条没红**。

- [ ] **Step 10：提交**

```bash
git add aiv/pipeline/pyv/layout.py aiv/pipeline/pyv/components.py \
        aiv/pipeline/pyv/scene_layout.py \
        aiv/pipeline/pyv/scenes/s02_serial.py \
        aiv/pipeline/pyv/scenes/s03_cores.py \
        aiv/pipeline/pyv/scenes/s04_parallel.py \
        aiv/pipeline/tests/test_components.py aiv/pipeline/tests/test_layout.py
git commit -m "feat(aiv): 版式层与组件层，迁三个代表场景

画幅级的版式常量与绘制入口收进 pyv/layout.py（横版 H / 竖版 V 两个实例），
旧的 scene_layout.py 降级成转发到 layout.V 的兼容层——26 个未迁移的场景
一个字都不用改。

可复用的画面组件收进 pyv/components.py：block / block_row / band /
matrix / arrow_v / arrow_h。组件只画一个东西，位置由调用方给，
组件内不得出现契约文案字面量。

迁 s02_serial / s03_cores / s04_parallel 三个代表场景——正是「等分一排块」
与「三带加箭头」这两处重复的源头。迁移后这 9 帧的逐像素基准必须全绿：
坐标、字号、颜色、字重、圆角半径一个都没改。"
```

- [ ] **Step 11：隔离 worktree 验这笔 commit 自身**

```bash
git worktree add --detach /tmp/aiv-verify-task2 HEAD
cd /tmp/aiv-verify-task2/aiv/pipeline && python3 -m pytest tests/ -q
git worktree remove /tmp/aiv-verify-task2
```

---

### Task 3：字体子集入库 + 安装机制 + 重录基准

**接口**：
- `pyv/fonts.py`：`font_family()` 的候选顺序改为
  `AIV_FONT_FAMILY` → 内置 `AIV Sans CJK SC` → PingFang SC → Noto Sans CJK SC /
  思源黑体 → fontconfig 兜底。
- 新增 `pyv/fonts.BUNDLED_FAMILY = "AIV Sans CJK SC"` 与
  `pyv/fonts.BUNDLED_PATH`（指向 `aiv/pipeline/assets/fonts/AIVSansCJKSC-Regular.otf`）。
- `pyv/doctor.py`：多一条「内置字体」的检查项。

- [ ] **Step 1：先写失败的测试**

新建 `aiv/pipeline/tests/test_font_subset.py`：

```python
"""内置字体子集：来源钉住、缺字就红。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pyv import fonts

AIV_ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = AIV_ROOT / "pipeline" / "assets" / "fonts"
MANIFEST = FONT_DIR / "SOURCE.json"
SUBSET = FONT_DIR / "AIVSansCJKSC-Regular.otf"


def _repo_chars() -> set[str]:
    """仓库里会被画到画面上的字符。

    与 `scripts/build_font_subset.py` 的提取逻辑**必须一致**——
    这里是它的独立复算，两边不一致就红。
    """
    chars: set[str] = set()

    def add(text: str) -> None:
        chars.update(ch for ch in text if ord(ch) > 31)

    for path in sorted((AIV_ROOT / "contracts").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))

        def walk(node):
            if isinstance(node, str):
                add(node)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)

        walk(raw)

    for path in sorted(AIV_ROOT.glob("字幕-*.md")):
        add(path.read_text(encoding="utf-8"))

    for pattern in ("pipeline/pyv/**/*.py", "brand/scripts/*.py",
                    "character/scripts/*.py"):
        for path in sorted(AIV_ROOT.glob(pattern)):
            for match in re.finditer(r'"([^"\\]*)"|\'([^\'\\]*)\'',
                                     path.read_text(encoding="utf-8")):
                add(match.group(1) or match.group(2) or "")

    add("".join(chr(i) for i in range(32, 127)))
    add("　·—…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*")
    return chars


def test_the_bundled_font_is_present():
    assert SUBSET.is_file(), f"内置字体不在：{SUBSET}"
    assert MANIFEST.is_file(), f"字体出处台账不在：{MANIFEST}"


def test_the_manifest_pins_the_upstream_source():
    """出处台账必须钉住版本与 sha256——不然换一份字体没人知道。"""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["family"] == fonts.BUNDLED_FAMILY
    assert data["license"] == "SIL Open Font License 1.1"
    assert re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
    assert data["upstream"].startswith("https://")


def test_the_subset_covers_every_character_we_draw():
    """**缺字就红**：新一期加了新字而没重跑子集脚本 → CI 红。

    没有这条守卫，手工维护的字符集必然漂；有了它，字符集只能是脚本算出来的。
    """
    from fontTools.ttLib import TTFont

    font = TTFont(SUBSET)
    cmap = font.getBestCmap()
    missing = sorted(ch for ch in _repo_chars() if ord(ch) not in cmap)
    assert not missing, (
        f"内置字体缺 {len(missing)} 个字：{missing[:20]}——"
        f"跑 scripts/build_font_subset.py 重生成子集"
    )


def test_the_subset_is_small():
    """子集的意义在于小。超了说明提取范围写宽了。"""
    size = SUBSET.stat().st_size
    assert size < 2 * 1024 * 1024, f"子集 {size} 字节，太大了"
```

- [ ] **Step 2：跑测试确认它红**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_font_subset.py -q
```

预期：FAIL——`内置字体不在`。

- [ ] **Step 3：写子集生成脚本**

新建 `aiv/pipeline/scripts/build_font_subset.py`：

- 从 GitHub 上游下载 Noto Sans CJK SC（**必须从上游拿，不从本机 `~/Library/Fonts` 拿**——
  那是本机状态，不可复现）。上游地址写死成常量，下载后核对 sha256。
  若网络不可用，允许用 `--from <本地路径>` 传入一份已下载的上游文件，
  但**必须**核对它与台账里钉的 sha256 一致。
- 字符集提取逻辑与 `tests/test_font_subset.py::_repo_chars()` **逐字一致**
  （两边独立复算，一致才说明子集是全的）。
- 子集化参数：`layout_features=["*"]`、`name_IDs=["*"]`、`hinting=True`、
  `desubroutinize=False`、`notdef_outline=True`。
- 族名改写为 `AIV Sans CJK SC`（name ID 1 / 3 / 4 / 6 / 16 / 17）。
- 输出 `aiv/pipeline/assets/fonts/AIVSansCJKSC-Regular.otf` 与 `SOURCE.json`：

```json
{
  "family": "AIV Sans CJK SC",
  "license": "SIL Open Font License 1.1",
  "upstream": "https://github.com/notofonts/noto-cjk/releases/download/…",
  "version": "…",
  "sha256": "…",
  "subset_sha256": "…",
  "chars": 1251
}
```

- [ ] **Step 4：跑脚本生成子集**

```bash
cd aiv/pipeline && python3 scripts/build_font_subset.py
```

预期：打印子集字节数（约 632KB）与字符数。

- [ ] **Step 5：跑测试确认它绿**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_font_subset.py -q
```

预期：全绿。

- [ ] **Step 6：写安装脚本**

新建 `aiv/pipeline/scripts/install_font.py`：

```python
#!/usr/bin/env python3
"""把内置字体装进 OS 的字体目录，让 cairo 找得到它。

**为什么不能只放在仓库里**：实测 cairo 在 macOS 上走 CoreText、
在 Linux 上走 fontconfig——两边的「字体目录」都不是仓库目录，
必须装到 OS 认的地方：

| 平台 | 装到 | 额外步骤 |
| --- | --- | --- |
| macOS | `~/Library/Fonts/` | CoreText 自动拾取 |
| Linux | `~/.local/share/fonts/` | `fc-cache -f` |

幂等：已安装且 sha256 相同 → 跳过。
"""
```

- [ ] **Step 7：改 `pyv/fonts.py`**

- 新增常量 `BUNDLED_FAMILY = "AIV Sans CJK SC"`、
  `BUNDLED_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "AIVSansCJKSC-Regular.otf"`。
- 候选顺序：`AIV_FONT_FAMILY` → 内置 → PingFang → Noto / 思源 → fontconfig。
- 候选的 `family_resolves()` 判定保持不变（用文本宽度与 `.notdef` 比对）。

- [ ] **Step 8：改 `pyv/doctor.py`**

多一条检查项「内置字体」：能解析到 `AIV Sans CJK SC` → 报「已就位」；
不能 → 报「未安装」并给出 `python3 scripts/install_font.py` 这条修复命令。

- [ ] **Step 9：改 `tests/test_assets_are_tracked.py`**

把内置字体加进 `REQUIRED_ASSETS`：

```python
    "aiv/pipeline/assets/fonts/AIVSansCJKSC-Regular.otf": "内置中文字体（渲染必需）",
```

⚠ `test_no_tracked_media_outside_the_allowlist` 的媒体后缀表里**没有** `.otf`，
所以字体不会被它拦下——但要确认它确实被 git 跟踪（由 `test_required_asset_is_tracked` 保证）。

- [ ] **Step 10：重录基准（换了字体，画面必然变）**

```bash
cd aiv/pipeline && python3 scripts/capture_scene_baseline.py
```

**前置**：本机要能解析到 `AIV Sans CJK SC`。先装：

```bash
cd aiv/pipeline && python3 scripts/install_font.py
```

预期：`capture.font` 变成 `AIV Sans CJK SC`，108 帧全部重抓。

- [ ] **Step 11：改文档**

- `aiv/上机指南.md` §三：字体那一节改成「两台机器用同一份内置字体」，
  删掉「像素不同、逐像素基准跳过」的说法。
- `aiv/形象与音色规范.md` §1.3：同样更新。
- `aiv/README.md`「跑一遍」那节：加一句装字体的步骤。

- [ ] **Step 12：跑全量测试**

```bash
cd aiv/pipeline && python3 -m pytest tests/ -q
```

预期：全绿。

- [ ] **Step 13：提交**

```bash
git add aiv/pipeline/assets/fonts/ aiv/pipeline/pyv/fonts.py \
        aiv/pipeline/pyv/doctor.py aiv/pipeline/scripts/build_font_subset.py \
        aiv/pipeline/scripts/install_font.py \
        aiv/pipeline/tests/test_font_subset.py \
        aiv/pipeline/tests/test_assets_are_tracked.py \
        aiv/pipeline/tests/fixtures/scene_baseline.json \
        aiv/上机指南.md aiv/形象与音色规范.md aiv/README.md
git commit -m "feat(aiv): 内置字体子集入库，跨机用同一份字体

Noto Sans CJK SC（SIL OFL 1.1，可随软件分发）按仓库实际用到的 1251 个
字符子集化：16.4MB → 632KB。族名改成 AIV Sans CJK SC（唯一名，
不与系统字体抢）。

字符集**从仓库自动提取**，不手工维护；一条守卫断言子集覆盖当前
仓库用到的每个字符——新一期加了新字而没重跑脚本，CI 就红。

实测过两件关键事实：
- cairo 在 macOS 走 CoreText、不认 fontconfig 目录 → 字体必须装进
  OS 字体目录（macOS ~/Library/Fonts，Linux ~/.local/share/fonts + fc-cache）
- 跨 OS 逐像素一致做不到（CoreText ≠ FreeType），能保的是布局一致：
  同一份字体文件给出同一组步进宽度（实测差 ≤0.45px）

基准在换字体后重录：macOS 从 PingFang SC 换成 AIV Sans CJK SC，
成片内容一字不变，像素与历史成片不同。"
```

- [ ] **Step 14：隔离 worktree 验这笔 commit 自身**

```bash
git worktree add --detach /tmp/aiv-verify-task3 HEAD
cd /tmp/aiv-verify-task3/aiv/pipeline && python3 -m pytest tests/ -q
git worktree remove /tmp/aiv-verify-task3
```

⚠ 隔离 worktree 里**没有**已安装的内置字体 → `fonts.py` 会回退到 PingFang →
基准会 skip（这是预期）。**但**缺字守卫与素材跟踪守卫必须绿。
若基准没 skip 而红了 → 说明字体解析出了问题，要查。

---

### Task 4：跨机布局指纹守卫

**接口**：
- 新增 `aiv/pipeline/scripts/capture_layout_fingerprint.py`
- 新增 `aiv/pipeline/tests/fixtures/layout_fingerprint.json`
- 新增 `aiv/pipeline/tests/test_layout_fingerprint.py`

- [ ] **Step 1：先写失败的测试**

新建 `aiv/pipeline/tests/test_layout_fingerprint.py`：

```python
"""跨机布局指纹守卫。

**为什么要有它**：逐像素基准在 macOS 与 Linux 之间不可比——
cairo 在 macOS 走 CoreText、在 Linux 走 FreeType，栅格化不同，像素必然不同。
但**轮廓、坐标与步进宽度**来自字体文件与场景代码，与栅格化无关，跨机可比。

指纹记四类量：
- 落笔坐标 (x, y)：场景代码里的纯算术，跨机完全一致
- 字号：`fit_size` 收敛后的结果
- 步进宽度 `x_advance`：字体文件 hmtx
- 轮廓包围盒：`text_path` + `path_extents`，是字形轮廓不是像素

**容差写死字面量**，不从被测代码 import——阈值自证等于永远绿。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod

FIXTURE = Path(__file__).parent / "fixtures" / "layout_fingerprint.json"

#: 扫的时刻。
TIMES = (0.0, 0.25, 0.5, 0.75, 1.0)

#: 两个画幅。
CANVASES = (("horizontal", 1920, 1080), ("vertical", 1080, 1920))

# ---- 容差（字面量，不从被测代码 import）--------------------------------
#
# 依据（2026-11-16 实测，同一份 NotoSansCJKsc-Regular.otf）：
# cairo(CoreText) 与 PIL(FreeType) 的步进宽度在 24~68px 上相差 ≤ 0.45px，
# PIL 侧取整。取 1.0px 留一倍以上余量。
ADVANCE_TOLERANCE_PX = 1.0
# 字号是 `fit_size` 的收敛值，字号变了步进宽度就变，容差同量级。
SIZE_TOLERANCE = 1.0
# 轮廓包围盒：字号与步进的微小差异会放大到轮廓两端，各留 2px。
OUTLINE_TOLERANCE_PX = 2.0
# 坐标：场景代码里的纯算术，跨机应当完全一致，留 0.01 吃浮点噪声。
COORD_TOLERANCE_PX = 0.01
```

采集与比对**共用一份代码**（`pyv/fingerprint.py`）——采集脚本与测试各写一套，
两边一定会漂，那时守卫就变成了「比自己的影子」。

```python
# aiv/pipeline/pyv/fingerprint.py

"""布局指纹的采集。

指纹记的是**与栅格化无关**的量：落笔坐标、字号、步进宽度、轮廓包围盒。
采集靠插桩拦 `draw.text` 与 `scene_layout.text`（照
`tests/test_scene_overlap.py` 的 `Probe` 做法，但记的量不同）。
"""
from __future__ import annotations

import cairo

from pyv import fonts


class TextProbe:
    """插桩：记录每次绘制的文字的指纹量。"""

    def __init__(self) -> None:
        self.items: list[list[float]] = []

    def text(self, ctx, s, x, y, size, color, anchor="left", bold=False,
             alpha=1.0):
        if s and s.strip():
            ctx.select_font_face(
                fonts.font_family(), cairo.FONT_SLANT_NORMAL,
                cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
            )
            ctx.set_font_size(size)
            advance = ctx.text_extents(s).x_advance
            origin = x
            if anchor == "center":
                origin = x - ctx.text_extents(s).width / 2
            elif anchor == "right":
                origin = x - ctx.text_extents(s).width
            ctx.new_path()
            ctx.move_to(origin, y)
            ctx.text_path(s)
            x0, y0, x1, y1 = ctx.path_extents()
            ctx.new_path()
            self.items.append([round(x, 3), round(y, 3), round(size, 3),
                               round(advance, 3),
                               round(x0, 3), round(y0, 3),
                               round(x1, 3), round(y1, 3)])
        return None
```

比对测试（`tests/test_layout_fingerprint.py`）：

```python
def _all_segments():
    for episode in episodes_mod.EPISODE_ORDER:
        contract = contract_mod.load_contract(
            AIV_ROOT / "contracts" / f"{episode}.json")
        for segment in contract.segments:
            yield episode, segment


def _expected_keys() -> set[str]:
    return {
        f"{episode}/{segment.id}/{canvas}@{t}"
        for episode, segment in _all_segments()
        for canvas, _, _ in CANVASES
        for t in TIMES
    }


def test_the_fingerprint_covers_every_segment_and_canvas():
    """指纹必须覆盖六期 × 2 画幅 × 5 时刻——少一条就有一段没人守。"""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = set(data["frames"])
    expected = _expected_keys()
    assert actual == expected, (
        f"指纹覆盖对不上：缺 {sorted(expected - actual)[:5]}；"
        f"多 {sorted(actual - expected)[:5]}"
    )


def test_the_layout_fingerprint_matches(monkeypatch):
    """每个量都在容差内。超了就报出是哪一期哪一段哪个量差多少。"""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    findings: list[str] = []
    for episode, segment in _all_segments():
        for canvas, w, h in CANVASES:
            for t in TIMES:
                key = f"{episode}/{segment.id}/{canvas}@{t}"
                expected = data["frames"][key]
                actual = fingerprint.collect(segment, canvas, w, h, t, monkeypatch)
                if len(actual) != len(expected):
                    findings.append(
                        f"{key} 文字数 {len(actual)} != 基准 {len(expected)}")
                    continue
                for index, (want, got) in enumerate(zip(expected, actual)):
                    checks = (
                        ("x", 0, COORD_TOLERANCE_PX),
                        ("y", 1, COORD_TOLERANCE_PX),
                        ("size", 2, SIZE_TOLERANCE),
                        ("advance", 3, ADVANCE_TOLERANCE_PX),
                        ("x0", 4, OUTLINE_TOLERANCE_PX),
                        ("y0", 5, OUTLINE_TOLERANCE_PX),
                        ("x1", 6, OUTLINE_TOLERANCE_PX),
                        ("y1", 7, OUTLINE_TOLERANCE_PX),
                    )
                    for name, slot, tolerance in checks:
                        if abs(want[slot] - got[slot]) > tolerance:
                            findings.append(
                                f"{key} 第 {index} 个文字的 {name}："
                                f"{got[slot]:.2f} vs 基准 {want[slot]:.2f}"
                                f"（差 {abs(want[slot] - got[slot]):.2f} > {tolerance}）")
    assert not findings, "布局指纹对不上：\n  " + "\n  ".join(findings[:40])
```

- [ ] **Step 2：跑测试确认它红**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_layout_fingerprint.py -q
```

预期：FAIL——fixture 不存在。

- [ ] **Step 3：写采集脚本**

新建 `aiv/pipeline/scripts/capture_layout_fingerprint.py`：

- 用**插桩**（照 `tests/test_scene_overlap.py` 的 `Probe` 做法）拦 `draw.text`
  与 `scene_layout.text`，每次记录 `(x, y, size, x_advance, 轮廓包围盒)`。
- 遍历六期契约 × 2 画幅 × 5 时刻。
- 写 `tests/fixtures/layout_fingerprint.json`。

- [ ] **Step 4：写比对逻辑**

逐项按容差判；任何一项超容差就红，报出是哪一期哪一段哪个量差多少。

- [ ] **Step 5：跑测试确认它绿**

```bash
cd aiv/pipeline && python3 -m pytest tests/test_layout_fingerprint.py -q
```

预期：全绿。

- [ ] **Step 6：验证它真的会红（注入缺陷）**

改一个场景里的一个字号（比如 `s03_cores` 里的某个字号 +1），
跑测试 → 必须红；改回来 → 必须绿。

**没验过这条的守卫不算写完。**

- [ ] **Step 7：改 CI**

`.github/workflows/aiv-pipeline.yml`：

- 装上内置字体（`python3 scripts/install_font.py` + `fc-cache -f`）；
- `fonts-noto-cjk` 降级为兜底（保留但不作为主力）。

- [ ] **Step 8：跑全量测试并提交**

```bash
cd aiv/pipeline && python3 -m pytest tests/ -q
git add aiv/pipeline/scripts/capture_layout_fingerprint.py \
        aiv/pipeline/tests/test_layout_fingerprint.py \
        aiv/pipeline/tests/fixtures/layout_fingerprint.json \
        .github/workflows/aiv-pipeline.yml
git commit -m "feat(aiv): 跨机布局指纹守卫

逐像素基准在 macOS 与 Linux 之间不可比——cairo 在 macOS 走 CoreText、
在 Linux 走 FreeType，栅格化不同像素必然不同。但轮廓、坐标与步进宽度
来自字体文件与场景代码，与栅格化无关，跨机可比。

指纹记四类量：落笔坐标、字号、步进宽度、轮廓包围盒（text_path 的
path_extents，是轮廓不是像素）。容差写死字面量并写清依据：实测
CoreText 与 FreeType 的步进差 ≤0.45px，取 1.0px 余量。

CI 装上内置字体，让 Linux 上的布局指纹与 macOS 同字体、同步进。"
```

- [ ] **Step 9：隔离 worktree 验这笔 commit 自身**

```bash
git worktree add --detach /tmp/aiv-verify-task4 HEAD
cd /tmp/aiv-verify-task4/aiv/pipeline && python3 -m pytest tests/ -q
git worktree remove /tmp/aiv-verify-task4
```

---

## 收尾

- [ ] 全量测试通过（主工作区 + 隔离 worktree）
- [ ] `aiv/README.md` 与 `aiv/上机指南.md` 的说法与新状态一致
- [ ] 五笔提交各自在干净检出上绿（逐笔验过）

## 不做什么（重申）

- 不追求跨平台逐像素一致（实测不可达）。
- 不要求维护者准备第二台 Linux 机器来录基准。
- 不改任何一期的文案、契约、旁白。
- 不做 998 处硬编码比例的全面收编——版式层是**搬运**，收编随场景迁移
  增量进行，本批只迁三个代表场景。
- 不动 `h3` 那条路。
