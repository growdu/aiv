# browser —— 发布执行器（Playwright + Chromium）

> **这是什么**：用**真实浏览器**把「人在平台后台上手动做的事」做成脚本。
> 服务那些**没有公开发布 API** 的平台（如微信视频号、头条号草稿灌图、B站存草稿）。
> 它**不是 adapter**：adapter 出包（平台知识），browser 消费包做交互（浏览器交互知识），互不 import。

---

## 一、结构

```
browser/
├── browser/          # 引擎：cli / driver / session / probe / plan / doctor / pw + flows/
├── docs/             # 设计文档（00-设计.md）
├── scripts/          # 辅助脚本
├── selectors/        # 平台页面选择器
└── tests/            # 执行器私产测试
```

## 二、命令

```bash
python3 -m browser.cli doctor        # 这台机器能不能跑浏览器投稿
python3 -m browser.cli probe         # 打开平台后台，扫码，dump 页面结构
python3 -m browser.cli prepare <EP>  # 上传 + 填表 + 截图，不发表
python3 -m browser.cli submit <EP>   # 上传 + 填表 + 截图 + 确认后发表
python3 -m browser.cli bilibili-draft <EP>   # 传片 + 填表 + 存草稿
```

- **prepare 与 submit 分开**：「发表」是不可逆的外部可见动作。`prepare` 留下截图与「填了什么」清单；
  `submit` 会重走填表、点「发表」前打印截图路径并等确认。
- `bilibili-draft` 只到「存草稿」（B站「立即投稿」会公开，存草稿只进创作中心）。

## 三、层间关系（必守）

- **消费包，不 import adapter**：读 `platforms/*/outbox/*.json`（公开的契约文件），不 import 平台代码。
- 三层分离：adapter（出包）/ 契约层（出什么、发到哪）/ browser（点哪个按钮、往哪个框填字）。
- **头条号 flow 是更新已有草稿**（带 `pgc_id`），不是新建——没有平台侧草稿 id 就不做。

## 四、AI 如何使用本目录

- **改这里先跑**：`cd browser && python3 -m pytest tests/ -q`。
- 它只服务**没有公开 API** 的平台；有 API 的平台走 adapter 出包。
- 「不可逆的发表」动作一定要经人确认（`submit` 的等确认、`bilibili-draft` 只存草稿）。
- 设计说明见 [`docs/00-设计.md`](docs/00-设计.md)，命令口径见 [`browser/cli.py`](browser/cli.py)。
