"""期号定位的守卫：一期 = 一个目录，路径说了算。

**这里没有登记表**：期在磁盘上是什么，路径就是什么。
所以这些用例盯的不是「登记表和代码对得上」，而是「目录扫得出来、
路径指得对、期号读得到」三件事。
"""
from __future__ import annotations

import shutil

from pyv import episodes as episodes_mod


def _make_episode(root, slug: str, *, front_matter: str | None = None) -> None:
    """在 `root` 下造一期的目录（内容不算数，只有形状算数）。"""
    directory = root / slug
    directory.mkdir(parents=True)
    if front_matter is not None:
        (directory / episodes_mod.SCRIPT_NAME).write_text(
            front_matter, encoding="utf-8")


def test_known_eps_scans_the_episodes_dir(tmp_path, monkeypatch):
    """期就是 `episodes/` 下的子目录——扫出来就认。"""
    _make_episode(tmp_path, "beta")
    _make_episode(tmp_path, "alpha")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == ["alpha", "beta"]


def test_known_eps_ignores_files_and_hidden_dirs(tmp_path, monkeypatch):
    """说明文件与隐藏目录不是期。"""
    _make_episode(tmp_path, "alpha")
    (tmp_path / "README.md").write_text("说明", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == ["alpha"]


def test_known_eps_at_scans_any_root(tmp_path):
    """指定根目录时同样按目录扫——夹具期与外部调用走这条。"""
    _make_episode(tmp_path, "one")
    _make_episode(tmp_path, "two")
    assert episodes_mod.known_eps_at(tmp_path) == ["one", "two"]


def test_known_eps_is_empty_when_there_are_no_episodes(tmp_path, monkeypatch):
    """没有期就没有期——空列表是合法答案，不是错。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == []
    assert episodes_mod.known_eps_at(tmp_path / "nope") == []


def test_episode_paths_all_live_in_the_episode_dir(tmp_path, monkeypatch):
    """期目录里的每个文件名都是定好的，路径一律从期目录派生。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    ep = episodes_mod.episode("some-slug")
    base = tmp_path / "some-slug"
    assert ep.script == base / "口播稿.md"
    assert ep.contract == base / "contract.json"
    assert ep.publish == base / "publish.json"
    assert ep.narration == base / "narration.mp3"
    assert ep.storyboard == base / "storyboard.json"
    assert ep.review == base / "review.md"
    assert ep.frames_dir == base / "frames"
    assert ep.frames_manifest == base / "frames.md"


def test_module_level_path_helpers_match_the_episode(tmp_path, monkeypatch):
    """模块级的那几个 `*_path()` 说的是同一件事。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.script_path("s") == tmp_path / "s" / "口播稿.md"
    assert episodes_mod.contract_path("s") == tmp_path / "s" / "contract.json"
    assert episodes_mod.publish_path("s") == tmp_path / "s" / "publish.json"
    assert episodes_mod.narration_path("s") == tmp_path / "s" / "narration.mp3"
    assert episodes_mod.storyboard_path("s") == tmp_path / "s" / "storyboard.json"
    assert episodes_mod.review_path("s") == tmp_path / "s" / "review.md"
    assert episodes_mod.frames_dir("s") == tmp_path / "s" / "frames"
    assert episodes_mod.frames_manifest_path("s") == tmp_path / "s" / "frames.md"


def test_episode_at_accepts_any_root(fixture_episode_dir):
    """夹具期不在默认根下时，路径照样由目录说了算。"""
    ep = episodes_mod.episode_at(fixture_episode_dir, "fixture")
    assert ep.slug == "fixture"
    assert ep.root == fixture_episode_dir
    assert ep.script == fixture_episode_dir / "口播稿.md"
    assert ep.contract == fixture_episode_dir / "contract.json"


def test_ep_number_is_read_from_the_script_front_matter(tmp_path, monkeypatch):
    """期号是编辑事实，落在口播稿 front matter 的 `episode_number` 里。

    **`episode` 是 slug（身份），不是期号**——两者混了，期号会取成目录名。
    """
    _make_episode(tmp_path, "s",
                  front_matter='---\ntitle: "x"\nepisode: s\n'
                               'episode_number: ep07\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("s") == "ep07"


def test_ep_number_does_not_read_the_slug(tmp_path, monkeypatch):
    """front matter 里只有 `episode`（slug）时，期号取不到——空串。"""
    _make_episode(tmp_path, "s", front_matter='---\nepisode: s\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("s") == ""


def test_ep_number_reads_the_fixture_episode(tmp_path, monkeypatch, fixture_episode_dir):
    """夹具期的 front matter 也要能被读出来。"""
    target = tmp_path / "fixture"
    target.mkdir()
    shutil.copy(fixture_episode_dir / "口播稿.md", target / "口播稿.md")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("fixture") == "ep01"


def test_the_fixture_episode_names_itself_after_its_directory(fixture_episode_dir):
    """夹具期的 `episode` 要跟期目录名一致。

    **身份由目录说了算**：slug 进路径（改标题不改路径），
    front matter 的 `episode` 跟它对齐。
    """
    fields = episodes_mod._front_matter(fixture_episode_dir / "口播稿.md")
    assert fields.get("episode") == fixture_episode_dir.name, (
        f"夹具期的 episode 写着 {fields.get('episode')!r}，"
        f"期目录名是 {fixture_episode_dir.name!r}——身份由目录说了算"
    )
    assert fields.get("episode_number") == "ep01"


def test_ep_number_is_empty_when_there_is_no_front_matter(tmp_path, monkeypatch):
    """取不到期号就返回空串——没有就该是空的，不该编一个。"""
    _make_episode(tmp_path, "s", front_matter="# 就是一份普通文档\n")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("s") == ""


def test_ep_number_is_empty_when_there_is_no_script(tmp_path, monkeypatch):
    """期目录存在但没有口播稿时，同样是空串。"""
    _make_episode(tmp_path, "s")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("s") == ""


def test_ep_number_is_empty_when_front_matter_has_no_episode(tmp_path, monkeypatch):
    """front matter 里有别的键、就是没有期号时，也是空串。"""
    _make_episode(tmp_path, "s", front_matter='---\ntitle: "x"\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number("s") == ""
