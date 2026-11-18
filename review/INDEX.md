# 审校进度索引

审校范围：`docs/` 全树（621 篇）里**面向读者的技术文章**（413 篇）。
非内容（站点目录页、代码仓库说明、内部工作文档、外链指北、只有标题的未成稿）、
速查/清单/操作类、非技术内容与**转载稿**共 208 篇已排除——分类与逐篇清单见
[`scope/2026-11-14-scope-classification.md`](scope/2026-11-14-scope-classification.md)。

> 转载稿（正文顶部有 `> 来源:`，署名他人）不按原创稿审改——改写等于改别人的东西。
> 怎么处理（保留标注 / 删除 / 重写）是站长的决定。

规范见 [`README.md`](README.md)，落地机制见
[`specs/2026-11-13-content-review-design.md`](specs/2026-11-13-content-review-design.md)，
实现计划见 [`plans/2026-11-13-content-review.md`](plans/2026-11-13-content-review.md)。

## 怎么读这张表

| 列 | 含义 |
| --- | --- |
| 记录 | 审校记录；点进去是逐条建议 |
| 支柱 | `docs/` 下的一级目录 |
| 状态 | 待审 → 审校中 → 建议中 → 已确认 → 已合入 |
| 信号 | 检查器给出的 warn 级信号条数（warn 规则共 8 条，所以是 0~8；全树实测最高 3 条） |
| 待确认 | 「事实待核」里还没销掉的条目数——状态为「已合入」时必须是 0 |
| 不阻塞 | 标了「不适用」的条目数：事实本身还没核实，但本次改动没碰它，不卡合并 |
| 批次 | 试点 / 1 / 2 … |

**信号为 0 不等于文章没问题**——检查器只出机械信号，技术深度、定位、语气这类
判断是人工做的，机械信号干净的文章照样可能需要改。

## 进度

已审 18 篇（首批试点：数据库内核四支柱 5 篇），批次 1 按信号密度新增 5 篇，
批次 2 按信号密度清完 cluster 支柱的 2 信号队列（8 篇，已核空）。
同标题的两对文章已各自合并为一篇：`corosync-down网卡仍处于多数派`（并掉 `-1` 版）
与 `两地三中心`（并掉 `tptc_improve`）——站点上不再保留重复的第二篇。
范围扩到全树后按信号密度排序继续——排序依据见范围分类文档的「逐支柱分布」。

图示可读性规则（`FIG-01` 图太长该拆 / `FIG-02`「下图」离图太远）加入后，
全树 621 篇里 84 篇命中 `FIG-01`、5 篇命中 `FIG-02`。已审文章中
`一文读懂openguass dcf网络模块`（6 张超长链式流程图）与 `06-heap-and-mvcc`
（HeapTuple 结构图 + UPDATE 流程图）的信号数因此各 +1。
**已合入的文章不保证信号为 0**——规则是后加的，之前的稿子没按新规则重审。

> `FIG-01` 的判定原先会抖：算「一条流程多长」时由 `set` 的迭代顺序决定
> DFS 从哪个框出发，而字符串哈希每进程随机 —— 同一棵树连跑四次，
> warn 在 509 / 510 之间来回跳（`tools/review-check.py` 的 `_longest_path`）。
> 2026-11-17 改成「先做一次确定性 DFS 找回边、切成 DAG 再算最长路径」，
> 现在连跑四次结果逐条相同，全树 warn 稳定在 **487**
> （工程与语言这一块搬完之后是 509：14 个旧目录页换成 6 个新目录页，warn 跟着少 6 条；
> 数据面这一块搬完之后再少 2 条 —— 7 篇内部稿移出 `docs/`；
> AI 工具与实践这一块搬完之后是 494：净少 13 条 = 目录页换了一批
> （删 2 个旧的、补 5 个新的）**外加** 19 条 `STR-04` 误报被修掉 ——
> 站上 `%20` 编码的链接指向带空格的文件名，检查器原来一律判成断链）；
> 「Linux 与网络」这一块搬完之后是 489：净少 5 条 = 删 5 个旧目录页
> （`protocol/`、`storage/`、`computer_communication/`、`programmer_self_cultivation/`、
> `environment/`，每个 -1 条 `DEP-00`），补 1 个新的（`engineering/observability/`，+1），
> `networking/_index.md` 因为多列 7 篇而不再命中 `DEP-00`（-1）——
> 5 - 1 - 1 = 5；
> 「手记副线」这一块搬完之后是 487：净少 2 条 = `docs/blog/` 里那两篇
> 各带 1 条 `AIF-03` 的内部稿（架构、重构方案）移出了 `docs/`，
> 留站的 4 篇一条信号都没多也没少）。

