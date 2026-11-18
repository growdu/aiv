# growdu · 博客与内容生产线

> 一个仓库，**两条流水线、六个第三方平台**：
> **文档流**（growdu.cn / 公众号 / 头条号）、**视频流**（抖音 / 视频号 / B 站）。
> 共同的**入口**是 `drafts/` —— 稿子先落草稿箱，**审过**才往下走；
> 共同的**出口**是 `platforms/` —— 六个第三方平台，站点也在其中。
> 母稿在 `docs/`（文档流）与 `video/`（视频流），那里是内容的唯一真相。

本文件是**仓库级总览**：讲清楚整体架构与模块划分。
想改文章、改样式，看 [`internal/blog/架构.md`](internal/blog/架构.md)（站点构建链路，更细）。
想改视频、看契约，看 [`video/README.md`](video/README.md)。
想改平台适配，看 [`platforms/README.md`](platforms/README.md)（六个平台的共同规矩与核心流程）。
想改发布逻辑，看 [`publish/spec/00-架构设计.md`](publish/spec/00-架构设计.md) 与
[`publish/spec/06-发布计划与调度.md`](publish/spec/06-发布计划与调度.md)、
[`publish/spec/07-视频发布契约.md`](publish/spec/07-视频发布契约.md)。

---

## 一、整体架构

```text
                              主题（一段话）
                                   │
                       ┌───────────┴───────────┐
                       ▼                       ▼
                    手动编写                 自动生成
                       └───────────┬───────────┘
                                   ▼
                          drafts/  草稿箱
                          （两条流水线的共同入口）
                                   │
                              总审核 review/
                                   │
          ┌────────────────────────┴────────────────────────┐
          ▼                                                 ▼
     ┌─────────┐                                       ┌─────────┐
     │  docs/  │  文档流母稿                           │ video/  │  视频流母稿
     └────┬────┘                                       └────┬────┘
          │                                                 │
          │                                                 │ pyv 渲染引擎
          │                                                 │ (cairo + ffmpeg)
          │                                                 ▼
          │                                        out/<EP>.mp4（成片，不入库）
          │                                                 │
          └──────────────────────┬──────────────────────────┘
                                 ▼
                     publish/publishkit（契约层，平台无关）
                     读 platforms/<plat>/capability.toml（平台能力 = 数据）
                     写 platforms/<plat>/outbox/*.json（发布快照 = 幂等键）
                                 ▼
                          platforms/（六个平台）
            ┌──────────┬──────────┬──────────┬──────────┬────────┼───────┐
            ▼          ▼          ▼          ▼          ▼        ▼       ▼
         wechat/   toutiao/     blog/     douyin/  channels/ bilibili/
        （公众号） （头条号）  （站点）   （抖音）  （视频号）  （B 站）
            └──────────┴──────────┴──────────┴──────────┴────────┴───────┘
                   目录名即包名，各自一套 adapter：
                   适配 → 生成 → review → output → upload

  站点这个平台（blog/）的实现是 hexo 那一套：
     docs/ ──sync-hexo.py──▶ content/units/ ──adapt-units.py──▶ platforms/blog/site/source/_posts/
            ──hexo generate──▶ platforms/blog/site/public/ ──CI──▶ growdu.cn
  （站点这一平台的构建链就住在 platforms/blog/site/）
```

> **存量说明**：`docs/` 里现有的 560 篇、`video/` 里现有的 6 期成片是**存量**——
> 它们在草稿箱这一层存在之前就写完、审过、验证过，停在 `review` 的**下游**，
> **不倒回去**走 `draft → review`。草稿箱约束的是**新内容**。
> 所以「那 560 篇的草稿在哪」是个没有答案、也**不需要有答案**的问题。

### 三条产线的分工

按**产出形态**切，三条产线：

