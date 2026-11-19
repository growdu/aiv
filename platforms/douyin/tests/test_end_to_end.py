"""端到端：合成成片 + 合成元数据走完整条出包链路。

**为什么单独立这一层。** 单元测试用的是合成的 fixture：它能验「出包这个
函数怎么工作」，验不了「成片和文案凑在一起还成立」。

这一层用**测试时现造的东西**：

- 成片：ffmpeg 现场编的一段竖版 9:16 小视频（抖音这一档真正发的那一版）；
- 元数据：临时目录里现造的 `publish.json`（四层坐标的期目录）。

跑的是真正的 `build_package`，不是拼出来的假象。

**仓库里不再存着任何一期**——内容是使用者自己的事（框架只做框架），
所以这一层也不依赖仓库里有哪几期：期在测试里现造，形状跟现在的坐标一致。
"""

import json
from pathlib import Path

import pytest

from conftest import EP_PATH, publish_payload, write_episode
from douyin import contract, package
from pyv import epmeta, preflight

#: 三个档位：同一篇文档的三档是三期，各有各的文案。
TIERS = ("short", "mid", "full")


def _episode(root: Path, episode: str) -> epmeta.EpisodeMeta:
    """在期根 `root` 下造一期，返回读回来的元数据。

    走 `epmeta.load_meta(episode, root=...)`——`root` 给定时，
    当成**期目录本身**（`meta_path` 的这一条语义就是给测试与外部调用留的）。
    """
    directory = write_episode(root, episode, publish_payload(episode))
    return epmeta.load_meta(episode, root=directory)


@pytest.fixture(scope="module")
def vertical_video(tmp_path_factory):
    """一段够长的竖版合成成片。

    竖版 9:16（同时也是无品牌导流版）——抖音这一档实际发出去的那一版。
    刻意不用横版：拿横版出包，验的就不是要发的那条片子了。

    模块级：造一次，三档共用——ffmpeg 编一次比编三次省得多。
    """
    from conftest import _encode

    return _encode(tmp_path_factory.mktemp("video") / "vertical.mp4",
                   seconds=5, size="1080x1920")


# --- 一期走完 ---------------------------------------------------------------


def test_a_synthetic_episode_packages_end_to_end(episode_dir, on_disk_meta,
                                                  vertical_video, tmp_path,
                                                  outbox):
    """合成成片 + 合成元数据 → 出包 → 快照。"""
    result = package.build_package(EP_PATH, on_disk_meta, vertical_video,
                                   tmp_path / "out")

    # 包里的东西都在
    for name in ("video.mp4", "cover.jpg", "title.txt", "description.txt",
                 "topics.txt", "text.txt", "publish.md", "meta.json"):
        assert (result.dir / name).is_file(), f"缺 {name}"

    # 软链指向真实成片，不是复制品
    assert (result.dir / "video.mp4").resolve() == vertical_video.resolve()

    # 发出去的那一版是**竖版 9:16**。成片哪天换回横版，这条要红。
    info = preflight.probe(vertical_video)
    assert (info.width, info.height) == (1080, 1920), (
        f"成片不是竖版 9:16（{info.width}×{info.height}）"
    )

    # text.txt 是元数据拼出来的那一段，一个字不差
    copy = contract.slice_copy(on_disk_meta)
    assert (result.dir / "text.txt").read_text(encoding="utf-8") == \
        contract.build_text(copy)

    # 快照写对了，而且写进的是本次测试的临时目录（没往仓库里写）
    shot = json.loads((outbox / f"{EP_PATH}__douyin.json")
                      .read_text(encoding="utf-8"))
    assert shot["platform"] == "douyin"
    assert shot["content_id"] == EP_PATH
    assert shot["status"] == "packaged"
    assert shot["published_url"] is None


def test_a_synthetic_cover_is_actually_a_frame(episode_dir, on_disk_meta,
                                                vertical_video, tmp_path):
    """封面得是**有内容**的一帧，不能是一张纯色图。

    「文件生成了」不等于「画面里真有东西」：抽帧点算错、ffmpeg 只输出了
    一个空帧，文件照样在。这条断言用的是**像素本身有变化**——
    纯色图（黑帧、白帧、纯色底）的像素方差接近 0。
    """
    from PIL import Image, ImageStat

    result = package.build_package(EP_PATH, on_disk_meta, vertical_video,
                                   tmp_path / "out")
    with Image.open(result.dir / "cover.jpg") as cover:
        cover = cover.convert("RGB")
        stat = ImageStat.Stat(cover)
        spread = max(stat.stddev)
        assert spread > 5, (
            f"封面几乎是纯色（最大通道标准差 {spread:.2f}）——"
            f"抽到的不是有画面的那一帧"
        )


# --- 三档全量 ---------------------------------------------------------------


@pytest.mark.parametrize("tier", TIERS)
def test_every_episode_packages_with_a_synthetic_video(tier, episodes_root,
                                                        vertical_video,
                                                        tmp_path):
    """三个档位都得能出包。

    这一条不依赖任何本机成片，所以**在 CI 上也真的跑**——
    证明的是「元数据 + 能力声明 + 预检」这一段链路是通的。
    """
    episode = "/".join((*EP_PATH.split("/")[:-1], tier))
    meta = _episode(episodes_root, episode)
    result = package.build_package(episode, meta, vertical_video,
                                   tmp_path / "out")
    assert result.status == "packaged"
    assert result.warnings == []


@pytest.mark.parametrize("tier", TIERS)
def test_the_packaged_text_never_carries_an_outbound_link(tier, episodes_root,
                                                            vertical_video,
                                                            tmp_path):
    """出包里的整段文案不得有站外引流。

    这是抖音最容易踩的雷：文案粘到平台上才被限流，
    而那时已经发出去了，只能删了重发。
    """
    episode = "/".join((*EP_PATH.split("/")[:-1], tier))
    meta = _episode(episodes_root, episode)
    result = package.build_package(episode, meta, vertical_video,
                                   tmp_path / "out")
    text = (result.dir / "text.txt").read_text(encoding="utf-8")
    assert contract.check_no_outbound(text) == [], episode
