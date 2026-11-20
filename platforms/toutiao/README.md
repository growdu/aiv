# toutiao — 博客到头条号的切片与发布

把 `content/units/` 下的博客文章裁成**头条版**（3K 精简稿 + 最多 3 张图，0 张也行），
产出发布包交人工上传；账号拿到 API 权限后，同一套代码改为直接调接口。

> **这个目录与 `platforms/wechat/` 平级、互不引用。** 两个平台的实现是分开做的，
> 详见 [../publish/spec/00-架构设计.md](../publish/spec/00-架构设计.md) §11.1。

## 现状

- **路线已定（2026-11-11）**：双轨并行——
  轨道 A 半自动出包（**本周就能发**），轨道 B 职业认证（并行解锁 API 权限）
- **账号现状**：未认证，粉丝 < 1000 → **开放平台 API 权限开不了**
  （2026-11-12 实测：后台**连「开放平台」入口都不渲染**，不是灰掉是菜单里没有；
  排查清单见 [docs/02-试点记录.md](docs/02-试点记录.md) §R1）
- **限额已实测（2026-11-13）**：用 Playwright 驱动真实编辑器走完一整篇，
  六组观测（标题 / 摘要 / 正文 / 图片 / 封面 / 发表）都记在
  [docs/02-试点记录.md](docs/02-试点记录.md) §R2。两条更正最要紧：
  **封面是横图 `452:352` 不是 3:4 竖图**；**编辑器底部「共 N 字」不是字符数**
  （平台字 = 非 ASCII 逐字 + ASCII 每两个折一个，单段 > 200 平台字会告警）
- **「保存失败」不等于「发不出去」**（2026-11-13 实测）：保存与发表是**同一个接口的两个分支**
  —— `save=0`（自动存草稿）稳定返回 `err_no 7050`「保存失败」，
  `save=1`（发表）**成功**。编辑器脚本报红只是自动存草稿被拒，发表走的是另一个分支
- **草稿档回来了（2026-11-15 实测）**：同一个 `save=0` 分支现在返回
  `{"code":0,"err_no":0,"message":"保存成功"}`，**草稿真的建进后台的「草稿箱」了**
  （草稿箱从 0 条变成 3 条，逐条对得上）。两天前的 7050 已经不复存在 ——
  平台侧那个故障好了，所以现在多了一档 `drafted`（草稿已在平台上，等人点发表）。
  详见 [docs/02-试点记录.md](docs/02-试点记录.md) §R4
- **草稿补图也做成了（2026-11-17 实测）**：59 篇有图的草稿，
  图与封面都灌进去了（平台草稿箱 547 条不变，只更新不新建）。
  做法与平台接口的实测形状见 [docs/02-试点记录.md](docs/02-试点记录.md) §R5，
  工具在 [../browser/browser/flows/toutiao.py](../browser/browser/flows/toutiao.py)：
  ```bash
  cd "$(git rev-parse --show-toplevel)"/browser && \
    python3 -m browser.cli toutiao-images "<content id>" --cdp http://127.0.0.1:9333
  ```
- **⚠️ 编辑器里没有「保存草稿」按钮**：草稿只有「草稿将自动保存」这一条自动路径。
  另外**同一轮编辑器会话里连写两篇会覆盖上一条**（两篇共用同一个草稿 id），
  所以每篇都要开一个全新会话——批量灌草稿时就是「刷新 → 填 → 存 → 再刷新」
- **第一篇已发表（2026-11-13 14:05 / 14:11）**：标题 / 正文 / 2 张图 / 封面都按出包清单走了一遍，
  正文与出包逐行一致。账号内容数 89 → 93（2 篇文章 + 平台自动生成的 2 条微头条），带首发标记
- **⚠️ 别拿「拦请求」当干跑手段**：排查时试着拦下发布请求再点按钮，
  其中一次**照样把文章发出去了**——平台还有别的通道能把 `save=1` 送出去
  （详见 [docs/02-试点记录.md](docs/02-试点记录.md) §R2.F）
- **自动化能到的最远一步（当前）**：产出发布包 + **把图与封面灌进平台草稿箱**，
  等人工点「确认发布」。
  （灌草稿走的是浏览器里的后台接口，**不是开放平台的 API** ——
  账号仍未认证，`automation` 那一栏维持 `manual`）
- **实现状态**：切片、渲染、出包、幂等状态、通知、批量出包、命令行**都已实现**
  （[docs/11-实施计划.md](docs/11-实施计划.md) 的 Task 1~10），**397 条用例**。
  其中 2 条是**语料级回归**——内容单元 `content/units` 不入库，
  干净检出里它们是 `skipped`（395 passed / 2 skipped），
  本地有母稿时才会真跑（397 passed）。
  逐条任务见 [docs/00-设计.md](docs/00-设计.md)