站内链接另有一把尺子：`tools/check-internal-links.py`（2026-11-17 新增）。
母稿侧查相对链接能不能解析到目标，产物侧查 `public/` 里的站内 href 有没有落到
不存在的页面上。首跑抓出 **11 条产物侧死链**（线上的死链，多在
`db/opengauss-*` 两篇文章里，指向 `db/postgresql/` 下少了一级的路径），
母稿侧 **62 条**相对链接解析不到（多在 `database/_index.md` —— 分类页本身
不发，读者看不见，但迁移时会咬人）。这两组数字是**迁移前**的基线，
搬家后必须回到 0（死链）/ 不增加（母稿侧）。

**PostgreSQL 试点搬完后的实测（2026-11-17）**：产物侧 **11 → 0**
（132457 条站内 href 全通）；母稿侧 **62 → 5**，剩下的 5 条逐条核对过，
都是迁移前就在的误报（`{image_url}` 模板占位符、`life/shehui/_index.md` × 2、
两个代码块里的 `DatumGetPointer(...)` / `order_date`），在 master 上逐字相同。

**Linux 块搬完后的实测（2026-11-17）**：`docs/linux/` 38 篇 + `docs/network/` 9 篇
（47 篇）收进 `docs/source-tracks/linux/`，分成 5 个系列：日常操作与工具 12、
存储与文件系统 1、内核机制与驱动 14、内存与动态链接 9、网络协议与抓包 11。
母稿侧死链 5 → 5（没动，逐条核对过）；**产物侧死链 0**（144689 条站内 href 全通）；
日期漂移 0（`capture-dates.py --check` 逐篇比 572 篇）；
47 篇正文逐字节相同（合并 master 后重比：全树 1721 个文件，
只有 63 个改了路径，内容逐字节相同，另 6 个是新建的目录页）；
学习路径分类 572 篇逐篇比对，0 处变化；
`publish/outbox/` 46 份快照按新路径改名，全部 567 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（源码侧能说死：master 的树与合并后的树，
1309 张唯一 mermaid 源码的集合完全相同，0 张新增、0 张消失）。

**分布式块搬完后的实测（2026-11-17）**：`docs/cluster/` 61 篇 + `docs/openguass/` 4 篇
（65 篇 + 26 个资源）收进 `docs/distributed/`，分成 6 个系列：分布式基础 7、
一致性协议 28、高可用与容灾 9、分布式存储 5、选型与对比 4、实战与故障现场 11
（合并了一对**逐字节相同**的 raft 副本，实际落地 64 篇）。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（152963 条站内 href 全通）；
日期漂移 0（`capture-dates.py --check` 逐篇比 574 篇）；
65 篇正文逐字节相同（62 篇一字不差，3 篇只差跟着新位置重算的相对链接），
26 个资源一字不差；
学习路径分类 581 篇逐篇比对「赛道 + 阶段」，**0 处变化**
（少的那篇是合并掉的重复副本，`distributed` 赛道 65 → 64）；
`publish/outbox/` 60 份快照按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（产物侧唯一源码 1308 张；源码侧：唯一 mermaid 源码的集合完全相同）。
顺带修掉四处：重复副本合并后两个旧 URL 都在（重定向表的键现在可以带一段日期）、
带空格的文件名在模板里的链接原来改不掉（「只编码空格」那一种写法补上了）、
落地页的白名单改成逐篇列出（`DISTRIBUTED_DB_KERNEL`）、
落地页里那条指向被合并副本的链接也改成了幸存那篇的真实地址（产物侧查出的 1 条死链）。

