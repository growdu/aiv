# 视觉词汇扩容 + 跨机像素一致：设计

**日期**：2026-11-16
**范围**：`aiv/pipeline/pyv/`（layout / components / fonts）、`aiv/pipeline/tests/fixtures/`、
`aiv/pipeline/scripts/`、`.github/workflows/aiv-pipeline.yml`
**触发**：能力分析发现三个短板——视觉词汇窄、跨机像素不一致、像素基准只覆盖 23%。

---

## 零、三条实测事实（设计的全部依据）

这三条都是本轮实测出来的，不是推断。**设计必须建立在它们之上**，尤其是事实 2
推翻了上一轮结论里的一句话。

### 事实 1：cairo 在 macOS 上走 CoreText，不认 fontconfig 目录

把子集字体放进只有 fontconfig 能看到的目录后：

| 检查 | 结果 |
| --- | --- |
| `fc-list` | 找得到 `AIV Sans CJK SC` |
| cairo `select_font_face` | 找不到，宽度回落到 `.notdef` 的 98.83 |

`otool -L` 显示 cairo 同时链接了 fontconfig 与 CoreText，但 **toy 字体的实际解析
走 CoreText**；`CAIRO_DEBUG_FONT_BACKEND` 在这个构建上不生效（设成非法值也不报错）。

**影响**：仓库内置的字体**必须装进 OS 字体目录**才能被 cairo 看见——
macOS `~/Library/Fonts/`（CoreText 自动拾取），Linux `~/.local/share/fonts/` + `fc-cache -f`。

### 事实 2：跨 OS 逐像素一致做不到；能做到的是布局一致

同一字体文件（`NotoSansCJKsc-Regular.otf`），CoreText（cairo）与 FreeType（PIL）的
步进宽度：

| 字号 | cairo（CoreText） | PIL（FreeType） | 差值 |
| --- | --- | --- | --- |
| 24 | 251.448 | 251.000 | +0.448 |
| 40 | 419.080 | 419.000 | +0.080 |
| 68 | 712.436 | 712.000 | +0.436 |

步进宽度一致（差 ≤ 0.45px，PIL 侧取整），但**栅格化器不同 → 像素不同**。

**修正上一轮的结论**：上一轮说「字体入库 → 跨机逐像素一致成立」，这是错的。
正确的目标分三层：

| 层次 | 跨机可达？ | 保证什么 |
| --- | --- | --- |
| **布局一致** | ✅ 成立 | 同一份字体文件 → 同一组 advance → `fit_size` 收出同一个字号 → 文字不会出框 |
| **同平台逐像素一致** | ✅ 成立 | macOS↔macOS、Linux↔Linux |
| **跨平台逐像素一致** | ❌ 不成立 | CoreText ≠ FreeType，不再追求 |

### 事实 3：`text_path` + `path_extents` 给出字形轮廓包围盒，与栅格化无关

`tests/test_scene_overlap.py` 用它做元素级判据（字压字 / 箭头穿字），
**在 Linux CI 上一直是绿的**——说明轮廓量跨后端稳定。

**影响**：跨机可比的守卫应该比**轮廓**与**坐标**，不是比像素。

---

## 一、任务 1：像素基准补全到全部 36 段

### 现状

`tests/fixtures/scene_baseline.json` 只有 **18 帧**（`pg-parallel-decode` 的 6 段 ×
3 个时刻），而目录里有 **26 个场景模块**、六期契约里共 **36 个视觉段**。
覆盖率 23%。

`tests/test_scene_overlap.py::test_every_scene_module_is_covered` 已经钉住了
「26 个模块」，但那是**元素级**守卫；**逐像素**基准只覆盖 6 段——新增一个场景模块，
基准守卫压根扫不到它，改坏画面没人拦。

### 改法

**基准的粒度从「模块」改成「段」。**

同一个渲染器在不同期用的 `params` 不同 → 画面不同 → 哈希不同。所以基准不能按模块
存一份，必须按**段**存：`(期号, 段 id, 渲染器, 时刻)` → 哈希。

