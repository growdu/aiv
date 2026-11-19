# 第三方平台层

这里是**平台适配层**：每一个第三方平台一个目录，各自一套 adapter。
「第三方」的意思是——**内容发到别人的地盘上**，那边的规则由那边定。

现在有**六个**平台：

| id | 名字 | 内容形态 | 自动化档位 | 发布前审核 | 目录 |
| --- | --- | --- | --- | --- | --- |
| `wechat` | 微信公众号 | 文档 | `api_draft` | 平台机审 | [`wechat/`](wechat/) |
| `toutiao` | 头条号 | 文档 | `manual` | 平台机审 | [`toutiao/`](toutiao/) |
| `bilibili` | 哔哩哔哩 | 视频 | `manual` | 平台机审 | [`bilibili/`](bilibili/) |
| `channels` | 微信视频号 | 视频 | `manual` | 平台机审 | [`channels/`](channels/) |
| `douyin` | 抖音 | 视频 | `manual` | 平台机审 | [`douyin/`](douyin/) |
| `blog` | 个人站点 | 文档 | `api_publish` | 本地预检 | [`blog/`](blog/) |

> `blog` 是 2026-11-18 顶层设计加进来的第六个平台——**站点也是第三方平台**。
> 讲清楚它跟另外五个哪儿一样、哪儿不一样，见
> [`blog/docs/01-站点即第三方平台.md`](blog/docs/01-站点即第三方平台.md)。

---

## 一、这一层在整条流水线上的位置

```
                    草稿箱 drafts/
                         │
                    总审核 review/          ← 内容本身能不能进流水线
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
      docs/                             video/
   （文档流母稿）                    （视频流母稿）
        │                                 │
        ▼                                 ▼
  platforms/<plat>/                 platforms/<plat>/
   适配 → 生成 → review → output → upload
```

**两条流水线的共同入口是草稿箱**，但它们的下游是**两拨**平台：

- **文档流** → `wechat` `toutiao` `blog`
- **视频流** → `douyin` `channels` `bilibili`

一个内容单元可以同时属于两条线（既是站点文章，又是某一期视频的母稿）——
两条流水线**正交**，不互斥。

> **存量不回炉。** 现存的 560 篇母稿与 6 期成片是审完之后的样子，
> 它们停在 `review → docs` / `review → video` 这道出口上，
> **不需要**再走一遍 `draft → review`。草稿箱管的是**新内容**。
> 详见 `review/specs/2026-11-18-顶层设计与目录调整.md` §1.3。

### 加平台影响的是哪一段

**加平台只动 `platforms/`。**

- 平台怎么发是这个平台的事，别的平台不碰；
- 契约层（`publish/publishkit/`）**不认识任何平台**，
  它只认「能力声明」与「发布清单」这两样东西；
- 每加一个平台，**下游**要各自适配一遍（内容适配 → 视频生成 → review → output → upload），
  **上游**（`docs/` `video/` `drafts/` `review/`）一个字都不用改。

> 站点这一平台的构建链（Astro 工程 / 内容同步 / 学习流编译 / 守卫测试）
> **已经搬进 `platforms/blog/site/`**，所以「加平台只动 `platforms/`」这句话
> 对六个平台**全都**成立。

---

## 二、六个平台共同的规矩

### 规矩一：目录名 = 平台 id = Python 包名 = 快照后缀

`platforms/blog/` 这个目录，在四个地方是**同一个词**：

| 出现在哪 | 长什么样 |
| --- | --- |
| 目录名 | `platforms/blog/` |
| 能力声明里的 `id` | `id = "blog"` |
| import | `from blog import ...` |
| 快照文件名后缀 | `<content_id>__blog.json` |

**一个平台一个词**，不搞映射表。
（微信平台原来是目录 `weixin/`、包 `wechat/`，2026-11-17 统一成了 `wechat/`。）

这条由 `publish/tests/test_real_declarations.py` 守着。

### 规矩二：能力即数据

平台限额与自动化档位写在 `platforms/<plat>/capability.toml` 里，**不在 Python 里**。
平台规则变了改 TOML，不改代码。

```toml
id = "toutiao"
kind = "document"
automation = "manual"
review = "platform"
verified = "2026-11-13"

[limits]
title_chars = 30
body_chars = 3000
image_bytes = 20971520
```

**每个数字后面都要写清「实测到什么、还没测到什么」**——
「实测了 A」不等于「B 也实测了」。

### 规矩三：发布状态记在 `outbox/`

`platforms/<plat>/outbox/<content_id>__<plat>.json`，
一个内容单元在一个平台上的发布状态就是一份 JSON。
字段是**六个平台共用**的（`publish/publishkit/manifest.py` 写的那套）：
`content_id` `platform` `kind` `status` `title` `published_url` `reason` `updated_at`。

**文件名就是幂等键**——同一个 `content_id` 在同一个平台上只该有一份快照。
重跑一遍发布撞到已有快照，就说明「这篇发过了」，不重复发。

### 规矩四：接缝只有两处

```
        publish/publishkit/            （契约层，平台无关）
                │
                │  读同一份 capability.toml
                │  认同一份 manifest JSON
                ▼
          platforms/<plat>/          （平台层，六个各自一份）
```