## 为什么是「裁」而不是「搬」

头条版**不是母稿的搬运**。三条硬约束叠在一起：

| 约束 | 来源 | 后果 |
| --- | --- | --- |
| 标题 ≤ 30 字 | 平台限额 | 标题要重写，不能直接截断母稿标题 |
| 正文**不能用外链图片** | 平台行为（2026-11-13 那轮**未测**外链图是否显示） | 每张图都得在编辑器里重新上传 → **图越少越好** |
| 正文放可点击站外 URL 受限 | 外链是独立创作者权益 | 链接降级成纯文本 |

所以头条版是 **3K 精简稿 + 最多 3 张图（0 张也行）+ 纯文本提及博客全文**。
完整版链接由站点反向承担（文章页的跨平台索引区块）。

规则明细见 [../publish/spec/06-发布计划与调度.md](../publish/spec/06-发布计划与调度.md) §6.6。

## 三档自动化

能力模型 `platforms/toutiao/capability.toml` 里的 `automation` 是数据，**换档改一行**：

| 档 | 前提 | 行为 |
| --- | --- | --- |
| `manual` | 未认证（**当前**） | 产出发布包 + 通知，人工上传 |
| `api_draft` | API 权限开通，但无直接发表权限 | 调 API 建草稿，人工点发表 |
| `api_publish` | API 权限开通且可直接发表 | 调 API 发布，轮询审核状态 |

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/00-设计.md](docs/00-设计.md) | **实现规格**：模块划分、切片规则、出包结构、幂等、CLI 契约、测试要求 |
| [docs/01-接口与发布.md](docs/01-接口与发布.md) | 开放平台接口、字段限制、OAuth2 绑定、错误码（实测后补） |
| [docs/02-试点记录.md](docs/02-试点记录.md) | Phase 0 实测清单：认证前 / 认证后两阶段，逐步填答 |
| [docs/11-实施计划.md](docs/11-实施计划.md) | **实施计划**：10 个任务，逐条带测试代码与提交命令 |

上位契约：[../publish/spec/00-架构设计.md](../publish/spec/00-架构设计.md)（整体架构）、
[../publish/spec/06-发布计划与调度.md](../publish/spec/06-发布计划与调度.md)（头条号一节）。

## 目录结构

```
platforms/toutiao/                   # Python 包（目录名即包名）
├── __init__.py
├── cli.py             # 命令行入口
├── contract.py        # 头条版切片规则
├── render.py          # Markdown → 头条 HTML
├── assets.py          # 图片转 webp、封面 3:4 裁切
├── publish.py         # 调 API 或产出发布包
├── state.py           # 幂等状态
├── notify.py          # 通知
├── docs/                  # 设计与实测记录
├── tests/                 # 单元 + 集成测试
├── out/                   # 发布包等本地产物（gitignore）
├── secrets.json           # 凭据（gitignore，永不入库）
└── secrets.example.json  # 凭据模板（入库）
```

## 命令

```bash
# 盘点：哪些文章能发到头条号，为什么
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli scan

# 切片 + 出包（不调接口）
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli convert <slug>

# 整个语料一次性出包（五百多篇就是靠这一条跑的）
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli convert --all

# 只出包，不动账本：给**已经在平台上的草稿**补东西时用这一档。
# 发布包是本地产物（platforms/toutiao/out/ 在 .gitignore 里），清一次就没了；
# 而账本里那篇仍然是 drafted，convert 会认定「内容没变、跳过」，
# 于是包再也回不来。--packages-only 把包重新生出来，
# 但**不写快照、不碰状态文件**——「草稿已在平台上」这件事不会被抹掉。
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli convert --all --packages-only

# 顺带把正文里的外链图下载下来打进包里（默认**不**下载）。
# 头条不能用外链图片（每张图都得重新上传），这一步是把外链图变成
# 可上传的本地文件。下不到的（死链、防盗链）仍然列在清单里等人工处理。
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli convert --all --packages-only --fetch-remote

# 出包 + 通知（API 权限开通后才是真正的「发布」）
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli publish <slug>

# 草稿已经建在平台后台的草稿箱里了，记一笔（要平台侧的草稿 id）
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli mark drafted <slug> --draft-id <草稿id>

# 人工在编辑器里发表之后，把结果记回账（没有公开链接就不算「已发布」）
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli mark published <slug> --url <公开链接>

# 查看状态
cd "$(git rev-parse --show-toplevel)"/platforms && python3 -m toutiao.cli status
```