**工程与语言块搬完后的实测（2026-11-17）**：`docs/` 下 14 个平铺目录
（`alg/`、`base/`、`language/`、`page/`、`faq/`、`code/`、`edit/`、`opc/`、`tools/`、
`docker/`、`es/`、`go_web/`、`vue/`、`web/`）共 109 篇 + 690 个资源收进
`docs/engineering/`，分成 5 个系列：计算机基础与语言入门 31、速查与清单 12、
编译、测试与调试 27、容器与环境 15、Web、前端与搜索 24。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（145298 条站内 href 全通；
搬家前是 152963 条，少的那 7665 条是 14 个平铺分类收成 6 个之后
每个页面的「分类」清单各少 7 条 —— 页面数反而 1187 → 1294）；
日期漂移 0（`capture-dates.py --check` 逐篇比 574 篇）；
109 篇正文逐字节相同（108 篇一字不差，1 篇只差跟着新位置重算的相对链接），
690 个资源一字不差；
学习路径 570 篇逐篇比对「赛道 + 阶段」，**赛道变了 0 篇、阶段变了 12 篇**
（`page/` 的 11 篇与 `faq/` 的 1 篇收进「速查与清单」，阶段各挪一位）；
**迁移幂等**：同一张表再跑一遍 0 处变更（链接改写 0、搬运 0、
29 个目录页重新生成但内容一字不差、四个常量文件逐字节相同、外部引用 0 处）；
`publish/outbox/` 104 份快照按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（产物侧唯一源码 1308 张）；
旧地址一个没丢：重定向页 337 → 446（+109 篇）、分类重定向 16 → 30（+14 个平铺分类），
`/categories/工具/` 这类旧地址现在是指向新分类的 meta refresh 跳转页。
顺带修掉四处：链接重写的捷径把「目标没动」当成了「相对位置没变」
（`docs/engineering/foundations/file.md` 的 3 条相对链接差点成死链）、
外部引用改写再跑一遍会把前缀叠两遍（审校记录里 11 条叠了两遍）、
落地页补了一行指向工程与语言、审校记录里的「`docs/code/` 开头」机械规则跟着搬家。
顺带多了 32 条搜索索引：`page/` 12 篇 + `tools/` 20 篇第一次能被搜到
（老目录名在「元文档目录」名单里，搬进 `engineering/` 就不在了）。