| 产线 | 输入 | 产物 | 事实来源 |
| --- | --- | --- | --- |
| 技术站点 | `docs/` | 静态站 `platforms/blog/site/public/` | `docs/` |
| 品牌视频 AIV | `video/contracts/*.json` + 口播稿 + 旁白 | 1920×1080 成片 | 契约 + 规范文档 |
| 多平台分发 | `content/units/` 内容单元 + 能力声明 | 草稿 / 出包 / 已发链接 | `docs/`（内容）+ `platforms/<plat>/outbox/`（状态） |

按**内容类型**切，是**两条流水线**（文档流 / 视频流）——见上面的图。
两种切法**正交**：文档流的下游既有站点（`docs/`）也有文本平台（公众号、头条），
视频流的下游是视频平台；一个内容单元可以既是站点文章，又是某一期视频的母稿。

> **站点也是第三方平台**（2026-11-18 起）。`platforms/blog/` 与另外五个平级，
> 目录名即平台 id、同样有 `capability.toml` 与 `outbox/`。
> 唯一的差别是**出包粒度**：那五个逐篇出包、发一篇，站点是整站重建一次。
> 见 [`platforms/blog/docs/01-站点即第三方平台.md`](platforms/blog/docs/01-站点即第三方平台.md)。

---

## 二、模块划分

### 2.1 全局分层

| 层 | 位置 | 职责 | 允许依赖 |
| --- | --- | --- | --- |
| **草稿层** | `drafts/` | 主题 → 手动编写 / 自动生成 → 底稿；两条流水线的共同入口。**新增与修改都从这里开始**，过审才进 `docs/` / `video/`。六条线各有一份镜像（`source-tracks/` 那份是供视频线读素材的工作副本）。**目录即接口**：一级目录 = 分类，二级目录 = 二级内容，一篇文档 = 一期——在这里建目录就是新增一个对外可见的分类，慎重 | 只读 `docs/`、`video/` |
| **内容层** | `docs/` | 母稿、图片、分类元数据 | 无（纯内容） |
| **内容编译层** | `tools/`（平台无关）+ `platforms/blog/site/tools/`（站点这一平台的实现） | `docs/` → 内容单元、主题补丁、校验 | 只读 `docs/`，只写 `content/units/` 与站点源目录 |
| **展示层** | `platforms/blog/site/themes/matery/` | EJS 模板、CSS/JS、静态资源 | Hexo 运行时 |
| **视频生产层** | `video/` | 契约 → 时间轴 → 片段 → 成片 | 只读自己的契约与素材 |
| **审核层** | `review/`、`video/review/` | 审校规则、一期一条记录、抽帧清单 | 只读 `docs/`、`video/` 的契约与产物 |
| **发布契约层** | `publish/publishkit/` | 内容契约 / 能力模型 / manifest / 调度 | **不认识任何平台** |
| **平台适配层** | `platforms/<plat>/`（每个平台一个目录：wechat / toutiao / **blog** / douyin / channels / bilibili） | 平台切片、渲染、出包、发布、状态 | 只认 TOML 与 manifest JSON |

**依赖方向是单向的**：平台层不 import 契约层，契约层不 import 平台层。
两边唯一的接缝是**同一份 `platforms/<plat>/capability.toml`** 与**同一份 manifest JSON**。
这条规矩由 `publish/tests/test_capability_compat.py` 之类的一致性测试守住。

### 2.2 站点构建链

**站点这一平台的构建链住在 `platforms/blog/site/`**——站点是六个平台之一，
它的实现就该住在自己的目录里，「加平台只动 `platforms/`」这句话对站点才成立。

