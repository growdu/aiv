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
| 母稿 / review | `docs/` `tools/review-*.py` | `python3 -m pytest tests/ -q` | 母稿层自己的规矩（审校信号、审校记录） |
| 内容单元仓库 | `content/units/` | ——（见下方「内容单元仓库没有自己的套件」） | 单元齐、id 唯一、front matter 合契约 |
| 站点 | `platforms/blog/site/` | `cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q` | 站点自己构建得出来 |
| publish 契约层 | `publish/` | `cd publish && python3 -m pytest tests/ -q` | 读得懂内容单元 |
| 头条 adapter | `platforms/toutiao/` | `cd platforms/toutiao && python3 -m pytest tests/ -q` | 读得懂内容单元、出包不丢图 |
| 微信 adapter | `platforms/wechat/` | `cd platforms/wechat && python3 -m pytest tests/ -q` | 同上 |
| 抖音 adapter | `platforms/douyin/` | `cd platforms/douyin && python3 -m pytest tests/ -q` | 同上 |
| B站 adapter | `platforms/bilibili/` | `cd platforms/bilibili && python3 -m pytest tests/ -q` | 同上 |
| 视频号 adapter | `platforms/channels/` | `cd platforms/channels && python3 -m pytest tests/ -q` | 同上 |
| 视频流水线 | `video/pipeline/` | `cd video/pipeline && python3 -m pytest tests/ -q` | 自己的套件 |
| 发布执行器 | `browser/` | `cd browser && python3 -m pytest tests/ -q` | 浏览器流程的形状（真发不发） |

**每条命令都在模块目录里跑。** 这件事是靠两个约定成立的：

- 每个模块目录下有 `conftest.py`，它把**仓库根**与**根 `tools/`** 塞进 `sys.path`
  —— 不然 `from paths import DOCS` 会在别的 cwd 下以「模块不存在」假红。
- **路径常量只有一处**：`tools/paths.py`。测试不再自己拼
  `Path(__file__).resolve().parents[N]`，也不再用 cwd 相对的 `"docs/…"`。

### 内容单元仓库没有自己的套件

`content/units/` 是**构建产物**（`.gitignore` 里的 `/content/units/`），不入库，
因此没有「自己的测试目录」可跑。它的契约由下面三条守住：

- **I2**——契约层从 `content/units/` 读出的 `content_id` 集合与单元 id 集合相等；
  **有测试钉着了**——编译器自己住在仓库根套件的 `tests/test_content_units.py`
  里（§五 第 9 条还账：真跑一遍 `tools/build-content-units.py`，比对两边集合）；
- **I3**——两个 adapter 默认的文章目录 == 内容单元仓库；**已还**（§五 第 3 条：
  adapter 默认目录 == `content/units/`，不再各读站点的副本）；
- **I4**（新）——站点读到的那批文章 == 内容单元仓库。

---

## 二、跨模块的接口验收（只三条）

| 接口 | 从 → 到 | 怎么验 | Expected |
| --- | --- | --- | --- |
| I2 内容单元 → publish 契约层 | `content/units/` → `publish/` | 契约层从 `content/units/` 读出的 `content_id` 集合 == 单元 id 集合 | 集合相等（有测试钉着：`tests/test_content_units.py` 在根套件里） |
| I3 内容单元 → toutiao / wechat | `content/units/` → 两个 adapter | 两个 adapter 默认的文章目录 == 内容单元仓库 | 相等（**已还**：adapter 默认目录 == `content/units/`） |
| I4 内容单元 → 站点 | `content/units/` → `platforms/blog/site/` | 站点 `tools/build-posts.py` 读的文章目录 == 内容单元仓库 | 相等 |

**I1 作废了**（2026-11-20，站点换成 hexo 那轮）——原来那条是
「站点拿到的那份是逐字节副本」（`diff -r content/units platforms/blog/site/src/content/units`）。
**副本没有了**：站点与两个 adapter 都**直接读 `content/units/`**。
副本是字节级重复，而仓库早就把它记成欠账——这轮把它兑现了。

**I3 已还**（§五 第 3 条）——两个 adapter 现在直接读 `content/units/`，
不再读站点的副本。图片由编译器拷进 `content/units/images/`，
解析基准是显式的图片根；adapter 默认文章目录 == `content/units/`，
可以真验「adapter 直接读内容单元」。

---

## 三、每条命令跑什么、Expected 是什么

数字是 **2026-11-22** 合并 `feature/interfaces-debts`（站点以 hexo+matery 为准）
之后**逐条单独跑**量出来的。
**归位之后，总数必须与合并跑时一致**——少一条就是某条用例消失了，
多一条就是某个目录被收集了两次。