**数据面块搬完后的实测（2026-11-17）**：`docs/dpdk/` 26 篇 + `docs/vpp/` 18 篇
（44 篇 + 154 个资源）收进 `docs/source-tracks/dpdk/`，分成 4 个系列：
环境与入门 18、架构与核心数据结构 7、插件与业务开发 8、测试、验证与性能 4
（DPDK 与 VPP 合并成一条主线，不拆到 `engineering/`）。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（150,429 条站内 href 全通）；
日期漂移 0（`capture-dates.py --check` 逐篇比 567 篇）；
44 篇正文 + 154 个资源逐字节相同（198 个一字不差、不同 0 个；
另 2 个是旧目录页，被 5 个新目录页取代）；
学习路径 574 篇逐篇比对「赛道 + 阶段」，**赛道变了 0 篇、阶段变了 0 篇**
（L1:18 L2:7 L3:8 L4:4，少的 7 篇正是移出 `docs/` 的那 7 篇）；
发布快照 42 份按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（唯一源码 1,309 张）；
旧地址一个没丢：重定向页 446 → 483（+37 篇）、分类重定向 30 → 32
（`/categories/DPDK/`、`/categories/VPP/` 现在指向 `/categories/源码主线/DPDK与VPP/`）。
**这一块第一次真的执行了 §4.3 那个「不发布（移出 `docs/`）」的桶**：
7 篇内部工作稿连同 13 张图片搬进 `internal/`，不再发布面；
为此改了两处 `tools/migrate-tree.py`：`out_map` 的整目录展开要在**搬之前**算
（搬完旧目录就没了，展开不出任何文件，日期表会给已经不存在的路径留记录），
以及 bundle 目录（`<目录>/index.md`）整体跟着它的文章走
（bundle 目录里常常还带一包图片，两条别的规则都会让图片跟丢）。
顺带两处分类名上的坑：目录名是 slug 化的、分类显示名不是
（`write_category_redirects()` 用 `quote()` 不是 `slugize()`，
显示名里带空格或 `·` 会生成一个指向不存在页面的跳转，所以定成 `DPDK与VPP`）；
三级链是「源码主线 → DPDK与VPP → 系列」，
`/categories/源码主线/DPDK与VPP/环境与入门/` 这样的地址真实存在。
首页首屏的分类徽章少了 `DPDK`、`VPP` 两块 —— 徽章按**分类名**反查路径，
两个分类合并后旧名不存在了，徽章被跳过（与之前合并 `openGauss`/`集群`/`工具` 同例）；
徽章表在 `tools/patch-theme.py` 里，不在「只动 `docs/`」的范围内，**这次没改**。
这一块搬完之后合并了上游的 39 个提交：发布快照整个下沉成
`platforms/<平台>/outbox/`（566 份，42 份改名在新目录里重做一遍），
`docs/` 全树变成 **628 篇**（565 母稿 + 63 目录页），学习路径语料 **574 篇**，
`docs/` 的 p90 仍是 **22,609**（628 篇重算；上游那 39 个提交自己也刷过一次，
632 篇口径 22,304，两边各自实测互相印证）。

**AI 工具与实践块搬完后的实测（2026-11-17）**：`docs/ai/` 29 篇 + `docs/chatgpt/` 2 篇
（31 篇 + 34 个图片资源）收进 `docs/engineering/ai-tooling/`，分成 4 个系列：
AI认知与入门 19、AI工具箱 5、把AI变成杠杆 2、AI视频平台设计 5。
这一块是**第一个挂在别的项目下面的** —— `engineering/ai-tooling/` 挂在
`engineering/` 下面，于是分类链第一次是三层：
工程与语言 → AI工具与实践 → 系列。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（156,165 条站内 href 全通；
比数据面那块的 150,429 条多 5,736 条 —— 三层分类链让每个页面的「分类」清单多了一行）；
站点里 8,927 条图片引用逐条查过，**指向不存在文件的 0 条**；
日期漂移 0（`capture-dates.py --check` 逐篇比 568 篇）；
31 篇正文 + 34 个资源逐字节相同（一字不差）；
学习路径 568 篇逐篇比对「赛道 + 阶段」，**赛道变了 0 篇、阶段变了 0 篇**
（ai-tools 31 篇 L1:19 L2:5 L3:2 L4:5）；
发布快照 30 份按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（唯一源码 1,309 张）；
旧地址一个没丢：重定向页 483 → 514（+31 篇）、分类重定向 32 → 34
（`/categories/AI/`、`/categories/ChatGPT/` 现在指向
`/categories/工程与语言/AI工具与实践/`）；
`docs/` 全树变成 **631 篇**（565 母稿 + 66 目录页），学习路径语料 **574 篇**，
`docs/` 的 p90 刷到 **22,304**（631 篇重算）。
这一块顺带修掉三处：

1. **目录页合并时保住小节之间的空行**（`tools/migrate-tree.py`）——
   原来每跑一次迁移，不相关的目录页就会少一行空行
   （`source-tracks/postgresql/_index.md` 首当其冲）
2. **相对链接先 URL 解码再查存在性**（`tools/review-check.py`）——
   站上 `%20` 编码的链接指向带空格的文件名，原来一律判成断链；
   全树误报 19 条（跟 `tools/check-internal-links.py` 同一套规矩）
3. **摘要复核表里 20 条悬空路径** —— 13 条由迁移表改写（那张表用的路径形态是
   `docs` 相对路径，bundle 目录在 `flat` 形态下是拍平后的 `xxx.md`，对不上），
   7 条指向 `internal/`（那几篇已经移出发布面）

