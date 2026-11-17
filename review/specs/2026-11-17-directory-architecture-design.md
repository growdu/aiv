---
title: "目录架构调整：视频独立成一条线，平台按平台划分"
date: 2026-11-17
---

# 目录架构调整：视频独立成一条线，平台按平台划分

## 一、意图

现在仓库根目录是二十几个文件夹平铺，三件事混在一起：

| 现状 | 问题 |
| --- | --- |
| 视频生产线叫 `aiv/`（品牌缩写） | 看目录名不知道是视频，得先查 aiv 是什么 |
| 五个平台适配层各占一个顶层目录（`weixin/` `toutiao/` `douyin/` `bilibili/` `channels/`） | 加一个平台就要在根目录再开一个文件夹；平台之间的共性（能力声明、发布契约、出包）散在 `publish/` 里，跟平台的对应关系看不出来 |
| 稿子直接进 `docs/`，审校在原地做 | 没有「未定稿」这个状态；文章的审核记录按 `docs/…` 路径索引，审校与成稿混在一处 |

要调成的形状是**两条流水线，共用一个草稿箱入口**：

```
草稿箱 drafts/                     所有新写的稿子只落这里，审完也留着（底稿）
      │
      ▼ 总审核（根 review/）        内容本身能不能进 video/ 和 docs/ 的闸门
      │
      ├──▶ docs/                   文章成品（个人网站，也是一个平台）
      │
      └──▶ video/                  视频生产线
              │
              ▼ 成片层审核（video/review/）
              │
              └──▶ platforms/     各视频平台的发布内容
```

**关键性质：加平台只动 `platforms/`。** 平台怎么发是这个平台的事，别的平台不碰；
`publish/` 里的契约层不认识任何平台，只认能力声明与快照。

### 两条审核线的分界

| | 管什么 | 在哪 | 认不认平台 |
| --- | --- | --- | --- |
| 总审核（外部） | 内容本身能不能进 `video/` 和 `docs/` | 根 `review/`（文章）、`video/review/`（成片） | 不认 |
| 平台审核（平台适配层内） | 这个平台自己的规矩：封面尺寸、标题裁剪、栏目、口径 | `platforms/<plat>/` 里 | 只认自己 |

## 二、目标结构

```
/
├── drafts/                      草稿箱（新建，只带流程说明）
├── review/                      总审核 · 文章侧（不动）
│   └── specs/ plans/ <分类>/    审校记录与复盘
├── docs/                        个人网站内容（不动，含 life/aiv/ 这条 URL 命名空间）
├── video/                       ← aiv/ 整体搬来并改名，内部结构不动
│   ├── pipeline/                渲染引擎（pyv/ + tests/ + scripts/）
│   ├── contracts/               视觉分镜契约（一期一个 json）
│   ├── publish/                 每期各平台的标题、简介、话题、分区
│   ├── review/                  成片层审核（VT-*/VV-*、六期记录、抽帧清单）
│   ├── brand/ character/ voice/ music/    素材与规范
│   ├── scripts/                 sync_publish_docs.py
│   ├── build/ out/              产物（不入库）
│   └── *.md *.mp3 *.json        规范文档、口播稿、旁白、storyboard
│
├── platforms/                   ← 五个平台收进来，每个平台一个目录（压平）
│   ├── wechat/                  微信公众号
│   │   ├── __init__.py cli.py capability.py contract.py notify.py
│   │   ├── capability.toml      ← publish/capabilities/wechat.toml
│   │   ├── outbox/              ← 该平台已发布内容的快照
│   │   ├── docs/ tests/ tools/ deploy/ assets/
│   │   └── README.md *.example.json .gitignore
│   ├── toutiao/  douyin/  bilibili/  channels/     同上
│
├── publish/                     平台无关的发布契约层
│   ├── publishkit/              contract / manifest / capability / episode / schedule
│   ├── spec/  plans/  deploy/  tests/
│   └── schedule.json
├── browser/  source/  themes/  tools/  scripts/  data/  tests/  requirements/
```

对比现状的三个变化：

1. `aiv/` → `video/`（**只改名，内部结构不动**）。
2. 五个平台从根目录收进 `platforms/`，内层包**压平**：
   `weixin/wechat/` → `platforms/wechat/`，`toutiao/toutiao/` → `platforms/toutiao/`，其余同理。
