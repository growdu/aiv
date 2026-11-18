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

# 站点（第六个平台）的家
SITE = REPO_ROOT / "platforms" / "blog" / "site"
SITE_SOURCE = SITE / "source"          # 站点私有的源目录
SITE_POSTS = SITE_SOURCE / "_posts"    # 站点拿到的那份内容单元副本
SITE_PUBLIC = SITE / "public"          # 站点产物（整站）
SITE_THEMES = SITE / "themes"
SITE_TOOLS = SITE / "tools"
SITE_CONFIG = SITE / "_config.yml"
#: 站点自己的主题覆盖配置（对 matery 的覆盖层）
SITE_MATERY_CONFIG = SITE / "_config.matery.yml"

# 根 tools/ —— 平台无关的工具住这儿
ROOT_TOOLS = REPO_ROOT / "tools"
