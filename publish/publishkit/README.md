# publish/publishkit/ —— 契约层的代码实现

> **这是什么**：发布契约的可执行一侧。能力模型、内容契约校验、出包、调度、快照——
> 全在这里。**只定规则、做调度，不出包不上传**；平台 adapter 才是执行者。

---

## 一、模块清单

| 模块 | 干什么 |
|------|--------|
| `capability.py` | 能力模型：读各平台 `capability.toml`，知道谁能发什么、限额多少、什么档位 |
| `contract.py` | 内容契约校验：字段表与格式规则的**实现**（规则文档在 `../spec/`） |
| `manifest.py` | 出包清单：把一篇内容单元按平台能力组装成可发的包 |
| `schedule.py` | 调度器：选内容、写周键、记失败；**只调度不上传** |
| `episode.py` | 期号/视频坐标的口径实现（与 `video/pipeline/pyv/episodes.py` 同一套） |
| `urls.py` | URL 规则读取器（读 `rules/urls.json`） |
| `exit_codes.py` | 退出码表（0 成功 / 1 参数错 / 2 前置不足 / 3 接口或写盘错），各层取值处 |
| `cli.py` | 命令行入口（`schedule weekly/status/candidates`、`publish`） |

## 二、层间关系（必守）

- **不许 import 任何平台层**；`../tools/paths.py` 与 `../tools/url_rules.py` 也**不许**反向 import 本包。
- 两层之间的接缝是**文件**：`content/units/`、`capability.toml`、`outbox/*.json`、`rules/urls.json`。
- 退出码的语义在 `exit_codes.py` **定死**，各层 CLI 从这里**取值**——不是各自定义。

## 三、AI 如何使用本目录

- **改这里先跑**：`cd .. && python3 -m pytest tests/ -q`（在本目录内）。
- 改校验规则 → 先看 `../spec/00-架构设计.md` 的字段表，再改 `contract.py`，**不要另写一份规则**。
- 跑调度：`PYTHONPATH=.. python3 -m publishkit.cli schedule weekly`。
- 新增/改平台能力 → 平台层改自己的 `capability.toml`（契约层只是读取），**不要在契约层写死平台**。
- 期号/视频坐标改动 → 同步 `episode.py` 与 `video/pipeline/pyv/episodes.py`（同一口径两处）。