| # | 命令（各自在模块目录里跑） | 跑的是什么 | Expected | 实测 |
| --- | --- | --- | --- | --- |
| 1 | `python3 -m pytest tests/ -q`（仓库根） | 母稿 / review 层：审校信号、审校记录、身份守卫 | 114 passed | 114 passed |
| 2 | `cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q` | 站点：身份通用性、地址形状、学习流归属、死链、页面齐全、首页一屏 | 86 passed | 86 passed |
| 3 | `cd publish && python3 -m pytest tests/ -q` | publish 契约层：内容契约、能力模型、发布清单、调度、退出码 | 348 passed / 1 skipped | 348 passed / 1 skipped |
| 4 | `cd platforms/toutiao && python3 -m pytest tests/ -q` | 头条 adapter：切片、出包、草稿箱 | 399 passed / 2 skipped | 399 passed / 2 skipped |
| 5 | `cd platforms/wechat && python3 -m pytest tests/ -q` | 微信 adapter：同上 | 521 passed / 1 skipped | 521 passed / 1 skipped |
| 6 | `cd platforms/douyin && python3 -m pytest tests/ -q` | 抖音 adapter：出包不带上站外地址、无品牌导流版 | 119 passed | 119 passed |
| 7 | `cd video/pipeline && python3 -m pytest tests/ -q` | 视频流水线：自己的套件 | 1060 passed / 60 skipped | 1060 passed / 60 skipped |
| 8 | `cd platforms/bilibili && python3 -m pytest tests/ -q` | B站 adapter：出包、条件必填、状态回填 | 77 passed | 77 passed |
| 9 | `cd platforms/channels && python3 -m pytest tests/ -q` | 视频号 adapter：同上 | 59 passed | 59 passed |
| 10 | `cd browser && python3 -m pytest tests/ -q` | 发布执行器：浏览器流程的形状 | 1 failed / 99 passed / 64 skipped | 1 failed / 99 passed / 64 skipped |

### 数字为什么变过（别拿旧基线来对账）

| 时间 | 根 | 站点 | publish | toutiao | wechat | douyin | video | bilibili | channels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-18（归位那轮） | 196 / 3 skip | 26 | 411 / 1 skip | 394 / 2 skip | 504 / 1 skip | 119 / 12 skip | 1269 / 23 skip / 3 red | 68 | 55 |
| 2026-11-19（清库那轮） | 81 | 51 / 1 skip | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1052 / 60 skip | 68 | 55 |
| 2026-11-19（视频线不发布那轮） | 81 | 51 / 1 skip | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1050 / 60 skip | 68 | 55 |
| 2026-11-20（站点换 hexo 那轮） | 81 | 79 | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1050 / 60 skip | 68 | 55 |
| 2026-11-19（还 §五 欠账那轮） | 114 | 59 / 1 skip | 348 / 1 skip | 399 / 2 skip | 521 / 1 skip | 119 | 1060 / 60 skip | 77 | 59 |

> 口径说明：站点换 hexo 那轮与还 §五 欠账那轮在两条分支上**并行**发生。
> 合并后站点以 hexo+matery 为准：hexo 的 79 条 + 还欠账那轮里仍适用的
> URL 形状、图片基准、身份守卫共 7 条，合起来 **86**（§三 第 2 行）。

### 还 §五 欠账那轮（2026-11-19 晚）

把 [整体架构与模块边界](../../review/specs/2026-11-19-整体架构与模块边界.md) §五 列的 1~4、9~14
条接口欠账按 §七 的拍板全部还掉。各套件变动：

| 套件 | 变动 | 为什么 |
| --- | --- | --- |
| 根 | 81 → 114 | 新增身份守卫 `tests/test_instance_identity.py`（§五 第 12 条：全仓库扫实例身份）；编译器抽取的 `tests/test_content_units.py` 钉住「I2：契约层读出的 `content_id` 集合 == 单元 id 集合」（§五 第 9 条）；外加退出码、内容契约、能力模型的守卫 |
| 站点 | 26 → 59 | URL 形状改读共享规则 `rules/urls.json` 之后的守卫（§五 第 10 条：落地地址与站点逐字相同）；分类归档地址改 `/docs/<id>/` 的守卫（§七 第 3 条） |
| publish | 338 → 348 | 退出码语义（§五 第 14 条：`publishkit/exit_codes.py` + `tests/test_exit_codes.py`）、落地地址派生（§五 第 10 条）的守卫；`test_video_publish_contracts.py` 的字幕守卫从空转（指一个从来没过的路径）改成真扫 `video/episodes/` |
| toutiao | 394 → 399 | adapter 默认文章目录接上内容单元仓库、退出码与分类归档地址按新口径的守卫 |
| wechat | 504 → 521 | `WX_SOURCE_URL` → `SITE_URL`（缝 3 取值）、分类归档地址改 `/docs/<id>/` 之后的守卫补齐 |
| douyin | 115 → 119 | 成片分目录（`out/<系列>/<合集>/<文档>/<档位>.mp4`）、期身份四层、退出码的守卫 |
| video | 1050 → 1060 | 品牌文案搬进 `config.toml`（缝 3）、成片分目录、`episodes.cut_path` 等的守卫 |
| bilibili | 68 → 77 | 成片分目录、storyboard 真路径（字幕守卫不再空转）、期身份四层的守卫 |
| channels | 55 → 59 | 同 bilibili |