**「Linux 与网络」剩下的 18 篇搬完后的实测（2026-11-17）**：
`protocol/` 11 篇 + `storage/` 5 篇 + `computer_communication/` 1 篇 +
`programmer_self_cultivation/` 1 篇，收进
`source-tracks/linux/networking/`（+7）、`source-tracks/linux/filesystem/`（+5）、
`engineering/web-and-frontend/`（nginx，+1）、
`engineering/observability/`（OpenTelemetry 三篇，**新开的系列**）、
`engineering/engineering-practice/`（coredump，+1）、
`engineering/foundations/use-tools/`（vfox 使用指南，+1，**顺带改了文件名**）。
删掉 5 个旧目录页（`protocol/`、`storage/`、`computer_communication/`、
`programmer_self_cultivation/`、`environment/`），补 1 个新的
（`engineering/observability/`）。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（153,051 条站内 href 全通）；
站点里 9,355 条图片引用逐条查过，**指向不存在文件的 0 条**；
日期漂移 0（`capture-dates.py --check` 逐篇比 568 篇）；
18 篇正文 + 10 个图片资源逐字节相同（一字不差）；
学习路径 568 篇逐篇比对「赛道 + 阶段」，**赛道变了 6 篇**（全是
`linux-network` → `engineering`，其中三篇 OpenTelemetry 的阶段从 L4 落到 L2）、
**其余 562 篇赛道与阶段都没变**，语料 568 篇不变；
发布快照 17 份按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（唯一源码 1,309 张）；
旧地址一个没丢：重定向页 +18（`data/redirects.json` 497 → 515）、
分类重定向 +5（`协议`、`存储`、`计算机通信`、`程序员自我修养`、`环境配置`
各指向一个新分类）。

站内 href 比上一块**少 3,114 条**（156,165 → 153,051），
少的不是文章，是**分类清单**：每个页面的分类栏把全部分类都列一遍
（1,389 个页面，每页平均 51 条 `/categories/` 链接）。
删掉 5 个旧分类让 816 个页面各少 5 条 ≈ −4,080，
新增「可观测性」让这 816 个页面各多 1 条 ≈ +816。

**「手记副线」这一块搬完后的实测（2026-11-18）**：`docs/blog/` 9 篇 + `docs/life/blog-to-wechat/` 1 篇，
分成两堆：**留站的 5 篇**（博客搭建指南、阿里云 ECS 选购指南、mermaid 图渲染问题诊断与修复、
视频嵌入指南、从 Hexo 博客到公众号与视频号）收进 `docs/notes/site-ops/`，
分类链第一次是**两级**：`手记` → `站务手记`；
**移出 `docs/` 的 5 篇**（架构、部署到服务器、同步到公众号方案、同名文章-html-与-md-版本管理、
重构方案）搬进 `internal/blog/`（§4.3 那个「不发布」桶）。
删掉 3 个旧目录页（`blog/`、`blog/mermaid/`、`life/blog-to-wechat/`），补 2 个新的
（`notes/`、`notes/site-ops/`）。
母稿侧死链 5 → 5（没动）；**产物侧死链 0**（150,946 条站内 href 全通）；
站点里 8,864 条图片引用逐条查过，**指向不存在文件的 0 条**；
日期漂移 0（`capture-dates.py --check` 逐篇比 563 篇）；
10 篇正文逐篇比对：3 篇一字不差、7 篇只差跟着新位置重算的相对链接；
学习路径 574 篇逐篇比对「赛道 + 阶段」，**赛道变了 0 篇、阶段变了 0 篇**
（留站的 5 篇换了路径但赛道与阶段一字没动：博客搭建指南 L1、阿里云 ECS 选购指南 L1、
mermaid 诊断 L2、视频嵌入指南 L3、blog-to-wechat L3）；
移出 `docs/` 的 5 篇不在语料里了 —— 语料 **574 → 569 篇**（563 母稿 + 6 期视频）；
发布快照 10 份按新路径改名，全部 566 份快照逐个核过，
文件名与 `content_id` **0 处不一致**；
mermaid 渲染失败 **109 张，与搬家前持平**（唯一源码 1,309 张）；
旧地址一个没丢：重定向页 515 → **522**（+7 = 5 篇留站的 + 架构与重构方案那两条
「移出但对外发过」的）、分类重定向 36 → **39**（+3：`博客搭建`、`Mermaid`、`视频与自媒体`
各指向 `手记/站务手记`）；
`docs/` 全树变成 **621 篇**，审校工作面 418 → **413 篇**（少的 5 篇正是移出 `docs/` 的那 5 篇），
检查器 warn 489 → **487**（少的 2 条 = 架构与重构方案各带的 1 条 `AIF-03`）；
`docs/` 的 p90 仍是 **22,609**（621 篇重算；此前 627 篇口径同为 22,609）。
这一块顺带修掉四处：

