# 竖版（抖音档）版式改造 实施计划

> **本计划对应设计**：`aiv/pipeline/plans/2026-11-15-vertical-douyin-layout-design.md`
> **执行方式**：本会话内直接执行（每个任务自带测试与提交）。

**目标**：让竖版（1080×1920，抖音那一档）的画面内容集中、字号顶得住、
右下角不被平台按钮压住——**横版一个字都不改**。

**架构**：共用版式常量集中在 `pyv/scene_layout.py`（四个位置 + 右侧安全区），
各场景的竖版画法各写各的、但规矩不许各写各的。两个「内容分散」最严重的场景
（s03 核阵列、s04 线程拓扑）单独重排。守卫加两条：右侧按钮栏、内容下沿。

**技术栈**：Python 3.11+ / pycairo / pytest / ffmpeg（本机 Windows）

## 全局约束

- **横版（1920×1080）一个字都不改**：只动 `h > w` 的竖版分支。
- **契约（`aiv/contracts/*.json`）不动**：`caption` 字段保留（横版还在用）。
- **字幕文案不动**。
- 竖版内容右缘 **≤ 960**（1080 − 120 的平台 UI 预留）。
- 竖版内容下缘 **≤ 1344**（字幕带从 1393 起）。
- 每行字都要过 `scene_layout.line()`（`fit_size` 收字号），**宁可字小也不能出框**。
- 提交信息：`type(scope): 中文描述`，正文说明「为什么」，结尾写测试结论。
- **只暂存本会话自己的文件**（同一仓库有并发会话在改 `toutiao/`）。

---

### Task 1：共用版式——右侧让出平台 UI，内容区落到底

**文件**
- 改：`aiv/pipeline/pyv/scene_layout.py`
- 改（21 个）：`aiv/pipeline/pyv/scenes/*.py`（把 `w * scene_layout.CONTENT_W` 换成 `scene_layout.content_width(w)`）
- 改：`aiv/pipeline/tests/test_canvas.py`（第 271 行同样换成 `content_width(width)`）
- 测：`aiv/pipeline/tests/test_canvas.py`

**产出接口**
- `scene_layout.RAIL_RIGHT = 120`
- `scene_layout.content_width(w) -> float`（= `w * (1 - MARGIN_X) - RAIL_RIGHT`）
- `scene_layout.content_left(w) -> float`、`scene_layout.content_right(w) -> float`
- `scene_layout.content_top(h) -> float`、`scene_layout.content_bottom(h) -> float`
- 常量：`TITLE_Y = 0.075`、`CONTENT_TOP = 0.130`、`CONTENT_BOTTOM = 0.700`、`TITLE_SIZE = 68`
- 删：`scene_layout.CONTENT_W`（不再有「内容宽 = 0.88 画布宽」这回事）

- [ ] **Step 1：先写失败的测试**

在 `aiv/pipeline/tests/test_canvas.py` 追加：

```python
def test_the_vertical_content_reserves_the_right_platform_buttons():
    """竖版内容右缘要留给抖音的点赞/评论/分享栏。"""
    from pyv import scene_layout

    width = 1080
    left = scene_layout.content_left(width)
    right = scene_layout.content_right(width)
    assert left == pytest.approx(width * 0.06)
    assert right == pytest.approx(960)
    assert scene_layout.content_width(width) == pytest.approx(895.2)


def test_the_vertical_content_band_reaches_down_to_the_subtitle():
    """内容区下沿要贴着字幕带上沿（1344），不再停在 1238 留一大片白。"""
    from pyv import scene_layout

    assert scene_layout.content_bottom(1920) == pytest.approx(1344)
    assert scene_layout.content_top(1920) == pytest.approx(250)
    assert scene_layout.content_top(1920) < scene_layout.content_bottom(1920)
```

- [ ] **Step 2：跑测试确认它失败**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/test_canvas.py -q -k "right_platform_buttons or content_band_reaches"
```
Expected: FAIL（`content_right` 不存在）

- [ ] **Step 3：改 `scene_layout.py`**

```python
#: 右侧平台 UI 预留（抖音的点赞/评论/分享栏落在这一带）。
#:
#: **这是工程上的保守取值，不是平台文档里写明的数字**——抖音没有公开
#: 「安全区」规格。与其等审核时才发现右下角的字被按钮压住，不如自己留出
#: 一条。横版不用留（横版不叠平台 UI）。
RAIL_RIGHT = 120

#: 左边距（比例相对画面宽度）。横版的内容从 w*0.06 开始，竖版沿用同一个边距。
MARGIN_X = 0.06