3. `publish/outbox/`（567 个快照）与 `publish/capabilities/`（5 个 toml）是**按平台**的，
   跟着平台走；`publish/` 只留平台无关的部分。

上面是**最终形态**，不是示意模板。

## 三、逐项决策

| # | 决策 | 取舍 |
| --- | --- | --- |
| D1 | 视频目录叫 `video/` | 自解释。代价：`aiv/` 出现在 125 个文件里，要全改 |
| D2 | 平台目录压平成 `platforms/<plat>/` | 少一层嵌套。代价：import 写法要改，子进程 cwd 要改 |
| D3 | outbox 跟平台走 | 「加平台 = 只动 `platforms/`」才真正成立。代价：publishkit 写快照的路径要改，**读快照的 8 处调用点也要改** |
| D4 | capabilities 跟平台走 | 同上 |
| D5 | 两根审核线：根 `review/` 管文章，`video/review/` 管成片 | 视频审核模块是刚做完的大量工作，合成一层要改路径与链接 |
| D6 | `drafts/` 新建，先不搬现有文件 | 现有 1708 篇文章没有「未审」标记，判定不了 |
| D7 | **平台目录名 = 平台 id = Python 包名**（`wechat` / `toutiao` / `douyin` / `bilibili` / `channels`） | 仓库里原来只有微信是例外（目录 `weixin`、包 `wechat`、id `wechat`）。统一之后「一个平台一个词」在目录、文件名、import、快照后缀上是同一个词，能力声明按 id 查目录不需要映射表。代价：微信平台的目录从 `weixin/` 改成 `wechat/`（官方域名 `api.weixin.qq.com` 不受影响） |
| D8 | **只改写侧不够，读侧必须一起改** | outbox 从「一个目录」变成「每个平台一个目录」，所有读者都得改——包括两个**不会报错**的工具 |

### D7 的取舍细节（若要改回 `weixin/`）

改成 `platforms/weixin/` 也能跑，但会留下两处不一致：

- 能力声明按 id 查目录就得多一层映射（id `wechat` → 目录 `weixin`）；
- `-m` 调 adapter 时包名得跟目录名一致，于是包名 `weixin` 与快照后缀 `__wechat` 又是两个词。

代价是 118 处 `wechat` 引用（主要在 `weixin/tests/` 的 import 与 docstring）要改成 `weixin`。
换句话说：**叫 `wechat` 几乎不改代码，叫 `weixin` 要改 118 处**。这里选前者。

## 四、迁移清单

### 4.1 目录搬移（用 `git mv`，历史跟着走）

| 源 | 目标 | 备注 |
| --- | --- | --- |
| `aiv/` | `video/` | 整棵树，内部结构不动 |
| `weixin/` | `platforms/wechat/` | 内层 `weixin/wechat/*.py` 压到 `platforms/wechat/`（包名仍是 `wechat`，import 不用改） |
| `toutiao/` | `platforms/toutiao/` | 内层 `toutiao/toutiao/*.py` 压到 `platforms/toutiao/` |
| `douyin/` | `platforms/douyin/` | 内层 `douyin/douyin/*.py` 压到 `platforms/douyin/` |
| `bilibili/` | `platforms/bilibili/` | 内层 `bilibili/bilibili/*.py` 压到 `platforms/bilibili/` |
| `channels/` | `platforms/channels/` | 内层 `channels/channels/*.py` 压到 `platforms/channels/` |
| `publish/outbox/<内容>__<平台>.json` | `platforms/<平台>/outbox/` | 567 个文件，按 `__<平台>` 后缀分流；**文件名不变** |
| `publish/capabilities/<平台>.toml` | `platforms/<平台>/capability.toml` | 5 个文件 |
| —— | `drafts/`（新） | 只有 `README.md` |

平台目录压平后，每个平台目录下要有 `__init__.py`（原来在内层包里，压平后要提到外层）。

**深度不变的地方**（`parents[N]` 不用改）：`weixin/wechat/x.py` 与 `platforms/wechat/x.py` 都是三层，
`parents[2]` 都还是仓库根。`aiv/` → `video/` 同深度。

**深度会变的地方**：`platforms/<plat>/tests/conftest.py` 的 `parents[2]` 从「仓库根」变成
「`platforms/`」→ 必须改成 `parents[3]`。五个平台的 conftest 都要改。

