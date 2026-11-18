"""growdu.cn（个人站点）adapter。

**站点是六个第三方平台之一**——这是 2026-11-18 顶层设计定下的事。

在这之前站点不在平台层里：它走 `docs/` → `tools/sync-hexo.py` → `source/`
→ `public/` 这条链，跟另外五个平台（公众号、头条号、抖音、视频号、B 站）
是**两套东西**——那五个走「能力声明 → 发布清单 → outbox 快照」，
站点不走。于是顶层的心智模型缺了一块：目录里数得出来五个平台，
设计里说的是六个。

现在站点住进 `platforms/blog/`，跟另外五个同构：

| | 公众号等五个 | 站点 |
| --- | --- | --- |
| 能力声明 | `capability.toml` | `capability.toml`（同一种格式） |
| 发布状态 | `outbox/*.json` 快照 | `outbox/*.json` 快照（同一套文件名约定） |
| 限额与档位 | 平台实测值 | 站点自己的取舍（见 `capability.toml` 里的注释） |
| 出包 | 逐篇出包 + 人工/API 发布 | **全量构建**：push 到 master → CI 重建全站 |

**唯一的差别是出包方式**：那五个平台是「逐篇出包、发一篇文章」，
站点是「一次 push 重建 2400 个页面」。所以本包**没有** `publish` 子命令——
逐篇的事留给 CI，这里只回答两个问题：
「这个平台是什么」与「这一篇能不能进站」。

本包与 `platforms/` 下另外五个平台平级、互不引用，
也不 import 契约层（`publish/publishkit/`）——
两边唯一的接缝是同一份 `capability.toml`。
"""
from __future__ import annotations

from pathlib import Path

# platforms/blog/__init__.py → parents[2] 是仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
OUTBOX_DIR = Path(__file__).resolve().parent / "outbox"

#: 站点的内容单元是**文档**：站点上的一切都是 markdown 页面。
#:
#: 视频规范页面（`docs/life/aiv/` 那一批）也是文档——它们是文章，
#: 不是成片。成片发去抖音、视频号、B 站，不发到站点。
#:
#: 这也是能力声明里 `kind = "document"` 的由来。
KIND = "document"

#: 站上 URL 最深几段（2026-11-18 实测 `docs/` 树得出）。
#:
#: 现在的链是：赛道 → 系列 → 阶段 → 文章，即
#: `/source-tracks/postgresql/extensions-perf/<文章>/` 这样 4 段，
#: 最深的一篇是 5 段。**这不是站点的限制，是目录现状**——
#: 它记在这里，是为了让「新写的稿子别再往深里塞」有一条可查的线，
#: 而不是让 `check` 去判现存的文章不合格（现存的最深就是 5 段）。
#:
#: 注意这里数的是 **URL 段数**，不是目录层数：
#: 文章目录形态（`docs/a/b/c/index.md`）比平铺形态（`docs/a/b/c/x.md`）少一段。
MAX_CATEGORY_DEPTH = 5

#: 构建期被整棵排除的工程目录名。
#:
#: `tools/sync-hexo.py` 扫 `docs/` 时会把这些目录**整棵剪掉**——
#: 文章、分类页、图片都不进产物。这份名单是那边 `EXCLUDED_DIR_NAMES` 的副本：
#: **改那边要改这边**。之所以抄一份而不是 import：
#: 平台层不 import 编译层（接缝原则），而这九个名字两年不会变。
#:
#: 它防的是「将来有人在 `docs/` 下建了 `tests/`、`pipeline/` 这类工程目录，
#: 构建期把它们当成文章发布」。
EXCLUDED_DIR_NAMES = frozenset(
    {
        "tests",
        "test",
        "fixtures",
        "plans",
        "pipeline",
        "build",
        "out",
        "_staging",
        "frames",
    }
)