> 这一轮**没有一条用例是因为逻辑坏了而红**——全是新增守卫 + 把空转的守卫接上真路径。

变红的是**被测对象没了**，不是逻辑坏了：

- 根套件 196 → 81：站点那一套 332 条早已归位；这轮又删掉了
  几批**测已删脚本**的用例（`tools/draft-descriptions.py` 等），
  并把**依赖仓库内容**的用例改成在 `tmp_path` 里造语料。
- publish 411 → 338：删掉的是测 hexo 时代 `sync-hexo.py` 的集成用例；
  母稿相关的用例改成在临时目录里造稿子，不再依赖仓库里曾经有过的内容。
- 站点 26 → 51 → 79：站点重做之后补的守卫（学习流归属、围栏、死链）；
  换 hexo 那轮又补了一批（身份通用性、地址形状、目录页、首页一屏、
  mermaid 渲染、分类退休、`<nav>` 误用、`/all/` 跳转、性能按需加载），
  同时删掉了 Astro 时代的活动账本与占位符那几套。
- video 1269 → 1052：视频线清空重来，期目录的用例随内容一起少了；
  清库那轮剩的 1 条红（品牌文案与文档不同步）也补掉了——文案搬进
  `video/config.toml` 之后，那条用例改成钉「文案来自配置键」这条**关系**，
  不再逐字比对文档里的一份副本。
- douyin 131 → 115（原先 19 条红）：视频线清空后，「入库的六期」这个对象没了，
  依赖它的用例改成在 `tmp_path` 里现造四层坐标的期；测「真实成片」的那
  12 条（永远 skip）并进了合成成片的端到端用例。
- wechat 505 → 505（原先 22 条红）：adapter 之前 import 一个已删的 hexo 脚本、
  又 shell out 调两个同样已删的脚本做 sync，读不到任何文章。改成接今天的两条
  （`tools/build-content-units.py` + `platforms/blog/site/tools/sync-content.py`）。

**「视频线不发布」那轮（2026-11-19 晚）**：owner 拍板视频线的文档不进站点，
`docs/` 归零。连带动到四套件——每一条变动的根因都是同一个：
**用例依赖了「仓库里曾经有过的内容」**。

| 套件 | 变动 | 为什么 |
| --- | --- | --- |
| video | 1052 → 1050 | 删了 `test_publish_copy.py` 那 3 条（被测的脚本没了）；「规范里的引用必须存在」那条拆成两条——一条查引用，一条查引用正则本身还认不认得出引用（原来它靠 `docs/` 里有稿子才不空转） |
| publish | 338 → 338 | 那条「两份解析器在真语料上答案相同」原来扫 `docs/` 全树，`docs/` 归零后它永远 skip——**永远 skip 的守卫等于没有守卫**。改成自己造 12 段语料（各种 front matter 形状） |
| 根 | 81 → 81 | 两条 review-check 集成用例原来指着 `docs/life/aiv/人格规范.md`；改成在 `tmp_path` 里造自己的语料树（工具多了一个 `--docs-root` 参数） |
| 站点 | 51 → 51 | 「没有内容就没有目录树」从报错改成正面断言 |

> **规律：一条用例如果依赖「仓库里曾经有过的内容」，它迟早会因为
> 内容被清掉而变成假红。** 新的用例一律在自己造语料。

**「站点换 hexo」那轮（2026-11-20）**：站点从 Astro 换成 Hexo + matery。
守卫整套重写——不是改，是**删掉旧的、另起一套**：

| 套件 | 变动 | 为什么 |
| --- | --- | --- |
| 站点 | 51 / 1 skip → 79 | 删掉 Astro 时代的活动账本、占位符、侧栏那几套；补上身份通用性、地址形状、目录页、首页一屏、mermaid 渲染、分类与标签退休、`<nav>` 误用、`/all/` 跳转、资源本地化与重库按需加载、图片残留清理 |
| publish | 338 → 338 | 不变 |
| 别的套件 | 全不变 | 站点换了实现，但**跨模块接口没动**：地址形状仍是 `/docs/<id>/`，内容单元仍是那一半，`capability.toml` 一个字没改 |