#: 竖版的几个位置（比例相对画面高度）
TITLE_Y = 0.075
CONTENT_TOP = 0.130
CONTENT_BOTTOM = 0.700

#: 标题与说明的字号（竖版比横版大一号：手机上看，标题要顶得住）
TITLE_SIZE = 68
```

把 `content_width` 改成：

```python
def content_width(w: int) -> float:
    """内容区的宽度：左边距起，右边让出平台 UI 的按钮栏。"""
    return w * (1 - MARGIN_X) - RAIL_RIGHT


def content_right(w: int) -> float:
    """内容区的右边缘。"""
    return content_left(w) + content_width(w)
```

删掉 `CONTENT_W` 常量与 `caption()` 之外的旧 `caption` 位置常量 `CAPTION_Y`
（Task 2 才删 `caption()`，这一步先留着）。

- [ ] **Step 4：把 21 个场景的宽度取法换掉**

用脚本批量替换（保持 CRLF 行尾）：

```python
import pathlib
for path in pathlib.Path("pyv/scenes").glob("*.py"):
    text = path.read_text(encoding="utf-8")
    new = text.replace("w * scene_layout.CONTENT_W", "scene_layout.content_width(w)")
    if new != text:
        path.write_text(new, encoding="utf-8")
```

`tests/test_canvas.py` 第 271 行同样换成 `scene_layout.content_width(width)`。

- [ ] **Step 5：跑测试**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/ -q -rs
```
Expected: aiv 套件全绿（Windows 基线 953 passed / 5 failed / 16 skipped，
5 个失败是仓库原有的 Windows 兼容问题，不是我引进的）

- [ ] **Step 6：提交**

```bash
git add -- aiv/pipeline/pyv/scene_layout.py aiv/pipeline/pyv/scenes aiv/pipeline/tests/test_canvas.py
git commit -m "feat(aiv): 竖版内容让出右侧平台 UI"
```

---

### Task 2：竖版去掉说明行，底部只留字幕

**文件**
- 改：`aiv/pipeline/pyv/scene_layout.py`（删 `caption()`）
- 改（23 个）：`aiv/pipeline/pyv/scenes/*.py`（删 `scene_layout.caption(...)` 调用）
- 测：`aiv/pipeline/tests/test_vertical_layout.py`

**为什么**：说明行与字幕讲的是同一句话（csn/s02 说明「按时间戳排，并不可靠」，
字幕「并发提交 时间顺序不可靠」），两行叠在下面只会互相干扰；s02 的字幕甚至
和标题一字不差。横版的说明行**保留**（横版底部没有字幕）。

- [ ] **Step 1：先写失败的测试**

在 `aiv/pipeline/tests/test_vertical_layout.py` 追加：

```python
def test_no_vertical_scene_draws_a_caption_line():
    """竖版底部只留字幕，不再有说明行。

    说明行与字幕讲的是同一句话，两行叠在下面只会互相干扰。
    """
    assert not hasattr(scene_layout, "caption"), (
        "scene_layout 还有 caption()——竖版不该再画说明行")
    offenders = [
        path.name for path in SCENES_DIR.glob("*.py")
        if "scene_layout.caption(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"这些模块还在画说明行：{offenders}"
```

并在该文件的 import 里补 `from pyv import scene_layout`。

- [ ] **Step 2：跑测试确认它失败**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/test_vertical_layout.py -q -k caption_line
```
Expected: FAIL（`scene_layout.caption` 还在）

- [ ] **Step 3：删掉 `caption()` 与 23 处调用**

`scene_layout.py` 里删掉整个 `caption()` 函数与 `CAPTION_Y` 常量，
并把文件头的规矩文档补上第三条：

```
规矩三：**底部只留字幕。**
    竖版不再画说明行——底部那一行是字幕的位置，说明行与字幕讲的是
    同一句话，两行叠在下面只会互相干扰（s02 的字幕甚至和标题一字不差）。
    横版的说明行保留：横版底部没有字幕，也没有平台 UI。
```

场景模块里用脚本批量删（每处都是单独一行、四个空格缩进）：

```python
import pathlib, re
pattern = re.compile(r"^[ \t]*scene_layout\.caption\([^\n]*\)\n", re.MULTILINE)
for path in pathlib.Path("pyv/scenes").glob("*.py"):
    text = path.read_text(encoding="utf-8")
    new = pattern.sub("", text)
    if new != text:
        path.write_text(new, encoding="utf-8")
