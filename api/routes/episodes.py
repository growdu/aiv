"""视频流的路由：期目录树、读一期、起出片与出包作业。

**期路径是四层**：`<系列>/<合集>/<文档>/<档位>`，相对 `video/episodes/`。
目录即接口——没有登记表，扫目录就得到全部期。

**这一层不 import `pyv`**：判据（哪些目录算一期）抄在
`api/services/paths.py` 的 `TIERS` 里，与 `pyv/episodes.py` 的
`TIERS` 逐字一致——但**不 import**，层间零 import。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import artifacts, commands, frontmatter
from ..services import drafts as draft_service
from ..services import review as review_service
from ..services.jobs import RUNNER, Job
from ..services.paths import (
    DRAFTS_DIR,
    EPISODES_DIR,
    EPISODE_FACT_FILES,
    PLATFORMS_DIR,
    REPO_ROOT,
    SCRIPT_NAME,
    TIERS,
    episode_to_draft,
)

router = APIRouter(prefix="/api/episodes", tags=["episodes"])

#: 平台 id 的形状。**不写死任何一个平台名**——合法的 id 从
#: `GET /api/platforms` 拿，这里只挡形状不对的（路径穿越、命令行注入）。
PLATFORM_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _split(episode: str) -> tuple[str, str] | None:
    """期路径 → `(文档路径, 档位)`。形状不对（不是四层 / 档位不认识）→ `None`。"""
    parts = [p for p in episode.strip("/").split("/") if p]
    if len(parts) != 4 or parts[3] not in TIERS:
        return None
    return "/".join(parts[:3]), parts[3]


def _episode_dir(episode: str) -> Path:
    """期路径 → 期目录。不存在 → 404。"""
    if _split(episode) is None:
        raise HTTPException(status_code=404, detail="没有这一期")
    path = (EPISODES_DIR / episode.strip("/")).resolve()
    if EPISODES_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="没有这一期")
    return path


def _episode_known(episode: str) -> bool:
    """这一期认不认识——母稿层有期目录，**或者**草稿箱里有对应的单元。

    草稿箱里有就够：过审那一步会把它复制进母稿层。
    """
    if (EPISODES_DIR / episode.strip("/")).is_dir():
        return True
    try:
        draft_service.find_unit(episode_to_draft(episode), root=DRAFTS_DIR)
    except draft_service.DraftNotFound:
        return False
    return True


def _title(episode_dir: Path) -> str:
    """一期的标题——从口播稿的 front matter 读，读不到就用目录名。"""
    script = episode_dir / SCRIPT_NAME
    if script.is_file():
        return frontmatter.title(script.read_text(encoding="utf-8"),
                                 episode_dir.name)
    return episode_dir.name


def _list_episodes() -> list[dict]:
    """扫期目录树：四层且末段是档位 → 一期。"""
    out = []
    for dirpath, dirnames, _files in os.walk(EPISODES_DIR):
        rel = Path(dirpath).relative_to(EPISODES_DIR).as_posix()
        if rel == ".":
            continue
        parts = rel.split("/")
        if len(parts) != 4 or parts[3] not in TIERS:
            continue
        out.append({
            "episode": rel,
            "doc": "/".join(parts[:3]),
            "tier": parts[3],
            "title": _title(Path(dirpath)),
        })
    return sorted(out, key=lambda e: e["episode"])


# ── 出片与出包 ──────────────────────────────────────────────────────────

#: 旁白合成的那条命令。**第一版 `api/` 不调它**——它要联网，且在 `pyv/`
#: 之外（规格 §九 的待还账 ②）。缺旁白时把这条命令原样报给人。
NARRATION_COMMAND = ("python3 video/voice/scripts/synthesize_narration.py "
                     "--script video/episodes/{episode}/口播稿.md "
                     "--out video/episodes/{episode}/narration.mp3")


def _promote_step(episode: str):
    """第一步：把草稿**复制**进母稿层（过审 = 只复制）。

    没有草稿单元就跳过——**日志里说一句**，不假装做了。
    """
    def step(job: Job) -> int:
        draft_id = episode_to_draft(episode)
        try:
            unit = draft_service.find_unit(draft_id, root=DRAFTS_DIR)
        except draft_service.DraftNotFound:
            job.note(f"没有草稿单元 {draft_id}，跳过过审")
            return 0
        try:
            result = draft_service.promote_unit(unit, repo_root=REPO_ROOT)
        except draft_service.PromoteError as exc:
            job.note(f"过审失败：{exc}")
            return 1
        for target in result.targets:
            job.note(f"过审复制了 {target}")
        for step_text in result.manual_steps:
            job.note(f"还要人手工做：{step_text}")
        return 0
    return step


def _narration_step(episode: str):
    """第二步：查旁白在不在。

    不在 → **退出码 2**（前置条件没满足），并把合成命令原样报出来。
    """
    def step(job: Job) -> int:
        narration = EPISODES_DIR / episode.strip("/") / "narration.mp3"
        if narration.is_file():
            return 0
        job.note("这一期还没有旁白（narration.mp3）")
        job.note("先合成旁白："
                 + NARRATION_COMMAND.format(episode=episode.strip("/")))
        return 2
    return step


def build_steps(episode: str) -> list:
    """出片的四步。**次序不能换**：

    1. **先过审**（复制入库事实）——不然渲染读的是旧稿；
    2. 查旁白——不在就停（退出码 2），并报出合成命令；
    3. 对齐时间轴（`align`）；
    4. 出片（`make EP=… all`）。
    """
    return [
        _promote_step(episode),
        _narration_step(episode),
        commands.video_align(episode),
        commands.video_build(episode),
    ]


#: 出片的四步。**测试把它换成无害命令**——真跑一次渲染要几分钟。
BUILD_STEPS = build_steps


class PackageBody(BaseModel):
    platform: str


@router.get("")
def list_episodes():
    """期目录树：系列 → 合集 → 文档 → 档位。扫目录得到，没有登记表。"""
    return {"episodes": _list_episodes()}


# ⚠️ **带后缀的路由必须注册在 `/{episode:path}` 之前**——
# `path` 匹配是贪婪的，`{episode:path}` 会把 "…/short/draft" 整条吃掉。
@router.get("/{episode:path}/draft")
def episode_draft(episode: str):
    """这一期对应的草稿单元。

    **不存在 → 404**——由前端引导去新建（规格 §六）。
    """
    if _split(episode) is None:
        raise HTTPException(status_code=404, detail="没有这一期")
    draft_id = episode_to_draft(episode)
    try:
        unit = draft_service.find_unit(draft_id, root=DRAFTS_DIR)
    except draft_service.DraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"draft_id": draft_id, "exists": True, "kind": unit.kind,
            "files": list(unit.files)}


@router.post("/{episode:path}/build")
def build_episode(episode: str):
    """起出片作业：**先过审，再出片**。

    期目录不在、也没有对应的草稿单元 → 404。
    （有草稿就行——过审那一步会把它复制进母稿层。）
    """
    if _split(episode) is None:
        raise HTTPException(status_code=404, detail="没有这一期")
    episode = episode.strip("/")
    if not _episode_known(episode):
        raise HTTPException(status_code=404, detail="没有这一期")
    job = RUNNER.submit_steps("build", list(BUILD_STEPS(episode)),
                               key=f"build:{episode}")
    return {"job_id": job.id, "status": job.status}


@router.post("/{episode:path}/package")
def package_episode(episode: str, body: PackageBody):
    """给一个平台出包。

    **平台 id 由前端从 `GET /api/platforms` 拿**，这里只透传——
    源码里不写死任何一个平台名。
    """
    if _split(episode) is None:
        raise HTTPException(status_code=404, detail="没有这一期")
    episode = episode.strip("/")
    platform = body.platform.strip()
    if not PLATFORM_ID.match(platform):
        raise HTTPException(status_code=400, detail=f"平台 id 不像样：{platform!r}")
    if not (PLATFORMS_DIR / platform).is_dir():
        raise HTTPException(status_code=404, detail=f"没有这个平台：{platform}")
    command = commands.platform_package(platform, episode)
    job = RUNNER.submit("package", command.argv, command.cwd,
                        key=f"package:{platform}:{episode}")
    return {"job_id": job.id, "status": job.status}


@router.get("/{episode:path}/artifacts")
def episode_artifacts(episode: str):
    """这一期的产物清单：成片、旁白、时间轴、抽帧、片段。

    **每项带一个 `artifact_id`**——前端拿它去 `GET /api/artifacts/{id}` 取字节。
    """
    episode = episode.strip("/")
    if _split(episode) is None:
        raise HTTPException(status_code=404, detail="没有这一期")
    return {"artifacts": artifacts.episode_artifacts(episode,
                                                      repo_root=REPO_ROOT)}


@router.get("/{episode:path}")
def get_episode(episode: str):
    """读一期：三个入库事实 + 审校状态。

    **缺哪个事实就是空串**，不报错——期目录里可能只写了口播稿。
    """
    episode = episode.strip("/")
    path = _episode_dir(episode)
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="没有这一期")
    doc, tier = _split(episode)

    files = {}
    for name in EPISODE_FACT_FILES:
        file_path = path / name
        files[name] = (file_path.read_text(encoding="utf-8")
                       if file_path.is_file() else "")

    gate = review_service.episode_gate(episode, repo_root=REPO_ROOT)
    return {
        "episode": episode,
        "doc": doc,
        "tier": tier,
        "title": _title(path),
        "files": files,
        "review": {
            "subject": {"kind": "episode", "id": episode,
                        "path": f"video/episodes/{episode}"},
            "layer": "episode",
            "counts": {"error": 0, "warn": 0, "info": 0},
            "signals": [],
            "notes": ["信号要先跑 GET /api/review/episodes/{episode} 才有"],
            "gate": gate,
        },
    }
