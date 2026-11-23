# AGENTS.md —— 给 AI 的中央入口

> **这是什么**：AI 协作者进入这个仓库后**第一份**要读的文档。
> 它回答四个问题：仓库是什么、有哪些模块、每条流水线怎么走、我（AI）该读什么不该碰什么。
>
> **给谁读**：AI 协作者。人读 [`README.md`](README.md)（仓库总览）与
> [`review/specs/`](review/specs/)（架构与协议）。
>
> **维护规则**：模块增删、流水线阶段变化、缝的位置移动时，**必须**同步这份文件——
> 它是仓库对 AI 的唯一契约。

---

## 一、仓库是什么

**一个内容生产线**：两条流水线（文档流、视频流）、六个第三方平台（站点 / 公众号 / 头条号 / B站 / 视频号 / 抖音）、
一个共享规则层、一份审校判据、一套验收矩阵。

**核心原则**：内容与发布解耦。内容是**母稿**（`docs/`、`video/`），发布是**逐篇出包**（`platforms/`）。
两者之间只有**缝**（`content/units/`、`capability.toml`、`rules/urls.json`、验收命令）能跨层说话，
**层间零 import**——这是硬规矩。

---

## 二、模块地图

| 模块 | 一级目录 | 二级目录（如有） | 它拥有 | 验收命令 |
|------|----------|------------------|--------|----------|
| **草稿层** | `drafts/` | —— | 在改的稿子（未过审） | ——（无测试，靠 `review/` 守） |
| **母稿层** | `docs/` | —— | 已过审的文档母稿 | `cd . && python3 -m pytest tests/ -q`（编译器在根 `tests/` 里测） |
| **视频母稿层** | `video/` | `episodes/`、`pipeline/`、`brand/`、`character/`、`music/`、`voice/`、`scripts/`、`review/` | 视频生产全链 | `cd video/pipeline && python3 -m pytest tests/ -q` |
| **审校层** | `review/` | `specs/`、`plans/`、`scope/` | 什么算「已过审」的判据 | ——（判据是文档，不是测试） |
| **编译器** | `tools/` | —— | `docs/` → `content/units/`；`video/` → `content/units/video/` | `cd . && python3 -m pytest tests/ -q`（编译器在根 `tests/` 里测） |
| **站点** | `platforms/blog/` | `site/`（hexo+matery 工程）、`docs/` | 站点平台 adapter + hexo 构建链 | `cd platforms/blog/site && python3 -m pytest tests/ -q` |
| **平台适配层** | `platforms/` | `wechat/`、`toutiao/`、`bilibili/`、`channels/`、`douyin/` | 五个第三方平台 adapter | 各自目录内 `python3 -m pytest tests/ -q` |
| **契约与发布层** | `publish/` | `publishkit/`、`spec/`、`deploy/`、`plans/` | 能力模型、内容契约、发布清单、调度、规格 | `cd publish && python3 -m pytest tests/ -q` |
| **发布执行器** | `browser/` | `browser/`、`scripts/`、`selectors/`、`docs/` | 浏览器自动化（只服务没有公开 API 的平台） | `cd browser && python3 -m pytest tests/ -q` |
| **共享规则** | `rules/` | —— | 跨模块共享的规则（`urls.json`） | ——（读取器各自有测试） |
| **验收矩阵** | `acceptance/` | —— | 各模块的验收命令与实测数字 | ——（文档，不是代码） |
| **仓库根测试** | `tests/` | —— | 身份守卫、编译器、退出码、内容契约、死路径守卫 | `cd . && python3 -m pytest tests/ -q` |

**跳过**（AI 不读不改）：`content/units/`（构建产物）、`node_modules/`、`.venv/`、`__pycache__/`、
`platforms/blog/site/themes/`（第三方主题）、`.remember/`（会话记忆）、`.worktrees/`（并行工作区）。

---

## 三、两条流水线

### 3.1 文档流（drafts → review → docs → platforms）

```
drafts/          稿子在改，没过审
  │
review/          审校：什么算「已过审」的判据（specs/）
  │
docs/            母稿层：唯一的内容真相
  │
tools/           编译器：docs/ → content/units/（只拷贝 front matter，正文一字不改）
  │
platforms/blog/site/  站点：content/units/ → source/_posts/ + source/docs/（hexo）
platforms/wechat/    公众号：content/units/ → 出包
platforms/toutiao/   头条号：content/units/ → 出包
```

**关键缝**：`content/units/`（构建产物，不入库，CI 里现编）、`rules/urls.json`（地址形状）、
各平台的 `capability.toml`（限额、自动化档位、审核要求）。

### 3.2 视频流（drafts → review → video → platforms + out）

```
drafts/          稿子在改，没过审
  │
review/          审校：视频线自己的判据
  │
video/           视频母稿层：
  │              episodes/<系列>/<合集>/<文档>/<档位>/  ← 期目录
  │              brand/character/music/voice/          ← 素材与配置
  │              pipeline/pyv/                          ← 渲染引擎
  │
out/<系列>/<合集>/<文档>/<档位>.mp4  成片（不入库）
  │
content/units/video/<期号>.md        视频内容单元（编译器生成）
  │
publish/publishkit/                  契约层：出包、调度、快照
  │
platforms/bilibili/ channels/ douyin/ 三个视频平台 adapter
  │
platforms/<平台>/outbox/<系列>-<合集>-<文档>-<档位>__<平台>.json  发布快照（入库）
```

**关键缝**：期目录（`video/episodes/`）、`video/config.toml`（身份与素材路径）、
`platforms/<平台>/outbox/*.json`（扁平快照目录，每个视频平台各一份）、`content/units/video/`（视频内容单元）。