退出码：`0` 成功 / `1` 参数或配置写错了（少给*命令行*必填参数也是这一档）/
`2` 东西不存在（文章 / 快照 / 目录不在）或该篇不合格 / `3` 接口或写盘错误。
这四个码的**语义由契约层定死**（`publish/publishkit/exit_codes.py`），本 adapter
读自己能力声明里的 `[exit]` 段——五个平台是同一张表。
分界一句话：**「少给一个*命令行*的必填参数」是 1；「参数没写错，但它指的东西还没有 /
还够」是 2。**

`mark` 有两档，各带各的凭据：

| 档 | 凭据 | 意思 |
| --- | --- | --- |
| `drafted` | `--draft-id`（平台侧的草稿 id） | 草稿已在后台草稿箱里，等人点发表 |
| `published` | `--url`（公开链接） | 已经发出去了 |

**没有凭据就不许说那句话**：草稿档没有草稿 id、已发布档没有公开链接，
命令都会拒绝（退出码 1）。「已存草稿」一旦说错，下一轮就会把它当成没发过
再发一遍——发重了比发慢了糟糕得多。

**已经发出去过的文章要改内容，去后台「编辑已发表文章」，别另建一份草稿。**
内容一变指纹就变，批量灌草稿会把它当成「没发过」再灌一份；而且
`mark drafted` 会把快照里的公开链接抹成空——账本里「这篇发出去过」
这件事就没了（2026-11-16 实测，见 [docs/02-试点记录.md](docs/02-试点记录.md) §R4.G）。

`convert --all` 一次跑完整个语料，每篇一行，最后一行是账。
**语料里切不出内容的那几篇不算失败**（它们会被点名，但不会拖垮整批）；
真的失败（写盘出错、状态文件坏过）才让退出码变成 3。

`<slug>` 是文章相对 `content/units/` 的路径去掉 `.md`（就是内容单元 id），
例如 `source-tracks/postgresql/logical-replication/postgresql-logical-replication-add-guc`。

每个命令都能把落盘位置指到别处，**但要把每一处都指走**，否则还是会写进仓库：
`--posts-dir`（内容单元目录，默认 `content/units`）/ `--images-dir`
（图片根目录，默认 `content/units/images`）/ `--out-dir` / `--outbox-dir` /
`--state-file` / `--capability`。
另外三个选项管内容与通知：`--source-url`（正文末尾署名的站点地址）、
`--notify`（通知通道：serverchan / wechat_work / webhook）、`--notify-key`（通知凭据）。
选项写在命令名前后都行。

正文里的一张图落在 ``图片根/单元目录/正文里的相对路径``——单元目录是内容单元
id 的目录部分（`db/x/_index` 的目录是 `db/x`，顶层单元是空串）。这条规则跟站点、
跟公众号 adapter 是同一条。

⚠️ **只指 `--out-dir` 是不够的**：`convert` 会把状态快照写进仓库里的
`platforms/toutiao/outbox/<slug>__toutiao.json`——**那个文件是被 git 跟踪的**，
而快照里的 `package_dir` 会变成相对你那个 `--out-dir` 的路径。
结果就是仓库里多出一处改动，它指向的包却根本不在仓库里。
只在仓库里试跑，就**别传** `--out-dir`；要让仓库完全不动，
`--outbox-dir` 和 `--state-file` 也要一起指走。

**两件事它不会悄悄做**：状态文件损坏会打到 stderr 并让退出码变成 `3`
（空状态读起来就是「什么都没发过」= 再发一遍的起点）；一篇文章切不出来
会退出 `2` 并说明原因，不会「成功地什么都没做」。

## 依赖

| 依赖 | 用途 |
| --- | --- |
| Python 3.11+ | 运行时 |
| pillow | 图片转 webp、封面裁剪（已装） |
| pytest | 测试（已装） |

除上面这些外只用标准库：front-matter 是手写解析器，HTTP 用 `urllib`。
**能力模型的限额用 `tomllib` 读**（3.11 标准库，零依赖）。

## 测试

```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m pytest platforms/toutiao/tests -q
```

测试不依赖网络：头条接口用本地假 HTTP server 模拟（绑定 `127.0.0.1`），
手法照抄 `platforms/wechat/tests/test_publish.py`。

## 边界

- **发布在本地执行**：与公众号同理，平台侧有 IP / 凭据约束
- **不做静默成功**：每个「成功」都必须显式确认过。发重了比发慢了糟糕得多
- **超限跳过并记录原因**，不做静默截断
- **通知措辞必须区分三种状态**：「待上传」/「待你点发表」/「已发布」——
  含糊说「已发布」是发布场景里最贵的 bug
- **不 import `platforms/wechat/`**，也不 import `publish/` 的包——契约只通过
  `platforms/toutiao/capability.toml` 与 manifest JSON 传递
