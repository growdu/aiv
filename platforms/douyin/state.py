"""抖音的幂等状态。

沿用 `platforms/channels/state.py` 的形状，但有两处不同：

- **内容层键是成片的 sha256**——成片重出了就得重新出包
  （文案没变但成片变了很常见：重混音、修关键帧）。
- **档位有三个**：`packaged`（出包待上传）、`drafted`（草稿已在抖音后台，
  等人点发表）、`published`（已发布）。

`drafted` 这一档是 **2026-11-15 实测出来的**，不是拍脑袋设的：
点「暂存离开」之后，平台首页的「作品发布」卡片上会出现「继续编辑」
（辅助提示是「你有一个上次未发布的作品」），点进去的 URL 是
`creator-micro/content/post/video?enter_from=home_draft`，
视频、标题、描述、话题全在原处——**草稿真的存下来了，且能恢复**。

⚠️ **但抖音没有「草稿箱」列表。** 实测：内容管理 → 作品的筛选只有
「全部 / 已发布 / 审核中 / 未通过」，**没有草稿一栏**；上传页
（`content/upload`）也没有草稿列表。草稿**只有首页那一个入口**。
所以这一档的准确含义是「草稿已暂存在后台，等人从首页点『继续编辑』去发表」，
不是「草稿在某个草稿箱里可以逐条翻」。
（同时能存几条草稿**没实测**，只验过一条。）

状态文件留在 `platforms/douyin/out/` 下，永不入库。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class DouyinState:
    """一期在抖音上发到哪一步了。"""

    episode: str = ""
    video_sha256: str | None = None
    # packaged（出包待上传）| drafted（草稿已在后台，等人点发表）| published（已发布）
    status: str = "packaged"
    published_url: str | None = None
    updated_at: str | None = None


class StateStore:
    """一个 JSON 文件存着每一期的状态。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        episodes = raw.get("episodes", {})
        return episodes if isinstance(episodes, dict) else {}

    def get(self, episode: str) -> DouyinState:
        entry = self._load().get(episode)
        if not isinstance(entry, dict):
            return DouyinState(episode=episode)
        known = {}
        for name, spec in DouyinState.__dataclass_fields__.items():
            known[name] = entry.get(name, spec.default)
        known["episode"] = episode
        return DouyinState(**known)

    def save(self, episode: str, state: DouyinState) -> None:
        episodes = self._load()
        state.episode = episode
        state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        episodes[episode] = asdict(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"episodes": episodes}, ensure_ascii=False, indent=2,
                       sort_keys=True),
            encoding="utf-8",
        )