---

## 四、AI 协作者的行为准则

### 4.1 必读

进入仓库后，**按顺序读**：

1. **本文件**（`AGENTS.md`）——中央入口
2. **`README.md`**（仓库总览）
3. **要改的模块的 `README.md`**（如改微信 adapter 就读 `platforms/wechat/README.md`）
4. **要改的模块的契约**（如改发布逻辑就读 `publish/spec/00-架构设计.md`）
5. **`review/specs/2026-11-19-整体架构与模块边界.md`**（架构现状与欠账）

### 4.2 必守

- **层间零 import**：平台层不 import 契约层，契约层不 import 平台层，根 `tools/` 不 import 任何平台层。
  两层之间只通过**缝**说话（`content/units/`、`capability.toml`、`rules/urls.json`）。
- **身份缝**：框架源码里不许出现站名（`tests/test_instance_identity.py` 守着）。值全在使用者一侧（`site.json`、`config.toml`）。
- **验收按模块拆开**：谁改了什么，只有谁的套件会红。跨模块只验接口，不验实现。
- **改动稿先落 `drafts/`**：改 `docs/` 或 `video/` 里已有的内容，先改 `drafts/` 那份，过审再覆盖。
  框架代码（`tools/`、`platforms/`、`publish/`）不受此限——它们是代码，不是内容。

### 4.3 禁碰

- **`content/units/`**：构建产物，不入库，CI 里现编。改它没用，下次编译就覆盖。
- **`platforms/blog/site/themes/`**：第三方主题（hexo matery），不是本仓库的代码。
- **`.remember/`、`.worktrees/`**：会话记忆与并行工作区，不是仓库的一部分。
- **`out/`、`build/`**（视频线）：成片与片段产物，不入库。

### 4.4 改之前先跑

- **改根 `tools/`**：先跑 `cd . && python3 -m pytest tests/ -q`（身份守卫、编译器、退出码）
- **改 `publish/`**：先跑 `cd publish && python3 -m pytest tests/ -q`（契约层）
- **改某个平台 adapter**：先跑 `cd platforms/<平台> && python3 -m pytest tests/ -q`
- **改站点**：先跑 `cd platforms/blog/site && python3 -m pytest tests/ -q`
- **改视频线**：先跑 `cd video/pipeline && python3 -m pytest tests/ -q`

---

## 五、用户 → AI → 本项目的接入接口

**用户（协作者）**通过**自然语言**或**Claude Code**与 AI 对话：

- 「加一篇讲 PostgreSQL 基操的文档」→ AI 读 `drafts/README.md`、`review/scope/`，在 `drafts/` 下建目录与母稿，
  过审后覆盖 `docs/`，跑编译器，跑站点测试。
- 「把这篇发到公众号」→ AI 读 `platforms/wechat/README.md`、`publish/spec/`，跑编译器，跑微信 adapter 的出包命令，
  检查出包目录，报告给用户。
- 「改一下站点的配色」→ AI 读 `platforms/blog/site/README.md`、`platforms/blog/site/themes/matery/`，
  改主题文件，跑 `npm run build`，报告构建结果。

**视频流（AIV 品牌系列）**同样用自然语言驱动，但**没有登记表、坐标就是接口**：

- 「给 AIV 加一期讲 PostgreSQL 行锁的短视频」→ AI 读 [`video/episodes/README.md`](video/episodes/README.md)，在
  `video/episodes/AIV/<合集>/<文档>/<档位>/` 建四层目录（建目录即登记），放 `口播稿.md`（front matter 记 `episode`/`episode_number`/`tier`）
  与 `contract.json`（其 `episode` 记**四层期路径**），再跑 `video/voice/scripts/synthesize_narration.py` 合成旁白。
- 「把这期出片（或出个竖版给抖音）」→ AI 进 `video/pipeline/`，先 `make EP=<系列>/<合集>/<文档>/<档位> align`，再
  `make EP=... all`（抖音竖版用 `vertical`、无品牌导流版用 `nobrand`）。**忘了 `EP=` 会退出 2**，不会拿空路径跑。
- 「这期发 B站 / 视频号 / 抖音」→ adapter 是 `manual` 档：AI 只 `python3 -m <平台>.cli package <期号>` 出包并报告，
  **上传与点发表在人工手里**（可逆的 prepare / 不可逆的 submit 见 [`browser/README.md`](browser/README.md)）。

> ⚠️ **现状**：AIV 系列当前是**空壳**——`video/episodes/` 下只有 `README.md`，没有 `AIV/` 目录。
> 所以现在能交互的是「建一期 / 跑空流水线 / `make doctor` 查环境」，**还出不了真成片**：
> 先按 `make doctor` 配好环境与素材（[`video/config.toml`](video/config.toml)），并由使用者建出入库的期目录。

**AI**通过**模块 README** 与**契约文档**理解边界，通过**验收命令**验证改动，通过**缝**（`content/units/`、`capability.toml`、
`rules/urls.json`）跨模块通信，**不 import 其他模块的代码**。视频流的坐标口径在 `publish/publishkit/episode.py` 与
`video/pipeline/pyv/episodes.py` **两处对齐**，改一处两处一起改。

---

## 六、维护这份文件

- 模块增删时，**必须**更新 §二（模块地图）。
- 流水线阶段变化时，**必须**更新 §三（两条流水线）。
- 缝的位置变化时，**必须**更新 §四（AI 协作者的行为准则）。
- 验收命令变化时，**必须**更新 `acceptance/README.md`（各模块的实测数字）。

**这份文件是仓库对 AI 的唯一契约**——它说谎，AI 就会走错路。
