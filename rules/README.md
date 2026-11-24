# rules/ —— 全仓库的共享规则

## 这条缝是什么

`rules/` 住**跨模块共享的规则**：规则的**内容只有一份**（一个 JSON 文件），
**读取器各归各层**（每层有自己的语言、自己的目录、自己的依赖约束）。

这一层存在的理由：**同一条规则被三处需要**——站点的 TypeScript、
根 `tools/` 的 Python、契约层 `publish/publishkit/` 的 Python。
三处各写一份，形状迟早漂：改了一处，另外两处还在按旧的拼，
表现是「一批死链」或者「链接检查忽然报一堆 404」。

所以形状提成**文件**，不是 import：

- **共享的是文件，不是代码。**`publish/publishkit/` 不 import 根 `tools/`，
  根 `tools/` 也不 import `publish/publishkit/`——那两个方向都禁止，
  两层之间的接缝就是这份 JSON。同理，站点是 TypeScript，
  它读的是同一份 JSON，而不是某个 Python 包的导出。
- **改这里要连带改路由。**这份规则管的是「**内容单元 id → 地址**」的形状，
  **管不到路由**：站点的真实路由来自 Astro 的文件路由
  （`site/src/pages/docs/`、`site/src/pages/videos/`）与
  `site/data/site.json` 的导航。把 `doc_prefix` 从 `/docs/` 改成别的，
  文档页的**路由目录**也得跟着改，否则链接指向一个没有路由的地址。
  `site/tests/test_url_rules.py` 里有一条守卫盯着 `site.json` 的导航
  （「改了前缀却忘了改导航」是这条缝最容易犯的错）。
- 所以它入库（不是构建产物），而且改动要跟「改动地址」这件事一起做。

## 谁读它

| 读取器 | 语言 | 位置 | 怎么读 |
| --- | --- | --- | --- |
| 站点 | TypeScript | `platforms/blog/site/src/lib/rules.ts` | 构建时 JSON import（Vite 内联进产物，不读文件系统） |
| 站点（渲染层） | JavaScript | `platforms/blog/site/src/lib/remark-site-links.mjs` | 由 `astro.config.mjs` 把路径递进来，插件自己读文件 |
| 站点（校验方） | Python | `platforms/blog/site/tests/url_shape.py` | `json.loads`（仓库根 = 往上四级） |
| 根工具层 | Python | `tools/url_rules.py` | `json.loads`（仓库根 = 本文件上一级） |
| 契约层 | Python | `publish/publishkit/urls.py` | `json.loads`（仓库根 = 环境变量 `PUBLISH_REPO`，取不到按目录层级推） |

**层间关系**（只有这几条，别再加）：

- **平台层与站点工具读根 `tools/url_rules.py`**：
  `platforms/blog/cli.py` 与 `platforms/blog/site/tools/build-activity.py`
  把它放进 `sys.path` 再 import（仓库既有做法，对照
  `build-activity.py` 里的 `from paths import CONTENT_UNITS`）。
- **根 `tools/` 不反向 import 平台层**——方向只有这一条。
- **契约层不 import 根 `tools/`**，反过来也不许：两层的接缝是那份 JSON。
- **站点（TypeScript / JavaScript）不 import 任何 Python**：
  它读的是同一个**文件**。

四份（站点两份算一份）读取器**都遵守同一条口径**：

- 单元 id 是内容单元相对 `content/units/` 的路径（不带 `.md`）；
- 文档与分类页去掉分类页后缀，视频去掉视频前缀；
- **不 percent-encode**——拼出来的地址逐字照抄单元 id。

**部署含义**：契约层可以独立部署（`publish/deploy/` 的模板里就是
`PYTHONPATH=__REPO__/publish PUBLISH_REPO=__REPO__`）。
`PUBLISH_REPO` 必须指向一个**含 `rules/` 目录**的检出——
否则契约层的读取器找不到规则文件（读不到就抛错，不会猜）。

## 什么算「URL 形状」，什么不算

**算**（在本文件里）：