### 4.2 导入方式与子进程 cwd

压平后平台代码的包名 = 平台名：

```python
# 之前（toutiao/tests/conftest.py）
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "toutiao"))
from toutiao import cli          # 包名 toutiao，在 toutiao/ 底下

# 之后
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "platforms"))
from toutiao import cli          # 包名 toutiao，在 platforms/ 底下
```

平台内部代码用的是**相对导入**（`from .capability import …`），压平后依然成立——
只要模块还在一个包里。压平后 `platforms/<plat>/` 本身就是那个包。

**子进程 cwd 要跟着改**：`publish/publishkit/cli.py::invoke_adapter` 现在是
`working_dir = config.repo_root / package`（包目录），命令 `python3 -m toutiao.cli`
靠 cwd 在 `sys.path` 里找到 `toutiao/` 这个内层包。压平后内层包没了，
`python3 -m toutiao.cli` 要靠 `platforms/` 在 `sys.path` 里，所以：

```python
working_dir = config.repo_root / "platforms"          # 不再是 / <package>
if not (working_dir / package).is_dir():              # 存在性检查跟着挪
    raise ScheduleConfigError(...)
```

五个 toml 的 `[adapter]` 段统一成：

```toml
[adapter]
package = "<平台 id>"
command = ["python3", "-m", "<平台 id>.cli"]
```

### 4.3 能力声明（写侧 + 读侧）

**契约层**：`publish/publishkit/capability.py`

- `default_capabilities_dir()` → 改成 `default_platforms_dir()`，返回 `<repo>/platforms`。
- `load_capability(platform_id)` → 读 `<platforms>/<platform_id>/capability.toml`。
- `list_capabilities()` → 扫 `<platforms>/*/capability.toml`（原来扫一个目录里的 `*.toml`）。
- `available_platforms()` → 跟着改。
- `publish/publishkit/cli.py` 的 `--capabilities-dir` → `--platforms-dir`。

**视频线的读侧**（原来设计稿漏了）：

| 位置 | 改动 |
| --- | --- |
| `video/pipeline/pyv/epmeta.py:24` | `CAPABILITIES_DIR = REPO_ROOT / "publish" / "capabilities"` → `REPO_ROOT / "platforms"`；`load_limits(platform, capabilities_dir)` → `load_limits(platform, platforms_dir)`，读 `<platforms>/<platform>/capability.toml` |
| `video/pipeline/pyv/preflight.py:194` | `_load_media()` 同改 |

**平台自己那份读法**：

| 位置 | 改动 |
| --- | --- |
| `platforms/toutiao/capability.py:107` | `_REPO_ROOT / "publish" / "capabilities" / "toutiao.toml"` → `_REPO_ROOT / "platforms" / "toutiao" / "capability.toml"` |
| `platforms/douyin/contract.py:169` | docstring 里的路径 |
| `platforms/bilibili/package.py:203-207` | `capabilities_dir` 参数 → `platforms_dir`，默认指向 `<platforms>` |
| `platforms/bilibili/tests/test_package.py:316` | 真实 toml 的路径 |

**守卫要跟着换**：`publish/tests/test_real_declarations.py:57` 现在断言
`capability.path.stem == capability.id`（文件名就是平台名）。文件统一改名成
`capability.toml` 之后这条断言不再成立，要换成新的不变量：

> 目录名 == 文件里的 `id` —— 也就是 `platforms/<id>/capability.toml` 里的 `id` 必须等于目录名 `<id>`。

### 4.4 出包快照（写侧 + 读侧）

**写侧**：

- `ScheduleConfig.outbox_dir`（默认 `<repo>/publish/outbox`）→ `outbox_root`（默认 `<repo>/platforms`）。
- 新增 `outbox_dir_for(platform)` → `<root>/<platform>/outbox`。
- `publish/publishkit/cli.py` 的 `_write_snapshot` / `write_snapshot` → 写进 `outbox_dir_for(platform)`。
- `--outbox-dir` → `--outbox-root`。
- **快照文件名保持 `<content_id>__<platform>.json` 不变**——它是幂等键，改名等于换键，
  会让已发过的内容被当成没发过。目录已经表达了平台，文件名里的后缀冗余但无害。
