# platforms/douyin —— 抖音视频平台 adapter

> **这是什么**：把视频线的内容单元 + 成片组装成可发到抖音的发布包。
> **自动化档位 `manual`**——出包后由人工上传（个人主体拿不到开放平台 OAuth2 凭据，
> 走浏览器/创作者中心后台），真发出去用 `mark published` 回填链接。
> 与视频号同一套路。

---

## 一、结构

```
platforms/douyin/
├── capability.toml   # 能力声明（限额、manual 档、退出码、命令）
├── cli.py            # 命令行入口（package / status / mark）
├── contract.py       # 标题/描述/话题/编码等口径校验（build_text）
├── package.py        # 组装发布包
├── snapshot.py       # 发布快照（写 outbox/*.json）
├── state.py          # 发布状态机
├── notify.py         # webhook 通知
├── assets.py         # 素材/封面
├── outbox/           # 扁平发布快照目录（入库）
└── tests/            # 平台私产测试
```

## 二、命令

```bash
python3 -m douyin.cli package <期号>                        # 出包
python3 -m douyin.cli status <期号>                         # 看状态
python3 -m douyin.cli mark published <期号> --url <链接>     # 回填已发布链接
```

退出码由契约层定死（`publish/publishkit/exit_codes.py`），声明在 `capability.toml` 的
`[exit]` 段：0 成功 / 1 用法错 / 2 缺前置条件 / 3 做事失败。

## 三、AI 如何使用本目录

- **改这里先跑**：`cd platforms/douyin && python3 -m pytest tests/ -q`。
- 与 `bilibili/`、`channels/` **平级、互不引用**。
- 发布走 `manual`：adapter 只**出包 + 写快照**，不自动上传；上传与点发表在人工手里。
- 平台能力数值改 `capability.toml`（数据），**不要**在 Python 里写死限额。
- 期号/坐标口径与 `video/pipeline/pyv/episodes.py` 同一套。
- 设计说明见 [`docs/00-设计.md`](docs/00-设计.md)。
