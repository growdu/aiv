"""通用渲染器的**预览图**：人眼过一遍的那一套。

**为什么要有预览**：逐像素基准能说「变了」，说不出「变得好不好看」。
配色、留白、字号、行距是看出来的——所以得有一套能重复跑出来的预览。

**守卫守的是三件事**：

- **预览盖住全部段 × 两个画幅**——漏了一段，就以为看全了；
- **预览与逐像素基准盖的是同一批段**——看的东西和测的东西不是一回事，
  就白看了（一边看的是合成夹具，一边量的是真实内容）；
- **预览图不进版本库**——预览是产物，跟着本机的字体与素材走。

**预览走基准的那套画法**（`pyv.baseline.render_frame`）：底色、尺寸、画法
都一样，看的就是基准量的那张画布。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pyv import baseline
from pyv import contract as contract_mod

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASELINE = FIXTURES / "generic_baseline.json"
SCRIPT = PIPELINE_DIR / "scripts" / "preview_generic.py"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True)


def _expected_names(contract) -> set[str]:
    return {
        f"{w}x{h}_{segment.id}.png"
        for w, h in baseline.CANVASES
        for segment in contract.segments
    }


@pytest.fixture(scope="module")
def preview(tmp_path_factory) -> Path:
    """跑一遍预览脚本，把 PNG 落在临时目录里。"""
    out = tmp_path_factory.mktemp("preview")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        cwd=PIPELINE_DIR, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, (
        f"预览脚本跑挂了：\n{result.stdout}\n{result.stderr}"
    )
    return out


def test_the_preview_covers_every_segment_and_both_canvases(preview):
    """**预览要盖住全部段 × 两个画幅**——漏了一段，就以为看全了。"""
    contract = contract_mod.load_contract(baseline.GENERIC_CONTRACT)
    expected = _expected_names(contract)
    actual = {path.name for path in preview.glob("*.png")}
    assert actual == expected, (
        f"预览的图跟该有的对不上：少 {sorted(expected - actual)}，"
        f"多 {sorted(actual - expected)}"
    )


def test_the_preview_and_the_baseline_cover_the_same_segments(preview):
    """**预览与基准盖的是同一批段**。

    两边看的不是同一批，就白看了——过眼的那几张，基准一条都没盖住，
    等于没看。
    """
    data = baseline.load_baseline(BASELINE)
    in_baseline = {key.split("/")[1] for key in data["frames"]}

    contract = contract_mod.load_contract(baseline.GENERIC_CONTRACT)
    in_contract = {segment.id for segment in contract.segments}

    assert in_contract == in_baseline, (
        f"契约里的段与基准里的段对不上：契约有基准没有 "
        f"{sorted(in_contract - in_baseline)}；基准有契约没有 "
        f"{sorted(in_baseline - in_contract)}"
    )

    in_preview = {path.name.split("_", 1)[1][:-4] for path in preview.glob("*.png")}
    assert in_preview == in_baseline, (
        f"预览的段与基准的段对不上：预览有基准没有 "
        f"{sorted(in_preview - in_baseline)}；基准有预览没有 "
        f"{sorted(in_baseline - in_preview)}"
    )


def test_the_preview_default_output_is_outside_the_repository():
    """**预览图的默认落点在仓库外**——预览是产物，不进版本库。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_preview_generic", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    default_out = Path(module.DEFAULT_OUT).resolve()
    assert REPO_ROOT.resolve() not in default_out.parents, (
        f"预览图的默认落点 {default_out} 在仓库里——"
        f"预览是产物，不该落在仓库里"
    )


def test_a_preview_png_inside_the_repository_would_still_be_ignored():
    """**就算落在仓库里，PNG 也不许被跟踪**。

    守卫是双份的：默认落点在仓库外（上一条），仓库里的 PNG 也不许跟踪
    （这一条）——省得有人改了默认落点就把预览提交上去。
    """
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("不在 git 仓库里，跳过")
    result = _git("check-ignore", "-q",
                  "video/_staging/preview-generic/1920x1080_s01_code.png")
    assert result.returncode == 0, (
        "仓库里的 PNG 竟然不被 .gitignore 拦着——预览一不小心就提交进去了"
    )
