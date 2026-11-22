# publish/ —— 契约与发布层（能力模型 / 内容契约 / 调度 / 快照）

> **这是什么**：内容与发布之间的**契约层**。它定义「一个内容能不能发、发到哪、怎么调度」，
> 出包与调度都照这套走。**它不 import 任何平台层，平台层也不 import 它**——
> 两层只通过**文件**对话（这是硬规矩，由测试守着）。

---

## 一、目录结构

```
publish/
├── publishkit/    # 契约层的代码实现（出包、调度、能力模型、快照）
├── spec/          # 契约的权威规格（00-架构设计.md 是总纲）
├── deploy/        # 部署模板（crontab / launchd / github-action）
├── plans/         # 实施计划（视频发布、长视频三档）
├── schedule.json  # 调度状态（周键、已选稿、失败记录）
└── tests/         # 契约层自己的测试套件
```

### 子模块速览

| 目录 | 是什么 |
|------|--------|
| [`publishkit/`](publishkit/) | 契约层代码：能力模型、内容契约、出包、调度、快照、URL 读取器、退出码表 |
| [`spec/`](spec/) | 契约的权威文档，`00-架构设计.md` 是总纲 |
| [`deploy/`](deploy/) | 三个部署模板（crontab / launchd.plist / GitHub Action），不是流水线代码 |
| [`plans/`](plans/) | 实施计划，是过程文档不是契约 |
| `tests/` | 契约层验收：`cd publish && python3 -m pytest tests/ -q` |

## 二、出包与调度

```bash
cd publish
python3 -m publishkit.cli schedule weekly [--dry-run]   # 按周选稿
python3 -m publishkit.cli schedule status                # 看调度状态
python3 -m publishkit.cli schedule candidates            # 看可选稿
python3 -m publishkit.cli publish <content_id> --platform <id> [--publish]
```

## 三、AI 如何使用本目录

- **改这里先跑**：`cd publish && python3 -m pytest tests/ -q`。
- **层间零 import**：契约层不 import 平台层，平台层不 import 契约层；缝是**文件**
  （`content/units/`、`capability.toml`、`outbox/*.json`、`rules/urls.json`）。
- 改契约规则先看 [`spec/00-架构设计.md`](spec/00-架构设计.md)（§4.1/§4.2 是内容契约字段表）。
- 调度器**只做调度**（选内容、写周键、记失败），不出包、不上传——那是平台 adapter 的活。
- 要发某个平台 → 去对应 `../platforms/<平台>/`，本层只决定「发什么、发到哪」。
