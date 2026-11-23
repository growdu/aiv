"""期定位的守卫：一期 = 一个档位目录，坐标说了算。

**坐标就是接口**：期路径 = `系列/合集/文档/档位`，相对期根四层。
期 = 一个**档位目录**——同一篇文档的三档是三期，各有自己的口播稿、
契约、旁白；共享的是那一篇文档的骨架。

**这里没有登记表**：期在磁盘上是什么，路径就是什么。
所以这些用例盯的不是「登记表和代码对得上」，而是「坐标扫得出来、
路径指得对、三个名字读得到」四件事。
"""
from __future__ import annotations

import shutil

from pyv import episodes as episodes_mod

#: 一条典型的期路径。
EP = "系列甲/合集甲/文档甲/short"
#: 它属于哪篇文档（去掉档位）。
DOC = "系列甲/合集甲/文档甲"


def _make_episode(root, ep: str, *, front_matter: str | None = None) -> None:
    """在 `root` 下造一期的目录（内容不算数，只有形状算数）。"""
    directory = root / ep
    directory.mkdir(parents=True)
    if front_matter is not None:
        (directory / episodes_mod.SCRIPT_NAME).write_text(
            front_matter, encoding="utf-8")


def test_known_eps_scans_the_episodes_dir(tmp_path, monkeypatch):
    """期就是坐标四层、末段是档位名的目录——扫出来就认。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short")
    _make_episode(tmp_path, "系列乙/合集乙/文档乙/full")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == [
        "系列乙/合集乙/文档乙/full",
        "系列甲/合集甲/文档甲/short",
    ]


def test_known_eps_ignores_files_hidden_dirs_and_shallow_dirs(tmp_path, monkeypatch):
    """说明文件、隐藏目录、层数不对的目录都不是期。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short")
    (tmp_path / "README.md").write_text("说明", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    # 层数不对：三级（文档目录本身）与五级。
    (tmp_path / "系列甲" / "合集甲" / "文档甲" / "short" / "frames").mkdir()
    (tmp_path / "系列乙" / "合集乙").mkdir(parents=True)
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == ["系列甲/合集甲/文档甲/short"]


def test_known_eps_ignores_dirs_whose_last_segment_is_not_a_tier(tmp_path, monkeypatch):
    """末段不是档位名的目录不是期——**档位名是坐标的一部分**。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short")
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/预览")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == ["系列甲/合集甲/文档甲/short"]


def test_known_eps_at_scans_any_root(tmp_path):
    """指定根目录时同样按坐标扫——夹具期与外部调用走这条。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short")
    _make_episode(tmp_path, "系列甲/合集甲/文档乙/mid")
    assert episodes_mod.known_eps_at(tmp_path) == [
        "系列甲/合集甲/文档乙/mid",
        "系列甲/合集甲/文档甲/short",
    ]


def test_known_eps_is_empty_when_there_are_no_episodes(tmp_path, monkeypatch):
    """没有期就没有期——空列表是合法答案，不是错。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_eps() == []
    assert episodes_mod.known_eps_at(tmp_path / "nope") == []


def test_known_docs_groups_the_three_tiers_of_one_document(tmp_path, monkeypatch):
    """文档是三期的父目录——一篇文档出三期，共享一份骨架。"""
    for tier in episodes_mod.TIERS:
        _make_episode(tmp_path, f"系列甲/合集甲/文档甲/{tier}")
    _make_episode(tmp_path, "系列甲/合集甲/文档乙/short")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.known_docs() == [
        "系列甲/合集甲/文档乙",
        "系列甲/合集甲/文档甲",
    ]


def test_episode_paths_all_live_in_the_episode_dir(tmp_path, monkeypatch):
    """期目录里的每个文件名都是定好的，路径一律从期目录派生。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    ep = episodes_mod.episode(EP)
    base = tmp_path / EP
    assert ep.script == base / "口播稿.md"
    assert ep.contract == base / "contract.json"
    assert ep.publish == base / "publish.json"
    assert ep.narration == base / "narration.mp3"
    assert ep.storyboard == base / "storyboard.json"
    assert ep.review == base / "review.md"
    assert ep.frames_dir == base / "frames"
    assert ep.frames_manifest == base / "frames.md"


def test_episode_knows_its_document_and_tier(tmp_path, monkeypatch):
    """一期知道自己是哪篇文档的哪一档。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    ep = episodes_mod.episode(EP)
    assert ep.doc == DOC
    assert ep.tier == "short"


def test_module_level_path_helpers_match_the_episode(tmp_path, monkeypatch):
    """模块级的那几个 `*_path()` 说的是同一件事。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.script_path(EP) == tmp_path / EP / "口播稿.md"
    assert episodes_mod.contract_path(EP) == tmp_path / EP / "contract.json"
    assert episodes_mod.publish_path(EP) == tmp_path / EP / "publish.json"
    assert episodes_mod.narration_path(EP) == tmp_path / EP / "narration.mp3"
    assert episodes_mod.storyboard_path(EP) == tmp_path / EP / "storyboard.json"
    assert episodes_mod.review_path(EP) == tmp_path / EP / "review.md"
    assert episodes_mod.frames_dir(EP) == tmp_path / EP / "frames"
    assert episodes_mod.frames_manifest_path(EP) == tmp_path / EP / "frames.md"


def test_skeleton_lives_in_the_document_dir(tmp_path, monkeypatch):
    """讲稿骨架是**文档级**的——三档共用一份。"""
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.skeleton_path(DOC) == tmp_path / DOC / "skeleton.yaml"


def test_ep_id_flattens_the_coordinate_into_one_filename(tmp_path, monkeypatch):
    """期路径压平成一个文件名片段——**片段目录**与 outbox 快照文件名用它。"""
    assert episodes_mod.ep_id(EP) == "系列甲-合集甲-文档甲-short"


def test_the_cut_path_is_nested_under_the_episode(tmp_path, monkeypatch):
    """成片的路径由**一处**算出来：out/<系列>/<合集>/<文档>/<档位>.mp4。

    preflight 与 review 今天各算一遍（两处都写着 ``episodes.ep_id(...)``），
    改的时候漏一处就找不到成片了——所以收进 ``episodes.cut_path``。
    """
    monkeypatch.setattr(episodes_mod, "AIV_ROOT", tmp_path)
    assert episodes_mod.cut_path("演示系列/演示合集/夹具文档/short") == \
        tmp_path / "out" / "演示系列/演示合集/夹具文档/short.mp4"


def test_episode_at_accepts_any_root(fixture_episode_dir):
    """夹具期不在默认根下时，路径照样由目录说了算。"""
    ep = episodes_mod.episode_at(fixture_episode_dir, "演示系列/演示合集/夹具文档/short")
    assert ep.ep == "演示系列/演示合集/夹具文档/short"
    assert ep.root == fixture_episode_dir
    assert ep.doc == "演示系列/演示合集/夹具文档"
    assert ep.tier == "short"
    assert ep.script == fixture_episode_dir / "口播稿.md"
    assert ep.contract == fixture_episode_dir / "contract.json"


def test_ep_number_is_read_from_the_script_front_matter(tmp_path, monkeypatch):
    """期号是编辑事实，落在口播稿 front matter 的 `episode_number` 里。

    **`episode` 是文档路径，`tier` 是档位**——都不是期号。
    """
    _make_episode(tmp_path, EP, front_matter='---\ntitle: "x"\n'
                                             'episode: 演示系列/演示合集/夹具文档\n'
                                             'tier: short\n'
                                             'episode_number: ep07\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == "ep07"


def test_ep_number_does_not_read_the_document_path(tmp_path, monkeypatch):
    """front matter 里只有 `episode`（文档路径）时，期号取不到——空串。"""
    _make_episode(tmp_path, EP,
                  front_matter='---\nepisode: 演示系列/演示合集/夹具文档\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == ""


def test_ep_number_reads_the_fixture_episode(tmp_path, monkeypatch, fixture_episode_dir):
    """夹具期的 front matter 也要能被读出来。"""
    target = tmp_path / EP
    target.mkdir(parents=True)
    shutil.copy(fixture_episode_dir / "口播稿.md", target / "口播稿.md")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == "ep01"


def test_the_fixture_episode_names_its_document_and_tier(fixture_episode_dir):
    """夹具期的 `episode` 是**文档路径**，`tier` 是档位。

    **身份由目录说了算**：期目录是四层坐标，`episode` 记前三层（哪篇文档），
    `tier` 记第四层（哪一档）。
    """
    fields = episodes_mod._front_matter(fixture_episode_dir / "口播稿.md")
    assert fields.get("episode") == "演示系列/演示合集/夹具文档", (
        f"夹具期的 episode 写着 {fields.get('episode')!r}——"
        f"它该是文档路径（去掉档位）"
    )
    assert fields.get("tier") == "short"
    assert fields.get("episode_number") == "ep01"


def test_ep_number_is_empty_when_there_is_no_front_matter(tmp_path, monkeypatch):
    """取不到期号就返回空串——没有就该是空的，不该编一个。"""
    _make_episode(tmp_path, EP, front_matter="# 就是一份普通文档\n")
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == ""


def test_ep_number_is_empty_when_there_is_no_script(tmp_path, monkeypatch):
    """期目录存在但没有口播稿时，同样是空串。"""
    _make_episode(tmp_path, EP)
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == ""


def test_ep_number_is_empty_when_front_matter_has_no_episode(tmp_path, monkeypatch):
    """front matter 里有别的键、就是没有期号时，也是空串。"""
    _make_episode(tmp_path, EP, front_matter='---\ntitle: "x"\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_number(EP) == ""


def test_ep_doc_and_ep_tier_read_the_two_other_names(tmp_path, monkeypatch):
    """**三个名字各读各的**：`episode` 是文档路径，`tier` 是档位。

    混了的后果：契约比对会把三档当成三篇不同的文档，
    于是同一篇文档的 short 与 full 互相「不一致」。
    """
    _make_episode(tmp_path, EP, front_matter='---\n'
                                             'episode: 演示系列/演示合集/夹具文档\n'
                                             'tier: short\n'
                                             'episode_number: ep07\n---\n')
    monkeypatch.setattr(episodes_mod, "EPISODES_DIR", tmp_path)
    assert episodes_mod.ep_doc(EP) == "演示系列/演示合集/夹具文档"
    assert episodes_mod.ep_tier(EP) == "short"


# ── 坐标与口播稿要对得上 ─────────────────────────────────
#
# **坐标是目录说了算**（期路径四层），口播稿 front matter 里的
# `episode` / `tier` / `episode_number` 是同一件事的**第二遍抄写**。
# 两遍抄写对不上时，没有哪一遍是对的——所以这里把它们对一遍。


def test_a_tier_that_disagrees_with_the_directory_is_caught(tmp_path):
    """口播稿写的档位必须等于目录的第四层。

    对不上的后果不是「显示难看」：三档裁剪器按 role 裁出 short / mid / full，
    而**目录名**才是这一期到底是什么档的凭据。两处对不上时，
    出片管线裁的是一档，发出去的是另一档。
    """
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short",
                  front_matter="---\nepisode: 系列甲/合集甲/文档甲\n"
                               "tier: mid\n---\n")
    problems = episodes_mod.coordinate_problems(tmp_path)
    assert any("tier=mid" in p and "目录是 short" in p for p in problems), problems


def test_a_document_path_that_disagrees_with_the_directory_is_caught(tmp_path):
    """口播稿的 `episode` 记的必须是**文档路径**（前三层）。

    记成别的，契约比对就把同一篇文档的三档当成三篇不同的文档——
    short 与 full 互相「不一致」，而人看不出哪一处错了。
    """
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short",
                  front_matter="---\nepisode: 系列甲/合集甲/文档乙\n"
                               "tier: short\n---\n")
    problems = episodes_mod.coordinate_problems(tmp_path)
    assert any("episode=系列甲/合集甲/文档乙" in p for p in problems), problems


def test_two_episodes_with_the_same_number_are_caught(tmp_path):
    """**两个期不许共用一个期号**。

    期号是内容单元的文件名（``content/units/video/<期号>.md``）——
    两期共用一个期号，内容单元就撞车了，后写的把先写的**盖掉**，
    而且**一声不响**：构建成功，产物少一期。
    """
    for ep in ("系列甲/合集甲/文档甲/short", "系列乙/合集乙/文档乙/full"):
        _make_episode(tmp_path, ep,
                      front_matter="---\n"
                                   f"episode: {ep.rsplit('/', 1)[0]}\n"
                                   "tier: short\n"
                                   "episode_number: ep01\n---\n")
    problems = episodes_mod.coordinate_problems(tmp_path)
    assert any("期号 ep01" in p and "重复" in p for p in problems), problems


def test_a_consistent_episode_tree_has_no_problems(tmp_path):
    """对得上的时候不许报问题——这条守卫不许变成噪音。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short",
                  front_matter="---\nepisode: 系列甲/合集甲/文档甲\n"
                               "tier: short\nepisode_number: ep01\n---\n")
    assert episodes_mod.coordinate_problems(tmp_path) == []


def test_a_directory_without_a_script_is_not_an_episode(tmp_path):
    """没有口播稿的目录不是期——不算坐标问题，也别拿它当一期。"""
    _make_episode(tmp_path, "系列甲/合集甲/文档甲/short")
    assert episodes_mod.coordinate_problems(tmp_path) == []


def test_the_real_episode_tree_has_no_coordinate_problems():
    """仓库里真的那些期，坐标与口播稿必须对得上。

    今天期树是空的（视频线清空重来），所以这条**此刻是空的断言**——
    等第一批期入库，它立刻开始盯人。
    """
    assert episodes_mod.coordinate_problems() == []


def test_every_document_has_a_short_tier():
    """每一篇文档都得有 **short** 档。

    short 是默认档：学习流、视频平台（抖音 / 视频号只收 short）
    与站上那一面都指向它。缺了 short，一期视频在默认的口径下**哪儿都不出现**。
    """
    root = episodes_mod.EPISODES_DIR
    if not root.is_dir():
        return
    for doc in episodes_mod.known_docs_at(root):
        tiers = {
            path.name for path in (root / doc).iterdir()
            if path.is_dir() and path.name in episodes_mod.TIERS
        }
        assert "short" in tiers, f"{doc} 没有 short 档"
