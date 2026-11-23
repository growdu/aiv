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
| 创作平台门面 | `api/` | `cd api && python3 -m pytest tests/ -q` | HTTP 面的形状（路由、作业、审校、过审只复制） |
| 创作平台前端 | `front/` | `cd front && npm run test` | 界面自己的规矩（缝、身份守卫、组件） |

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

数字是 **2026-11-23**（站点以 hexo+matery 为准）**逐条单独跑**量出来的。
**归位之后，总数必须与合并跑时一致**——少一条就是某条用例消失了，
多一条就是某个目录被收集了两次。

| # | 命令（各自在模块目录里跑） | 跑的是什么 | Expected | 实测 |
| --- | --- | --- | --- | --- |
| 1 | `python3 -m pytest tests/ -q`（仓库根） | 母稿 / review 层：审校信号、审校记录、身份守卫、内容坐标与层间边界、**死路径** | 133 passed / 3 skipped | 133 passed / 3 skipped |
| 2 | `cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q` | 站点：身份通用性、地址形状、学习流归属、死链、页面齐全、首页一屏、目录页渲染、URL 跳转 | 125 passed / 1 skipped | 125 passed / 1 skipped |
| 3 | `cd publish && python3 -m pytest tests/ -q` | publish 契约层：内容契约、能力模型、发布清单、调度、退出码 | 356 passed / 1 skipped | 356 passed / 1 skipped |
| 4 | `cd platforms/toutiao && python3 -m pytest tests/ -q` | 头条 adapter：切片、出包、草稿箱 | 399 passed / 2 skipped | 399 passed / 2 skipped |
| 5 | `cd platforms/wechat && python3 -m pytest tests/ -q` | 微信 adapter：同上 | 521 passed / 1 skipped | 521 passed / 1 skipped |
| 6 | `cd platforms/douyin && python3 -m pytest tests/ -q` | 抖音 adapter：出包不带上站外地址、无品牌导流版、档位闸 | 117 passed | 117 passed |
| 7 | `cd video/pipeline && python3 -m pytest tests/ -q` | 视频流水线：自己的套件 | 1103 passed / 60 skipped | 1103 passed / 60 skipped |
| 8 | `cd platforms/bilibili && python3 -m pytest tests/ -q` | B站 adapter：出包、条件必填、状态回填 | 77 passed | 77 passed |
| 9 | `cd platforms/channels && python3 -m pytest tests/ -q` | 视频号 adapter：同上 | 59 passed | 59 passed |
| 10 | `cd browser && python3 -m pytest tests/ -q` | 发布执行器：浏览器流程的形状 | 1 failed / 99 passed / 64 skipped | 1 failed / 99 passed / 64 skipped |
| 11 | `cd api && python3 -m pytest tests/ -q` | 创作平台门面：路由形状、作业与 SSE、审校面板的数据模型、**过审只复制**、目录穿越、**端到端六场景** | 124 passed | 124 passed |
| 12 | `cd front && npm run test` | 创作平台前端：**零 import 缝**、身份守卫、草稿箱与编辑器、审校面板、产物与作业 | 20 passed | 20 passed |

### 创作平台的手测记录（2026-11-23）

规格 §10.4 的六条，**在真浏览器里点了一遍**（Chrome + vite dev server +
`uvicorn api.app:app`），每条记下实际结果。脚手架：`api/tests/test_end_to_end.py`
把同样的六条**钉成用例**（审校信号用的是真的 `tools/review-check.py`，
只把语料换到临时树）。

| # | 场景 | 实际结果 |
| --- | --- | --- |
| 1 | 建空白文档草稿 → 平台里看到它 → 编辑 → 保存 → **文件确实变了** | 草稿箱列出它；改完点「存进草稿箱」，盘上的文件从 38 字节变成 347 字节（md5 变了），提示「已存进草稿箱。」 |
| 2 | 建视频草稿单元 → 编辑口播稿 → 保存 → **契约校验过** | 口播稿改完存进草稿箱；`contract.json` 仍能 `json.loads`，`episode` 是**四层期路径**；口播稿 front matter 的 `episode` 是**三层文档路径**——界面把两者分成两块摆开，各带一行说明 |
| 3 | 文档流的审校面板**出信号** | 母稿层那篇故意带 AI 味 → 面板出 **AIF-01 / AIF-02 / AIF-04** 等 4 条 warn + 5 条 info，**错误 0**；闸门写「待审 —— 还没有审校记录」。**信号不是门禁**——另一篇记录写着「已合入」的稿子，闸门放行 |
| 4 | 点「出片」→ **先 promote 再跑 make** → 日志滚动 | 日志依次是：复制 3 个入库事实 → 报还差哪三步手工 →「这一期还没有旁白」→ 给出合成旁白的命令；作业**退出码 2（precondition）**。`make` 一次没跑（视频线今天是空壳，缺旁白与素材）——**次序**是对的 |
| 5 | 「过审」复制进母稿层，且**草稿仍在**；提示还差哪三步 | `docs/<路径>.md` 出现，**草稿还在原地**；界面列出三条手工步骤（建/更新审校记录、补两个 `INDEX.md`、提交） |
| 6 | 出包状态表显示各平台快照 | 表头五列（平台/状态/标题/更新时间/地址），读出 toutiao 的 `packaged` 快照 |