1. **目录页标题取 front matter 的 `title:`**（`tools/migrate-tree.py` 的 `_read_title()`）——
   原来对全文做正则，把正文里的**示例**当成了标题：
   博客搭建指南的正文里有一段讲「怎么写 front matter」的 YAML 例子
   （`title: 分类中文名`），目录页上它的标题一度显示成「分类中文名」；
   视频嵌入指南同理显示成「视频合集」。口径跟 `tools/sync-hexo.py` 对齐。
2. **新增 `rewrite_out_refs()`**（`tools/migrate-tree.py`）——
   移出 `docs/` 的文章不在 `moves` 里（它们不再是站上的文章），
   `rewrite_refs()` 看不见它们，于是 README、规格文档、工具注释、复核表里
   指着 `docs/blog/架构.md` 的那些引用会悬空。新函数按三种形态改写：
   `repo`（仓库相对路径）、`docs`（docs 相对路径）、`cid`（内容单元 id）。
3. **`build_redirects()` 多收一个 `unpublish` 参数**（`tools/migrate-tree.py`）——
   它重建整张 `data/redirects.json` 时**只保留「带日期的旧键」**，
   手写进去的重定向活不过第二次运行；架构与重构方案这两条「移出但对外发过」的
   落点因此要单独登记在迁移表的 `unpublish_redirects` 一节里。
4. **改写引用时保留文件原来的换行符**（`tools/migrate-tree.py` 的 `_read_text()` / `_write_text()`）——
   Python 的通用换行模式会把 CRLF 读成 LF、写回时又按平台默认写 LF，
   主题里有一批文件本来是 CRLF 的，改写一行注释就把**整个文件**的换行符换了，
   diff 看着像全文重写。

**整站语料对账（2026-11-18）**：把开工那一刻的 577 篇逐篇对到现在的 569 篇 ——
**赛道变了 6 篇，阶段变了 34 篇**（赛道变的那 6 篇在第七块：
`linux-network` → `engineering`；阶段变的 34 篇 = 19 篇在 PostgreSQL 试点那一步、
12 篇在「工程与语言」那一步、3 篇在第七块 ——
后者是 `page/` 与 `faq/` 进 `engineering/cheatsheets/` 时从 L4/L2 落到 L1 的那批，
第四块已逐条记过；第七块那 3 篇是 OpenTelemetry 从 L4 落到 L2）。
**这不违反「不许改语义」**：赛道名、阶段标题、阶段目标一个字没动，
变的是同一篇文章落在哪个阶段 —— 旧规则的 `path_prefix` 粗到只管到
`pgsql/`、`page/` 这种目录，搬家后细到系列，文章自然落进更贴切的那个阶段。
篇数差也有账：577 − 9（移出 `docs/` 进 `internal/`）+ 7（`platform-meta/` 新成稿）
− 1（`distributed/consensus/raft协议动态调整quorum.md` 与 `distributed/consensus/raft协议动态调整quorum.md`
**逐字节相同**，搬家时合成一篇）
− 5（「手记副线」这一块里移出 `docs/` 进 `internal/blog/` 的 5 篇）= **569**，一篇没丢。