| 模块 | 位置 | 干什么 |
| --- | --- | --- |
| 内容编译 | `platforms/blog/site/tools/sync-hexo.py` | `docs/` → `content/units/` + 站点 `source/images/`，重建 front matter，生成 landing page |
| 内容单元适配 | `platforms/blog/site/tools/adapt-units.py` | `content/units/` → 站点 `source/_posts/`（站点是内容单元的**一个消费者**） |
| 主题补丁 | `platforms/blog/site/tools/patch-theme.py` | marker-based 幂等注入：SEO meta、相关文章、PV、OG 卡片等 |
| 素材搬运 | `platforms/blog/site/tools/copy-vendor.py` | logo、打赏图 → 主题 `medias/` |
| 内容校验 | `platforms/blog/site/tools/check-markdown.py` / `tools/fix-markdown.py` | front matter、链接、格式校验与修复 |
| 契约闸门 | `tools/check-content-contract.py` | 按内容契约校验所有内容单元，违规退出码 1（CI 用） |
| CDN 本地化 | `tools/localize-cdn.py` | 把主题的 jsDelivr CDN 换成本地资源（国内访问） |
| 评论初始化 | `platforms/blog/site/tools/init-gitalk-issues.js` | 为新文章预创建 Gitalk issue |
| Hexo 扩展 | `platforms/blog/site/scripts/*.js` | filter/helper：mermaid 渲染、HTML 文章处理、智能摘要 |
| 主题 | `platforms/blog/site/themes/matery/` | 站点外观；覆盖配置在 `platforms/blog/site/_config.matery.yml`（**不要改主题自带的 `_config.yml`**） |

配置分工：`_config.yml` 是 Hexo 自身的；`_config.matery.yml` 是对主题的覆盖。
站点的 `source/` 与 `public/` 都在 `.gitignore` 里，CI 现生成；
`content/units/` 同理——它也是构建产物。

> **内容单元住在 `content/units/`**，不在站点目录里：它**所有平台共用**，
> 是「内容单元」这一层与各平台之间的接缝。站点通过 `adapt-units.py` 拿自己那份副本。
> 见 [`review/specs/2026-11-18-顶层设计与目录调整.md`](review/specs/2026-11-18-顶层设计与目录调整.md) §4.2。

### 2.3 AIV 视频生产线

| 模块 | 位置 | 干什么 |
| --- | --- | --- |
| 视觉分镜契约 | `video/contracts/<期>.json` | 一期视频的段落划分、画面文案与数字（**每期只写这里**） |
| 发布元数据 | `video/publish/<期>.json` | 每期各平台的标题、简介、话题与分区（`pyv publish check` 体检） |
| 渲染引擎 | `video/pipeline/pyv/` | `pyv/cli.py` + `scenes/` + 28 个模块：`align`/`render`/`compose`/`timeline`/`subtitle`/`bgm`/`brand`/`persona`/`topics`/`doctor`/`preflight`/`review`/`layout`/`components`/`fingerprint`… |
| 审核 | `video/review/` + `pyv/review.py` | 文本层 `VT-*` 与成片层 `VV-*` 的规则、一期一条记录、抽帧清单 |
| 时间轴 | `storyboard_<EP>.json` | 由旁白对齐算出的产物，**不入库** |
| 场景模板 | `video/pipeline/pyv/scenes/*.py` | 位置、尺寸、配色、动效等版式常量 |
| 形象 | `video/character/scripts/` | 3D 小象生成、加眼镜、铭牌盖章 |
| 品牌 | `video/brand/scripts/` | 片头/片尾渲染与配乐 |
| 音色 | `video/voice/scripts/` | 旁白合成、读音验收（多音字） |
| 音乐 | `video/music/` | 授权台账（入库）+ 曲库文件（不入库） |
| 规范文档 | `video/*.md` | 人格规范、形象与音色规范、背景音乐规范、选题库 |
| 发布副本同步 | `video/scripts/sync_publish_docs.py` | 把面向读者的文档同步到 `docs/life/aiv/`（博客发的是副本） |

**核心规矩**：文案与数字进契约，版式常量留代码。
契约少参数 → 渲染前抛 `MissingParam`；契约里的文案不许回流成场景代码里的字面量
（`pipeline/tests/test_contract.py` 盯这条）。

