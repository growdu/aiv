"""视频流：期目录树、读一期、起出片与出包作业。

**这些测试不许碰真的 `video/episodes/`**——它们把路由里的 `EPISODES_DIR`
与 `DRAFTS_DIR` 换到临时目录，出片的步骤也换成无害命令。
"""
from __future__ import annotations

import sys

from api.routes import episodes
from api.services.commands import Command
from api.services.jobs import Job

EPISODE = "系列/合集/文档/short"


def _episodes(tmp_path, monkeypatch):
    """把期目录与草稿箱都换到临时目录。"""
    episodes_dir = tmp_path / "video" / "episodes"
    episodes_dir.mkdir(parents=True)
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    monkeypatch.setattr(episodes, "EPISODES_DIR", episodes_dir)
    monkeypatch.setattr(episodes, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(episodes, "REPO_ROOT", tmp_path)
    return episodes_dir, drafts_dir


def _make_episode(episodes_dir, episode=EPISODE, title="标题"):
    path = episodes_dir / episode
    path.mkdir(parents=True)
    (path / "口播稿.md").write_text(
        f"---\ntitle: {title}\nepisode: 系列/合集/文档\n---\n\n口播正文\n",
        encoding="utf-8")
    (path / "contract.json").write_text(
        '{"episode": "系列/合集/文档/short", "segments": []}', encoding="utf-8")
    return path


def test_the_route_table_is_mounted(client):
    response = client.get("/api/episodes")
    assert response.status_code == 200
    assert "episodes" in response.json()


def test_an_unknown_episode_is_404(client):
    assert client.get("/api/episodes/没有/这一期/文档/short").status_code == 404


def test_a_path_that_is_not_four_levels_is_404(client):
    """期路径是四层。三层不是期。"""
    assert client.get("/api/episodes/系列/合集/文档").status_code == 404


def test_the_list_shows_the_four_level_path(client, tmp_path, monkeypatch):
    episodes_dir, _ = _episodes(tmp_path, monkeypatch)
    _make_episode(episodes_dir)

    items = client.get("/api/episodes").json()["episodes"]
    assert len(items) == 1
    assert items[0]["episode"] == EPISODE
    assert items[0]["doc"] == "系列/合集/文档"
    assert items[0]["tier"] == "short"
    assert items[0]["title"] == "标题"


def test_reading_an_episode_returns_its_facts(client, tmp_path, monkeypatch):
    episodes_dir, _ = _episodes(tmp_path, monkeypatch)
    _make_episode(episodes_dir)

    body = client.get(f"/api/episodes/{EPISODE}").json()
    assert body["tier"] == "short"
    assert "口播正文" in body["files"]["口播稿.md"]
    assert body["files"]["publish.json"] == ""      # 缺的文件是空串，不报错
    assert body["review"]["gate"]["status"] == "待审"


def test_the_draft_route_says_whether_a_draft_exists(client, tmp_path, monkeypatch):
    _episodes(tmp_path, monkeypatch)
    assert client.get(f"/api/episodes/{EPISODE}/draft").status_code == 404


def test_the_draft_route_finds_the_draft_unit(client, tmp_path, monkeypatch):
    _episodes_dir, drafts_dir = _episodes(tmp_path, monkeypatch)
    tier = drafts_dir / "_video" / "系列" / "合集" / "文档" / "short"
    tier.mkdir(parents=True)
    (tier / "口播稿.md").write_text("稿子", encoding="utf-8")

    body = client.get(f"/api/episodes/{EPISODE}/draft").json()
    assert body["draft_id"] == "_video/系列/合集/文档/short"
    assert body["exists"] is True
    assert body["kind"] == "episode"


def test_the_build_route_starts_a_job(client, tmp_path, monkeypatch):
    episodes_dir, _ = _episodes(tmp_path, monkeypatch)
    _make_episode(episodes_dir)
    monkeypatch.setattr(episodes, "BUILD_STEPS",
                        lambda episode: [Command(argv=[sys.executable, "-c",
                                                        "print('出片了')"],
                                                 cwd=tmp_path, key="fake")])

    response = client.post(f"/api/episodes/{EPISODE}/build")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"].startswith("j-")
    assert body["status"] in {"queued", "running"}


def test_the_build_of_an_unknown_episode_is_404(client, tmp_path, monkeypatch):
    _episodes(tmp_path, monkeypatch)
    assert client.post("/api/episodes/没有/这一期/文档/short/build").status_code \
        == 404


def test_a_missing_narration_stops_with_the_precondition_code(tmp_path,
                                                               monkeypatch):
    """没有旁白 → **退出码 2**（前置条件没满足），并报出合成命令。"""
    _episodes(tmp_path, monkeypatch)
    job = Job(id="j-1", kind="build")

    code = episodes._narration_step(EPISODE)(job)
    assert code == 2
    assert any("synthesize_narration" in line for line in job.log)


def test_a_present_narration_passes_the_precondition(tmp_path, monkeypatch):
    episodes_dir, _ = _episodes(tmp_path, monkeypatch)
    path = _make_episode(episodes_dir)
    (path / "narration.mp3").write_bytes(b"x")
    job = Job(id="j-1", kind="build")

    assert episodes._narration_step(EPISODE)(job) == 0


def test_the_promote_step_says_so_when_there_is_no_draft(tmp_path, monkeypatch):
    """没有草稿单元就跳过——**日志里说一句**，不假装做了。"""
    _episodes(tmp_path, monkeypatch)
    job = Job(id="j-1", kind="build")

    assert episodes._promote_step(EPISODE)(job) == 0
    assert any("跳过过审" in line for line in job.log)


def test_the_package_route_refuses_a_platform_that_does_not_exist(
        client, tmp_path, monkeypatch):
    _episodes(tmp_path, monkeypatch)
    response = client.post(f"/api/episodes/{EPISODE}/package",
                           json={"platform": "nosuchplat"})
    assert response.status_code == 404


def test_the_package_route_refuses_a_platform_id_that_looks_wrong(
        client, tmp_path, monkeypatch):
    """平台 id 会拼进 `python3 -m <id>.cli`——形状不对的挡掉。"""
    _episodes(tmp_path, monkeypatch)
    response = client.post(f"/api/episodes/{EPISODE}/package",
                           json={"platform": "../../etc/passwd"})
    assert response.status_code == 400
