"""占位名单不许有查无此人的 id。

**背景**
------
六期视频现在是占位稿（口径与术语是历史产物，正在重写）。
站点在 `data/placeholder-units.json` 里列了它们，在页面上标出来。

名单会烂：稿子重写完、单元改名、目录调整之后，名单里的 id 就可能指向
不存在的东西——那时候占位标记会悄悄失效（或者标在一个已经没了的页面上）。
这个测试把它钉住：名单里的每个 id 都得真有对应页面。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paths import CONTENT_UNITS, SITE

DIST = SITE / "dist"
PLACEHOLDERS = SITE / "data" / "placeholder-units.json"


def _listed_ids() -> list[str]:
    data = json.loads(PLACEHOLDERS.read_text(encoding="utf-8"))
    return list(data.get("units", []))


def _unit_exists(unit_id: str) -> bool:
    return (CONTENT_UNITS / f"{unit_id}.md").exists()


@pytest.fixture(scope="module")
def placeholder_ids() -> list[str]:
    if not PLACEHOLDERS.exists():
        pytest.skip("还没有占位名单")
    return _listed_ids()


def test_placeholder_ids_exist(placeholder_ids):
    missing = [uid for uid in placeholder_ids if not _unit_exists(uid)]
    assert not missing, "占位名单里有查无此人的内容单元：\n" + "\n".join(missing)


def test_placeholder_pages_exist(placeholder_ids):
    """名单里的单元也要真有页面——不然占位块会指着一页空气。"""
    if not DIST.exists():
        pytest.skip("还没构建（先跑 npm run build）")
    missing = []
    for unit_id in placeholder_ids:
        if unit_id.startswith("video/"):
            target = DIST / "videos" / unit_id.removeprefix("video/") / "index.html"
        else:
            target = DIST / "docs" / unit_id / "index.html"
        if not target.exists():
            missing.append(f"{unit_id} → {target}")
    assert not missing, "占位名单里的单元没有页面：\n" + "\n".join(missing)