流水线按期号切：`make EP=<期号> align|validate|brand|render|compose`。
`align` 是手工步骤（需要旁白音频），其余可全自动。

同一套还有几档变体与审校命令：

| 命令 | 干什么 |
| --- | --- |
| `make EP=<期号> nobrand` | 无品牌导流版（抖音那一档，去品牌片头/片尾；`NOBADGE=1` 再去铭牌） |
| `make EP=<期号> vertical` | 9:16 竖版画布（抖音那一档，本来就不套品牌片） |
| `make EP=<期号> mix-verify` | 成片级混音验收（稳态 duck 深度、电平差、真峰值） |
| `make EP=<期号> review-text` | 审校·文本层（`VT-*`）：审要讲什么 |
| `make EP=<期号> review-video` | 审校·成片层（`VV-*`）：审做出来是什么样 |
| `make EP=<期号> review-frames` | 抽帧 + 清单：每段两帧 + 关键帧，给人和 Agent 逐帧看画面 |

审校的规则与边界见 [`video/review/README.md`](video/review/README.md)。

### 2.4 发布契约层（`publish/publishkit/`）

平台无关，只回答「发什么、怎么切、按什么规则触发」，不管「怎么发」。

| 模块 | 职责 |
| --- | --- |
| `contract.py` | 内容契约：母稿 front matter 的字段表与格式规则（扁平 `key: value` + 单层列表） |
| `capability.py` | 能力模型：读 `platforms/<platform>/capability.toml`，严格校验后交给 adapter |
| `manifest.py` | 发布清单：一个内容单元 × 一个平台的纯数据（可重放、无时间戳、无凭据） |
| `schedule.py` | 调度层：候选集、选题规则、ISO 周键、调度状态文件 |
| `cli.py` | 命令行入口：`schedule weekly/status/candidates`、`publish <content_id> --platform <id>` |

配套资产：

| 路径 | 内容 |
| --- | --- |
| `platforms/<plat>/capability.toml` | 平台限额与自动化档位（**数据不是代码**，平台规则变了改这里） |
| `platforms/<plat>/outbox/*.json` | 发布结果快照（幂等键 + 站点发布索引的数据源） |
| `publish/schedule.json` | 调度状态，按周键幂等 |
| `publish/spec/*.md` | 契约规格（架构设计 / 调度 / 视频发布） |
| `publish/deploy/*.template` | crontab、launchd、GitHub Action 模板 |
| `publish/tests/` | 契约、能力、清单、调度、CLI 的测试 |

### 2.5 平台适配层

六个 adapter **同构布局**，彼此独立：

| 平台 | 目录 | 形态 | 自动化档位 |
| --- | --- | --- | --- |
| 微信公众号 | `platforms/wechat/` | 图文 → 草稿箱（`draft/add`） | `api_draft`：自动生成 + 自动进草稿箱，**发表由人点**（账号无发表接口权限） |
| 今日头条 | `platforms/toutiao/` | 图文 → 头条版排版包 / 半自动出包 | `manual`（能力声明）：出包 + 人工发（账号未认证，API 权限开不了） |
| **个人站点** | `platforms/blog/` | markdown → 整站静态站 → CI 部署 | **`api_publish`**：六个里唯一——推上去就部署（`review = "precheck"`，靠本地闸门） |
| 抖音 | `platforms/douyin/` | 视频 → 竖版切片 + 出包 + 浏览器上传（后台可暂存 `drafted`，待你点发表） | `manual`：个人主体拿不到 API 凭据，走浏览器自动化 |
| 微信视频号 | `platforms/channels/` | 视频 → 切片 + 人工发布清单 | `manual`：视频号无普通创作者发布接口 |
| 哔哩哔哩 | `platforms/bilibili/` | 视频 → 投稿包 + 字幕 | `manual`（`ARC_BASE` 权限开通后可转 `api_publish`） |