| | 现在 | 改后 |
| --- | --- | --- |
| 帧数 | 18 | 36 段 × 3 时刻 = **108** |
| 覆盖段数 | 6 / 36 | **36 / 36** |
| 覆盖模块数 | 6 / 26 | **26 / 26** |

**连带改动**：

1. `scripts/capture_scene_baseline.py`：从「只抓默认契约」改成「遍历六期契约的
   全部 36 段 × 3 时刻」。
2. `tests/test_contract.py` 的基准守卫：从「参数化到单期 contract fixture」改成
   「遍历六期」。
3. `tests/test_contract.py:315` 那条 `assert len(baseline["frames"]) == 18`
   改成**从六期契约推导**（`len(segments) * 3`），而不是写死数字——以后加期
   不用再改这里，但**漏抓会红**。
4. 新增一条覆盖声称守卫：`基准里的段集合 == 六期契约里的段集合`，
   照 `test_scene_overlap.py` 的写法（集合相等，不是子集）。

### 验收

- 新增一个场景模块但不入契约 → 基准测试红（覆盖声称被钉住）。
- 任意一段的画面被改动 → 对应的那一条红。

---

## 二、任务 2：版式层（横版补齐）+ 组件层

### 2a. 现状

- `pyv/draw.py`：5 个原语（`rounded_rect` / `stroke_rect` / `arrow` / `text` / `text_width`）。
- `pyv/scene_layout.py`：**只有竖版**（模块 docstring 自述「竖版（1080×1920）的共用版式件」）。
- 26 个场景模块里 **998 处** `w * 0.07` / `h * 0.145` 这类硬编码比例。
- 同一套排布逻辑被复制多份：`chip_layout` / `chip_slots` / `chip_slots_vertical` /
  `chip_layout_vertical` / `node_positions` / `layer_count` / `landing_slots_vertical` …
  「等分一排块」在 s02_serial、s03_cores、s04_spill 里各写一遍。

### 2b. 横版版式层：新建 `pyv/layout.py`

```python
layout.H   # 横版 1920×1080
layout.V   # 竖版 1080×1920
```

每个画幅一份版式常量集合 + 一份绘制入口（`title` / `line` / `content_width` /
`content_left` / `content_right` / `content_top` / `content_bottom`）。

**关键约束：这一层是「搬运」，不是「规范化」。**

现状横版的取值本来就是混的（`w*0.06` 出现 56 次、`w*0.07` 出现 13 次）。
把它们统一成一个值 = 改画面 = 破坏像素基准。所以：

- 常量的**值必须精确等于现状的取值**；
- 历史上不同的取值收成**不同的常量名**（而不是抹平成一个）；
- 迁移 = 把字面量换成同值常量 → **像素不变**。

收益不是"变整齐"，而是：新场景作者从常量表里挑值，而不是随手写 `h * 0.145`；
历史差异被固化成**有名字的**常量。

`scene_layout.py` 保留为薄兼容层，转发到 `layout.V`——避免一次改 26 个文件。

### 2c. 组件层：新建 `pyv/components.py`

组件只负责「画一个东西」，位置由调用方给（或由 layout 给默认）。组件内不写死文案
（`tests/test_contract.py` 的 AST 守卫会抓住）。

| 组件 | 语义 | 取代的重复 |
| --- | --- | --- |
| `block()` | 圆角块 + 居中/左对齐文字（文字走 `fit_size`） | 场景里手写的三行 `rounded_rect` + `text` + 收字号 |
| `block_row()` | 等分一排块 | s02_serial 的 5 块、s03_cores 的 4+3、s04_spill 的 chips |
| `band()` | 整幅色带 | s04_parallel 的 reader / walsender 带 |
| `matrix()` | 网格 | s03_lock_modes / s04_lock_matrix |
| `arrow_v()` / `arrow_h()` | 竖向 / 横向箭头 | 场景里自己算坐标的箭头 |

