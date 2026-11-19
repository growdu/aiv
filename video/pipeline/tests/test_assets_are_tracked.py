"""素材的**归属**规矩：规则级的入库，用户自带的不入库。

原来这条规矩是反的：立绘、曲库、品牌片这些**用户自带的**素材被要求
入库。放在一个人自用的仓库里没问题——换个平台就不成立了：

- 立绘的版权是**用这套流水线的人**的，仓库要发布给所有人；
- 曲库的授权是**一首一首**的，跟着别人入库等于替别人担保；
- 品牌片是**这一家**的东西，别人拿去用是别人的事。

所以规矩改成两条：

1. **规则级素材入库**——内置字体子集。两台机器用同一份字体文件，
   跨机的版式（步进宽度、收字号结果）才一致。这是**框架**的一部分。
2. **用户素材不入库**——立绘、曲库、品牌片、品牌音轨、落版头像。
   它们的位置写在 `video/config.toml` 里；**没配不是错**，
   **配了但文件不在才是错**（doctor 报这个）。

另有两条老规矩照旧：产物目录里不许有被跟踪的文件；
入库的媒体文件只有规则级那些。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AIV_ROOT = REPO_ROOT / "video"

#: 规则级素材：相对仓库根的路径 → 为什么它跟着框架走
#:
#: **内置字体子集**：两台机器用同一份文件，跨机的版式（步进宽度、
#: 收字号结果）才一致。没装就退到系统字体，画面照样能出，
#: 但跨机就不保证一致了。
#:
#: **粗体也要入库**：只装常规字重的话，cairo 会用各后端自己的办法
#: 合成粗体，两个平台合成出来的不一样（实测轮廓差 3.14px）——
#: 跨机版式就又对不上了。
RULE_ASSETS = {
    "video/pipeline/assets/fonts/AIVSansCJKSC-Regular.otf": "内置中文字体（渲染必需）",
    "video/pipeline/assets/fonts/AIVSansCJKSC-Bold.otf": "内置中文字体的粗体面（渲染必需）",
}

#: 用户素材的**目录**（相对仓库根）：这些目录里不许有被跟踪的媒体文件。
#:
#: 素材的**位置**由 `video/config.toml` 声明；这里盯的是「别不小心入库」。
#: 目录而不是具体文件——换素材的人自己决定文件名，规矩是文件不跟着仓库走。
USER_ASSET_DIRS = {
    "video/character": "立绘（形象素材：版权与口味是用这套流水线的人自己的）",
    "video/music/tracks": "曲库（曲子的授权是一首一首的）",
    "video/brand/clips": "品牌片（这一家的东西）",
    "video/brand/audio": "品牌成品音轨（这一家的东西）",
}

#: 用户素材里**唯一**该入库的东西：它记的是**事实**，不是素材本身。
#:
#: 曲库台账记「每首曲子从哪来、什么授权」——这份事实要跟着仓库走，
#: 不然别人不知道能放哪首曲子。
FACT_FILES = {
    "video/music/library.json": "曲库授权台账（记的是授权事实）",
    "video/brand/brand_windows.json": "品牌片头尾的配乐窗口（记的是挑窗决策）",
}

#: 产物目录：里面不许有被跟踪的文件
PRODUCT_DIRS = ("video/out", "video/build", "video/frames")

#: 期目录里的产物：**抽出来的帧**与**时间轴**都是产物，不入库。
#: 入库的是期目录里的事实（口播稿、契约、发布元数据、审校记录、抽帧清单），
#: 产物只留本机——仓库不该背着成片的中间件长大。
#:
#: 期路径是四层（系列/合集/文档/档位），所以 glob 也是四层。
EPISODE_PRODUCT_PATTERNS = (
    "video/episodes/*/*/*/*/frames/*",
    "video/episodes/*/*/*/*/storyboard*.json",
)

#: 媒体文件的后缀——「入库的媒体只有规则级那些」这条判据用它。
MEDIA_SUFFIXES = (".mp3", ".mp4", ".wav", ".png", ".jpg", ".jpeg")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


@pytest.fixture(scope="module", autouse=True)
def _require_git_repo():
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("不在 git 仓库里，跳过")


@pytest.mark.parametrize("relative", sorted(RULE_ASSETS))
def test_rule_asset_is_tracked(relative):
    """规则级素材必须在版本控制里，否则别的机器上会凭空消失。"""
    assert (REPO_ROOT / relative).is_file(), f"{relative} 本机就没有"
    result = _git("ls-files", "--error-unmatch", relative)
    assert result.returncode == 0, (
        f"{relative} 没被 git 跟踪（{RULE_ASSETS[relative]}）——"
        f"别的机器 clone 完会缺这一件"
    )


@pytest.mark.parametrize("relative", sorted(RULE_ASSETS))
def test_rule_asset_is_not_ignored(relative):
    """`.gitignore` 的放行清单必须真的放行了它。"""
    result = _git("check-ignore", "-q", relative)
    assert result.returncode != 0, f"{relative} 被 .gitignore 拦着"


@pytest.mark.parametrize("directory", sorted(USER_ASSET_DIRS))
def test_user_assets_are_not_tracked(directory):
    """用户自带的素材**不入库**——版权是他们的，仓库要发给所有人。

    台账类的事实文件不算素材，单独放行（见 `FACT_FILES`）。
    """
    result = _git("ls-files", directory)
    tracked = [
        line for line in result.stdout.splitlines()
        if line.strip() and line not in FACT_FILES
        and not line.endswith((".py", ".sh", ".md", ".json", ".gitkeep"))
    ]
    assert tracked == [], (
        f"{directory} 里有被跟踪的用户素材：{tracked}"
        f"（{USER_ASSET_DIRS[directory]}）——把它从仓库里拿掉，"
        f"位置写进 video/config.toml"
    )


@pytest.mark.parametrize("relative", sorted(FACT_FILES))
def test_fact_file_is_tracked(relative):
    """台账与决策是**事实**，要跟着仓库走。"""
    assert (REPO_ROOT / relative).is_file(), f"{relative} 本机就没有"
    result = _git("ls-files", "--error-unmatch", relative)
    assert result.returncode == 0, (
        f"{relative} 没被 git 跟踪（{FACT_FILES[relative]}）"
    )


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


def test_no_tracked_media_outside_the_rule_assets():
    """入库的媒体文件只有规则级那些（字体）。

    **字体是框架的一部分**（跨机版式一致）；立绘、曲子、品牌片是
    用户自带的，一律不入库。
    """
    result = _git("ls-files", "video")
    unexpected = [
        path for path in result.stdout.splitlines()
        if path.endswith(MEDIA_SUFFIXES) and path not in RULE_ASSETS
    ]
    assert unexpected == [], f"有媒体文件没走白名单就入库了：{unexpected}"