- **快照正文不改**：567 个快照里有 `package_dir`（如 `toutiao/out/life-aiv-brand-README`）
  这类本机相对路径，搬迁后会失效。它是历史信息，站点构建不读它
  （`tools/build-publish-index.py` 只读 content_id / platform / status / title /
  published_url / reason / updated_at），**不重写历史快照**。

**读侧**（这是最容易被漏掉的一半——`load_outbox_index` 的调用点有 8 处）：

| 读 outbox 的地方 | 现在 | 之后 |
| --- | --- | --- |
| `publish/publishkit/schedule.py` 的 `load_outbox_index(...)`（3 处） | `config.outbox_dir` | `config.outbox_root`（函数改成扫 `<root>/*/outbox/*.json`） |
| `publish/publishkit/cli.py` 的 `load_outbox_index(...)`（5 处） | 同上 | 同上 |
| `publish/publishkit/cli.py:335` `PUBLISH_OUTBOX_DIR` | `config.outbox_dir` | `config.outbox_dir_for(capability.id)`——**每个平台不同** |
| `publish/publishkit/schedule.py:184` `discover_repo_root()` | 往上找含 `publish/capabilities` 的那一层 | 往上找含 `publish/publishkit` 的那一层（能力声明散了，原来的锚点没了） |
| `publish/publishkit/schedule.py:162` 凭据默认路径 | `root / "weixin" / "secrets.json"` | `root / "platforms" / "wechat" / "secrets.json"` |
| `browser/browser/cli.py:44` `DEFAULT_OUTBOX` | `REPO_ROOT / "publish" / "outbox"` | `REPO_ROOT / "platforms"`（按平台扫子目录） |
| `tools/build-publish-index.py:30` `OUTBOX_DIR` | 同上 | 同上 |
| `tools/build-video-pages.py:44` `OUTBOX_DIR` | 同上 | 同上 |
| `publish/tests/test_schedule.py:43` `REPO_OUTBOX` | `root / "publish" / "outbox"` | `root / "platforms"` |
| `platforms/toutiao/tests/conftest.py:18` `OUTBOX_DIR` | `root / "publish" / "outbox"` | `root / "platforms" / "toutiao" / "outbox"` |
| `platforms/douyin/tests/conftest.py:76` `repo_outbox` | 同上 | 同上 |
| `platforms/wechat/snapshot.py:26` `OUTBOX_DIR` | `parents[2] / "publish" / "outbox"` | `parents[2] / "platforms" / "wechat" / "outbox"` |

> **两个工具会静默失败**：`tools/build-publish-index.py` 与 `tools/build-video-pages.py`
> 的测试把 `OUTBOX_DIR` monkeypatch 到临时目录，所以路径写错时**测试照样全绿**，
> 只有真跑 hexo 构建时才出问题。验收里必须真跑一次（见 §6）。

**引用 outbox 路径的文档字符串**：`publish/publishkit/contract.py`、`episode.py` 里
`publish/outbox/<EP>__<平台>.json` 的写法要改。

### 4.5 平台适配层内部

| 位置 | 改动 |
| --- | --- |
| `platforms/<plat>/tests/conftest.py` | `parents[2]` → `parents[3]`；sys.path 指向 `<repo>/platforms`；`REPO_ROOT / "aiv" / "pipeline"` → `REPO_ROOT / "video" / "pipeline"`（douyin / bilibili / channels 三个 conftest 都有这行） |
| `platforms/<plat>/.gitignore` | 随目录搬走即可（`out/`、`secrets.json` 的规则是相对目录的，搬走后仍然生效） |
| `platforms/<plat>/docs/` 里的路径引用 | 属于「活文档」，要改 |
| `platforms/wechat/docs/03-试点记录.md` 等 | 里面的 `weixin/…` 路径 → `platforms/wechat/…` |

### 4.6 CI 与配置

| 文件 | 改动 |
| --- | --- |
| `.github/workflows/aiv-pipeline.yml` | paths `aiv/**` → `video/**`；`working-directory: aiv/pipeline` → `video/pipeline`；requirements 路径 |
| `.github/workflows/contracts.yml` | `pytest toutiao/tests` → `pytest platforms/toutiao/tests`；`weixin/tests` → `platforms/wechat/tests`；其余平台同理 |
| `.github/workflows/site-guard.yml` | 注释里提到 `aiv` 的地方 |
| `ruff.toml` | `"weixin/tools/*.py"` → `"platforms/wechat/tools/*.py"` |
| `pyrightconfig.json` | extraPaths：`publish` `weixin` `toutiao` `channels` `bilibili` `browser` `aiv/pipeline` → `publish` `platforms` `browser` `video/pipeline` |
| `requirements/*.txt`（4 个文件） | 里面的 `aiv/…` 路径 |
| `.gitignore` / `video/.gitignore` | 随目录搬走 |

