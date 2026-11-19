"""出包：产物结构、字幕、封面尺寸、幂等、状态快照。"""

import dataclasses
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from bilibili import assets, package, snapshot, state
from conftest import EP_PATH, publish_payload, reprint_payload, write_episode


# --- 产物结构 ----------------------------------------------------------------


def test_build_package_writes_every_file(meta, video, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    for name in ("video.mp4", "cover.jpg", "title.txt", "description.txt", "tags.txt", "publish.md", "meta.json"):
        assert name in result.files, f"发布包缺 {name}"
        assert result.files[name].exists()


def test_the_video_is_a_symlink_not_a_copy(meta, video, tmp_path):
    """成片软链过去，不重复占空间。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    link = result.files["video.mp4"]
    assert link.is_symlink()
    assert link.resolve() == video.resolve()


def test_the_text_files_hold_the_copy(meta, video, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    assert result.files["title.txt"].read_text(encoding="utf-8") == meta.bilibili["title"]
    assert result.files["description.txt"].read_text(encoding="utf-8") == meta.bilibili["description"]
    assert result.files["tags.txt"].read_text(encoding="utf-8") == "openGauss,数据库,源码"


def test_the_checklist_says_pending_upload_not_published(meta, video, tmp_path):
    """「已发布」是发布场景里最贵的一种 bug——人以为发出去了，其实没有。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    checklist = result.files["publish.md"].read_text(encoding="utf-8")
    assert "待你上传" in checklist
    assert "已发布" not in checklist


def test_the_checklist_carries_the_partition_and_the_tags(meta, video, tmp_path):
    """清单是给人照着做的：分区与标签必须在里面。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    checklist = result.files["publish.md"].read_text(encoding="utf-8")
    assert "tid = 231" in checklist
    assert "openGauss,数据库,源码" in checklist


# --- 封面 --------------------------------------------------------------------


def test_the_cover_meets_the_bilibili_minimum(meta, video, tmp_path):
    """B站建议 ≥1146×717、最低 ≥960×600。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    with Image.open(result.files["cover.jpg"]) as image:
        assert image.size[0] >= assets.COVER_MIN[0]
        assert image.size[1] >= assets.COVER_MIN[1]
        assert image.size == assets.COVER_SIZE


def test_the_cover_is_cropped_not_stretched():
    """封面不能被拉变形——信息流里一眼就能看出来。

    做法：源图正中放一个正方形色块，裁切缩放之后它必须还是正方形。
    直接 resize 到目标尺寸会把 16:9 的画面横向压扁。
    """
    source = Image.new("RGB", (1920, 1080), "white")
    for x in range(960 - 54, 960 + 54):
        for y in range(540 - 54, 540 + 54):
            source.putpixel((x, y), (0, 0, 0))

    out = assets.fit_cover(source, assets.COVER_SIZE)
    assert out.size == assets.COVER_SIZE

    # 黑色块的包围盒：宽高必须一致
    # 阈值走查表（point 的序列重载）而不是 lambda：lambda 那条重载把参数
    # 标成 ImagePointTransform，在它上面做 < 比较类型检查器不认。
    black = out.convert("L").point([255 if v < 128 else 0 for v in range(256)])
    bbox = black.getbbox()
    assert bbox is not None, "封面里没有黑色块"
    left, upper, right, lower = bbox
    assert abs((right - left) - (lower - upper)) <= 2, f"封面被拉伸了：色块 {right - left}×{lower - upper}"
    # 而且不能小到没影：源图 108/1920 的宽度，缩放后仍是这个比例
    assert 60 <= (right - left) <= 85


def test_the_cover_cuts_the_sides_not_the_top_and_bottom():
    """16:9 比目标比例宽 → 切左右两边，不是上下。

    切错方向会把画面主体切掉。
    """
    source = Image.new("RGB", (1920, 1080), "white")
    # 左上角放一个标记点：切上下的话它会留下，切左右就会没
    for x in range(0, 40):
        for y in range(0, 40):
            source.putpixel((x, y), (0, 0, 0))

    out = assets.fit_cover(source, assets.COVER_SIZE)
    assert out.getpixel((0, 0)) != (0, 0, 0), "切的方向不对：左右没切掉"


def test_the_cover_is_a_jpeg(meta, video, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    with Image.open(result.files["cover.jpg"]) as image:
        assert image.format == "JPEG"


def test_the_cover_fails_loudly_when_the_frame_point_is_past_the_end(video, tmp_path):
    """取帧点超出成片时长时，ffmpeg 会「成功」但一个画面也不输出。

    实测：ffmpeg 退出码是 0，stderr 里写着 "Output file is empty"，
    但**没有生成文件**。不检查的话，就会把一个不存在的路径交给下一步——
    包里的 cover.jpg 是坏的，而命令报「成功」。
    """
    with pytest.raises(RuntimeError):
        assets.make_cover(video, 99.0, tmp_path / "cover.jpg")
    assert not (tmp_path / "cover.jpg").exists()


# --- 字幕 --------------------------------------------------------------------


def test_the_subtitle_file_is_written_when_events_are_given(meta, video, subtitle_events, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out", subtitle_events=subtitle_events)
    assert "subtitle.srt" in result.files
    text = result.files["subtitle.srt"].read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:00,000 --> 00:00:02,500\n第一句")


def test_the_subtitle_file_is_parsable(meta, video, subtitle_events, tmp_path):
    """SRT 的时间码格式：HH:MM:SS,mmm。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out", subtitle_events=subtitle_events)
    text = result.files["subtitle.srt"].read_text(encoding="utf-8")
    blocks = [b for b in text.strip().split("\n\n") if b.strip()]
    assert len(blocks) == 2
    for index, block in enumerate(blocks, start=1):
        lines = block.split("\n")
        assert lines[0] == str(index)
        assert re.fullmatch(
            r"\d{2}:\d{2}:\d{2},\d{3} --> "
            r"\d{2}:\d{2}:\d{2},\d{3}",
            lines[1],
        )
        assert lines[2].strip()


def test_without_events_there_is_no_subtitle_file(meta, video, tmp_path):
    """清单说「有的话一起传」——没有字幕就别留一个空文件。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    assert "subtitle.srt" not in result.files
    assert not (result.dir / "subtitle.srt").exists()


def test_the_subtitle_is_refreshed_when_the_events_change(meta, video, subtitle_events, tmp_path):
    """字幕是产物，跟着 storyboard 走——storyboard 变了，字幕必须跟着变。"""
    from bilibili import subtitle

    out = tmp_path / "out"
    package.build_package("ep02", meta, video, out, subtitle_events=subtitle_events)
    changed = [subtitle.SubtitleEvent(start=0.0, end=1.0, text="换了")]
    package.build_package("ep02", meta, video, out, subtitle_events=changed)
    text = (out / "ep02" / "subtitle.srt").read_text(encoding="utf-8")
    assert "换了" in text
    assert "第一句" not in text


def test_a_stale_subtitle_is_removed_when_the_events_are_gone(meta, video, subtitle_events, tmp_path):
    """storyboard 没了却留着旧字幕，人会传一个对不上的版本。"""
    out = tmp_path / "out"
    package.build_package("ep02", meta, video, out, subtitle_events=subtitle_events)
    assert (out / "ep02" / "subtitle.srt").exists()

    result = package.build_package("ep02", meta, video, out)
    assert "subtitle.srt" not in result.files
    assert not (out / "ep02" / "subtitle.srt").exists()


# --- 幂等 --------------------------------------------------------------------


def test_building_twice_with_the_same_video_is_idempotent(meta, video, tmp_path):
    out = tmp_path / "out"
    first = package.build_package("ep02", meta, video, out)
    second = package.build_package("ep02", meta, video, out)
    assert first.video_sha256 == second.video_sha256
    assert second.reused is True


def test_a_changed_video_rebuilds_the_package(meta, video, tmp_path, make_video):
    """成片变了就得重新出包——内容层键是成片的 sha256。"""
    out = tmp_path / "out"
    package.build_package("ep02", meta, video, out)

    # 重写成一段时长不同的合法视频（别往 mp4 里塞垃圾字节，抽帧会失败）
    make_video(video, seconds=2)

    again = package.build_package("ep02", meta, video, out)
    assert again.reused is False


def test_changing_the_copy_refreshes_the_package(meta, video, tmp_path):
    """改了文案重跑，文案必须跟着更新。

    成片没变 ≠ 文案没变。只认成片 sha256 的幂等会让包里的标题停在旧版本，
    而命令还报「成功」——那是静默成功。
    """
    out = tmp_path / "out"
    package.build_package("ep02", meta, video, out)

    changed = dataclasses.replace(meta, bilibili={**meta.bilibili, "title": "新标题"})
    result = package.build_package("ep02", changed, video, out)

    assert result.reused is True  # 视频与封面确实复用了
    assert (out / "ep02" / "title.txt").read_text(encoding="utf-8") == "新标题"
    assert "新标题" in (out / "ep02" / "publish.md").read_text(encoding="utf-8")


def _mark_published(out, episode, url):
    """模拟 `bilibili.cli mark published`：状态与包内快照一起更新。"""
    store = state.StateStore(out / "state.json")
    current = store.get(episode)
    current.status = "published"
    current.published_url = url
    store.save(episode, current)
    package.mark_published(out / episode, url)


def test_repackaging_keeps_the_published_status(meta, video, tmp_path, outbox):
    """重出包不能把人工回填的「已发布」抹成「待上传」。

    已经发出去的就是这一条片子，重新出包只是刷新文案。
    """
    out = tmp_path / "out"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    package.build_package("ep02", meta, video, out)
    _mark_published(out, "ep02", url)

    result = package.build_package("ep02", meta, video, out)
    assert result.status == "published"

    meta_json = json.loads((out / "ep02" / "meta.json").read_text(encoding="utf-8"))
    assert meta_json["status"] == "published"
    assert meta_json["published_url"] == url

    shot = json.loads((outbox / "ep02__bilibili.json").read_text(encoding="utf-8"))
    assert shot["status"] == "published"
    assert shot["published_url"] == url


def test_a_changed_video_resets_the_status(meta, video, tmp_path, make_video):
    """成片变了，之前发出去的是另一条片子，状态回到「待上传」。"""
    out = tmp_path / "out"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    package.build_package("ep02", meta, video, out)
    _mark_published(out, "ep02", url)

    other = make_video(tmp_path / "other.mp4", seconds=4)
    result = package.build_package("ep02", meta, other, out)

    assert result.reused is False
    assert result.status == "packaged"
    meta_json = json.loads((out / "ep02" / "meta.json").read_text(encoding="utf-8"))
    assert meta_json["status"] == "packaged"
    assert meta_json["published_url"] is None


def test_the_checklist_follows_the_state(meta, video, tmp_path):
    """清单写着「待你上传」而状态是「已发布」，人会**再传一遍**。

    人只看 `publish.md`——它和状态文件说的不是一回事，就是在平台上
    多出一条重复的作品。状态一变，清单的抬头与状态说明就得跟着变。
    """
    out = tmp_path / "out"
    package.build_package("ep02", meta, video, out)
    checklist = (out / "ep02" / "publish.md").read_text(encoding="utf-8")
    assert checklist.startswith("# 待发布：")
    assert "待你上传" in checklist

    _mark_published(out, "ep02", "https://www.bilibili.com/video/BV1xx411c7mD")
    checklist = (out / "ep02" / "publish.md").read_text(encoding="utf-8")
    assert checklist.startswith("# 已发布：")
    assert "待你上传" not in checklist


# --- 快照 --------------------------------------------------------------------


def test_the_package_writes_an_outbox_snapshot(meta, video, tmp_path):
    outbox = tmp_path / "outbox"
    package.build_package("ep02", meta, video, tmp_path / "out", outbox_dir=outbox)
    data = json.loads((outbox / "ep02__bilibili.json").read_text(encoding="utf-8"))
    assert data["platform"] == "bilibili"
    assert data["kind"] == "video"
    assert data["status"] == "packaged"
    assert data["published_url"] is None
    # 快照要入库——package_dir 必须是相对路径，不能是本机绝对路径
    assert not Path(data["package_dir"]).is_absolute(), f"package_dir 是绝对路径：{data['package_dir']}"


def test_the_snapshot_reads_the_automation_from_the_capability_file(meta, video, tmp_path, outbox):
    """档位由能力声明说了算，不能写死。

    写死的话，改完 TOML 快照还在说旧档位——那是静默的假话。
    """
    caps = tmp_path / "platforms"
    caps.mkdir()
    source = (Path(__file__).resolve().parents[3] / "platforms" / "bilibili"
              / "capability.toml")
    platform = caps / "bilibili"
    platform.mkdir()
    (platform / "capability.toml").write_text(
        source.read_text(encoding="utf-8").replace('automation = "manual"', 'automation = "api_publish"'),
        encoding="utf-8",
    )

    package.build_package("ep02", meta, video, tmp_path / "out", platforms_dir=caps)
    data = json.loads((outbox / "ep02__bilibili.json").read_text(encoding="utf-8"))
    assert data["automation"] == "api_publish"


def test_the_snapshot_automation_matches_the_repository_capability(meta, video, tmp_path, outbox):
    """默认出包时，档位就是仓库里那份能力声明写的那个。"""
    package.build_package("ep02", meta, video, tmp_path / "out")
    data = json.loads((outbox / "ep02__bilibili.json").read_text(encoding="utf-8"))
    assert data["automation"] == snapshot.automation_of()


def test_an_unchanged_snapshot_keeps_its_timestamp(tmp_path, monkeypatch):
    """内容没变，`updated_at` 不动。

    否则每次重跑都把工作树弄脏，而内容一个字都没变。
    """
    path = tmp_path / "outbox" / "ep02__bilibili.json"
    # 显式标注成 dict[str, Any]：dict(...) 推导出来的值类型是
    # str | None（published_url=None 拉低了整条），**payload 展开后
    # 每个关键字都变成 str | None，与 write_snapshot 的签名对不上。
    payload: dict[str, Any] = dict(
        episode="ep02",
        status="packaged",
        title="短标题",
        package_dir="platforms/bilibili/out/ep02",
        published_url=None,
        reason="理由",
    )
    snapshot.write_snapshot(path, **payload)
    first = json.loads(path.read_text(encoding="utf-8"))

    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    monkeypatch.setattr(snapshot, "_now", lambda: later)
    snapshot.write_snapshot(path, **payload)
    second = json.loads(path.read_text(encoding="utf-8"))

    assert second == first
    assert second["updated_at"] == first["updated_at"]


# --- 预检：error 停止，warning 继续但要写进清单 ------------------------------


def test_a_hard_violation_stops_the_package(meta, video, tmp_path, monkeypatch):
    """预检里 error 级别的要报错并停止——不能静默出一个发不出去的包。"""
    from pyv import epmeta

    def fake_check_meta(*args, **kwargs):
        return [epmeta.Finding("epmeta.text-limit", epmeta.ERROR, "bilibili 的 title 太长", "ep02")]

    monkeypatch.setattr(package.epmeta, "check_meta", fake_check_meta)
    out = tmp_path / "out"
    with pytest.raises(package.PackageError):
        package.build_package("ep02", meta, video, out)
    assert not (out / "ep02").exists(), "出包失败了就不该留下半个包"


def test_a_warning_is_written_into_the_checklist(meta, video, tmp_path, monkeypatch):
    """warning 级别的要告警但继续，而且要让人在清单里看得见。"""
    from pyv import epmeta

    def fake_check_meta(*args, **kwargs):
        return [epmeta.Finding("epmeta.cover-at", epmeta.WARNING, "封面帧取在片尾", "ep02")]

    monkeypatch.setattr(package.epmeta, "check_meta", fake_check_meta)
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    checklist = result.files["publish.md"].read_text(encoding="utf-8")
    assert "封面帧取在片尾" in checklist
    assert result.warnings, "告警不能吞掉"


def test_a_clean_package_has_no_warnings(meta, video, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    assert result.warnings == []


@pytest.mark.parametrize(
    "section",
    [
        {
            "title": "标" * 80,
            "description": "短",
            "tags": ["a"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },  # 标题 > 79 字
        {
            "title": "短",
            "description": "字" * 250,
            "tags": ["a"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },  # 简介 > 249 字
        {
            "title": "短",
            "description": "短",
            "tags": ["字" * 200],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },  # 标签总长 > 199
        {
            "title": "短",
            "description": "短",
            "tags": ["字" * 21],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },  # 单个标签 > 20 字
        {
            "title": "短",
            "description": "短",
            "tags": ["a"],
            "tid": 231,
            "copyright": 3,
            "no_reprint": 1,
        },  # copyright 越界
        {
            "title": "短",
            "description": "短",
            "tags": ["a"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 5,
        },  # no_reprint 越界
        {
            "title": "短",
            "description": "短",
            "tags": ["a"],
            "tid": 231,
            "copyright": 2,
            "no_reprint": 1,
        },  # 转载缺 source
    ],
)
def test_the_limits_are_errors_not_truncations(meta, video, tmp_path, section):
    """超限要报错，不能悄悄裁一刀（规格 §6.3）。"""
    from pyv import epmeta

    broken = epmeta.EpisodeMeta(
        episode="ep02",
        title=meta.title,
        cover_at=meta.cover_at,
        url=meta.url,
        bilibili=section,
    )
    out = tmp_path / "out"
    with pytest.raises(package.PackageError):
        package.build_package("ep02", broken, video, out)
    assert not (out / "ep02").exists()


def test_the_channels_section_is_not_the_bilibili_adapters_business(meta, video, tmp_path):
    """B站的 adapter 不该被视频号那段文案绊住。"""
    from pyv import epmeta

    only_bilibili = epmeta.EpisodeMeta(
        episode="ep02",
        title=meta.title,
        cover_at=meta.cover_at,
        url=meta.url,
        channels=None,
        bilibili=meta.bilibili,
    )
    result = package.build_package("ep02", only_bilibili, video, tmp_path / "out")
    assert result.warnings == []


# --- 回填 --------------------------------------------------------------------


def test_marking_published_updates_the_package_meta(meta, video, tmp_path):
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    package.mark_published(result.dir, "https://www.bilibili.com/video/BV1xx")
    data = json.loads((result.dir / "meta.json").read_text(encoding="utf-8"))
    assert data["status"] == "published"
    assert data["published_url"] == "https://www.bilibili.com/video/BV1xx"


# --- 命令行端到端 ------------------------------------------------------------
#
# 本机素材（成片、storyboard）按 **adapter 自己找它们的路径**摆：
# 写死一份路径的话，adapter 换了路径约定，测试还在原地测一个
# 它早就不去的地方。


def _stage_video(cli, monkeypatch, tmp_path, make_video) -> Path:
    """把成片摆到 adapter 默认找它的位置。"""
    monkeypatch.setattr(cli, "AIV_ROOT", tmp_path / "video")
    video = cli._video_path(EP_PATH)
    video.parent.mkdir(parents=True, exist_ok=True)
    make_video(video)
    return video


def _stage_storyboard(cli, tmp_path) -> Path:
    """把 storyboard 摆到 adapter 默认找它的位置。

    里面有一条字幕——storyboard 在，字幕就得在。
    """
    storyboard = cli._storyboard_path(EP_PATH)
    storyboard.parent.mkdir(parents=True, exist_ok=True)
    storyboard.write_text(
        json.dumps(
            {
                "subtitles": [{"start": 0.0, "end": 1.5, "text": "命令行也出字幕"}],
                "scenes": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return storyboard


def test_the_cli_packages_and_marks_an_episode(episode_dir, tmp_path, monkeypatch,
                                               make_video):
    """期号 → 元数据 → 发布包 → 回填链接，一条线走完。

    期在临时目录里现造（四层坐标的期目录 + `publish.json`），
    成片与 storyboard 也是现场摆的——仓库里既没有内容，也没有成片。
    """
    from bilibili import cli

    _stage_video(cli, monkeypatch, tmp_path, make_video)
    _stage_storyboard(cli, tmp_path)

    out = tmp_path / "out"
    assert cli.main(["package", EP_PATH, "--out", str(out)]) == 0
    checklist = (out / EP_PATH / "publish.md").read_text(encoding="utf-8")
    assert "待你上传" in checklist
    assert "已发布" not in checklist
    # storyboard 在，字幕就得在
    assert "命令行也出字幕" in (out / EP_PATH / "subtitle.srt").read_text(encoding="utf-8")

    url = "https://www.bilibili.com/video/BV1xx"
    assert cli.main(["mark", "published", EP_PATH, "--url", url, "--out", str(out)]) == 0
    assert cli.main(["status", EP_PATH, "--out", str(out)]) == 0

    state_data = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert state_data["episodes"][EP_PATH]["status"] == "published"
    assert state_data["episodes"][EP_PATH]["published_url"] == url

    shot = json.loads((tmp_path / "outbox" / f"{EP_PATH}__bilibili.json")
                      .read_text(encoding="utf-8"))
    assert shot["status"] == "published"
    assert shot["published_url"] == url
    # 回填出来的快照同样要相对路径——快照要入库
    assert not Path(shot["package_dir"]).is_absolute(), f"package_dir 是绝对路径：{shot['package_dir']}"


def test_the_cli_fails_loudly_when_the_video_is_missing(episode_dir, tmp_path,
                                                       monkeypatch, capsys):
    """成片不在就报错退出，不能出一个没有视频的包。

    元数据是有的（期在临时目录里现造）——不然这条命令撞在「读元数据」
    那步就退出了，「成片不存在」这条分支根本没被走到。
    """
    from bilibili import cli

    monkeypatch.setattr(cli, "AIV_ROOT", tmp_path / "video")

    assert cli.main(["package", EP_PATH, "--out", str(tmp_path / "out")]) == 1
    assert "成片不存在" in capsys.readouterr().err


# --- 通知 --------------------------------------------------------------------


def test_the_phrases_distinguish_the_states():
    from bilibili import notify

    assert "待你上传" in notify.phrase("packaged")
    assert "审核中" in notify.phrase("submitted")
    assert notify.phrase("published") == "已发布"


def test_the_drafted_phrase_does_not_say_published():
    """「已存草稿」和「已发布」是两件完全不同的事。

    **含糊地说「已发布」是发布场景里最贵的一种 bug**——
    用户以为视频发出去了，实际它还躺在草稿箱里，谁都看不见。
    """
    from bilibili import notify

    phrase = notify.phrase("drafted")
    assert "草稿" in phrase
    assert "已发布" not in phrase
    assert phrase != notify.phrase("published")


def test_marking_drafted_keeps_it_unpublished(episode_dir, tmp_path, monkeypatch,
                                             make_video):
    """标成 drafted：状态与快照都更新，但**没有公开链接**。"""
    from bilibili import cli

    _stage_video(cli, monkeypatch, tmp_path, make_video)

    out = tmp_path / "out"
    assert cli.main(["package", EP_PATH, "--out", str(out)]) == 0
    assert cli.main(["mark", "drafted", EP_PATH, "--out", str(out)]) == 0

    state_data = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert state_data["episodes"][EP_PATH]["status"] == "drafted"
    assert state_data["episodes"][EP_PATH]["published_url"] is None

    shot = json.loads((tmp_path / "outbox" / f"{EP_PATH}__bilibili.json")
                      .read_text(encoding="utf-8"))
    assert shot["status"] == "drafted"
    assert shot["published_url"] is None


def test_marking_published_without_a_url_is_refused(episode_dir, tmp_path,
                                                     monkeypatch, capsys,
                                                     make_video):
    """没有公开链接就不许说「已发布」。

    **「存了草稿」被人当成「发出去了」是最贵的错**，
    所以这条命令必须拒绝没有 --url 的 published。
    """
    from bilibili import cli

    _stage_video(cli, monkeypatch, tmp_path, make_video)

    out = tmp_path / "out"
    assert cli.main(["package", EP_PATH, "--out", str(out)]) == 0
    assert cli.main(["mark", "published", EP_PATH, "--out", str(out)]) == 2
    assert "--url" in capsys.readouterr().err


# --- 磁盘上的那一期 ---------------------------------------------------------


def test_the_episode_on_disk_carries_the_episode_path_as_its_identity(
        on_disk_meta):
    """期身份 = 期目录相对期根的路径。

    `publish.json` 里的 `episode` 字段填的就是它——出包时 adapter 要拿
    命令行上的那个期号跟它对上（`pyv.epmeta.check_meta` 的 `epmeta.episode`
    那道闸）。填错了就是两期认成一期。
    """
    assert on_disk_meta.episode == EP_PATH
    assert on_disk_meta.bilibili["tid"] == 231
    assert on_disk_meta.bilibili["copyright"] == 1


# --- 转载那一档：copyright = 2 必须给 source ---------------------------------


def test_a_reprint_episode_packages_with_its_source(episodes_root, tmp_path,
                                                    monkeypatch, make_video):
    """转载那一档（`copyright = 2`）给出 `source` 就能出包。

    `source` 是转载的来源地址——平台会拒没有来源的转载（规格 §4.3）。
    清单里也要说清这是转载：人照着清单填投稿表单。
    """
    from bilibili import cli

    write_episode(episodes_root, EP_PATH, reprint_payload(EP_PATH))
    _stage_video(cli, monkeypatch, tmp_path, make_video)

    out = tmp_path / "out"
    assert cli.main(["package", EP_PATH, "--out", str(out)]) == 0
    checklist = (out / EP_PATH / "publish.md").read_text(encoding="utf-8")
    # 清单里「原创」那一行的**取值**是转载（行标题就叫「原创」，
    # 说的是这个字段本身）。
    assert "| 原创 | 转载 |" in checklist


def test_a_reprint_without_a_source_is_refused(episodes_root, tmp_path,
                                               monkeypatch, make_video, capsys):
    """转载缺 `source` 就不许出包。

    这条规矩由契约层判（`pyv.epmeta` 的 `required_when`），adapter 只负责
    把 finding 变成一次干净的失败——**不能悄悄出一个发不出去的包**。
    """
    from bilibili import cli

    payload = publish_payload(EP_PATH)
    payload["bilibili"]["copyright"] = 2      # 转载，但不给 source
    write_episode(episodes_root, EP_PATH, payload)
    _stage_video(cli, monkeypatch, tmp_path, make_video)

    out = tmp_path / "out"
    assert cli.main(["package", EP_PATH, "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "source" in err
    assert not (out / EP_PATH).exists(), "预检没过还留下了半个包"


def test_a_failing_webhook_does_not_break_the_run(capsys):
    """通知推送失败只告警，不崩——发布本身不能被一条通知带崩。"""
    from bilibili import notify

    text = notify.notify("ep02", "packaged", "标题", "platforms/bilibili/out/ep02", webhook="not-a-url")
    assert "待你上传" in text
    assert "WARNING" in capsys.readouterr().out


def test_a_missing_file_in_the_package_forces_a_rebuild(meta, video, tmp_path):
    """**复用不是「目录还在就算数」。**

    上一版的复用分支只看「成片没变」和「meta.json 在」，包里少了东西
    （软链悬空、封面被人删）照样报「复用成功」——而那个包根本发不出去。
    """
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    (result.dir / "cover.jpg").unlink()

    again = package.build_package("ep02", meta, video, tmp_path / "out")
    assert not again.reused, "包里缺了封面还报复用"
    assert (again.dir / "cover.jpg").is_file()


def test_a_dangling_video_symlink_forces_a_rebuild(meta, video, tmp_path):
    """软链悬空也要重出——成片被挪走或删了，那个包发不出去。"""
    result = package.build_package("ep02", meta, video, tmp_path / "out")
    (result.dir / "video.mp4").unlink()

    again = package.build_package("ep02", meta, video, tmp_path / "out")
    assert not again.reused
    assert (again.dir / "video.mp4").is_symlink()
    assert (again.dir / "video.mp4").exists()


def test_the_cover_is_re_extracted_when_the_frame_moves(meta, video, tmp_path):
    """封面与 `meta.json` 记的取帧点必须对得上。

    上一版复用时不重抽封面：元数据里的 `cover_at` 从 1.0 改成 2.0，
    清单与 `meta.json` 都写着 2.0，包里那张封面却还是 1.0 秒那一帧——
    人按清单选封面，选到的是另一帧。
    """
    import dataclasses

    first = package.build_package("ep02", meta, video, tmp_path / "out")
    cover_before = (first.dir / "cover.jpg").read_bytes()

    moved = dataclasses.replace(meta, cover_at=2.0)
    again = package.build_package("ep02", moved, video, tmp_path / "out")
    cover_after = (again.dir / "cover.jpg").read_bytes()

    assert cover_after != cover_before, "换了取帧点，封面还是原来那张"
    data = json.loads((again.dir / "meta.json").read_text(encoding="utf-8"))
    assert data["cover_at"] == 2.0
