"""重抓场景画面的逐像素基准指纹。

用法（在 `video/pipeline/` 下跑）：

    python3 scripts/capture_scene_baseline.py

抓取方式与 `tests/test_contract.py` 里那条守卫**完全一致**：
cairo ARGB32 1920×1080，刷 `COLORS['bg']` 底色，对整帧字节取 sha256；
形象以 `character.Mascot._load` 强制降级为 none——3D 形象是媒体产物不入库，
基准若带着素材抓，换台机器、换个干净检出就必然对不上，
那条测试会退化成「看本机有没有图」，而不是「看这次改造有没有改到画面」。

**抓取口径与通用渲染器基准共用一处**：`pyv/baseline.py`
（帧指纹怎么算、基准绑在字体族与平台上、什么时候该跳过）。

**什么时候该重抓**：画面文案或版式**有意**改了之后。
那条守卫的本意是「文案搬进契约不该动到画面」，所以基准一红，
先问是不是手滑改了画面；确认是有意的，再跑这个脚本重抓。
"""
from __future__ import annotations

import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AIV_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from pyv import baseline  # noqa: E402
from pyv import contract as contract_mod  # noqa: E402
from pyv import episodes as episodes_mod  # noqa: E402

#: 抓取口径与通用渲染器基准**共用一处**（`pyv/baseline.py`）：
#: 帧指纹怎么算、基准绑在字体族与平台上、什么时候该跳过。
TIMES = baseline.TIMES
BASELINE = PIPELINE_ROOT / "tests" / "fixtures" / "scene_baseline.json"

NOTE = (
    "场景画面的基准指纹。**形象一律不画**——3D 形象是媒体产物不入库，"
    "基准若带着素材抓，换台机器或换个干净检出就必然对不上，"
    "测试就变成「看本机有没有图」。"
    "抓取方式：cairo ARGB32 1920×1080，刷 COLORS['bg'] 底色，"
    "对整帧字节取 sha256；形象以 character.Mascot._load 强制降级为 none。"
    "**基准绑在字体上**——capture.font 记着抓的时候用的字体族名，"
    "换字体后这条基准不适用于当前机器，测试会跳过并说明原因。"
    "**按段存，不按模块存**——同一个渲染器在不同期用的 params 不同，"
    "画面不同、哈希不同；键是 期号/段 id/渲染器@时刻。"
    "重抓脚本：pipeline/scripts/capture_scene_baseline.py"
)


def _all_segments():
    """所有期契约里的全部视觉段。

    **按段抓，不按模块抓。** 同一个渲染器在不同期用的 `params` 不同
    （`s01_intro` 与 `s06_outro` 每期都在用，每期的标题文案各不一样），
    画面就不同、哈希就不同——只按渲染器存一份，后面的期画面永远比不到。
    """
    for episode in episodes_mod.known_eps():
        contract = contract_mod.load_contract(
            episodes_mod.contract_path(episode))
        for segment in contract.segments:
            yield episode, segment


def frame_key(episode: str, segment, t: float) -> str:
    """基准的键：期号 + 段 id + 渲染器 + 时刻。"""
    return f"{episode}/{segment.id}/{segment.renderer}@{t}"


def _without_mascot() -> None:
    """让形象一律不画（与测试里的做法一致）。"""
    from pyv import character

    def _no_mascot(self) -> None:
        self._mode = "none"

    character.Mascot._load = _no_mascot


def main() -> None:
    _without_mascot()
    frames: dict[str, str] = {}
    for episode, segment in _all_segments():
        for t in TIMES:
            key = frame_key(episode, segment, t)
            frames[key] = frame_hash(segment.renderer, segment.params, t)
            print(f"  {key}  {frames[key][:16]}")

    payload = {
        "note": NOTE,
        # 基准**绑在字体与平台上**：换一款字体、换个平台，同一段文字的
        # 像素就不同——记下来，测试才知道什么时候这条基准不适用于当前机器
        #（见 `pyv/baseline.py` 的说明）。
        "capture": baseline.capture_meta(
            size="1920x1080",
            times=list(TIMES),
            mascot="none",
            # 覆盖了多少段——条数由所有期的契约推导，加期不用改这里，
            # 但漏抓会红（`tests/test_contract.py` 里有覆盖声称的守卫）。
            segments=sum(1 for _ in _all_segments()),
        ),
        "frames": frames,
    }
    baseline.save_baseline(BASELINE, payload)
    print(f"已写入 {BASELINE}（{len(frames)} 帧）")


if __name__ == "__main__":
    main()
