# `api/` —— 创作平台的 HTTP 门面

这是**创作平台**（`front/` + `api/`）的后端。它不是一个新流水线，
它是既有流水线**上面的一层观察窗与编辑器**。

## 它是什么

**一个 HTTP 门面，不含业务规则。** 它只做三件事：

1. **读文件**——母稿、草稿、审校记录、能力清单、发布快照。
2. **调 CLI**——审校、出片、出包，全部走 `subprocess`，命令与手敲命令行**逐字等价**。
3. **起后台作业**——把一条命令放到后台线程里跑，留日志，供界面轮询与 SSE 订阅。

**流水线是唯一的真相。** 门面的输出（成片、内容单元、发布快照）都是流水线产出的，
门面只是把它们端出来。

## 它不是什么

- **不是新的流水线。** 门面的作业调的就是既有命令：`make EP=… all`、
  `python3 tools/review-check.py …`、`python3 -m <平台>.cli package …`。
  门面**不改**这些命令的行为。
- **不是内容源。** 内容真相在 `docs/` 与 `video/episodes/`。
- **不是判据。** 「过审」在门面这里**只是复制**；建审校记录、补 INDEX、提交
  三步留给人。

## 缝在哪

| 缝 | 形状 |
| --- | --- |
| `front/` ↔ `api/` | **HTTP**（`http://127.0.0.1:8787`，前缀 `/api`） |
| `api/` ↔ 仓库 | **subprocess + 文件读**——不 import 契约层 |

**`api/` 不 import `publish/publishkit/`**（规格 D12）。也不 import 任何
`platforms/<平台>/` 包——出包一律走 subprocess，平台的包名由**扫目录**得到，
不写死。

## 怎么跑起来

**在仓库根跑**（`api` 要 import 得到）：

```bash
python3 -m pip install -r requirements/api.txt
uvicorn api.app:app --port 8787
```

开发时另开一个终端（**在 `front/` 里跑**）：

```bash
cd front && npm install && npm run dev
```

打开 <http://127.0.0.1:5173/>。vite 的 dev server 把 `/api` 代理到 8787。

## 怎么验收

**验收按模块拆开**——这一条只跑自己的套件，不跑根套件：

```bash
cd api && python3 -m pytest tests/ -q
```

## 目录

```
api/
  app.py            FastAPI app 装配：CORS、路由注册、/api/health
  routes/           一条路由一个文件（按资源分，不按平台分）
  services/         业务逻辑都在这里；routes 只做参数搬运
  tests/            套件与夹具（夹具只造语料，不依赖仓库现有内容）
```

**路由只按资源分**（`/api/drafts`、`/api/episodes`…），**不按平台分**——
平台名不在路由里，也不在源码里；平台清单是扫 `platforms/*/capability.toml` 得到的。
