"""产物取用。**不接受用户传的路径**——只认白名单根（规格 §6.1）。"""
from __future__ import annotations

from api.services.artifacts import episode_artifacts, resolve_artifact

EPISODE = "系列/合集/文档/short"


def test_an_artifact_id_cannot_escape_the_whitelisted_roots(tmp_path):
    assert resolve_artifact("../../etc/passwd", repo_root=tmp_path) is None
    assert resolve_artifact("/etc/passwd", repo_root=tmp_path) is None
    assert resolve_artifact("docs/a/b.md", repo_root=tmp_path) is None


def test_an_artifact_inside_out_is_allowed(tmp_path):
    out = tmp_path / "video" / "out"
    out.mkdir(parents=True)
    cut = out / "a-b-c-short.mp4"
    cut.write_bytes(b"x")
    assert resolve_artifact("video/out/a-b-c-short.mp4", repo_root=tmp_path) == cut


def test_a_file_that_does_not_exist_is_not_allowed(tmp_path):
    out = tmp_path / "video" / "out"
    out.mkdir(parents=True)
    assert resolve_artifact("video/out/没有.mp4", repo_root=tmp_path) is None


def test_a_directory_is_not_allowed(tmp_path):
    out = tmp_path / "video" / "out"
    (out / "一目录").mkdir(parents=True)
    assert resolve_artifact("video/out/一目录", repo_root=tmp_path) is None


def test_a_narration_of_an_episode_is_allowed(tmp_path):
    tier = tmp_path / "video" / "episodes" / EPISODE
    tier.mkdir(parents=True)
    narration = tier / "narration.mp3"
    narration.write_bytes(b"x")
    assert resolve_artifact(f"video/episodes/{EPISODE}/narration.mp3",
                             repo_root=tmp_path) == narration


def test_a_fact_of_an_episode_is_not_an_artifact(tmp_path):
    """口播稿是**入库事实**，不是产物——不归这条路由管。"""
    tier = tmp_path / "video" / "episodes" / EPISODE
    tier.mkdir(parents=True)
    (tier / "口播稿.md").write_text("稿子", encoding="utf-8")
    assert resolve_artifact(f"video/episodes/{EPISODE}/口播稿.md",
                             repo_root=tmp_path) is None


def test_a_frame_of_an_episode_is_allowed(tmp_path):
    tier = tmp_path / "video" / "episodes" / EPISODE
    (tier / "frames").mkdir(parents=True)
    frame = tier / "frames" / "s01.png"
    frame.write_bytes(b"x")
    assert resolve_artifact(f"video/episodes/{EPISODE}/frames/s01.png",
                             repo_root=tmp_path) == frame


def test_the_episode_artifact_list_gathers_the_cuts(tmp_path):
    out = tmp_path / "video" / "out" / "系列" / "合集" / "文档"
    out.mkdir(parents=True)
    (out / "short.mp4").write_bytes(b"x" * 3)
    (out / "short__nobrand.mp4").write_bytes(b"x" * 4)

    items = episode_artifacts(EPISODE, repo_root=tmp_path)
    kinds = {item["name"]: item["kind"] for item in items}
    assert kinds["short.mp4"] == "cut"
    assert kinds["short__nobrand.mp4"] == "cut"
    assert all(item["bytes"] > 0 for item in items)
    assert items[0]["artifact_id"].startswith("video/out/")


def test_the_episode_artifact_list_gathers_the_narration_and_frames(tmp_path):
    tier = tmp_path / "video" / "episodes" / EPISODE
    (tier / "frames").mkdir(parents=True)
    (tier / "narration.mp3").write_bytes(b"x")
    (tier / "storyboard.json").write_text("{}", encoding="utf-8")
    (tier / "frames" / "s01.png").write_bytes(b"x")

    kinds = {item["name"]: item["kind"]
             for item in episode_artifacts(EPISODE, repo_root=tmp_path)}
    assert kinds["narration.mp3"] == "narration"
    assert kinds["storyboard.json"] == "timeline"
    assert kinds["s01.png"] == "frame"


def test_the_artifact_route_serves_a_file(client, monkeypatch, tmp_path):
    from api.routes import artifacts as artifacts_route

    out = tmp_path / "video" / "out"
    out.mkdir(parents=True)
    (out / "a.mp4").write_bytes(b"x")
    monkeypatch.setattr(artifacts_route, "REPO_ROOT", tmp_path)

    response = client.get("/api/artifacts/video/out/a.mp4")
    assert response.status_code == 200
    assert response.content == b"x"
    assert response.headers["content-type"].startswith("video/mp4")


def test_the_artifact_route_is_404_for_a_bad_id(client, monkeypatch, tmp_path):
    from api.routes import artifacts as artifacts_route

    monkeypatch.setattr(artifacts_route, "REPO_ROOT", tmp_path)
    assert client.get("/api/artifacts/../../etc/passwd").status_code == 404
    assert client.get("/api/artifacts/docs/a.md").status_code == 404