每个组件**必须同时给横竖两套**（或用 layout 命名空间参数化）。

### 2d. 迁移范围：**3 个代表场景**

按用户决定：**建层 + 迁 3 个代表场景**，其余 23 个增量迁。

选的三个正是重复源头，也各自覆盖一类组件：

| 场景 | 覆盖组件 | 为什么选它 |
| --- | --- | --- |
| `s02_serial` | `block` / `block_row` / `arrow_v` | 积压块排 + 线程块 + 接收方，最基本的块布局 |
| `s03_cores` | `block_row` | 核阵列 + 两列并排块，「等分一排」的原型 |
| `s04_parallel` | `band` / `arrow_v` | reader/worker/walsender 三带 + 箭头 |

**硬约束：迁移后这 3 个场景的画面必须逐像素不变。**
由任务 1 的基准守住——迁移前基准全绿，迁移后仍全绿才算过。

### 2e. 测试

1. **组件单元测试**：给定参数 → 产出确定的墨迹范围（用轮廓量，不用逐像素，
   因为组件的绝对位置随调用方变）。
2. **组件的「字不出框」测试**：组件内文字的轮廓必须落在块内。
3. **迁移等价性**：任务 1 的基准守卫（3 个场景迁移后仍全绿）。
4. **组件不许写死文案**：AST 扫描 `components.py`，文案字面量必须来自 params。

---

## 三、任务 3：字体子集入库 + 跨机布局指纹守卫

### 3a. 字体子集入库

**源**：Noto Sans CJK SC（SIL OFL 1.1，**允许随软件分发**）。
**必须从上游可复现的源下载**，不能从本机 `~/Library/Fonts` 拿——那是本机状态，
不可复现。上游：`https://github.com/notofonts/noto-cjk`。

**钉住**：版本号 + sha256 写进 `aiv/pipeline/assets/fonts/SOURCE.md`，
照 `aiv/music/` 的授权台账模式（仓库已有这个模式：`library.json` + `tracks/`）。

**子集字符集从仓库自动提取，不手工维护**（手工维护必然漂）：

- 提取来源：六期契约 JSON 的全部字符串 + 六份字幕稿 + 场景/渲染层的字符串字面量
  + 基础 ASCII + 常用标点
- 本轮实测：**1251 个字符**
- 提取脚本：`aiv/pipeline/scripts/build_font_subset.py`

**体积**：实测 Noto Sans CJK SC 16.4MB → 子集 **632KB**。

**族名改写为 `AIV Sans CJK SC`**（唯一名 → 不与系统任何字体冲突，
避免 fontconfig 在系统字体与内置字体之间二选一）。

**缺字守卫（必做）**：一条测试断言**子集覆盖当前仓库用到的每一个字符**。
新一期加了新字而没重跑子集脚本 → CI 红。这条守卫让「手工维护」不可能漂。

### 3b. 安装机制

新脚本 `aiv/pipeline/scripts/install_font.py`（跨平台、幂等）：

| 平台 | 装到 | 额外步骤 |
| --- | --- | --- |
| macOS | `~/Library/Fonts/` | CoreText 自动拾取 |
| Linux | `~/.local/share/fonts/` | `fc-cache -f` |

已安装且 sha256 相同 → 跳过。

`doctor` 增加一条：检测 `AIV Sans CJK SC` 是否可解析；不可解析 → 给出安装命令
（沿用现有 `INSTALL_HINT` 的模式）。

`fonts.py` 的候选顺序：

1. `AIV_FONT_FAMILY` 环境变量（保留，最高优先级）
2. **内置 `AIV Sans CJK SC`**（装了才用）
3. PingFang SC（macOS 回退，保留兼容）
4. Noto Sans CJK SC / 思源黑体（Linux 回退）
5. fontconfig 兜底

### 3c. 跨机布局指纹守卫

**比什么**：每个场景模块 × 每个画幅 × 5 个时刻（0.0 / 0.25 / 0.5 / 0.75 / 1.0），
记录画面里每个文字元素的：