每个 adapter 的典型模块：`assets.py`（素材）、`contract.py`（平台契约）、
`render.py`/`package.py`（渲染/打包）、`state.py`（状态）、`snapshot.py`（快照）、
`notify.py`（通知）、`cli.py`（命令行），外加 `capability.toml`（能力声明）、
`outbox/`（发布快照）、`docs/`（设计与实施计划）与 `tests/`。

公众号线最成熟：`platforms/wechat/` 20 个模块，覆盖 Markdown 解析、封面、标题裁剪、
超长文章拆分、SVG/代码高亮、mermaid、合集与分类、品牌图文，已跑到草稿箱。

**站点是唯一的例外，例外只有一处：出包粒度。**
那五个是「一篇一个包、发一篇」，站点是「一次 push 重建全站 2400 个页面」——
所以 `platforms/blog/` **没有 `publish` 子命令**，只有 `status` 与 `check`。
详见 [`platforms/blog/docs/01-站点即第三方平台.md`](platforms/blog/docs/01-站点即第三方平台.md)。

六个平台的共同规矩、核心流程（五步）、以及「加一个平台要做什么」，
写在 [`platforms/README.md`](platforms/README.md)。

---

## 三、关键设计原则

1. **母稿唯一**：任何平台产物都能从 `content_id` 重建；真相只在 `docs/`。
2. **可重放 vs 有状态**：切片与渲染是纯函数，随便重跑；只有「发布」有状态，
   幂等键由 `platforms/<plat>/outbox/` 与 `publish/schedule.json` 承载。
3. **不静默成功**：平台的「成功」必须是**被显式确认过**的成功。发重了比发慢了糟糕得多。
4. **能力即数据**：平台限额与自动化档位在 TOML 里，不在 Python 里。
5. **只有一处接缝**：契约层与 adapter 互不 import，认的是同一份 TOML 与同一份 manifest JSON。
6. **入库的是事实，产物不入库**：音视频、时间轴、成片留在本机；入库的是规范、契约、台账、代码。
7. **规范公开，工程内部产物下线**：面向读者的规范在 `docs/` 发一份，工程内部留在仓库里。
8. **草稿是底稿，不是第二个产地**：稿子先进 `drafts/`，审过**复制**一份进
   `docs/` 或 `video/`；底稿留在原地**不再参与任何派生**。
   **新增与修改走同一段流程**——改动稿也先在 `drafts/` 里改，过审才覆盖
   `docs/`（或 `video/`）那一份，所以 `docs/` 里任何时刻都是**已过审的版本**。
   **主题**（用户产生 idea 时输入的一段话）也一样——它是流水线的**输入**，
   落进草稿的 front matter `topic:` 字段，不建目录、不单独成层。
9. **存量不回炉**：`docs/` 里现有的 560 篇、`video/` 里现有的 6 期成片是**存量**，
   在草稿箱这一层存在之前就写完、审过、验证过，停在 `review` 的**下游**。
   **不补草稿、不倒回去走 `draft → review`**——补出来的 560 份是假记录。
   草稿箱管的是**新内容与改动**，存量本身不回炉。
10. **目录即接口**：`docs/` 的**目录结构**就是接口——一级目录 = 一个分类，
    二级目录 = 一块二级内容，一篇文档 = 一期。方向与系列**目录派生**，
    不写进 front matter；分类的**中文名**写在 `_index.md` 的 `title:` 与
    `cascade.categories` 里（两份写同一个名字）。`drafts/` / `docs/` / `video/`
    三棵树**同形**。**在 `drafts/` 下建目录 = 新增一个对外可见的分类**，慎重。
    规程见 `review/specs/2026-11-18-目录即接口与分类增设.md`。

---

## 四、数据契约速查