- 文档地址的前缀（`doc_prefix`）；
- 视频地址的前缀（`video_prefix`）；
- 内容单元里的视频前缀（`video_id_prefix`）与分类页后缀（`category_suffix`）
  ——它们是**内容单元 id 里的形状**，URL 这一层负责抹掉；
- 地址结尾要不要带斜杠（`trailing_slash`）。

**不算**（不在本文件里）：

- **站点自己的路由**：`/learning/`、`/all/`、`/timeline/`、`/about/`——
  那是**站点模块**的路由，定义在 `site/data/site.json` 与 Astro 的文件路由里。
  站点是六个平台之一，它的私有路由不外传；
- **站点内容空间的路由目录名**：`/docs/` 与 `/videos/` 这两个**路由**
  是 Astro 的目录（`site/src/pages/docs/`、`site/src/pages/videos/`），
  本文件管的是**指向它们的地址怎么拼**，不是路由本身；
- **发布平台上的地址**：公众号、头条号、B 站……那些地址由各平台自己的
  能力声明（`capability.toml`）与发布清单决定，
  与站点上的地址无关；
- **站点部署的域名**：那是使用者的事（环境变量 `SITE_URL`），
  框架层不写死任何域名。

## 版本

`version` 只是个标记，**没有版本闸门**：四份读取器一起变。
改这份文件之前先想清楚——它动的是全站地址。

---

## 另一份规则：术语词表（`terminology.json`）

`rules/` 里现在有**两份**规则文件，各管各的：

| 文件 | 管什么 | 判据（人读的在哪儿） |
| --- | --- | --- |
| `urls.json` | **内容单元 id → 地址**的形状 | `publish/spec/00-架构设计.md` |
| `terminology.json` | **措辞**：哪些词不能造、哪些名字不合格、标题该用什么词 | `review/specs/2026-11-24-术语纪律与反造词.md`、`review/specs/2026-11-24-标题与章节顺序.md` |

### 这条缝是什么

同一份措辞判据，**审校检查器**要读，**创作平台的审校面板**以后也要读
（面板上显示的信号就是检查器出的）。两边都是 Python，都能读同一个 JSON——
跟 `urls.json` 一个路子：**共享的是文件，不是代码**。

所以词表**不写死在代码里**。要加一个禁词，改 `rules/terminology.json`，
读它的代码一个字都不用动。

### 谁读它

| 读取器 | 语言 | 位置 | 怎么读 |
| --- | --- | --- | --- |
| 根工具层 | Python | `tools/terminology_rules.py` | `json.loads`（仓库根 = 本文件上一级） |
| 审校检查器 | Python | `tools/review-check.py` | 经 `terminology_rules` 读，出 TERM-01/02/03 信号 |

> ⚠️ **方向同 URL 规则**：根 `tools/` 不 import 平台层；
> `publish/publishkit/` 不 import `tools/terminology_rules.py`——
> 要用就**读那份 JSON**。

### 里面有什么

五张表（值是给作者看的替换说明）：

| 表 | 内容 | 信号 |
| --- | --- | --- |
| `banned` | 硬禁词：本领域没有公认定义，一律换 | `TERM-01`（warn） |
| `soft` | 常见行话：建议具体化，改不改由人定 | `TERM-02`（info） |
| `bad_names` | 已判过「不合格」的命名（对仗式抽象短语） | `TERM-03`（warn） |
| `title_words` | 标题里的营销词（干货、揭秘、一文读懂……） | `HEAD-03`（warn） |
| `title_words_soft` | 标题里的懒词（深入、详解、初探……），标题得另有「讲什么」 | `HEAD-03`（info） |

### 什么算「术语规则」，什么不算

**算**（在本文件里）：

- 哪些词不能造、换成什么说法；
- 哪些命名已经被否掉。

**不算**（不在本文件里）：

- **什么算「有公认定义的术语」**——机器判不了，那是判据文档里给人看的部分；
- **稿子该怎么组织**（结构、深度、证据密度）——那些是 `review/README.md` 的判据，
  各自有各自的信号，不进这份文件；
- **仓库内部工程文档的措辞**（specs / plans / 代码注释里的「渲染管线」是准确的技术描述）——
  术语纪律只管对外内容（`docs/`、`drafts/`）。
