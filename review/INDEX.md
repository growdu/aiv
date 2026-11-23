# 审校进度索引

审校范围：`docs/` 全树（4 个文件——1 篇文章、2 张目录页、1 份模块说明
`docs/README.md`，编译器按保留名跳过）里**面向读者的技术文章**（1 篇）。
非内容（站点目录页、代码仓库说明、内部工作文档、外链指北、模块说明、只有标题的未成稿）、
速查/清单/操作类、非技术内容与**转载稿**共 3 篇已排除——分类与逐篇清单见
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
| 信号 | 检查器给出的 warn 级信号条数（warn 规则共 8 条，所以是 0~8；全树实测最高 3 条） |
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

2026-11-23 起，`docs/` 里重新有内容了——第一篇稿子走完了
「`drafts/` → `review/` → `docs/`」这条流程，批次表也跟着重新起头。

| 记录 | 支柱 | 状态 | 信号 | 待确认 | 不阻塞 | 批次 |
| --- | --- | --- | --- | --- | --- | --- |
| [cap-consistency-tradeoffs](distributed/foundations/cap-consistency-tradeoffs.md) | distributed | 已合入 | 0 | 0 | 0 | 1 |

当前工作面（桶 5 技术文章）：

| 支柱 | 原文 |
| --- | --- |
| distributed | `docs/distributed/foundations/cap-consistency-tradeoffs.md` |

这一篇是 `distributed` 这条线的第一篇，也是整条流水线（编译器 → 内容契约 →
站点 → 平台 adapter）第一次吃上真实输入。新文章进来时按五个桶重新分一次，
工作面跟着长。
