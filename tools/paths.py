"""仓库里所有构建脚本的路径常量——**唯一一处**。

这个模块存在的理由：站点的构建链搬进 `platforms/blog/site/tools/` 之后，
那些脚本比根 `tools/` 的脚本深了四层。各自写
`Path(__file__).resolve().parents[1]` 会指向 `platforms/` 而不是仓库根——
路径就散成了好几处，每搬一次目录就得改一遍。

集中在这里，各脚本 import 它，**路径就只有一处能改**。

契约层（`publish/publishkit/`）**不许 import 本模块**——两层之间不互相依赖，
那条接缝由 `publish/tests/test_episode.py` 守着。
"""

from pathlib import Path

# tools/paths.py → parents[0]=tools, parents[1]=仓库根
REPO_ROOT = Path(__file__).resolve().parents[1]

# 深度写死在各脚本里（站点脚本用 parents[4]）。所以这里断言一次——
# 层级数哪天变了，一 import 就炸，而不是静悄悄地指向错的地方。
assert (REPO_ROOT / "docs").is_dir(), f"REPO_ROOT 不对：{REPO_ROOT}"
assert (REPO_ROOT / "platforms").is_dir(), f"REPO_ROOT 不对：{REPO_ROOT}"

# 母稿（文档流的唯一真相）
DOCS = REPO_ROOT / "docs"

# 内容单元仓库：所有平台共用的那一半。站点只是它的一个消费者。
CONTENT_UNITS = REPO_ROOT / "content" / "units"

#: 内容单元仓库里的**图片**副本。编译器按 docs 相对路径把图片拷进来，
#: 站点与两个 adapter 都从这儿拿图（正文里的一张图落在
#: ``图片根/单元目录/正文里的相对路径``）。
CONTENT_UNIT_IMAGES = CONTENT_UNITS / "images"

#: 算「图片」的后缀。站点的 ``sync-content.py`` 原来自己有一份，
#: 搬到这儿——一处。
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif"}

# 站点（第六个平台）的家
SITE = REPO_ROOT / "platforms" / "blog" / "site"

#: 站点私有的**数据表**（学习流规则表、编译结果、代码块语言别名表……）。
SITE_DATA = SITE / "data"

#: 站点私有的工具（学习流编译、内容同步、围栏体检）。
SITE_TOOLS = SITE / "tools"

#: 站点的**构建产物**——Astro 的输出目录。整站构建的结果都在这儿。
SITE_DIST = SITE / "dist"

#: 站点的**静态资源源码**目录（`public/`）：favicon 入库，
#: `images/`、`js/` 是构建时从 `docs/` 与 `node_modules/` 同步进来的，不入库。
#:
#: ⚠️ 它**不是**站点产物——产物是 `SITE_DIST`。
#: （2026-11-18 站点重做之前，这里放的是 hexo 的产物 `public/`，
#: 同一个名字换了含义，这是那轮重做留下的最隐蔽的一处。）
SITE_PUBLIC = SITE / "public"

#: 站点的**源目录**（Astro 工程的 `src/`）。页面、组件、样式都在这儿。
SITE_SOURCE = SITE / "src"

#: 站点拿到的那份**内容单元副本**——Astro 的 content collection 读它。
#:
#: 它是**构建产物，不入库**：根 `tools/build-content-units.py` 把 `docs/`
#: 编译成 `content/units/`，再由 `platforms/blog/site/tools/sync-content.py`
#: 同步进这个目录。平台层（公众号、头条号……）读的就是这份副本。
SITE_POSTS = SITE_SOURCE / "content" / "units"

# --- 以下是 hexo 时代的路径 -------------------------------------------------
#
# 站点重做（2026-11-18）把 hexo 换成了 Astro，这些目录已经不存在了。
# 这些常量**先留着**：引用它们的模块（`publish/`、`platforms/wechat/`、
# `platforms/toutiao/`、`tools/` 里几个脚本）伸手进站点目录拿东西，
# 那是那些模块的欠账（见 `review/specs/2026-11-18-站点重做-学习流门面.md` §14.5），
# 该由那些模块自己解耦掉——**解耦的方式是把跨平台的规则搬回根 `tools/`，
# 不是继续引用某个平台的私有目录**。
SITE_THEMES = SITE / "themes"          # 主题目录（已不存在）
SITE_CONFIG = SITE / "_config.yml"     # 站点配置（已不存在）
#: 站点自己的主题覆盖配置（对 matery 的覆盖层，已不存在）
SITE_MATERY_CONFIG = SITE / "_config.matery.yml"
#: 主题外的自制素材（logo、头像、收款码……，已不存在）
SITE_ASSETS = SITE / "theme-assets"

# 根 tools/ —— 平台无关的工具住这儿
ROOT_TOOLS = REPO_ROOT / "tools"