### 4.7 工具与脚本

| 位置 | 改动 |
| --- | --- |
| `video/scripts/sync_publish_docs.py` | `AIV_ROOT` 由 `parents[1]` 推出（搬走后自然指向 `video/`）；白名单里的相对路径不变；`PUBLISH_DIR` 仍是 `docs/life/aiv/` |
| `docs/life/aiv/` | **目录名不改**（URL 稳定性是硬约束）。搬完跑一次同步脚本，副本自动更新 |
| `video/pipeline/tests/test_publish_copy.py` | 盯着源与副本一致，路径跟着改 |
| `tools/sync-hexo.py` | 注释里提到 `aiv/voice/README.md`、`docs/life/aiv/` 的地方 |
| `tools/build-publish-index.py` / `tools/build-video-pages.py` | outbox 路径 + `PLATFORM_NAMES` 里的平台键（`wechat` 不变，但取值来源要跟着目录走） |

### 4.8 仓库根的守卫与文档

| 位置 | 改动 |
| --- | --- |
| `tests/test_podcast_spec.py` | `REPO_TOP_DIRS` 加 `video` `platforms` `drafts`，去掉 `aiv` 与五个旧平台名；`PLANNED_PATHS` 里的 `aiv/…` → `video/…` |
| `tests/test_episode_block.py` | `aiv/` 路径引用 |
| 根 `README.md` | §2 整体架构、§2.3 AIV 视频生产线、平台表、目录表 |
| `video/*.md`（人格规范、形象与音色规范、背景音乐规范、选题库、上机指南、index.md） | 里面的 `aiv/` 路径引用 → `video/`。这些是 `docs/life/aiv/` 的源，改完同步过去 |
| `video/review/` 六期记录、`video/review/README.md` | 路径引用 |
| `publish/spec/*.md`（活的规格） | 路径引用。**注意**：根 `tests/test_podcast_spec.py` 会逐条核对规格里写的仓库路径是否存在——规格里的 `aiv/`、`weixin/` 不改，守卫就会红 |
| `review/README.md`、`review/specs/`、`review/plans/` | 路径引用 |

**不改（历史快照）**：

- `publish/plans/`、`video/review/plans/`、`review/plans/` 里的历史计划与试点记录——
  它们记录的是当时的路径与当时的做法，是复盘材料，改了就失真。
- `docs/` 下已发布的文章正文。

### 4.9 草稿箱

`drafts/README.md` 写清楚流程（这是**约定**，不是自动化）：

1. 新写的稿子放 `drafts/`，文件名带日期与主题。
2. 过总审核（文章看 `review/`，视频稿看 `video/review/` 的口径要求）。
3. 通过后**复制**一份进 `docs/` 或 `video/`（相应位置），**草稿箱留底稿**。
4. 平台版由 `platforms/<plat>/` 各自出包，落在 `platforms/<plat>/outbox/`。

### 4.10 仓库外的部署

`publish/deploy/` 里的两个模板在仓库内，要改：

- `crontab.template`：`PUBLISH_SECRETS=__REPO__/weixin/secrets.json` → `__REPO__/platforms/wechat/secrets.json`。
  `cd __REPO__/publish` 与 `PYTHONPATH=__REPO__/publish` **不变**（publishkit 还住 `publish/`）。
- `launchd.plist.template`：同上一条；`WorkingDirectory` = `__REPO__/publish` 不变。

**仓库外改不到的**：本机（Mac）已经装上的
`~/Library/LaunchAgents/com.growdu.publish.schedule.plist` 里写死了
`/Users/growduduan/code/blog` 和旧的 `PUBLISH_SECRETS` 路径。
仓库里改模板**不会**自动更新已装的 job，需要用户自己重新 `launchctl unload` / `load`
（或手改那个 plist）。服务器上的 crontab 同理。

## 五、非目标

