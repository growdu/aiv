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
    """一份合法的抖音发布元数据（`publish.json` 的内容）。

    `episode` 字段填**期路径**——出包时它要跟 adapter 拿到的那个期号对上
    （`pyv.epmeta.check_meta` 的 `epmeta.episode` 那道闸）。

    `url` 是站点详情页：**抖音这一档不许把它放进文案**，
    所以这里给它一个看着像站点地址的值，让那条规则有东西可守。
    """
    payload = {
        "episode": episode,
        "title": "PostgreSQL 18 并行逻辑解码",
        "cover_at": 1.0,
        "url": "https://example.invalid/2026/11/12/postgres/",
        # 平台段落在 `platforms` 下面——平台清单是扫出来的，
        # 顶层摊开的话「哪些键是平台」就又变成写死的清单了。
        "platforms": {
            "douyin": {
                "title": "32 核机器，解码只占 1 核",
                "description": "默认发布端只有一个解码线程，串行处理。",
                "topics": ["PostgreSQL", "逻辑复制", "数据库内核"],
            },
        },
    }
    payload.update(overrides)
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


def synthetic_copies() -> list[tuple[str, dict]]:
    """三期形状不同的合成文案：短版、中版、长版。

    三个档位各有自己的文案（同一篇文档的三档是三期），
    长度与话题数都不一样——闸要在这几种形状上都验一遍。
    """
    shapes = (
        ("数据库内核/事务与并发/行锁/short", {
            "title": "32 核机器，解码只占 1 核",
            "description": "默认发布端只有一个解码线程，串行处理。",
            "topics": ["PostgreSQL", "逻辑复制", "数据库内核"],
        }),
        ("数据库内核/事务与并发/行锁/mid", {
            "title": "行锁：一条 UPDATE 卡住整张表",
            "description": "从 MVCC 讲到锁的等待队列，看清楚并发是怎么串起来的。",
            "topics": ["PostgreSQL", "行锁", "MVCC", "事务", "并发"],
        }),
        ("数据库内核/事务与并发/行锁/full", {
            "title": "从快照隔离到 Serializable：隔离级别怎么实现的",
            "description": "从快照隔离到 Serializable，隔离级别到底怎么实现的，一讲到底。"
                          * 10,
            "topics": ["数据库", "内核"],
        }),
    )
    return [(episode, publish_payload(episode, douyin=section))
            for episode, section in shapes]


def _encode(path: Path, seconds: int = 3, size: str = "1920x1080") -> Path:
    """造一段合法的小视频。

    尺寸、像素格式与 faststart 都按视频平台自己的门槛来
    （`platforms/douyin/capability.toml` 的 `[media]`）：
    出包前要过技术预检，fixture 自己不合规的话，
    测到的就只剩预检，而不是出包。

    `size` 默认横版；抖音那一档实际发的是竖版 9:16，所以这里要能造竖版。
    """
    import subprocess

    proc = subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"testsrc=size={size}:rate=24:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(path),
    ], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return path


@pytest.fixture
def make_video():
    """给一个路径，在那儿造一段合规的小视频。"""
    def _make(path, seconds: int = 3, size: str = "1920x1080") -> Path:
        return _encode(Path(path), seconds, size)
    return _make


@pytest.fixture(autouse=True)
def outbox(tmp_path, monkeypatch):
    """测试期间状态快照写进临时目录。

    默认位置是 `platforms/douyin/outbox/`（规格 §7.5），那是仓库里的一个目录——
    测试不该往仓库里写东西，出了包也说不清是哪次跑的。
    """
    from douyin import snapshot

    target = tmp_path / "outbox"
    monkeypatch.setattr(snapshot, "OUTBOX_DIR", target)
    return target


@pytest.fixture(autouse=True, scope="session")
def _the_repo_outbox_stays_untouched():
    """测试不许往仓库里的 `platforms/douyin/outbox` 写东西。

    **基准是会话起点，不是每个测试的前后。** 前后比对看不见**上一个
    测试**留下的东西——那个文件在本次起点就已经存在了，于是「前后一样」，
    守卫报一切正常。而脏文件恰恰会活过整个 session，最后混进提交。

    再补一条判据：**入库目录里只允许有 git 跟踪的文件**。测试写出来的
    文件一定是未跟踪的，`git ls-files` 是唯一能发现「上个 session
    遗留」的办法。

    踩过的坑：命令行测试是**另一个进程**，conftest 里把快照目录改到
    临时区拦不住它——它把 `platforms/douyin/outbox/structured-ddl__douyin.json`
    写成了指向 pytest 临时目录的垃圾：文件在、JSON 合法、看着像真的
    状态，下一个人读到的是假的。
    """
    repo_outbox = REPO_ROOT / "platforms" / "douyin" / "outbox"

    def _on_disk():
        if not repo_outbox.is_dir():
            return {}
        return {path.name: path.read_bytes()
                for path in sorted(repo_outbox.glob("*.json"))}

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
        result = subprocess.run(["git", "ls-files", "-z", "platforms/douyin/outbox"],
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
    assert not changed, f"测试往仓库的 platforms/douyin/outbox 写了东西：{changed}"

    tracked = _tracked()
    if tracked is not None:
        untracked = sorted(
            name for name in after
            if f"platforms/douyin/outbox/{name}" not in tracked
        )
        assert not untracked, (
            f"platforms/douyin/outbox 里有没被 git 跟踪的文件：{untracked}"
            f"（上个 session 留下的脏文件，或本次测试写的）"
        )


@pytest.fixture
def meta():
    """一份合法的抖音元数据。

    `cover_at` 落在成片时长之内——取帧点超出成片，ffmpeg 抽不出画面。
    """
    return epmeta.EpisodeMeta(
        episode="ep01",
        title="PostgreSQL 18 并行逻辑解码",
        cover_at=1.0,
        url="https://growdu.cn/2026/11/12/life/aiv/",
        platforms={
            "douyin": {
                "title": "32 核机器，解码只占 1 核",
                "description": "默认发布端只有一个解码线程，串行处理。",
                "topics": ["PostgreSQL", "逻辑复制", "数据库内核"],
            },
        },
    )


@pytest.fixture
def video(tmp_path, make_video):
    """现场造一段 3 秒的小视频当成片。"""
    return make_video(tmp_path / "ep01.mp4")


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
