"""抖音 adapter。

抖音**有**公开发布接口（`upload_video` + `create_video`），但那要开放平台
应用的主体资质——官方「适用范围」写的是党政机关或事业单位，个人主体批不下来
（规格 §6.6.1）。所以这一档是 `manual`：自动出包（成片 + 封面 + 文案 + 清单），
人工点发布。

本包与 `platforms/channels/`、`platforms/bilibili/` 平级、互不引用，也不 import 契约层或
`platforms/wechat/` 的包。

`pyv` 住在 `video/pipeline/` 下面，没有装成 wheel，所以这里把它挂上 `sys.path`——
adapter 只**读** `pyv.epmeta`、`pyv.preflight` 与 `pyv.episodes`（坐标/路径助手），
不修改 video 侧的任何东西。
"""
from __future__ import annotations

import sys
from pathlib import Path

# platforms/douyin/__init__.py → parents[2] 是仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "video" / "pipeline"

if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