> **图片残留也是这轮查出来的。** `build-posts.py` 清掉了撤掉的**文章**，
> 却只往 `source/images/` 里**搬**、不**清**——源稿删了一张图，产物里
> 那张图就永远留着，而构建日志还在说「图片 0 张」，看不出异样。
> 修法是让图片跟文章守同一个规矩（撤掉的不许留在磁盘上），
> 并补一条自造语料的用例钉住它。

> 这轮还顺手修了一条**与站点无关**的红：`publish/tests/test_real_declarations.py`
> 把 `platforms/` 下每个目录都当平台看，而会话工具的 `.remember/` 临时目录
> 正好落在 `platforms/` 里 → 那条守卫红了。修法是**在仓库根的 `.gitignore`
> 里挡掉 `.remember/`**（不是改守卫——守卫没错，是仓库里混进了不该有的目录）。

### 「两个 adapter 补进矩阵」那轮（2026-11-19 夜）

B站与视频号两个 adapter 之前**既不在验收矩阵里，也不在任何 CI 工作流里**——
它们的红没人看得见。现已进矩阵、进 `contracts.yml`。

| 套件 | 变动 | 为什么 |
| --- | --- | --- |
| B站 | 6 红 → 0 红（68 条） | 跟抖音同款根因：`pyv.epmeta.PUBLISH_DIR` 这个常量随视频线重做一起改名成 `EPISODES_DIR` 了，4 处 `monkeypatch.setattr` 全抛 `AttributeError`，用例在夹具阶段就炸了，根本没跑到自己的断言。改法照抖音：自己在 `tmp_path` 里造四层坐标的一期（期目录 + `publish.json`），`monkeypatch` 掉 `epmeta.EPISODES_DIR`。生产代码一行未动 |
| 视频号 | 4 红 → 0 红（55 条） | 同上 |
| CI | +2 条 step | `contracts.yml` 现在有 10 条 step，每个模块一条，都带 `if: ${{ !cancelled() }}` |

> 顺带钉住一条以前没有的守卫：**测试不许往仓库的 `platforms/*/outbox/` 写东西**。
> 基准取**会话起点**而不是每个测试的前后——前后比对看不见**上一个测试**留下的
> 东西（那个文件在本次起点就已经存在了，于是「前后一样」）。
> 再补一条判据：入库目录里只允许有 git 跟踪的文件（`git ls-files -z`——
> 默认的 `git ls-files` 遇到非 ASCII 路径会写成八进制转义并加引号，
> 拿那个字符串跟文件系统上的真实中文名比对，永远比不上）。

> **B站那轮顺带查出两个真问题**（不是测试红，是生产代码与流水线对不上）：
> adapter 找成片的路径 `video/out/<期路径>.mp4` 跟流水线出片的
> `video/out/<ep_id>.mp4` 对不上；快照文件名带斜杠，落在入库目录的**子目录**里。
> 两条都记在 [`review/specs/2026-11-19-整体架构与模块边界.md`](../review/specs/2026-11-19-整体架构与模块边界.md) §五。

### 那 1 个红（`browser/`）

`browser/tests/test_session.py::test_a_script_can_attach_to_a_browser_that_is_already_running`
—— 需要一台**真的装好浏览器的机器**，容器里没有就 `BrowserUnavailable`。
**这是环境红，不是逻辑红。** 它的其余 99 条（形状验证）全绿。

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
| `.github/workflows/contracts.yml` | 母稿 / review 层、publish 契约层、头条 adapter、微信 adapter、抖音 adapter——**每个模块一条 step**，每条带 `if: ${{ !cancelled() }}`，一个模块红不挡住别的模块 |
| `.github/workflows/site.yml` | 站点模块：`verify` job 守约束（内容单元 / 围栏 / 学习流数据），`build` job 出产物（`npm ci` + `npm run build`）+ 跑站点守卫测试（带 `::error::` 注解，不登录也能看到是哪条挂了） |
| `.github/workflows/video-pipeline.yml` | 视频流水线 |

**每个模块只在一个地方跑一次**——不重复收集，也就不会「多出一条用例」。

**验收的粒度 = 模块的粒度。** 谁改了什么，就只有谁的套件会红。

> ⚠️ **`browser/` 还没进 CI。** 它的套件要 playwright 与一台装好浏览器的
> 机器（那条红就是环境红）。它不进 CI 的后果是**跟抖音一样**：没人知道
> 它的红是存量红还是新红。补它需要给仓库加一份 `requirements/browser.txt`
> 与一条装浏览器的步骤——**这是上线那一轮的事**，先记在这儿。

> ⚠️ 两条工作流（`contracts.yml`、`site.yml`）在 2026-11-19 之前一直
> 监听 `master`，而这个仓库的默认分支是 `main`——**闸门从来没跑过**。
> 已修（`d1da8f2d`）。