> ⚠️ **两件手测查出来的事**（都已修）：
>
> 1. **「重建」作业对目录链是真的严**：临时稿子的上级目录没有 `_index.md`，
>    编译器当场退出 2，日志写「目录链断了：… 的上级 … 没有 _index.md」。
>    这不是平台的毛病，是**「目录即接口」**的规矩在起作用。
> 2. **dev server 的日志原先落在 `platforms/blog/site/.dev-server.log`**——
>    平台在**别人的模块目录里**留了个文件。平台的唯一写点是 `drafts/`，
>    所以日志改落系统临时目录（`api/services/preview.py` 的 `DEV_SERVER_LOG`），
>    并补了一条守卫钉住「它不在仓库里」。
>
> 顺带查清了两件**不是**平台的事：预览 iframe 指向的是站点 dev server 的**真页面**
> （`http://127.0.0.1:4000/docs/<id>/`，单独开标签渲染正常）；头less 截图里
> iframe 是白的，是**无头浏览器不把跨源 iframe 画进元素截图**，不是页面坏了。



| 时间 | 根 | 站点 | publish | toutiao | wechat | douyin | video | bilibili | channels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-18（归位那轮） | 196 / 3 skip | 26 | 411 / 1 skip | 394 / 2 skip | 504 / 1 skip | 119 / 12 skip | 1269 / 23 skip / 3 red | 68 | 55 |
| 2026-11-19（清库那轮） | 81 | 51 / 1 skip | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1052 / 60 skip | 68 | 55 |
| 2026-11-19（视频线不发布那轮） | 81 | 51 / 1 skip | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1050 / 60 skip | 68 | 55 |
| 2026-11-20（站点换 hexo 那轮） | 81 | 79 | 338 / 1 skip | 394 / 2 skip | 504 / 1 skip | 115 | 1050 / 60 skip | 68 | 55 |
| 2026-11-19（还 §五 欠账那轮） | 114 | 59 / 1 skip | 348 / 1 skip | 399 / 2 skip | 521 / 1 skip | 119 | 1060 / 60 skip | 77 | 59 |
| 2026-11-23（README 保留名那轮） | 117 | 86 | 348 / 1 skip | 399 / 2 skip | 521 / 1 skip | 119 | 1060 / 60 skip | 77 | 59 |
| 2026-11-23（发布意图透传那轮） | 121 | 86 | 348 / 1 skip | 399 / 2 skip | 521 / 1 skip | 119 | 1060 / 60 skip | 77 | 59 |
| 2026-11-23（第一篇稿子进 `docs/` 那轮） | 121 | 89 | 348 / 1 skip | 399 / 2 skip | 521 / 1 skip | 119 | 1060 / 60 skip | 77 | 59 |
| 2026-11-23（`epmeta` 变通用加载器那轮） | 121 | 107 | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1071 / 60 skip | 77 | 59 |
| 2026-11-23（赛道改名 + Ceph 筹备中那轮） | 121 | 115 | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1071 / 60 skip | 77 | 59 |
| 2026-11-23（讲稿骨架那轮） | 121 | 115 | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1085 / 60 skip | 77 | 59 |
| 2026-11-23（学习流视频条目那轮） | 121 | 116 | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1085 / 60 skip | 77 | 59 |
| 2026-11-23（筹备中标记那轮） | 121 | 119 | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1085 / 60 skip | 77 | 59 |
| 2026-11-23（总验收那轮） | 125 / 3 skip | 125 / 1 skip | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1092 / 60 skip | 77 | 59 |
| 2026-11-23（死路径守卫那轮） | 129 / 3 skip | 125 / 1 skip | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1092 / 60 skip | 77 | 59 |
| 2026-11-23（BGM 铺底循环那轮） | 129 / 3 skip | 125 / 1 skip | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1101 / 60 skip | 77 | 59 |
| 2026-11-23（混音不重编码那轮） | 129 / 3 skip | 125 / 1 skip | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1103 / 60 skip | 77 | 59 |
| 2026-11-23（创作平台那轮） | 133 / 3 skip | 125 / 1 skip | 356 / 1 skip | 399 / 2 skip | 521 / 1 skip | 117 | 1103 / 60 skip | 77 | 59 |

