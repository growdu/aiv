import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "platforms", REPO_ROOT / "video" / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from pyv import epmeta  # noqa: E402


# --- 合成的一期 -------------------------------------------------------------
#
# **仓库里不再存着任何一期**：内容是使用者自己的事（框架只做框架）。
# 所以期在测试里现造——造出来的形状必须跟现在的坐标一致：
#
# ```
# video/episodes/<系列>/<合集>/<文档>/<档位>/publish.json
#                  一级   二级   三级   四级
# ```
#
# 一期 = 一个档位目录，期身份是**期目录相对期根的路径**（四段，斜杠连起来）。
# `pyv.epmeta.load_meta(期路径)` 落到 `期根/期路径/publish.json`，
# 所以期路径同时也是 adapter 命令行上那个「期号」。

#: 合成期的坐标：系列 / 合集 / 文档 / 档位。
EP_COORD = ("数据库内核", "事务与并发", "行锁", "short")

#: 期路径（期身份）：四段用斜杠连起来。
EP_PATH = "/".join(EP_COORD)


def publish_payload(episode: str = EP_PATH, **overrides) -> dict:
    """一份合法的B站发布元数据（`publish.json` 的内容）。

    `episode` 字段填**期路径**——出包时它要跟 adapter 拿到的那个期号对上
    （`pyv.epmeta.check_meta` 的 `epmeta.episode` 那道闸）。

    B站这一档的必填字段按 `pyv/epmeta.py` 的 `PLATFORM_SPECS["bilibili"]`：
    `title` / `description` / `tags`（列表）/ `tid`（整数）/
    `copyright`（1 = 原创，2 = 转载）/ `no_reprint`（0 或 1）。
    `copyright = 2`（转载）必须额外给 `source`——见 `reprint_payload`。

    `url` 是站点详情页，给它一个占位地址（框架源码与用例里不内联实例身份）。
    """
    payload = {
        "episode": episode,
        "title": "一个 64 位计数器，决定所有事务的提交顺序",
        "cover_at": 1.0,
        "url": "https://example.invalid/2026/11/12/row-lock/",
        "bilibili": {
            "title": "一个 64 位计数器，决定所有事务的提交顺序",
            "description": "并发时 commit 的先后是乱的。",
            "tags": ["数据库", "源码", "并发"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },
    }
    payload.update(overrides)
    return payload


def reprint_payload(episode: str = EP_PATH, **overrides) -> dict:
    """转载那一档的元数据：`copyright = 2`，必须给 `source`。

    `source` 是转载的来源地址——平台会拒没有来源的转载（规格 §4.3），
    所以这一档的语料里它必须在场。
    """
    payload = publish_payload(episode)
    payload["bilibili"].update({
        "copyright": 2,
        "no_reprint": 0,
        "source": "https://example.invalid/2026/11/12/row-lock/origin/",
    })
    payload["bilibili"].update(overrides)
    return payload


def write_episode(root: Path, episode: str = EP_PATH,
                  payload: dict | None = None) -> Path:
    """在期根 `root` 下造一期：四层坐标的目录 + `publish.json`。

    返回期目录。目录建在 `root/期路径` 下——期身份就是目录的相对路径。
    """
    target = Path(root) / episode
    target.mkdir(parents=True, exist_ok=True)
    (target / epmeta.PUBLISH_NAME).write_text(
        json.dumps(payload if payload is not None else publish_payload(episode),
                   ensure_ascii=False),
        encoding="utf-8")
    return target


def _encode(path: Path, seconds: int = 3) -> Path:
    """造一段合法的小视频。

    参数按B站自己的门槛来（`platforms/bilibili/capability.toml` 的 `[media]`）：
    B站不设最小分辨率，但设了 `max_keyframe_gap_s = 10`。
    夹具自己不合格的话，测到的就只剩预检，而不是出包。
    """
    import subprocess

    proc = subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"testsrc=size=320x180:rate=24:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-g", "48",
        str(path),
    ], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return path


@pytest.fixture
def make_video():
    """给一个路径，在那儿造一段合规的小视频。"""
    def _make(path, seconds: int = 3) -> Path:
        return _encode(Path(path), seconds)
    return _make


@pytest.fixture(autouse=True)
def outbox(tmp_path, monkeypatch):
    """测试期间状态快照写进临时目录。

    默认位置是 `platforms/bilibili/outbox/`（规格 §7.5），那是仓库里的一个目录——
    测试不该往仓库里写东西，出了包也说不清是哪次跑的。
    """
    from bilibili import snapshot

    target = tmp_path / "outbox"
    monkeypatch.setattr(snapshot, "OUTBOX_DIR", target)
    return target


