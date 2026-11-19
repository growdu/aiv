"""Makefile 的期号分流。

`make EP=<期路径>` 是换一期的唯一入口。**一期 = `video/episodes/<系列>/<合集>/<文档>/<档位>/` 一个目录**，
Makefile 里不再有期号登记表——路径从 `EP` 派生。

所以这条守卫盯住两件事：

1. 没给 EP 必须当场报错，不能拿空路径去跑；
2. 给了 EP，脚本 / 契约 / 旁白必须指向这一期的目录，不能串。
"""
import subprocess
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
MAKEFILE = PIPELINE / "Makefile"

#: 用来验路径派生的期号。目录在不在磁盘上不重要——这里只看路径怎么拼。
SLUG = "some-slug"


def _make(*args):
    return subprocess.run(
        ["make", *args], cwd=PIPELINE, capture_output=True, text=True
    )


def test_makefile_has_no_episode_registry():
    """Makefile 里不再有一份期号登记表——期路径由 EP 派生。"""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "ifeq ($(EP)," not in text
    assert "$(ROOT)/episodes/$(EP)" in text


def test_missing_ep_fails_loudly():
    """没给 EP 必须报错退出，不能拿空路径去跑。"""
    result = _make("align")
    assert result.returncode != 0, "没给 EP 竟然没有报错"
    assert "EP" in result.stderr + result.stdout


def test_unknown_ep_fails_loudly():
    """EP 指向不存在的期时必须报错，不能静悄悄地出片。"""
    result = _make("EP=definitely-not-an-episode", "align")
    assert result.returncode != 0, "未知 EP 竟然没有报错"


def test_ep_derives_the_episode_paths():
    """给了 EP，脚本 / 契约 / 旁白 / 时间轴都指向这一期的目录。"""
    result = _make("-n", f"EP={SLUG}", "align")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f"episodes/{SLUG}/口播稿.md" in out, "口播稿指错了"
    assert f"episodes/{SLUG}/contract.json" in out, "契约指错了"
    assert f"episodes/{SLUG}/narration.mp3" in out, "旁白指错了"
    assert f"episodes/{SLUG}/storyboard.json" in out, "时间轴指错了"


def test_each_ep_resolves_its_own_files():
    """换一个 EP，路径就换一个目录——不能串到别的期。"""
    for slug in ("alpha", "beta"):
        other = "beta" if slug == "alpha" else "alpha"
        result = _make("-n", f"EP={slug}", "align")
        assert result.returncode == 0, result.stderr
        out = result.stdout
        assert f"episodes/{slug}/contract.json" in out, f"{slug} 的契约指错了"
        assert f"episodes/{other}/" not in out, f"{slug} 串到了 {other}"


def test_build_and_out_dirs_are_split_per_episode():
    """片段目录与成片按期分开——各期的段 id 会重名（s01…）。"""
    for slug in ("alpha", "beta"):
        result = _make("-n", f"EP={slug}", "compose")
        assert result.returncode == 0, result.stderr
        out = result.stdout
        assert f"build/{slug}" in out, f"{slug} 的片段目录指错了"
        assert f"out/{slug}.mp4" in out, f"{slug} 的成片名不对"
