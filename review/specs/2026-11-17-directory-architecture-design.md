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
| `docs/platform-meta/**`（上游 2026-11-17 新增的六个系列） | **要改**：这些文章讲的是这个仓库自己的分层，文中引用了 `aiv/`、`weixin/`、`toutiao/` 等旧路径（见 `platform-overview/one-repo-three-pipelines.md` 的分层表）。它们是**活文档**，不是历史快照——改名后不改，文章就直接说错了。具体的回写清单见 §8.2 |

**不改（历史快照）**：

- `publish/plans/`、`video/review/plans/`、`review/plans/` 里的历史计划与试点记录——
  它们记录的是当时的路径与当时的做法，是复盘材料，改了就失真。
- `docs/` 下已发布文章的**正文内容**。但有一条例外：**描述仓库自身架构的文章**
  （`docs/platform-meta/**`）要跟着改路径引用，因为它讲的就是现在这套目录。

### 4.9 草稿箱

`drafts/README.md` 写清楚流程（这是**约定**，不是自动化）：

1. 新写的稿子放 `drafts/`，文件名带日期与主题。
2. 过总审核（文章看 `review/`，视频稿看 `video/review/` 的口径要求）。
3. 通过后**复制**一份进 `docs/` 或 `video/`（相应位置），**草稿箱留底稿**。
4. 平台版由 `platforms/<plat>/` 各自出包，落在 `platforms/<plat>/outbox/`。

**草稿箱不进派生。** `docs/platform-meta/` 里那条「母稿唯一」的不变量说的是
「真相只在 `docs/`」——如果 `drafts/` 里的稿子还能被拿去发布，
或者改完之后两边不一致，它就变成了第二个真相源，母稿唯一这条就不成立了。
所以规矩是：`drafts/` 是**底稿**，审校通过后**复制**一份进 `docs/`，
底稿留在原地**不再参与任何派生**；下游的一切都从 `docs/` 的母稿重建。
底稿的价值是「留个底」——能看出当初交上去的是什么、审校改了什么，
不是「另一个可以编辑的产地」。

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
- 不动 `docs/` 下 1708 篇文章的**正文内容**（描述仓库自身架构的 `docs/platform-meta/**` 除外，见 §4.8）；不动 `docs/life/aiv/` 这条 URL 命名空间。
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
10. **回写到位**（§8.2）：
    - `one-repo-three-pipelines.md` 里再 grep 不到 `` `aiv/` ``、`` `weixin/` ``
      这些旧路径；
    - 「平台总览」系列多出那篇《两条流水线，一个草稿箱》，
      `tools/sync-hexo.py` 跑完站点能出这一页；
    - `tests/test_learning_path.py` 绿（新文章没有落进 fallback 兜底）。

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

## 八、与 `docs/platform-meta/` 的关系：参考什么、写回什么

`docs/platform-meta/` 是**已经发表在站上的系列**，讲的是这个博客自己怎么造：
六个系列（平台总览 / 内容模型 / 构建流水线 / 多平台分发 / 视频生产线 / 信息架构），
已成稿三篇。工程文档回答「怎么改」，这一系列回答「为什么这么设计」。

目录架构一改，**这个系列就是最先说错的地方**——它文中引用的正是旧目录名。
所以它既是本次重构的**约束来源**，也是重构完成后**必须回写的地方**。

### 8.1 要参考的既有结论（重构必须满足）

| 出处 | 结论 | 本设计怎么满足 |
| --- | --- | --- |
| 平台总览 §三 | 依赖单向：契约层不认平台，平台层不引用契约层 | `publish/` 只留平台无关的部分；能力声明与快照随平台走，但**契约层不 import 任何平台** |
| 平台总览 §三 | 平台之间**不是共用，是复制** | `platforms/<plat>/` 下每个平台仍是独立副本，不抽公共模块 |
| 平台总览 §四·1 | 母稿唯一：真相只在 `docs/` | 草稿箱只留底稿、**不参与派生**（§4.9） |
| 平台总览 §四·3 | 不静默成功：拿不准就停下来，让人看一眼 | 两条审核线（总审核在 `review/` + `video/review/`，平台审核在 `platforms/<plat>/` 内）都是「停下来」的闸门 |
| 平台总览 §四·2 | 可重放 vs 有状态：切片渲染是纯函数，发布的幂等键单独落盘 | 幂等键就是快照文件名，**不改**；只改它所在的目录 |
| 平台元数据 §一 | 入库的是事实，不入库的是产物 | `drafts/`（底稿）、`platforms/<plat>/outbox/`（发布记录）是事实，入库；`build/` `out/` 是产物，不入库 |
| 内容模型 §一 | 三层模型：母稿 → 内容单元 → 平台产物 | 本设计**不动这三层**，只改母稿之外的目录摆放；草稿箱是母稿**之前**的一道工序，不是第四层 |