**部署链路顺带修掉一处断点（2026-11-17）**：连续两个 push 的 Deploy Hexo
都断在 "Upload build artifact" —— 旧分类「PostgreSQL 源码修炼之路:内核深度拆解专题」
的跳转页目录名带冒号，GitHub 的 upload-artifact 拒绝 `:*?"<>|`，
一个带冒号的目录就让整个产物传不上去。那个分类线上从来没出现过，
所以那一页不再生成（`tools/sync-hexo.py` 对文章重定向和分类重定向都加了这道检查），
`tests/test_sync_hexo_redirects.py` 守着。

| 记录 | 支柱 | 状态 | 信号 | 待确认 | 不阻塞 | 批次 |
| --- | --- | --- | --- | --- | --- | --- |
| [postgresql-mvcc](source-tracks/postgresql/transaction-mvcc/postgresql-mvcc.md) | source-tracks | 已合入 | 0 | 0 | 1 | 试点 |
| [postgresql-logical-replication-worker-model](source-tracks/postgresql/logical-replication/postgresql-logical-replication-worker-model.md) | source-tracks | 已合入 | 0 | 0 | 1 | 试点 |
| [06-heap-and-mvcc](source-tracks/postgresql/transaction-mvcc/learning-path/06-heap-and-mvcc.md) | source-tracks | 已合入 | 1 | 0 | 2 | 试点 |
| [checkpoint机制浅析](source-tracks/postgresql/wal-and-recovery/checkpoint机制浅析.md) | source-tracks | 已合入 | 0 | 0 | 0 | 试点 |
| [分布式一致性协议](distributed/foundations/分布式一致性协议.md) | distributed | 已合入 | 0 | 0 | 2 | 试点 |
| [file](engineering/foundations/file.md) | engineering | 已合入 | 0 | 0 | 3 | 1 |
| [corosync-down网卡仍处于多数派](distributed/field-notes/corosync-down网卡仍处于多数派.md) | distributed | 已合入 | 0 | 0 | 6 | 1 |
| [tptc](distributed/ha-and-dr/tptc.md) | distributed | 已合入 | 0 | 0 | 8 | 1 |
| [从原理到实践，彻底告别 IPv6 上网不稳定的问题](source-tracks/linux/networking/从原理到实践，彻底告别 IPv6 上网不稳定的问题.md) | source-tracks | 已合入 | 0 | 0 | 6 | 1 |
| [Postgresql存储、索引及系统优化、主备切换](source-tracks/postgresql/replication-ha/Postgresql存储、索引及系统优化、主备切换.md) | source-tracks | 已合入 | 1 | 0 | 2 | 1 |
| [raft重要概念](distributed/consensus/raft重要概念.md) | distributed | 建议中 | 2 | 4 | 0 | 2 |
| [sanlock实现共享corosync共享存储仲裁](distributed/field-notes/sanlock实现共享corosync共享存储仲裁.md) | distributed | 建议中 | 2 | 6 | 0 | 2 |
| [中移动数据库停库问题分析](distributed/ha-and-dr/中移动数据库停库问题分析.md) | distributed | 建议中 | 2 | 8 | 0 | 2 |
| [ha元信息常见存储方式](distributed/ha-and-dr/ha元信息常见存储方式.md) | distributed | 建议中 | 2 | 5 | 0 | 2 |
| [corosync-qdevice使用](distributed/field-notes/corosync-qdevice使用.md) | distributed | 建议中 | 2 | 5 | 0 | 2 |
| [corosync qnet挂死场景分析解决](distributed/field-notes/corosync qnet挂死场景分析解决.md) | distributed | 建议中 | 2 | 7 | 0 | 2 |
| [从两地三中心到OceanBase的多地多中心 - 墨天轮](distributed/distributed-storage/从两地三中心到OceanBase的多地多中心 - 墨天轮.md) | distributed | 建议中 | 2 | 8 | 0 | 2 |
| [一文读懂openguass dcf网络模块](distributed/consensus/一文读懂openguass dcf网络模块.md) | distributed | 建议中 | 3 | 7 | 0 | 2 |