- 不改任何平台适配层的业务逻辑（只改路径与 import）。
- 不动 `docs/` 下的 1708 篇文章，不动 `docs/life/aiv/` 这条 URL 命名空间。
- 不改任何 `content_id`（`life/aiv/voice/README` 这类）——它是站点内容 id，映射到 URL。
- 不重写 567 个快照的正文（`package_dir` 里的旧路径就让它过期）。
- 不把 `drafts/` 真的用起来——这次只建目录与约定。
- 不把根 `review/` 与 `video/review/` 合成一层。
- 不顺手拆 `video/` 的内部结构（`pipeline/` `contracts/` `brand/` 那些保持原样）。
- 不把 `publish/` 整个塞进 `platforms/`——它本来就是平台无关的。

## 六、验收

1. `aiv/` 与五个旧平台目录在仓库里**不存在**。
2. 全量测试通过：
   - `cd video/pipeline && python3 -m pytest tests/ -q`
   - `python3 -m pytest tests/ -q`（仓库根）
   - `python3 -m pytest publish/tests -q`
   - 五个平台各自的 `python3 -m pytest platforms/<plat>/tests -q`
3. CI 两个 workflow 的路径指向新位置。
4. `python3 video/scripts/sync_publish_docs.py` 跑完，`docs/life/aiv/` 与源一致
   （`test_publish_copy.py` 绿）。
5. 根 `README.md` 的架构表与实际目录一致。
6. `publishkit` 能按新路径读能力声明、写 outbox 快照：
   `python3 -m publishkit.cli ...`（`PYTHONPATH=publish`）能列出 5 个平台。
7. **静默失败项要真跑**（这两条测试查不出来）：
   - `python3 tools/build-publish-index.py` 真跑一次，产物里平台记录条数与迁移前一致
     （toutiao 549 + bilibili 6 + channels 6 + douyin 6）；
   - `python3 tools/build-video-pages.py` 真跑一次，产出的视频页数量与迁移前一致。
8. **残留引用兜底 grep**（应为空）：
   - `grep -rn "publish/outbox\|publish/capabilities" --include="*.py" --include="*.yml" --include="*.toml" --include="*.template" .`
   - `grep -rn '"aiv/\|'"'"'aiv/\|`aiv/' --include="*.py" --include="*.yml" --include="*.toml" --include="*.json" .`
     （历史快照文档 `publish/plans/`、`review/plans/`、`video/review/plans/` 不算）
   - `grep -rn '"weixin/\|'"'"'weixin/' --include="*.py" --include="*.yml" --include="*.toml" --include="*.template" .`
9. `platforms/<plat>/outbox/` 里的文件总数 = 567，且每个文件名仍满足
   `snapshot_name(content_id, platform) == path.name`。

## 七、风险与注意

| 风险 | 处理 |
| --- | --- |
| 漏改一处路径引用，某个平台脚本找不到文件 | 靠全量测试 + §6 的兜底 grep；平台测试大多用真实路径断言 |
| 漏改**读侧**，快照读不到 | §4.4 把 12 个读点列全；§6.7 真跑两个构建工具（它们的测试查不出来） |
| outbox 快照改名导致重复发布 | 快照文件名**不改**，只改目录 |
| `docs/life/aiv/` 的 URL 变了 | 目录名不改，URL 不变 |
| 快照正文里的 `package_dir` 过期 | 站点构建不读这个字段；不重写历史快照 |
| 平台包名压平后子进程调不起来（`-m` 找不到模块） | cwd 改成 `<repo>/platforms`；五个平台各跑一次真实 adapter 调用验证 |
| 微信目录从 `weixin/` 改成 `wechat/`，路径引用漏改 | 兜底 grep 里有 `weixin/` 一条；`wechat` 这个词本身不动 |
| `tests/test_podcast_spec.py` 的 `REPO_TOP_DIRS` 漏改 → 守卫变弱 | 它只跳过不认识的顶层目录，不是报错。改完要人工确认规格里的仓库路径都被核对上了 |
| `video/` 下的产物（`build/` `out/`）有 271M | 随目录搬走，仍在 `.gitignore` 里 |
| 历史文档里的旧路径会失效 | 历史计划不改；这是刻意的——它们是当时的快照 |
| 本机 launchd job 与服务器 crontab 仍指旧路径 | 仓库改不到；见 §4.10，需要用户自己重装 |