一条划分上的补充：平台总览按**产出形态**分三条产线（站点 / 视频 / 分发），
本设计按**内容类型**分两条流水线（文档流 / 视频流）。两者**正交**——
文档流的下游既有站点（`docs/`）也有文本平台（公众号、头条），
视频流的下游是视频平台。交叉点是分发层：一个内容单元可以既是站点文章，
又是某一期视频的母稿。

### 8.2 要回写的（搬完之后做，不属于代码迁移）

| # | 位置 | 改什么 |
| --- | --- | --- |
| W1 | `docs/platform-meta/platform-overview/one-repo-three-pipelines.md` | ① mermaid 图里的 `aiv/contracts/` → `video/contracts/`；② §三分层表：视频生产层 `aiv/` → `video/`；平台适配层 `weixin/`、`toutiao/`、`douyin/`、`channels/`、`bilibili/` → `platforms/`（每个平台一个目录） |
| W2 | `docs/platform-meta/platform-overview/` **新写一篇** | 《两条流水线，一个草稿箱》：目录架构本身——为什么视频独立成一条线、为什么平台收进 `platforms/` 按平台划分、草稿箱是什么、两条审核线怎么分工、以及这次为什么动了 `aiv/` 的名字。放「平台总览」系列，不另开新系列 |
| W3 | `docs/platform-meta/platform-overview/_index.md` | 「本系列文章」列表加上 W2 |
| W4 | `docs/platform-meta/multiplatform/_index.md`、`video-line/_index.md` | 这两个系列「尚未成稿」，它们各自规划的第一篇会写到旧路径：能力声明现在住在 `platforms/<plat>/capability.toml`（不在 `publish/capabilities/`），视觉分镜契约现在住在 `video/contracts/`。成稿时按新路径写 |

**写回不是「改完就完」**，还有三道手续：

1. **站点链路**：`docs/` → `source/_posts/` → `public/`，要跑 `tools/sync-hexo.py`；
2. **学习路径策展**：`data/learning-path.json` 已有 `platform-meta/platform-overview/`
   的前缀规则，新文章自动落位（不必改规则文件），但 `tests/test_learning_path.py`
   的「没有文章靠 fallback 兜底」这条守卫要绿；
3. **站点契约测试**：根 `tests/` 查死链与页内锚点，新文章里的相对链接要能解析。

### 8.3 一条边界

`docs/platform-meta/` 里那些**讲别的东西**的文章（构建流水线、内容模型）
引用的是 `docs/` `source/` `public/` `tools/` `themes/`——这些目录本次不动，
不用改。只有讲仓库自身分层的文章（平台总览）受影响。

## 九、附：与上游「内容分类与结构重构」的关系

上游 2026-11-17 拉进来一份独立的设计：`review/plans/2026-11-17-内容分类与结构重构.md`
（把 `docs/` 下 577 篇排成五条赛道）。两份设计**范围不重叠**，但有三处要记着：

1. **上游明确不动 `aiv/`。** 它在「零、范围」里写死了：`publish/` `aiv/` `tools/`
   `themes/` `source/` `public/` `review/` `data/` 都**不重排、不改名、不重构**。
   本设计把 `aiv/` 改成 `video/`，属于它划出去的那一块，两边不冲突。
2. **`docs/life/aiv/` 的 URL 仍然稳。** 上游的试点阶段不动 `life/`
   （「试点阶段不碰：`distributed/`、`engineering/`、`life/`、`notes/` —— 留在原地」），
   所以本设计的「`docs/life/aiv/` 目录名不改」这条硬约束没有被上游打破。
3. **`drafts/` 与上游那句「后续的文章也只能放到 `docs/` 下」**：
   本设计的 `drafts/` 是**底稿区**，不是发布位置——稿子审完后**复制**一份进 `docs/`，
   底稿留在 `drafts/`。发布出去的文章仍然只在 `docs/` 里，两条不矛盾。
   上游还会新建一个根目录 `internal/`（放不该给读者看的东西），根目录清单因此多一个。

上游这批提交里已经落地的东西跟本设计的交集只有一个：
`docs/platform-meta/platform-overview/one-repo-three-pipelines.md` 讲的是同一个分层
（视频生产层 / 发布契约层 / 平台适配层），但用的是旧目录名——按 §4.8 当活文档改路径即可，
文章的分层结论不用动：上游那篇给「平台适配层」下的目录列的是
`weixin/` `toutiao/` `douyin/` `channels/` `bilibili/`，本设计只是把这五个收进 `platforms/`。