| 契约 | 文件 | 生产者 | 消费者 |
| --- | --- | --- | --- |
| 内容契约（front matter） | `docs/**` 的 front matter | 作者 | sync-hexo → Hexo → 各 adapter |
| 平台能力 | `platforms/<id>/capability.toml` | 手写（对着平台文档复核） | publishkit + adapter |
| 发布清单 manifest | JSON（内存/落盘） | publishkit | adapter |
| 视觉分镜契约 | `video/contracts/<EP>.json` | 作者 | pyv 渲染引擎 |
| 发布元数据 | `video/publish/<EP>.json` | 手写 | `pyv publish check` + 各平台 adapter |
| 抽帧清单 | `video/review/frames/<EP>/frames.md` | 审核工具 | 审核记录（逐帧复核） |
| 发布结果快照 | `platforms/<platform>/outbox/<content>__<platform>.json` | adapter | 幂等判定 + 站点发布索引 |
| 调度状态 | `publish/schedule.json` | 调度层 | 调度层（周键幂等） |

---

## 五、目录速查

| 路径 | 内容 | 是否入库 |
| --- | --- | --- |
| `docs/` | 内容母稿（唯一真相） | ✅ |
| `content/units/` | 内容单元仓库（CI 生成；**所有平台共用的那一半**） | ❌ 构建产物 |
| `platforms/blog/site/source/` | Hexo 源（CI 生成；站点平台的产物） | ❌ 仅 `all/`、`recommended/` |
| `platforms/blog/site/public/` | 构建产物（站点平台的产物） | ❌ |
| `platforms/blog/site/themes/matery/` | 主题（站点平台的实现） | ✅ |
| `platforms/blog/site/` | 站点这一平台的构建链：配置、主题、脚本、hexo 扩展 | ✅（产物除外） |
| `tools/` | 平台无关的构建与校验脚本（含 `paths.py`——路径常量的唯一出处） | ✅ |
| `video/` | 视频生产线（规范 + 契约 + 代码） | ✅ 产物除外 |
| `video/build/`、`video/out/` | 片段与成片 | ❌ |
| `review/`、`video/review/` | 审校规则、一期一条记录、抽帧清单 | ✅ 帧除外 |
| `drafts/` | 草稿箱（主题 → 手动编写/自动生成 → 底稿；两条流水线的共同入口，底稿不参与派生；新增与修改都从这里开始，过审才进 `docs/` / `video/`；六条线各有一份镜像） | ✅ |
| `publish/` | 契约层与调度（发布契约规格、能力模型加载、manifest、周键） | ✅ |
| `platforms/<plat>/` | 平台 adapter（**六个**平台各一个目录，含能力声明 `capability.toml` 与发布快照 `outbox/`；目录名即平台 id） | ✅ |
| `platforms/blog/site/` | 站点这一平台的构建链（已搬到位） | ✅ |
| `requirements/` | 依赖清单（按模块分文件） | ✅ |
| `.github/workflows/` | `hexo.yml`（构建部署）、`contracts.yml`（契约闸门） | ✅ |

---

## 六、常用命令

```bash
# 站点（在 platforms/blog/site/ 里）
npm run sync          # docs → content/units/ → 站点 source/_posts/（等价 platforms/blog/site/tools/sync-hexo.py + adapt-units.py）
npm run build         # hexo generate
npm run server        # 本地预览

# AIV 视频（cd video/pipeline）
make test             # 全量测试
make topics           # 选题库规则检查
make persona          # 人格规范检查
make EP=<期号> all    # validate → brand → render → compose
make EP=<期号> mix-verify     # 成片级混音验收
make EP=<期号> review-text    # 审校·文本层（VT-*）
make EP=<期号> review-video   # 审校·成片层（VV-*）
make EP=<期号> review-frames  # 抽帧 + 清单（帧不入库，清单入库）

# 发布调度
cd publish && python3 -m publishkit.cli schedule candidates
cd publish && python3 -m publishkit.cli schedule weekly --dry-run
cd publish && python3 -m publishkit.cli schedule status

# 站点这个平台（cd platforms）
python3 -m blog.cli status                # 这个平台是什么、有什么限额、账本上多少条
python3 -m blog.cli check <content_id>    # 这一篇能不能进站（标题 / 构建排除 / 分类链）

# 契约闸门
python3 platforms/blog/site/tools/sync-hexo.py   # 先产出内容单元（content/units/）
python3 tools/check-content-contract.py         # 校验 578 个内容单元（572 篇文章 + 6 期视频内容单元），违规退出码 1
```

