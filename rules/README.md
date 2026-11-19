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
- **改这里等于改全站地址。**所以它入库（不是构建产物），
  而且改动要跟「改动地址」这件事一起做。

## 谁读它

| 读取器 | 语言 | 位置 | 怎么读 |
| --- | --- | --- | --- |
| 站点 | TypeScript | `platforms/blog/site/src/lib/rules.ts` | 构建时 JSON import（Vite 内联进产物，不读文件系统） |
| 站点（渲染层） | JavaScript | `platforms/blog/site/src/lib/remark-site-links.mjs` | 由 `astro.config.mjs` 把路径递进来，插件自己读文件 |
| 根工具层 | Python | `tools/rules.py` | `json.loads`（仓库根 = 本文件上一级） |
| 契约层 | Python | `publish/publishkit/urls.py` | `json.loads`（仓库根 = 环境变量 `PUBLISH_REPO`，取不到按目录层级推） |

四份读取器**都遵守同一条口径**：

- 单元 id 是内容单元相对 `content/units/` 的路径（不带 `.md`）；
- 文档与分类页去掉分类页后缀，视频去掉视频前缀；
- **不 percent-encode**——拼出来的地址逐字照抄单元 id。

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
- **发布平台上的地址**：公众号、头条号、B 站……那些地址由各平台自己的
  能力声明（`capability.toml`）与发布清单决定，
  与站点上的地址无关；
- **站点部署的域名**：那是使用者的事（环境变量 `SITE_URL`），
  框架层不写死任何域名。
