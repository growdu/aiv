"""出包：把一期变成一个「照着做就能发完」的目录。

产物结构见规格 §6.3。幂等靠成片的 sha256。

**出包前有两道闸。** 文案层（`pyv.epmeta.check_meta`）与技术层
（`pyv.preflight.check_video`）各出一份 finding：

- `error` 级别 → **报错并停止**。不静默出包——发不出去的包出了也是白出，
  问题会被推到人工点发布那一步才爆出来。
- `warning` 级别 → **告警但继续**，并且写进 `publish.md` 清单，
  让出包的人看得见。

判定只有 `pyv` 那一份，adapter 不自己判：两个地方各判一次会出现两个结论，
门槛数字也会漂（规格 §5.2）。

**幂等的三件事**（规格 §7.1）：抽帧与软链绑成片 sha256（复用），
文案绑当前元数据（每次重写），发布状态绑成片 sha256（保留）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from pyv import epmeta, episodes, preflight

from bilibili import assets, contract, snapshot, state, subtitle

# 仓库根：platforms/bilibili/package.py → platforms/bilibili → platforms → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]

# 清单里随状态改写的两处：抬头与状态说明。
#
# **状态一变，这两处就得跟着变。** 人只看 `publish.md`——
# 它写着「待你上传」而 `meta.json` 写着「已存草稿」，人就会**再传一遍**，
# 在平台上多出一条重复的作品。含糊地说状态是发布场景里最贵的一种 bug。
_STATUS_NOTE_START = "<!-- status-note:start -->"
_STATUS_NOTE_END = "<!-- status-note:end -->"

# 状态 → 清单抬头的说法
_STATUS_LABELS = {
    "packaged": "待发布",
    "drafted": "已存草稿，待发表",
    "submitted": "已投稿，待审核",
    "published": "已发布",
    "failed": "投稿失败",
}

# 包里必须有的东西。**清单、封面、软链一样都不能少**——少了就是
# 一个发不出去的包，而命令会报「成功」。
#
# **B站这一份是自己的清单**（含 `meta.json`）：各平台缺的东西不一样，
# 不许互相统一——统一了就等于替别的平台决定它发得出去。
REQUIRED_FILES: tuple[str, ...] = (
    "video.mp4",
    "cover.jpg",
    "title.txt",
    "description.txt",
    "tags.txt",
    "publish.md",
    "meta.json",
)


def missing_files(target: str | Path) -> list[str]:
    """这个包里少了哪些必须有的文件（按文件名排序）。

    **「包完整才算数」这条规则只有一个入口。** 复用、标草稿、标发布
    都问它——三处各写一遍判断，改一处就忘了另一处，
    于是「复用查了完整性、标发布没查」这类漏网出现。
    """
    directory = Path(target)
    return sorted(name for name in REQUIRED_FILES
                  if not (directory / name).exists())


def _status_heading(status: str, title: str, episode: str) -> str:
    label = _STATUS_LABELS.get(status, "待发布")
    return f"# {label}：{title}（{episode}）"


def _status_note(status: str) -> list[str]:
    """清单末尾的状态说明。措辞跟 `notify` 那一套对齐。"""
    if status == "drafted":
        return [
            "> **已存草稿，未投稿（视频还没公开）。** 草稿已经在平台上了——"
            "**这不是「待上传」**，再传一遍会多出一条重复的作品。",
        ]
    if status == "submitted":
        return [
            "> **已投稿，审核中。** 等平台过审就行；过审后回填链接。",
        ]
    if status == "published":
        return [
            "> **已发布。** 这一条已经发出去了。",
        ]
    if status == "failed":
        return [
            "> **投稿失败。** 这条没投出去——修好问题后重投，别当成已发布。",
        ]
    return [
        "> **待你上传。** 这一步没做完之前，状态只能写「待上传」。",
    ]


def rewrite_status_block(path: Path, status: str) -> None:
    """把清单里随状态改写的两处改成当前状态。

    `mark published` / `mark drafted` 改了 `meta.json`，清单也得跟着改——
    否则包里的 `publish.md` 与 `meta.json` 说的不是一回事。
    """
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# ") and "：" in line:
            # 只换抬头上的状态词，标题与期号原样留着。
            lines[index] = f"# {_STATUS_LABELS.get(status, '待发布')}：" + \
                line.split("：", 1)[1]
            break
    if _STATUS_NOTE_START in lines and _STATUS_NOTE_END in lines:
        start = lines.index(_STATUS_NOTE_START)
        end = lines.index(_STATUS_NOTE_END)
        lines[start + 1:end] = _status_note(status)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def repo_relative(path: str | Path, root: str | Path | None = None) -> str:
    """把路径写成相对仓库根的形式（**分隔符一律用 `/`**）。

    快照要入库。绝对路径换台机器就对不上，还把本机信息带进了库。

    两条规矩：

    1. **分隔符用正斜杠。** 快照是入库的文本，同一个仓库在 Windows 与
       Linux 上跑出来的内容必须一模一样——反斜杠会让每台机器各写一份，
       提交上去就成了「谁最后跑谁说了算」。
    2. **永远不是绝对路径。** 目标不在仓库里（甚至在另一个盘）时，
       `os.path.relpath` 拿不到相对路径；那就退回到目标所在盘根的相对形式，
       仍然不带盘符与绝对路径。
    """
    base = Path(root) if root else REPO_ROOT
    target = Path(path).resolve()
    try:
        relative = os.path.relpath(target, base.resolve())
    except ValueError:
        # Windows 跨盘符：两边没有共同祖先，relpath 直接抛。
        # 退回到目标所在盘的盘根——仍是相对路径，也不带本机盘符。
        relative = os.path.relpath(target, target.anchor)
    return Path(relative).as_posix()


class PackageError(RuntimeError):
    """出不了包：有硬约束违规（预检里 error 级别的 finding）。"""

    def __init__(self, findings):
        self.findings = list(findings)
        detail = "；".join(str(f) for f in self.findings)
        super().__init__(f"预检未通过（{len(self.findings)} 条）：{detail}")


@dataclass
class PackageResult:
    """一次出包的结果。"""

    episode: str
    dir: Path
    files: dict[str, Path] = field(default_factory=dict)
    video_sha256: str = ""
    status: str = "packaged"
    reason: str = ""
    reused: bool = False
    warnings: list[str] = field(default_factory=list)


def _checklist(
    episode: str,
    copy: contract.BiliCopy,
    info: preflight.VideoInfo,
    warnings: list[str],
    status: str = "packaged",
) -> str:
    tags = contract.tags_line(copy.tags)
    lines = [
        _status_heading(status, copy.title, episode),
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        f"| 视频 | `video.mp4`（{info.duration:.1f} s，{info.width}×{info.height}） |",
        f"| 标题 | {copy.title}（{len(copy.title)} 字） |",
        f"| 分区 | tid = {copy.tid} |",
        f"| 标签 | {tags} |",
        f"| 简介 | {copy.description[:40]}… |"
        if len(copy.description) > 40
        else f"| 简介 | {copy.description} |",
        "| 封面 | `cover.jpg` |",
        "| 字幕 | `subtitle.srt`（有的话一起传） |",
        f"| 原创 | {'原创' if copy.copyright == 1 else '转载'} |",
        f"| 允许转载 | {'否' if copy.no_reprint == 1 else '是'} |",
        "",
        "## 步骤",
        "",
        "- [ ] 打开B站创作中心 → 投稿",
        "- [ ] 上传 `video.mp4`",
        "- [ ] 填标题、简介、标签，选对分区",
        "- [ ] 上传 `cover.jpg` 作封面",
        "- [ ] 有 `subtitle.srt` 的话传上字幕",
        "- [ ] 声明原创，确认不允许转载",
        "- [ ] 提交投稿",
        "- [ ] 回填链接："
        f'`python -m bilibili.cli mark published {episode} --url "<链接>"`',
        "",
    ]
    if warnings:
        lines += ["## 预检告警", ""]
        lines += [f"- ⚠️ {warning}" for warning in warnings]
        lines += [""]
    lines += [
        _STATUS_NOTE_START,
        *_status_note(status),
        _STATUS_NOTE_END,
        "",
    ]
    return "\n".join(lines)


def _bilibili_only(meta: epmeta.EpisodeMeta) -> epmeta.EpisodeMeta:
    """只留B站那一段。

    `check_meta` 会把所有平台都看一遍，但B站的 adapter 只对B站负责——
    「这一期没配视频号文案」不是B站的发布问题，不该进B站的清单。
    """
    section = meta.platforms.get("bilibili")
    return epmeta.EpisodeMeta(
        episode=meta.episode,
        title=meta.title,
        cover_at=meta.cover_at,
        url=meta.url,
        platforms={"bilibili": section} if section is not None else {},
        tier=meta.tier,
        path=meta.path,
    )


def _for_bilibili(findings: list) -> list:
    """只留B站自己的 finding。"""
    kept = []
    for finding in findings:
        if (
            finding.rule_id == "epmeta.platform-missing"
            and "bilibili" not in finding.message
        ):
            continue
        kept.append(finding)
    return kept


def preflight_findings(
    meta: epmeta.EpisodeMeta,
    info: preflight.VideoInfo,
    episode: str,
    platforms_dir: str | Path | None = None,
) -> list:
    """出包前的预检：文案层 + 技术层。

    返回的 finding 里 `error` 的必须先改，`warning` 的要写进清单。
    """
    findings = epmeta.check_meta(
        _bilibili_only(meta),
        contract_episode=episode,
        duration=info.duration,
        limits_loader=epmeta.scoped_loader(epmeta.load_limits, platforms_dir),
        tiers_loader=epmeta.scoped_loader(epmeta.load_tiers, platforms_dir),
    )
    findings = _for_bilibili(findings)
    findings.extend(
        preflight.check_video(
            info,
            "bilibili",
            Path(platforms_dir) if platforms_dir is not None else None,
        )
    )
    return findings


def build_package(
    episode: str,
    meta: epmeta.EpisodeMeta,
    video: str | Path,
    out_root: str | Path,
    subtitle_events: Sequence[subtitle.SubtitleEventLike] | None = None,
    platforms_dir: str | Path | None = None,
    outbox_dir: str | Path | None = None,
) -> PackageResult:
    """出一期在B站上的发布包。

    `subtitle_events` 给了就把字幕转成 `subtitle.srt` 一并放进包里。

    **参数是字幕事件，不是 storyboard 对象**：adapter 只能 import
    `pyv.epmeta`、`pyv.preflight` 与 `pyv.episodes`（坐标/路径助手，规格 §3.3），
    碰不到 `pyv.timeline`。
    读 storyboard 的活儿由调用方（CLI）用 `subtitle.events_from_storyboard()` 做。
    """
    copy = contract.slice_copy(meta)
    video_path = Path(video)
    if not video_path.is_file():
        raise FileNotFoundError(f"成片不存在：{video_path}")

    info = preflight.probe(video_path)
    findings = preflight_findings(meta, info, episode, platforms_dir)
    errors = [f for f in findings if f.level == epmeta.ERROR]
    if errors:
        # 有硬约束违规就不出包——宁可现在报错，也不要出一个发不出去的包。
        raise PackageError(errors)
    warnings = [str(f) for f in findings if f.level != epmeta.ERROR]

    out_root = Path(out_root)
    target = out_root / episode
    store = state.StateStore(out_root / "state.json")
    previous = store.get(episode)
    digest = preflight.file_sha256(video_path)

    # 包里该有的东西（清单见 `REQUIRED_FILES`）：少了就是
    # 一个发不出去的包，而命令会报「成功」。
    files = {name: target / name for name in REQUIRED_FILES}

    reused = False
    if previous.video_sha256 == digest and (target / "meta.json").is_file():
        # 成片没变：抽帧与软链复用，不重做费事的那部分。
        # **但要复查包里东西还在不在**：软链会悬空（成片被删了/换了），
        # 别的文件也会被人手删。少了任何一件就重出——复用不是
        # 「目录还在就算数」。
        if not missing_files(target):
            reused = True
    if not reused:
        target.mkdir(parents=True, exist_ok=True)
        assets.make_cover(video_path, copy.cover_at, target / "cover.jpg")
        link = target / "video.mp4"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(video_path.resolve())
    else:
        # 封面重抽一次：包里那张是上一次抽的，而元数据里的取帧点可能改了。
        # 封面与 `meta.json` 记的 `cover_at` 对不上，人按清单选封面就会
        # 选错那一帧（清单说 1.0 秒，包里那张是 3 秒的）。
        assets.make_cover(video_path, copy.cover_at, target / "cover.jpg")

    # **文案每次都按当前元数据重写。**
    # 成片没变 ≠ 文案没变：改了标题再重跑，必须出新标题。
    # 否则包里的文案停在旧版本，而命令还报「成功」——那是静默成功。
    (target / "title.txt").write_text(copy.title, encoding="utf-8")
    (target / "description.txt").write_text(copy.description, encoding="utf-8")
    (target / "tags.txt").write_text(contract.tags_line(copy.tags), encoding="utf-8")

    # 人工回填的发布状态不能被出包抹掉。
    # 成片没变 → 之前发出去的就是这一条，状态保留；
    # 成片变了 → 发出去的是另一条片子，状态回到「待上传」。
    if reused:
        status = previous.status
        published_url = previous.published_url
    else:
        status = "packaged"
        published_url = None

    # 清单要按**当前状态**写：复用包的状态可能是「已存草稿」，
    # 清单还写「待你上传」，人会再传一遍。
    (target / "publish.md").write_text(
        _checklist(episode, copy, info, warnings, status=status),
        encoding="utf-8",
    )

    # 字幕跟着 storyboard 走：**有就每次重写**。
    # 字幕是本地产物，但清单里说「有的话一起传」——
    # 清单说有、包里没有，人传了个空字幕上去。
    # 反过来也一样：storyboard 没了却还留着旧字幕，人会传一个对不上的版本。
    if subtitle_events:
        srt_path = target / "subtitle.srt"
        srt_path.write_text(subtitle.build_srt(subtitle_events), encoding="utf-8")
        files["subtitle.srt"] = srt_path
    else:
        (target / "subtitle.srt").unlink(missing_ok=True)
        files.pop("subtitle.srt", None)

    (target / "meta.json").write_text(
        json.dumps(
            {
                "episode": episode,
                "video_sha256": digest,
                "files": sorted(files),
                "cover_at": copy.cover_at,
                # 人工发布这一步没做完，状态就只能是「待上传」。
                "status": status,
                "published_url": published_url,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    store.save(
        episode,
        state.BiliState(
            episode=episode,
            video_sha256=digest,
            status=status,
            resource_id=previous.resource_id,
            published_url=published_url,
        ),
    )

    reason = (
        "B站 ARC_BASE 权限未开通，已出包待人工上传"
        if status == "packaged"
        else "人工发布后回填"
    )
    outbox = Path(outbox_dir) if outbox_dir else snapshot.OUTBOX_DIR
    snapshot.write_snapshot(
        outbox / f"{episodes.ep_id(episode)}__bilibili.json",
        episode=episode,
        status=status,
        title=copy.title,
        package_dir=repo_relative(target),
        published_url=published_url,
        reason=reason,
        # 档位从**同一份**能力声明里读——写死的话，改完 TOML 快照还在说旧档位。
        automation=snapshot.automation_of(platforms_dir),
    )
    return PackageResult(
        episode=episode,
        dir=target,
        files=files,
        video_sha256=digest,
        status=status,
        reason=reason,
        reused=reused,
        warnings=warnings,
    )


def mark_published(target: str | Path, url: str) -> Path:
    """回填发布链接：包里的机器可读快照也跟着更新。"""
    directory = Path(target)
    path = directory / "meta.json"
    if not path.is_file():
        raise FileNotFoundError(f"发布包不存在：{directory}")
    missing = missing_files(directory)
    if missing:
        raise FileNotFoundError(f"发布包不完整，缺：{'、'.join(missing)}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "published"
    data["published_url"] = url
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rewrite_status_block(directory / "publish.md", "published")
    return path


def mark_drafted(target: str | Path) -> Path:
    """回填「已存草稿」：视频已存进B站的草稿箱，还没公开。

    **和 `published` 是两回事。** 草稿还没发出去，所以 `published_url` 要清掉——
    留着旧链接会让人以为这条已经发出去了。
    """
    directory = Path(target)
    path = directory / "meta.json"
    if not path.is_file():
        raise FileNotFoundError(f"发布包不存在：{directory}")
    missing = missing_files(directory)
    if missing:
        raise FileNotFoundError(f"发布包不完整，缺：{'、'.join(missing)}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "drafted"
    data["published_url"] = None
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rewrite_status_block(directory / "publish.md", "drafted")
    return path