> 2026-11-23（混音不重编码那轮）：**video +2 条**——新文件
> `video/pipeline/tests/test_compose_no_reencode.py`：混音阶段**复制视频流**（`-c:v copy`），
> 不再把视频编码第三遍（12 分钟的片子能省十几分钟）。
> 守卫分两层：命令层查 `-c:v copy`、成片层比**帧校验和 + 码流指纹**。
> ⚠️ 夹具**不能用纯色画面**——纯色重编码后逐帧一模一样，断言会恒真；
> 这里用 `testsrc2`。注入缺陷（退回 `encode_args`）两条都红。

> 2026-11-23（BGM 铺底循环那轮）：**video +9 条**——新文件
> `video/pipeline/tests/test_bgm_loop.py`：**曲子不够长时循环接回**，接缝落在最安静处，
> 铺底盖住整段正文（原来取 `min(曲子长度, 旁白长度)`，300 秒旁白只铺出 209 秒）。
> 成片级判据 `measure_duck_depth` 的**对照物换成同一份循环铺底**（拿原母带当对照，
> 量到的是两段不同素材的 RMS 差，实测能偏到 20 dB）。
> 两条守卫都**注入缺陷验过会红**——包括一条曾因夹具对称而**空转**的
> （夹具形状记在那个文件的 docstring 里，别改回对称样子）。

> 2026-11-23（死路径守卫那轮）：**根 +4 条**——新文件 `test_stale_paths.py`：
> 2026-11-17 目录重构搬走的那两棵平台私有目录（**能力模型**与**发布快照**）
> **不许再被任何文件提到**；白名单**今天留空**（留白也要写清理由才进白名单）。
> 守卫自己**要能抓到东西**（拿临时树试），并且先断言那两棵树**真的不在了**——
> 哪天它们被搬回来，守卫就该跟着退役，而不是继续拦人。
> 配套改的是 `platforms/toutiao/docs/` 两份文档里的**死路径**（**只改路径，
> 实测数字与判定一个字没动**）。**其余九套件一条没动。**

> 2026-11-23（总验收那轮）：**坐标系的 19 条验收逐条落成守卫**。
>
> | 套件 | 变化 | 落了什么 |
> | --- | --- | --- |
> | 根 `tests/` | +4 | 新文件 `test_coordinate_system.py`：期号与内容单元一一对应（**编译器撞了期号当场退出 1**）、每一期都有内容单元、内容单元仓库不在任何平台目录里、上游不伸手进平台目录也不 import 平台包 |
> | 站点 | +6 | 源码方向的「阶段 = 系列目录」一一对应（正向 + 反向）、学习流里一个视频单元只出现一次、旧地址逐条有跳转（**手工验过的那条变成守卫**）、跳转目标得有页面、跳转页要真发出去 |
> | 视频流水线 | +7 | 坐标与口播稿对得上：`tier` 对目录第四层、`episode` 对目录前三层、期号不重复、每篇文档都有 short 档 |
> | 其余六套件 | 一条没动 | —— |
>
> **三处「跳过」是有原因的**（不是用例消失了）：
> 根的三条要**有期**才有话说（视频线今天还是空的），
> 站点的一条要 `docs/source-tracks/` 在（源码方向的内容还没搬进来）。

> 2026-11-23（筹备中标记那轮）：**站点 +3 条**——筹备中的赛道在
> 总览页、赛道页与首页赛道卡上都挂「筹备中」徽标（虚线顶边 + 灰调徽标）：
> 「筹备中」和「规则缺失」在数据上长得一样（都是 0 篇），读者看的是页面，
> 区别得**看得见**。守卫钉住「总览页与赛道页都标」「正常赛道不标」
> 「徽标真的渲染到浏览器里」。**其余九套件一条没动。**

> 2026-11-23（学习流视频条目那轮）：**站点 +1 条**——视频条目按**期号**写
> （`video/<期号>`），守卫钉住「不带档位后缀」；顺带删掉视频线清空重来前
> 留下的六条旧期号条目（`video/row-lock` 之类）——那些期不存在了，
> 也不会再有那样的 content_id。**其余九套件一条没动。**

