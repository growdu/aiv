# 验收 —— 每个模块自己验自己

> **原则**（作者，2026-11-18）：
>
> 「验收应该是各个模块单独验收的，要解耦，而不是合并在一起。
> 做顶层设计的目的就是为了解耦，通过协议和接口来通信，而不是耦合在一起。」
>
> 所以验收分成两件事：
>
> 1. **每个模块自己验自己**——各跑各的套件，一条命令一件事
> 2. **跨模块的只验接口**——验「我读得懂你的东西」，不验「你的实现没变」
>
> 本文件是**模块之间的契约说明**：新人看一眼就知道谁对谁负责、
> 改动之后该跑哪条命令、跑出来的数字该是多少。

---

## 一、模块与接口矩阵

| 模块 | 住在哪 | 验收命令 | 它只该证明 |
| --- | --- | --- | --- |
| 母稿 / review | `docs/` `tools/review-*.py` | `python3 -m pytest tests/ -q` | 母稿层自己的规矩（审校信号、审校记录、摘要起草） |
| 内容单元仓库 | `content/units/` | ——（见下方「内容单元仓库没有自己的套件」） | 单元齐、id 唯一、front matter 合契约 |
| 站点 | `platforms/blog/site/` | `cd platforms/blog/site && python3 -m pytest tests/ -q` | 站点自己构建得出来 |
| publish 契约层 | `publish/` | `cd publish && python3 -m pytest tests/ -q` | 读得懂内容单元 |
| 头条 adapter | `platforms/toutiao/` | `cd platforms/toutiao && python3 -m pytest tests/ -q` | 读得懂内容单元、出包不丢图 |
| 微信 adapter | `platforms/wechat/` | `cd platforms/wechat && python3 -m pytest tests/ -q` | 同上 |
| 视频流水线 | `video/pipeline/` | `cd video/pipeline && python3 -m pytest tests/ -q` | 自己的套件 |

**每条命令都在模块目录里跑。** 这件事是靠两个约定成立的：

- 每个模块目录下有 `conftest.py`，它把**仓库根**与**根 `tools/`** 塞进 `sys.path`
  —— 不然 `from paths import DOCS` 会在别的 cwd 下以「模块不存在」假红。
- **路径常量只有一处**：`tools/paths.py`。测试不再自己拼
  `Path(__file__).resolve().parents[N]`，也不再用 cwd 相对的 `"docs/…"`。

### 内容单元仓库没有自己的套件

`content/units/` 是**构建产物**（`.gitignore` 里的 `/content/units/`），不入库，
因此没有「自己的测试目录」可跑。它的契约由下面两条守住：

- **I1**——站点拿到的那份是逐字节副本（`diff -r`）；
- **I2**——契约层从 `content/units/` 读出的 `content_id` 集合与单元 id 集合相等
  （`publish/tests/test_episode.py` 的集成用例钉着）。

> 计划里曾写「`python3 -m pytest tests/test_content_units.py -q`」——
> **那个文件不存在**，本仓库从来没有内容单元的独立套件。别拿它当基线。

---

## 二、跨模块的接口验收（只三条）

| 接口 | 从 → 到 | 怎么验 | Expected |
| --- | --- | --- | --- |
| I1 内容单元 → 站点 | `content/units/` → `platforms/blog/site/src/content/units/` | `diff -r content/units platforms/blog/site/src/content/units` | 无输出（逐字节副本） |
| I2 内容单元 → publish 契约层 | `content/units/` → `publish/` | 契约层从 `content/units/` 读出的 `content_id` 集合 == 单元 id 集合 | 集合相等 |
| I3 内容单元 → toutiao / wechat | `content/units/` → 两个 adapter | 两个 adapter 默认的文章目录 == 内容单元仓库 | 相等 |

I2 已经有测试钉着：`publish/tests/test_episode.py` 的集成用例
（真跑一遍 sync，比对母稿派生值与产物里的内容单元 id）。

**I3 现在是欠账**——两个 adapter 读的是**站点的副本**，
不是 `content/units/`（Ruling 14：图片还住在站点的 `source/images/`，
解析基准是「文章目录的上一级」，一换就丢图）。
这笔账归**编译器抽取**那个模块（24 任务计划的 Task 1）：
图片落成 `content/units/images/`，同时把解析基准从「文章目录的上一级」
改成显式的图片根。**在那之前，I3 只能验「副本与内容单元逐字节相同」**
（等于 I1），不能验「adapter 直接读内容单元」。
——**这条欠账要写明，不能装作没有。**

---

## 三、每条命令跑什么、Expected 是什么

数字是 2026-11-18 在 `feature/coordinates` 分支上**逐条单独跑**量出来的。
**归位之后，总数必须与合并跑时一致**——少一条就是某条用例消失了，
多一条就是某个目录被收集了两次。