---

## 七、开发环境

依赖清单在 [`requirements/`](requirements/README.md)，**按模块装**：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements/publish.txt        # 契约层与调度层（零运行时依赖）
pip install -r requirements/wechat.txt         # 公众号 adapter
pip install -r requirements/video-pipeline.txt # AIV 视频生产线
```

pip 装不了的系统依赖：`ffmpeg` / `ffprobe`（出片与切片）、中文字体（封面与字幕）、
cairo 的头文件（`pycairo`）。

### CI 闸门

| 工作流 | 干什么 | 触发 |
| --- | --- | --- |
| `hexo.yml` | 构建与部署 | push 到 master |
| `contracts.yml` | 内容契约 + 契约层 / 头条 / 公众号测试 | push 或 PR 到 master |
| `video-pipeline.yml` | 在 Ubuntu 上真跑一遍 AIV：装系统依赖与内置字体，跑全部测试（含真的合成出一段成片） | push / PR 到 master 且动了 `video/**` |
| `site-guard.yml` | 根级站点契约测试：部署工作流的形状、文档死链与页内锚点、站点根路径前缀 | push 或 PR 到 master |

`contracts.yml` 里的四步：产出内容单元 → 内容契约闸门（违规即失败）→
契约层测试 → 两个 adapter 的测试。视频线（video）不在里面：它要 cairo 与
ffmpeg 这套系统依赖，失败模式是「渲染不出片」而不是「契约被破」；
它有自己的 `video-pipeline.yml`——在 Linux 上装依赖、装内置字体，跑全部测试，
测试里**真的会合成出一段成片**并按规格核对（逐像素基准那条在 Linux 上会
跳过并说明原因，不是红，也不是假装绿）。

`site-guard.yml` 跑的是根级 `tests/`：这些测试以前只在本机跑，CI 里没有任何
地方执行它们，于是「测试全绿」和「CI 绿」是两件事。它**不阻塞部署**
（独立工作流、独立并发组），挂了只报注解。

### 给一篇文章声明发布平台

发布候选集的**唯一依据**是母稿 front matter 里的 `platforms`：

```yaml
---
platforms:
  - toutiao
  - wechat
---
```

不写 `platforms` 的文章不进任何平台的候选集——这是内容契约 §4.1 的规定，
不是调度器的默认行为。声明之后：

```bash
cd publish && python3 -m publishkit.cli schedule candidates   # 看候选集
cd publish && python3 -m publishkit.cli schedule weekly --dry-run
```

---

## 八、当前状态

| 模块 | 状态 |
| --- | --- |
| 站点构建 | 成熟，CI 全自动（2~3 分钟） |
| 内容契约 | 闸门已进 CI（`contracts.yml`）；578 个内容单元 0 违规 |
| 公众号 | 已实现到**草稿箱**；发表接口无权限（`48001`），自动化边界 = 自动进草稿箱；**已进契约层**（能力声明 + outbox 幂等键） |
| 头条号 | 出包可用；账号未认证，API 权限开不了，走「出包 + 人工发」 |
| 视频号 / B 站 | 出包 + 人工发布清单；B 站 `ARC_BASE` 未开通 |
| AIV | 六期已出片（EP01~EP06）；契约化流程稳定；抖音那两档（无品牌 / 竖版）已就位 |
| 审校 | 文档侧（`review/`）与视频侧（`video/review/`）两套机制都落地了；视频侧六期文本层跑完，成片层只有本机有成片的 EP06 跑过 |
| 发布调度 | 契约层与 CLI 已落地，周键幂等已接上；候选集由母稿 `platforms` 决定 |
| 顶层设计 | 2026-11-18 定了主题 → 草稿箱 → 两条流水线 → 六个平台；站点已登记进平台层（`platforms/blog/`） |

**平台与契约层的关系**（六个平台，三个档位）：

| 平台 | 能力声明 | 幂等键写在哪 | 自动化停在哪 |
| --- | --- | --- | --- |
| 公众号 | `platforms/wechat/capability.toml` | `platforms/wechat/outbox/`（入库） | 草稿箱（人工发表） |
| 头条号 | `platforms/toutiao/capability.toml` | `platforms/toutiao/outbox/`（入库） | 出包（人工上传） |
| **个人站点** | `platforms/blog/capability.toml` | `platforms/blog/outbox/`（**现在空着**，账本待回填） | **整站部署**（`api_publish`：推上去就部署；出包是全量重建，不是逐篇） |
| 抖音 | `platforms/douyin/capability.toml` | `platforms/douyin/outbox/`（入库） | 出包 + 浏览器上传 + 人工确认发表（个人主体拿不到 API 凭据） |
| 视频号 | `platforms/channels/capability.toml` | `platforms/channels/outbox/`（入库） | 出包 + 人工发布清单 |
| B 站 | `platforms/bilibili/capability.toml` | `platforms/bilibili/outbox/`（入库） | 投稿包（`ARC_BASE` 未开通） |

**还没就绪的三处**（详见各 spec 的「待验证项」）：

1. 站点**看不到视频**：video widget 关着、菜单无视频入口、outbox 也没汇总成
   `publish_index`。
2. 调度器**从未真正跑过**：`publish/deploy/` 里的 cron / launchd 模板还没安装，
   `publish/schedule.json` 仍是空的。
3. **视频审校还没闭环**：六期的文本层信号已出，成片层只有本机有成片的 EP06 跑过；
   「改稿 → 重出片 → 复审成片层」这一圈还没走完（见 `video/review/INDEX.md` 的批次表）。

---

## 九、延伸阅读

| 文档 | 内容 |
| --- | --- |
| [`internal/blog/架构.md`](internal/blog/架构.md) | 站点构建链路的操作手册（改文章、改样式、CI 步骤） |
| [`publish/spec/00-架构设计.md`](publish/spec/00-架构设计.md) | 多平台发布架构：内容契约 · 能力模型 · 清单 · 幂等 · 展示扩展点 |
| [`publish/spec/06-发布计划与调度.md`](publish/spec/06-发布计划与调度.md) | 调度层：候选集、选题规则、周键、触发器、失败与重试 |
| [`publish/spec/07-视频发布契约.md`](publish/spec/07-视频发布契约.md) | 视频发布：视频单元、成片预检、切片规则、状态机 |
| [`video/README.md`](video/README.md) | 视频生产线说明与换期流程 |
| [`video/review/README.md`](video/review/README.md) | 视频审校：文本层 `VT-*` 与成片层 `VV-*`、抽帧方法、一期一条记录 |
| [`review/README.md`](review/README.md) | 博客内容审校：文档侧的同构机制（`tools/review-check.py`） |
| [`video/人格规范.md`](video/%E4%BA%BA%E6%A0%BC%E8%A7%84%E8%8C%83.md) | 小象是谁、怎么想、怎么讲（9 条可机检规则） |
| `platforms/README.md` | 第三方平台层总览：六个平台、五条共同规矩、核心流程五步、加一个平台要做什么 |
| `platforms/<plat>/docs/` | 各平台 adapter 的设计与实施计划（wechat / toutiao / blog / douyin / channels / bilibili） |
| [`review/specs/2026-11-18-顶层设计与目录调整.md`](review/specs/2026-11-18-顶层设计与目录调整.md) | 顶层设计：主题、草稿箱、两条流水线、六个第三方平台 |
