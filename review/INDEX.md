# 审校进度索引

审校范围：`docs/` 全树（9 个文件——6 张目录页、1 份模块说明
`docs/README.md`，编译器按保留名跳过、2 篇技术文章）里**面向读者的技术文章**（2 篇）。
非内容（站点目录页、代码仓库说明、内部工作文档、外链指北、模块说明、只有标题的未成稿）、
速查/清单/操作类、非技术内容与**转载稿**共 7 篇已排除——分类与逐篇清单见
[`scope/2026-11-14-scope-classification.md`](scope/2026-11-14-scope-classification.md)。

> 转载稿（正文顶部有 `> 来源:`，署名他人）不按原创稿审改——改写等于改别人的东西。
> 怎么处理（保留标注 / 删除 / 重写）是站长的决定。

规范见 [`README.md`](README.md)，落地机制见
[`specs/2026-11-13-content-review-design.md`](specs/2026-11-13-content-review-design.md)，
实现计划见 [`plans/2026-11-13-content-review.md`](plans/2026-11-13-content-review.md)。

## 怎么读这张表

| 列 | 含义 |
| --- | --- |
| 记录 | 审校记录；逐条建议 |
| 支柱 | `docs/` 下的一级目录 |
| 状态 | 待审 → 审校中 → 建议中 → 已确认 → 已合入 |
| 信号 | 检查器给出的 warn 级信号条数（warn 规则共 16 条，所以是 0~16） |
| 待确认 | 「事实待核」里还没销掉的条目数——状态为「已合入」时必须是 0 |
| 不阻塞 | 标了「不适用」的条目数：事实本身还没核实，但本次改动没碰它，不卡合并 |
| 批次 | 试点 / 1 / 2 … |

**信号为 0 不等于文章没问题**——检查器只出机械信号，技术深度、定位、语气这类
判断是人工做的，机械信号干净的文章照样可能需要改。

## 进度

审校记录是**内容**：内容清空，记录跟着清空，索引里的批次表也清空了。
规则留在 [`README.md`](README.md) 与
[`scope/2026-11-14-scope-classification.md`](scope/2026-11-14-scope-classification.md) 里，
新文章进来时按那两份重新起记录。

2026-11-25 三篇稿子全部撤下——`distributed` 的 CAP 一篇与两篇 PostgreSQL 19 的稿子，
连审校记录一起删。`docs/` 回到「只有目录页」的状态。

同日新稿进来：PostgreSQL 19 的第一篇（模块、进程与扩展）过审，
落 `docs/source-tracks/postgresql/getting-started/`，两张目录页随它一起改指。
第二篇（行锁）同日过审，落 `docs/source-tracks/postgresql/transaction-mvcc/`，
L4 那一行从「未开目录」变成链接，系列页与 L4 站页随它一起改指。

| 记录 | 支柱 | 状态 | 信号 | 待确认 | 不阻塞 | 批次 |
| --- | --- | --- | --- | --- | --- | --- |
| [postgresql19-architecture](source-tracks/postgresql/getting-started/postgresql19-architecture.md) | source-tracks | 已合入 | 0 | 0 | 0 | 1 |
| [postgresql19-row-lock](source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md) | source-tracks | 已合入 | 0 | 0 | 0 | 1 |

当前工作面（桶 5 技术文章）：

| 支柱 | 原文 |
| --- | --- |
| source-tracks | `docs/source-tracks/postgresql/getting-started/postgresql19-architecture.md` |
| source-tracks | `docs/source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md` |

新文章进来时按五个桶重新分一次，工作面跟着长。