```

- [ ] **Step 4：跑测试**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/ -q -rs
```
Expected: 全绿（同样 5 个仓库原有的失败）

- [ ] **Step 5：提交**

```bash
git add -- aiv/pipeline/pyv/scene_layout.py aiv/pipeline/pyv/scenes aiv/pipeline/tests/test_vertical_layout.py
git commit -m "refactor(aiv): 竖版去掉说明行，底部只留字幕"
```

---

### Task 3：s03 核阵列竖版重排

**文件**
- 改：`aiv/pipeline/pyv/scenes/s03_cores.py`（`_render_vertical`）
- 测：`aiv/pipeline/tests/test_vertical_layout.py`、`aiv/pipeline/tests/test_scene_overlap.py`（自动覆盖）

**为什么**：现在是「核阵列 / 只用到 1 核 / 大事务 / 小事务高并发 / 都跟不上」
五个互不相干的行，谁是对比谁看不出来。改成「一片核 + 两列并排的压力 + 一句结论」。

- [ ] **Step 1：改 `_render_vertical`**

```python
def _render_vertical(ctx, t: float, w: int, h: int, p: Params) -> None:
    """竖版：核阵列在上，两组压力并排对比，结论收底。

    横版是左右分栏，竖版上下堆叠之后会散成五个互不相干的行——**谁跟谁
    对比就看不出来**。所以两组压力并排放：一列大事务（一整块），一列
    小事务高并发（许多小块），底下再来一句结论。
    """
    core_count = int(p["core_count"])
    cols = int(p["core_cols"])
    highlighted = int(p["highlighted_core"])

    left = scene_layout.content_left(w)
    full_w = scene_layout.content_width(w)

    scene_layout.title(ctx, p["title"], w, h)

    # ---- 核阵列：8 列 × 4 行，铺满内容区 ----
    cell_w, cell_h = 96, 88
    gap_x, gap_y = 18, 20
    grid_w = cols * cell_w + (cols - 1) * gap_x
    x0 = left + (full_w - grid_w) / 2
    y0 = scene_layout.content_top(h)
    pulse = easing.ease_out_cubic(max(0.0, (t - 0.20) / 0.55))
    lit = set(highlighted_cores(p.as_dict()))

    for i in range(core_count):
        col, row = i % cols, i // cols
        x = x0 + col * (cell_w + gap_x)
        y = y0 + row * (cell_h + gap_y)
        rounded_rect(ctx, x, y, cell_w, cell_h, 8,
                     COLORS["accent"] if i in lit else "#DCE1E8")

    cx = x0 + (highlighted % cols) * (cell_w + gap_x) + cell_w / 2
    cy = y0 + (highlighted // cols) * (cell_h + gap_y) + cell_h / 2
    ctx.set_source_rgb(*hex_to_rgb(COLORS["accent"]))
    ctx.set_line_width(6)
    ctx.arc(cx, cy, cell_w * (0.70 + 0.06 * pulse), 0, 6.2832)
    ctx.stroke()

    # ---- 只用到一核：浅橙底的 chip ----
    rounded_rect(ctx, left, 700, 520, 76, 14, "#FDF0DC")
    scene_layout.line(ctx, p["stat"], left + 28, 752, 460, 48,
                      COLORS["accent"], bold=True)

    # ---- 两组压力：并排两列（这才是这个场景要比的东西）----
    col_w = (full_w - 60) / 2
    right_x = left + col_w + 60
    scene_layout.line(ctx, p["big_label"], left, 872, col_w, 46,
                      COLORS["problem"], bold=True)
    scene_layout.line(ctx, p["small_label"], right_x, 872, col_w, 46,
                      COLORS["problem"], bold=True)

    # 大事务：一整块
    rounded_rect(ctx, left, 906, col_w, 294, 14, COLORS["problem"])

    # 小事务高并发：七个块排成 4 + 3
    block_w = (col_w - 3 * 14) / 4
    for i in range(SMALL_BLOCKS):
        col = i % 4
        row = i // 4
        x = right_x + col * (block_w + 14)
        y = 906 + row * 150
        rounded_rect(ctx, x, y, block_w, 130, 10,
                     COLORS["problem"] if i % 2 == 0 else "#F8C489")

    # ---- 结论 ----
    scene_layout.line(ctx, p["conclusion"], left, 1290, full_w, 60,
                      COLORS["primary"], bold=True)
```