| # | 命令（各自在模块目录里跑） | 跑的是什么 | Expected | 实测 |
| --- | --- | --- | --- | --- |
| 1 | `python3 -m pytest tests/ -q`（仓库根） | 母稿 / review 层：审校信号、审校记录、摘要起草 | 196 passed / 3 skipped | 196 passed / 3 skipped |
| 2 | `cd platforms/blog/site && python3 -m pytest tests/ -q` | 站点：学习流归属、死链、页面齐全（2026-11-18 站点重做后） | 26 passed | 26 passed |
| 3 | `cd publish && python3 -m pytest tests/ -q` | publish 契约层：内容契约、能力模型、发布清单、调度 | 411 passed / 1 skipped | 411 passed / 1 skipped |
| 4 | `cd platforms/toutiao && python3 -m pytest tests/ -q` | 头条 adapter：切片、出包、草稿箱 | 394 passed / 2 skipped | 394 passed / 2 skipped |
| 5 | `cd platforms/wechat && python3 -m pytest tests/ -q` | 微信 adapter：同上 | 504 passed / 1 skipped | 504 passed / 1 skipped |
| 6 | `cd video/pipeline && python3 -m pytest tests/ -q` | 视频流水线：自己的套件 | 1269 passed / 23 skipped / **3 failed** | 1269 passed / 23 skipped / 3 failed |

### 对账

- **站点那 26 个文件**（Task 10 归位的）= **332 条**。
- 归位前它们住在根 `tests/` 里，根 `tests/` 一共 **531 条**（528 passed + 3 skipped）。
- 归位后根 `tests/` 剩 **199 条**（5 个母稿/review 文件：196 passed + 3 skipped），
  站点 `tests/` **332 条**。**199 + 332 = 531**——一条不多、一条不少。
- 计划里写的基线「`tests/` + `publish/tests/` = 939 passed / 4 skipped」也仍然成立：
  归位前 528 + 411 = 939；归位后 (196 + 332) + 411 = 939。

> ⚠️ **站点重做（2026-11-18，hexo → Astro）推翻了上面这组账里的站点那一半。**
> 站点那一套 332 条是 hexo 时代的（渲染、构建、主题、部署工作流的形状），
> 随旧站点一起撤掉了；新的站点套件是 **26 条**（学习流归属、死链、页面齐全）。
> 所以「199 + 332 = 531」这条对账**只对归位那一轮成立**，
> 不是今天的基线——今天的站点基线是表里第 2 行的 **26 passed**。

### 视频流水线那 3 个红（**既有的，不是这次改动造成的**）

| 用例 | 为什么红 |
| --- | --- |
| `video/pipeline/tests/test_publish_copy.py::test_publish_copies_match_the_canonical_docs` | `video/` 正本与 `docs/life/aiv/` 发布副本漂移。**已知**，本轮之前就是红的 |
| `video/pipeline/tests/test_character.py::test_avatar_asset_lives_in_repo` | `video/pipeline/pyv/character.py` 的 `AVATAR_IMAGE` 还指着**搬家前的** `themes/matery/source/medias/avatar.jpg`；主题搬进 `platforms/blog/site/themes/` 之后那个路径没了 |
| `video/pipeline/tests/test_scenes.py::test_s06_uses_personal_avatar_and_no_banned_words` | 同上（`avatar_path()` 返回 `None`） |

后两条是**站点搬家（`bc876e42`）留下的陈旧路径**，不是测试归位造成的。
它们的修法有两条路——把常量改指新路径，或者把头像**搬进视频模块自己的素材目录**
（后者才真正解耦：视频线不该依赖站点的主题）。**这是个设计决定，留给人来定。**

---

## 四、明确不做的验收

- ❌ 整站页面清单快照比对（`/tmp/baseline-pages.txt`）
- ❌ 整站死链快照比对
- ❌ 「全套测试合跑一遍」

理由：这三个都要求**所有模块的产物同时在场**，任何一个模块改动都会让
别的模块的验收变红。而且快照基线放在 `/tmp`，**会被清**——
下一个人拿来比的时候比的是一个空文件，比出来的是「全绿」。

---

## 五、CI 里各模块各跑各的

| 工作流 | 跑哪几个模块 |
| --- | --- |
| `.github/workflows/contracts.yml` | 母稿 / review 层、publish 契约层、头条 adapter、微信 adapter——**每个模块一条 step**，每条带 `if: ${{ !cancelled() }}`，一个模块红不挡住别的模块 |
| `.github/workflows/site.yml` | 站点模块：`verify` job 守约束（内容单元 / 围栏 / 学习流数据），`build` job 出产物 + 跑站点守卫测试（带 `::error::` 注解，不登录也能看到是哪条挂了） |
| `.github/workflows/video-pipeline.yml` | 视频流水线 |

**每个模块只在一个地方跑一次**——不重复收集，也就不会「多出一条用例」。

**验收的粒度 = 模块的粒度。** 谁改了什么，就只有谁的套件会红。