@pytest.fixture(autouse=True, scope="session")
def _the_repo_outbox_stays_untouched():
    """测试不许往仓库里的 `platforms/bilibili/outbox` 写东西。

    **基准是会话起点，不是每个测试的前后。** 前后比对看不见**上一个
    测试**留下的东西——那个文件在本次起点就已经存在了，于是「前后一样」，
    守卫报一切正常。而脏文件恰恰会活过整个 session，最后混进提交。

    再补一条判据：**入库目录里只允许有 git 跟踪的文件**。测试写出来的
    文件一定是未跟踪的，`git ls-files` 是唯一能发现「上个 session
    遗留」的办法。
    """
    repo_outbox = REPO_ROOT / "platforms" / "bilibili" / "outbox"

    def _on_disk():
        if not repo_outbox.is_dir():
            return {}
        # **递归找。** 快照文件名是 `<压平期路径>__bilibili.json`
        # （期路径压平：斜杠换连字符），落在入库目录的**第一层**——
        # 递归着找更保险：第一层的东西本来就该被看见，
        # 将来若又有人在下面长出子目录，也不会漏。
        return {path.relative_to(repo_outbox).as_posix(): path.read_bytes()
                for path in sorted(repo_outbox.rglob("*.json"))}

    def _tracked():
        import subprocess

        probe = subprocess.run(["git", "rev-parse", "--git-dir"],
                               cwd=REPO_ROOT, capture_output=True)
        if probe.returncode != 0:
            return None                      # 不在 git 仓库里，跳过这条判据
        # **`-z` 是必须的**：默认的 `git ls-files` 遇到非 ASCII 路径会把它
        # 写成八进制转义并加引号（"a\346\227\245.json"），拿那个字符串去跟
        # 文件系统上的真实中文名比对，永远比不上——守卫就成了永远误报的摆设。
        # `-z` 输出的是 NUL 分隔的原始路径，不转义、不加引号。
        result = subprocess.run(
            ["git", "ls-files", "-z", "platforms/bilibili/outbox"],
            cwd=REPO_ROOT, capture_output=True)
        raw = result.stdout.decode("utf-8", errors="replace")
        return {line for line in raw.split("\0") if line.strip()}

    before = _on_disk()
    yield
    after = _on_disk()

    changed = sorted(
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    assert not changed, (
        f"测试往仓库的 platforms/bilibili/outbox 写了东西：{changed}")

    tracked = _tracked()
    if tracked is not None:
        untracked = sorted(
            name for name in after
            if f"platforms/bilibili/outbox/{name}" not in tracked
        )
        assert not untracked, (
            f"platforms/bilibili/outbox 里有没被 git 跟踪的文件：{untracked}"
            f"（上个 session 留下的脏文件，或本次测试写的）"
        )


@pytest.fixture
def meta():
    """一份合法的B站元数据。

    `cover_at` 落在成片时长之内——取帧点超出成片，ffmpeg 抽不出画面。
    """
    return epmeta.EpisodeMeta(
        episode="ep02",
        title="一个 64 位计数器，决定所有事务的提交顺序",
        cover_at=1.0,
        url="https://example.invalid/2026/11/12/row-lock/",
        bilibili={
            "title": "一个 64 位计数器，决定所有事务的提交顺序",
            "description": "并发时 commit 的先后是乱的。",
            "tags": ["openGauss", "数据库", "源码"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },
    )


@pytest.fixture
def video(tmp_path, make_video):
    """现场造一段 3 秒的小视频当成片。"""
    return make_video(tmp_path / "ep02.mp4")


@pytest.fixture
def subtitle_events():
    """几条字幕事件。"""
    from bilibili import subtitle

    return [
        subtitle.SubtitleEvent(start=0.0, end=2.5, text="第一句"),
        subtitle.SubtitleEvent(start=2.5, end=5.0, text="第二句"),
    ]


# --- 磁盘上的那一期 ---------------------------------------------------------


@pytest.fixture
def episodes_root(tmp_path, monkeypatch):
    """期根指到临时目录。

    `pyv.epmeta` 的期根是模块常量 `EPISODES_DIR`（`meta_path` 读它，
    `load_meta` 也就靠它找 `期路径/publish.json`）——
    改这一个常量，adapter 与测试就都落在临时目录里。

    仓库里不再存着任何一期，所以这不是「绕过」什么，是现在唯一的形态。
    """
    root = tmp_path / "episodes"
    root.mkdir()
    monkeypatch.setattr(epmeta, "EPISODES_DIR", root)
    return root


@pytest.fixture
def episode_dir(episodes_root):
    """一期合成的期目录（四层坐标），里面有一份 `publish.json`。"""
    return write_episode(episodes_root)


@pytest.fixture
def on_disk_meta(episode_dir):
    """从磁盘读回来的那一期元数据（走 `epmeta.load_meta` 的默认路径）。

    这是 adapter 真正走的那条路：命令行拿期号 → 读元数据。
    """
    return epmeta.load_meta(EP_PATH)