- [ ] **Step 2：跑测试**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/test_vertical_layout.py tests/test_scene_overlap.py -q
```
Expected: 全绿（s03 的竖版既没出框，也没让两处字压在一起）

- [ ] **Step 3：提交**

```bash
git add -- aiv/pipeline/pyv/scenes/s03_cores.py
git commit -m "feat(aiv): s03 核阵列竖版重排——两组压力并排对比"
```

---

### Task 4：s04 线程拓扑竖版重排

**文件**
- 改：`aiv/pipeline/pyv/scenes/s04_parallel.py`（`_render_vertical`）
- 测：同上

**为什么**：三条带之间各留 154px / 144px 白，箭头细长，链路像三段不相干的图。

- [ ] **Step 1：改版式常量与 `_render_vertical`**

```python
# 竖版：上下三段的版式常量（像素，绝对值——竖版只有这一档画布）
V_SOURCE_TOP, V_SOURCE_H = 250, 280
V_ARROW_H = 100
V_WORKER_TOP, V_WORKER_H = 630, 300
V_TARGET_TOP, V_TARGET_H = 1030, 280
V_WORKER_GAP_RATIO = 0.021    # 分支之间的列距（相对内容区宽度）
```

`_render_vertical` 的主体：

```python
    left = scene_layout.content_left(w)
    width = scene_layout.content_width(w)
    right = left + width

    scene_layout.title(ctx, p["title"], w, h)

    # ---- 来源方：一条横带 ----
    src_y, src_h = V_SOURCE_TOP, V_SOURCE_H
    rounded_rect(ctx, left, src_y, width, src_h, 18, COLORS["primary"])
    baseline = src_y + src_h * 0.63
    scene_layout.line(ctx, p["source_label"], left + width * 0.045, baseline,
                      width * 0.45, 52, "#FFFFFF", bold=True)
    scene_layout.line(ctx, p["source_sub"], right - width * 0.045, baseline,
                      width * 0.35, 34, "#FFFFFF", anchor="right")

    # ---- 并行分支：并排一行 ----
    count = int(p["worker_count"])
    gap = width * V_WORKER_GAP_RATIO
    box_w = (width - (count - 1) * gap) / count
    worker_y, worker_h = V_WORKER_TOP, V_WORKER_H
    for i in range(count):
        cx = left + i * (box_w + gap)
        delay = 0.10 * i
        grow = easing.ease_out_cubic(max(0.0, min(1.0, (t - delay) * 3.0)))
        box_h = worker_h * (0.4 + 0.6 * grow)
        rounded_rect(ctx, cx, worker_y, box_w, box_h, 14, COLORS["secondary"])
        label_alpha = max(0.0, min(1.0, (grow - 0.55) / 0.45))
        scene_layout.line(ctx, f"{p['worker_prefix']} {i + 1}", cx + box_w / 2,
                          worker_y + worker_h * 0.52, box_w, 40, "#FFFFFF",
                          alpha=label_alpha, anchor="center")
        # 来源 → 分支：竖着的箭头，从来源带底边落到分支顶边
        arrow(ctx, cx + box_w / 2, src_y + src_h + 12,
              cx + box_w / 2, worker_y - 12, COLORS["accent"], 5, 16)
        # 分支 → 汇聚：从分支底边落到汇聚带顶边
        arrow(ctx, cx + box_w / 2, worker_y + worker_h + 12,
              cx + box_w / 2, V_TARGET_TOP - 12, COLORS["secondary"], 4, 14)

    # ---- 汇聚方：一条横带 ----
    tgt_y, tgt_h = V_TARGET_TOP, V_TARGET_H
    rounded_rect(ctx, left, tgt_y, width, tgt_h, 18, "#DCE1E8")
    baseline = tgt_y + tgt_h * 0.63
    scene_layout.line(ctx, p["target_label"], left + width * 0.045, baseline,
                      width * 0.45, 48, COLORS["primary"], bold=True)
    scene_layout.line(ctx, p["target_sub"], right - width * 0.045, baseline,
                      width * 0.35, 34, COLORS["secondary"], anchor="right")
```

（末尾不再有 `scene_layout.caption(...)`——Task 2 已经删了。）

- [ ] **Step 2：跑测试**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/test_vertical_layout.py tests/test_scene_overlap.py -q
```
Expected: 全绿

- [ ] **Step 3：提交**

```bash
git add -- aiv/pipeline/pyv/scenes/s04_parallel.py
git commit -m "feat(aiv): s04 拓扑竖版重排——链路连成一条"
```

---

### Task 5：守卫加两条底线

**文件**
- 改：`aiv/pipeline/tests/test_vertical_layout.py`