**平台层不 import 契约层，契约层不 import 平台层。**
两边唯一的接缝是**同一份 `capability.toml`** 与**同一份 manifest JSON**。

这条规矩有实际后果：**声明里写的那个 adapter 到底在不在，没有编译器替我们把关**。
所以有守卫盯着：

| 守卫 | 查什么 |
| --- | --- |
| `test_every_declaration_points_at_an_adapter_that_exists` | 声明指着的 adapter 目录在不在 |
| `test_every_adapter_command_names_a_module_that_exists` | `python3 -m <plat>.cli` 的模块在不在 |
| `test_every_platform_directory_is_named_after_its_id` | 目录名 == 声明里的 `id` |
| `test_the_platform_dirs_keep_the_repo_root_at_the_right_depth` | 包有没有被挪深一层（相对路径的地基） |

### 规矩五：平台之间**不是共用，是复制**

`platforms/<plat>/` 下的代码**不抽公共模块**。
每个平台是一份独立副本——因为每个平台的规则真的不一样，
抽出来的公共部分最后会长成「谁都不满足」的中间层。

> 例外只有两处，都是**契约层**的东西，不是平台之间的共用：
> `publish/publishkit/` 里的内容契约与能力模型。

---

## 三、平台的核心流程

每个平台的 adapter 干的是同一件事，五个步骤：

| 步 | 干什么 | 站点上的对应物 |
| --- | --- | --- |
| **适配** | 按 `capability.toml` 的限额裁标题、压正文、配图、转换格式 | 根编译器 `tools/build-content-units.py`（母稿 → 内容单元） |
| **生成** | 渲染成平台要的形态（HTML / 竖版切片 / 投稿包 / 静态站） | Astro：`platforms/blog/site/` 的 `astro build` |
| **review** | 按这个平台自己的规矩过一遍（封面尺寸、栏目、口径） | `platforms/blog/site/tools/check-markdown.py docs/` + `build-learning-path.py`（漏归类即失败）+ `platforms/blog/site/tests/` |
| **output** | 出一个可发布的东西（包 / manifest / 整站） | `platforms/blog/site/dist/` |
| **upload** | 送出去（调平台 API / 浏览器自动化 / CI 部署） | **还没做**——归上线那一轮 |

**站点的 output 与 upload 粒度不同**：它是全量的一次，
另外五个是逐篇的一次。所以站点没有 `publish` 子命令。

> **站点的构建链也是平台层的东西。** Astro 工程、`public/`、站点脚本
> 都住在 `platforms/blog/site/`，跟站点 adapter 放在一起——
> 这样「加平台只动 `platforms/`」对站点也成立。
> 搬移见 `review/specs/2026-11-18-顶层设计与目录调整.md` §4.2（D9 / D10），
> 站点重做见 `review/specs/2026-11-18-站点重做-学习流门面.md`。

---

## 四、两条审核线的分界

| | 管什么 | 在哪 | 认不认平台 |
| --- | --- | --- | --- |
| **总审核** | 内容本身能不能进 `video/` 和 `docs/` | 根 `review/`（文章）、`video/review/`（成片） | 不认 |
| **平台审核** | 这个平台自己的规矩 | `platforms/<plat>/` 里 | 只认自己 |

**平台审核不是总审核的替代，是它的下游。**
一篇稿子要先过总审核（内容对不对），再过平台审核（这个平台能不能收）。
两道闸是串联的，不是二选一。

---

## 五、加一个平台要做什么

1. **建目录** `platforms/<新平台>/`，里面放 `__init__.py`——
   目录名就是包名（规矩一）；
2. **写能力声明** `platforms/<新平台>/capability.toml`——
   `id` 必须等于目录名；限额要**对着平台实测**再写，
   每个数字写清「实测到什么、还没测到什么」；
3. **写 adapter**：至少有一个 `cli.py`（声明里的 `[adapter].command`
   指着它，守卫会查）；
4. **定 `automation` 档位**：`manual` / `api_draft` / `api_publish`——
   档位由**平台那边的权限**决定，不是由我们想不想自动决定；
5. **定 `review`**：`none` / `platform` / `precheck`——
   平台机审还是本地预检；
6. **建 `outbox/`**（空的也行）与 `docs/`（写清楚这个平台的规矩）；
7. **跑守卫**：`python3 -m pytest publish/tests -q`。

**上游一个字都不用改**——`docs/` `video/` `drafts/` `review/` 都不动。
这就是「加平台只动 `platforms/`」的意思。

---

## 六、每个平台自己的文档

每个平台目录下的 `docs/` 写的是**这个平台**的事——
规则、实测、接口、试点记录。各不相同，不归拢到这里：

| 平台 | 文档入口 |
| --- | --- |
| `wechat` | [`wechat/docs/`](wechat/docs/)（最成熟，11 篇） |
| `toutiao` | [`toutiao/docs/`](toutiao/docs/) |
| `douyin` | [`douyin/docs/`](douyin/docs/) |
| `bilibili` | [`bilibili/docs/`](bilibili/docs/) |
| `channels` | [`channels/docs/`](channels/docs/) |
| `blog` | [`blog/docs/01-站点即第三方平台.md`](blog/docs/01-站点即第三方平台.md) |

契约层（平台无关的那部分）在
[`publish/spec/00-架构设计.md`](../publish/spec/00-架构设计.md)。
