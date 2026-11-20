"""个人站点（blog）adapter。

**站点是六个第三方平台之一**——这是 2026-11-18 顶层设计定下的事。

在这之前站点不在平台层里：它走 `docs/` → `content/units/` → `site/source/` →
`site/dist/` 这条链，跟另外五个平台（公众号、头条号、抖音、视频号、B 站）
是**两套东西**——那五个走「能力声明 → 发布清单 → outbox 快照」，
站点不走。于是顶层的心智模型缺了一块：目录里数得出来五个平台，
设计里说的是六个。

现在站点住进 `platforms/blog/`，跟另外五个同构：

| | 公众号等五个 | 站点 |
| --- | --- | --- |
| 能力声明 | `capability.toml` | `capability.toml`（同一种格式） |
| 发布状态 | `outbox/*.json` 快照 | `outbox/*.json` 快照（同一套文件名约定） |
| 限额与档位 | 平台实测值 | 站点自己的取舍（见 `capability.toml` 里的注释） |
| 出包 | 逐篇出包 + 人工/API 发布 | **全量构建**：一次 push 重建全站 |

**唯一的差别是出包方式**：那五个平台是「逐篇出包、发一篇文章」，
站点是「一次 push 重建全站」。所以本包**没有** `publish` 子命令——
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

#: **母稿层**：已过审的内容，站点编译的输入。单向——`drafts/` 的稿子过审后
#: 才进这里，没过审的不在这里（见 `review/specs/2026-11-18-草稿层与母稿层的接口协议.md`）。
DOCS_DIR = REPO_ROOT / "docs"

#: **草稿层**：在改的稿子。站点**不**读这里——读的是编译之后的内容单元。
#: 但 `check` 要能区分「在改」与「已过审」，所以平台层知道它在哪儿。
DRAFTS_DIR = REPO_ROOT / "drafts"

#: **内容单元仓库**：母稿编译出来的产物（平台无关，所有平台共用的那一半）。
#: 站点**直接读它**（`site/tools/build-posts.py`），不留副本——
#: 副本是字节级重复，仓库早就把它记成欠账（`acceptance/README.md` 的 I1/I3）。
#: **它是构建产物，不入库**——所以它不在的时候，`status` 要说「还没编译」，
#: 而不是报「0 篇内容」。
CONTENT_UNITS_DIR = REPO_ROOT / "content" / "units"

#: 本平台的发布账本（现在空着，理由见 `docs/01-站点即第三方平台.md` §五）。
OUTBOX_DIR = Path(__file__).resolve().parent / "outbox"

#: 站点的内容单元是**文档**：站点上的一切都是 markdown 页面。
#:
#: 视频内容单元（`video/<slug>`，口播稿）也是文档——它们是文章，
#: 不是成片。成片发去抖音、视频号、B 站，不发到站点。
#:
#: 这也是能力声明里 `kind = "document"` 的由来。
KIND = "document"

#: 站上 URL 最深几段（**URL 段数**，不是目录层数）。
#:
#: 新链里文档的地址是 `/docs/<内容单元 id>/`，内容单元 id 是它相对
#: `content/units/` 的路径（不带 `.md`）——所以
#: **URL 段数 = 目录路径段数 + 1**（`/docs/` 占一段）。
#:
#: 现在的取值来自两处：
#:
#: - **现状**：`docs/` 树最深是 `<一级>/<二级>/<三级>/<名>`
#:   （4 段）→ URL 5 段；
#: - **约定**：新写的稿子别再往深里塞。留这条线是为了让深度**可查**，
#:   不是为了让现存的文章不合格（现存的最深就是 5 段）。
#:
#: 注意 bundle 形态（`docs/a/b/c/index.md`）比 flat 形态（`docs/a/b/c.md`）
#: 在目录里多一层，URL 上也多一段——`check` 按它自己的形态算。
MAX_CATEGORY_DEPTH = 5