- [ ] **Step 1：加常量与新守卫**

```python
#: 右侧平台 UI 预留（抖音的点赞/评论/分享栏）
RAIL_RIGHT = 120
#: 内容右缘：预留之外
CONTENT_RIGHT = WIDTH - RAIL_RIGHT      # 960
#: 内容区下沿（内容不许掉到它以下——那已经在字幕带之上了）
CONTENT_BOTTOM = 1344
```

新守卫：

```python
@pytest.mark.parametrize("episode,segment", list(_segments()),
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in _segments()])
def test_the_vertical_scene_stays_left_of_the_platform_buttons(episode, segment):
    """竖版画面不许进右侧的点赞/评论/分享栏。

    抖音那一档的按钮栏落在右下角，内容压上去就等于没画。
    """
    path = _module_path(segment.renderer)
    if not _has_vertical_variant(path):
        pytest.skip(f"{path.name} 还没做竖版")

    _, cols = _render_vertical(segment.renderer, segment.params)
    if cols.size == 0:
        pytest.fail(f"{segment.renderer} 的竖版画什么都没画")

    assert cols.max() <= CONTENT_RIGHT, (
        f"{segment.renderer} 有东西跑到 x={cols.max()}，"
        f"右侧按钮栏从 x={CONTENT_RIGHT} 开始——会被压住"
    )
```

把 `test_the_vertical_scene_stays_above_the_subtitle` 的判据从 1393 收到
内容区下沿 1344（1393 是字幕带，1344 更严），并把 docstring 改成：

```python
    """竖版画面不许有墨掉到内容区下沿以下。

    竖版字幕抬到了平台 UI 之上（y=1393），内容下沿取 1344——
    内容掉下去就压在字幕上（横版踩过这个坑，见 `tests/test_scene_layout.py`）。
    """
```

- [ ] **Step 2：跑测试**

```bash
cd F:\ai\blog\aiv\pipeline
E:\dev_tool\venvs\aiv\Scripts\python.exe -m pytest tests/test_vertical_layout.py -q
```
Expected: 全绿（六个期全部场景段都过）

- [ ] **Step 3：提交**

```bash
git add -- aiv/pipeline/tests/test_vertical_layout.py
git commit -m "test(aiv): 竖版守卫加上右侧按钮栏与内容下沿"
```

---

### Task 6：重出竖版成片并验收

**文件**
- 产物（不入库）：`aiv/out/pg-parallel-decode__vertical.mp4`、`aiv/build/pg-parallel-decode__vertical/`
- 改（可选）：`aiv/pipeline/plans/2026-11-15-vertical-douyin-layout-design.md`（补实测结论）

- [ ] **Step 1：出片**

```bash
cd F:\ai\blog\aiv\pipeline
make vertical PY="E:/dev_tool/venvs/aiv/Scripts/python.exe"
```
（`make` 在 Windows 会挑错解释器，必须显式给 `PY=`）

- [ ] **Step 2：抽帧**

```bash
ffmpeg -hide_banner -loglevel error -i F:\ai\blog\aiv\out\pg-parallel-decode__vertical.mp4 -vf "fps=1/4,scale=540:-1" -frames:v 8 <临时目录>/f%02d.png
```

- [ ] **Step 3：逐帧看**

对着设计文档检查：底部只剩字幕、下缘不再有大片空白、右下角文字没进按钮栏、
s03 两组压力并排、s04 链路连成一条。

- [ ] **Step 4：把实测结论补进设计文档**

在设计文档末尾加一节「八、实测结论」，写清楚改前改后的差别与抽帧位置。

- [ ] **Step 5：提交**

```bash
git add -- aiv/pipeline/plans/2026-11-15-vertical-douyin-layout-design.md
git commit -m "docs(aiv): 竖版改造的实测结论"
```

---

## 自查

- **设计文档的要求逐条对上了吗**：右侧 120 ✓（Task 1/5）、内容下沿 1344 ✓（Task 1/5）、
  删说明行 ✓（Task 2）、s03 重排 ✓（Task 3）、s04 重排 ✓（Task 4）、守卫 ✓（Task 5）、
  出片验收 ✓（Task 6）、横版不动 ✓（全局约束）。
- **有没有占位**：没有，每个步骤都给了可粘贴的代码与命令。
- **名字前后一致**：`content_width` / `content_right` / `RAIL_RIGHT` / `CONTENT_BOTTOM`
  在 Task 1 定义、Task 5 在测试里独立定义（测试不依赖实现细节，只钉住数字）。