| 量 | 跨机来源 | 容差 | 依据 |
| --- | --- | --- | --- |
| 落笔坐标 (x, y) | 场景代码，纯算术 | ±0.01px | 与字体无关 |
| 字号 | `fit_size` 收敛值 | ±1.0 | 实测步进差 ≤0.45px |
| 步进宽度 `x_advance` | 字体文件 hmtx | ±1.0 | 同上 |
| 轮廓包围盒 `path_extents` | 字形轮廓（**与栅格化无关**） | ±2.0 | 事实 3 |

**容差写死字面量**，不从被测代码 import（守卫阈值自证 = 永远绿）。
每条容差都要写清「这个数字为什么是这个数」。

**fixture**：`tests/fixtures/layout_fingerprint.json`，约 260 条
（26 模块 × 2 画幅 × 5 时刻），每条是一段紧凑的 JSON。预计 ~100KB。

**它能抓什么**：换字体导致的收字号变化、元素位置漂移、文字出框。
**它抓不到什么**：颜色变了、间距挪了 2px、某个字形画错了形状——
那些由逐像素基准（任务 1，同平台）负责。

### 3d. 逐像素基准的定位修正

因为事实 2，**基准不可能在 macOS 与 Linux 之间互比**。

**决定**：基准明确为「作者本机的逐像素回归锁」，macOS 本地跑；
Linux CI 靠布局指纹守卫跨机版式。

**不**做双份（macOS + Linux）基准——那要求维护者额外准备一台 Linux 机器
来跑一次抓取脚本，运维成本高于收益。

CI 侧仍然装上内置子集字体（这样 Linux 上的布局指纹与 macOS 同字体、同 advance），
但 `fonts-noto-cjk` 降级为兜底。

### 3e. macOS 换字体的后果（用户已知并接受）

- 新成片与旧成片**像素不同**（字形从 PingFang 变思源黑体），**内容一字不变**。
- 像素基准要**重录**（`capture.font` 变成 `AIV Sans CJK SC`）。
- 文档要更新：
  - `aiv/上机指南.md` §三（字体差异那一节）
  - `aiv/形象与音色规范.md` §1.3（「视觉等价」的表述）
  - `aiv/README.md`（跑一遍那节）

---

## 四、提交边界

按「每个子模块完成立即 commit、每次 commit 配套测试且通过、每个 commit 在干净
检出上独立跑通全量」这条规矩，切成 5 笔：

| # | 提交 | 内容 | 配套测试 |
| --- | --- | --- | --- |
| 1 | `feat(aiv): 像素基准覆盖全部 36 个视觉段` | 抓基准脚本 + 基准守卫 + 覆盖声称 | 基准覆盖/推导条数 |
| 2 | `refactor(aiv): 版式层落地——横版常量入表` | `layout.py` + `scene_layout` 兼容层 | 版式常量与现状等值 |
| 3 | `feat(aiv): 组件层与三个代表场景迁移` | `components.py` + 迁 s02/s03/s04 | 组件单测 + 迁移后基准全绿 |
| 4 | `feat(aiv): 字体子集入库与安装机制` | 子集 + SOURCE.md + 安装脚本 + fonts.py + doctor + 重录基准 | 缺字守卫 + 素材跟踪守卫 |
| 5 | `feat(aiv): 跨机布局指纹守卫` | 指纹采集 + fixture + 比对 | 指纹覆盖 + 容差合理性 |

每笔提交后用**隔离 worktree** 跑一遍全量测试，确认该 commit 自身是绿的
（不依赖后续 commit 才引入的文件）。

---

## 五、不做什么

- 不做「跨平台逐像素一致」——事实 2 证明做不到，不假装能做到。
- 不要求维护者准备第二台 Linux 机器来录基准。
- 不改横版的现有取值（版本层是搬运不是规范化）。
- 不改任何一期的文案、契约、旁白。
- 不动 `h3` 那条路（无生成命令、契约没用）——它是独立议题，优先级在组件层之后。
