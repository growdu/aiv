"""出片必需的素材必须**在仓库里**。

一条规矩：**入库的是事实，不入库的是产物**。

但「出片必需的输入」是另一回事——旁白、曲库、形象素材、品牌片不是为了
「留个档」，而是**没有它们就出不了片**。它们必须跟着仓库走，
另一台机器（尤其是 Linux）clone 完就能直接 `make` 出片。

这条守卫盯两件事：

1. 白名单里的素材**确实被 git 跟踪**——`.gitignore` 改错一个字、
   或者有人 `git rm --cached` 了一下，素材就会在别人的机器上凭空消失；
2. 产物目录（`out/`、`build/`）里**没有**被跟踪的文件——产物一旦入库，
   仓库就会开始长，而且每个 commit 都要背着它。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AIV_ROOT = REPO_ROOT / "video"

#: 出片必需的素材：相对仓库根的路径 → 为什么需要它
#:
#: **旁白不入库**：旁白是**一期的产物**（`video/episodes/<slug>/narration.mp3`），
#: 跟着那一期走，不是规则级的素材。规则级的素材只有下面这些——
#: 音色定标参照稿、形象、品牌片、曲库、内置字体。
REQUIRED_ASSETS = {
    "video/ddl-voiceover.mp3": "音色定标的参照稿",
    "video/growdu2.jpeg": "形象原型（重新生成立绘的唯一来源）",
    "video/character/growdu_character_2k_nobg.png": "小象立绘（渲染必需）",
    "video/brand/clips/growdu_intro_3s_1080p.mp4": "品牌片头",
    "video/brand/clips/growdu_outro_3s_1080p.mp4": "品牌片尾",
    "video/brand/audio/intro_mix.wav": "片头成品音轨",
    "video/brand/audio/outro_mix.wav": "片尾成品音轨",
    "video/music/tracks/series-bed-01.wav": "正文铺底 BGM",
    "video/music/tracks/series-motif-01.wav": "片头片尾闭环的 motif",
    # 内置字体子集：两台机器用同一份文件，跨机的版式（步进宽度、
    # 收字号结果）才一致。没装就退到系统字体，画面照样能出，
    # 但跨机就不保证一致了。
    "video/pipeline/assets/fonts/AIVSansCJKSC-Regular.otf": "内置中文字体（渲染必需）",
    # **粗体也要入库**：只装常规字重的话，cairo 会用各后端自己的办法
    # 合成粗体，两个平台合成出来的不一样（实测轮廓差 3.14px）——
    # 跨机版式就又对不上了。
    "video/pipeline/assets/fonts/AIVSansCJKSC-Bold.otf": "内置中文字体的粗体面（渲染必需）",
}

#: 备用素材：入库了，但**不是**默认出片必需的（缺了照样能出片）。
#:
#: 抖音这一档备用：胸口那枚 `growdu` 铭牌也是品牌标识，被判「过度营销」
#: 时要换成无标牌那份（`make EP=… nobrand NOBADGE=1`）。入库是因为
#: 换素材这件事在另一台机器上也得能立刻做，不能临时还得先跑脚本。
OPTIONAL_ASSETS = {
    "video/character/growdu_character_2k_nobg_nobadge.png":
        "无标牌形象（抖音这一档备用：铭牌也是品牌标识）",
}

#: 产物目录：里面不许有被跟踪的文件
PRODUCT_DIRS = ("video/out", "video/build", "video/frames")

#: 期目录里的产物：**抽出来的帧**与**时间轴**都是产物，不入库。
#: 入库的是期目录里的事实（口播稿、契约、发布元数据、审校记录、抽帧清单），
#: 产物只留本机——仓库不该背着成片的中间件长大。
EPISODE_PRODUCT_PATTERNS = (
    "video/episodes/*/frames/*",
    "video/episodes/*/storyboard*.json",
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


@pytest.fixture(scope="module", autouse=True)
def _require_git_repo():
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("不在 git 仓库里，跳过")


@pytest.mark.parametrize("relative", sorted(REQUIRED_ASSETS))
def test_required_asset_is_tracked(relative):
    """必需素材必须在版本控制里，否则别的机器上会凭空消失。"""
    assert (REPO_ROOT / relative).is_file(), f"{relative} 本机就没有"
    result = _git("ls-files", "--error-unmatch", relative)
    assert result.returncode == 0, (
        f"{relative} 没被 git 跟踪（{REQUIRED_ASSETS[relative]}）——"
        f"别的机器 clone 完会缺这一件"
    )


@pytest.mark.parametrize("relative", sorted(REQUIRED_ASSETS))
def test_required_asset_is_not_ignored(relative):
    """`.gitignore` 的放行清单必须真的放行了它。"""
    result = _git("check-ignore", "-q", relative)
    assert result.returncode != 0, f"{relative} 被 .gitignore 拦着"


@pytest.mark.parametrize("relative", sorted(OPTIONAL_ASSETS))
def test_optional_asset_is_tracked(relative):
    """备用素材也要在版本控制里。

    它不是默认出片必需的，但「被平台判了要换素材」这种场景
    往往发生在一台刚 clone 完的机器上——素材不在，就得先跑脚本才能换。
    """
    assert (REPO_ROOT / relative).is_file(), f"{relative} 本机就没有"
    result = _git("ls-files", "--error-unmatch", relative)
    assert result.returncode == 0, (
        f"{relative} 没被 git 跟踪（{OPTIONAL_ASSETS[relative]}）"
    )
    assert _git("check-ignore", "-q", relative).returncode != 0, \
        f"{relative} 被 .gitignore 拦着"


@pytest.mark.parametrize("directory", PRODUCT_DIRS)
def test_product_directory_has_no_tracked_files(directory):
    """产物目录里不许有被跟踪的文件——成片一入库，仓库就开始长。"""
    result = _git("ls-files", directory)
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert tracked == [], f"{directory} 里有被跟踪的文件：{tracked}"


@pytest.mark.parametrize("pattern", EPISODE_PRODUCT_PATTERNS)
def test_episode_products_are_not_tracked(pattern):
    """期目录里的帧与时间轴是产物——入库了仓库就会开始长。"""
    result = _git("ls-files", pattern)
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert tracked == [], f"{pattern} 里有被跟踪的文件：{tracked}"


def test_no_tracked_media_outside_the_allowlist():
    """入库的媒体文件只有白名单里那些。"""
    result = _git("ls-files", "video")
    media_suffixes = (".mp3", ".mp4", ".wav", ".png", ".jpg", ".jpeg", ".otf")
    allowed = set(REQUIRED_ASSETS) | set(OPTIONAL_ASSETS)
    unexpected = [
        path for path in result.stdout.splitlines()
        if path.endswith(media_suffixes) and path not in allowed
    ]
    assert unexpected == [], f"有媒体文件没走白名单就入库了：{unexpected}"