> 2026-11-23（讲稿骨架那轮）：**视频线 +14 条**——`pyv/skeleton.py` 落地
> （骨架解析 + 按 role 裁三档）：一条守卫钉住 `ROLE_TIERS` 是《长视频三档》§5.2
> 那张表的**逐格照抄**（自己发挥的话，裁出来的片子跟规格说的不是一回事，
> 而片子看上去仍然是「正常的视频」）；一条钉住段序不动；
> 一条钉住**不认识的 role 要报错**（`mechanim` 少个 s，那一段会在三档里
> 同时消失，而页面上看不出来）；一条钉住不按字数截断。
> **其余九套件一条没动。**

> 2026-11-23（赛道改名 + Ceph 筹备中那轮）：**站点 +8 条**——① 赛道改名
> （`db-internals` → `postgresql`、`linux-network` → `linux`、
> `dataplane` → `dpdk`）：三条守卫钉住「赛道 id 是方向名」「id 是合法 slug」
> 「赛道配色与赛道 id 一一对应」（不钉住的话，改名后那条赛道**掉回默认色**，
> 页面看上去还是好的，只是几条赛道撞了色）；② Ceph 赛道（`status: "planned"`，
> 四个阶段骨架）：五条守卫钉住「状态位只认 active / planned」
> 「筹备中的赛道必须把大纲写出来」「阶段得落在本赛道范围内」
> 「筹备中的赛道不设兜底桶」「每个阶段都得声明将来收什么」。
> **其余九套件一条没动。**

> 2026-11-23 最后一轮：**站点 +3 条**——目录页的 layout 渲染出错被 Hexo 吞成
> **0 字节的空页面**（`site.posts` 是 Query 不是数组、`permalink` 两种形状
> 对不上），新守卫钉住「产物里不许有空页面 / 不许有不是完整 HTML 的页面 /
> 目录页必须列得出自己的直接子级」。其余九套件一条没动。

> 2026-11-23（`epmeta` 变通用加载器那轮）：**视频线 +11 条**——平台清单从
> 写死的三段搬进 `platforms/<plat>/publish-spec.json`，`epmeta` 不再认识任何平台名；
> 配套的守卫钉住「规格是扫出来的」「JSON 里 `required_when` 的整数键要还原」
> （不还原的话条件必填永远不触发）、「档位不在平台的 `tiers` 里就报红」。
> **publish +8 条**（能力声明加 `tiers` 字段的守卫）；**站点 +18 条**（URL 级重定向）；
> **抖音 −2 条**——三档全量出包那条改成「short 能出包、mid/full 被档位闸拒掉」
> （规格 §四：抖音只收 short 档），两条参数化用例合成一条加两条新的。

> 口径说明：站点换 hexo 那轮与还 §五 欠账那轮在两条分支上**并行**发生。
> 合并后站点以 hexo+matery 为准：hexo 的 79 条 + 还欠账那轮里仍适用的
> URL 形状、图片基准、身份守卫共 7 条，合起来 **86**（§三 第 2 行）。

> 2026-11-23 那两轮：根套件 +7 条——① 编译器把 `README.md` 当**保留名**
> （模块说明，不是稿子），配套 3 条用例钉住它；② 编译器补上**发布意图字段**
> （`platforms` / `publish_on`）的透传，配套 4 条用例钉住「母稿写了发布意图 →
> 内容单元**就是**发布候选」。**其余 9 条一条没动。**

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
| `.github/workflows/api.yml` | 创作平台门面（`api/`）：装 `requirements/api.txt`，跑 api 套件 |
| `.github/workflows/front.yml` | 创作平台前端（`front/`）：`npm ci` → vitest → `npm run build` |

**每个模块只在一个地方跑一次**——不重复收集，也就不会「多出一条用例」。

**验收的粒度 = 模块的粒度。** 谁改了什么，就只有谁的套件会红。

> ⚠️ **`browser/` 还没进 CI。** 它的套件要 playwright 与一台装好浏览器的
> 机器（那条红就是环境红）。它不进 CI 的后果是**跟抖音一样**：没人知道
> 它的红是存量红还是新红。补它需要给仓库加一份 `requirements/browser.txt`
> 与一条装浏览器的步骤——**这是上线那一轮的事**，先记在这儿。

> ⚠️ 两条工作流（`contracts.yml`、`site.yml`）在 2026-11-19 之前一直
> 监听 `master`，而这个仓库的默认分支是 `main`——**闸门从来没跑过**。
> 已修（`d1da8f2d`）。
