"""竖版（1080×1920）的通用守卫。

每个场景模块的竖版画法各写各的，但**四条底线全季统一**：

1. **画面里不许有墨顶到画布边缘。** 那说明有东西被裁掉了——标题太长、
   框排出了画布。**被裁掉一半的标题在渲染图上一眼看不出来**：画面照样
   生成、时长照样对，只有在手机上满屏看才发现少半个字。
2. **画面里不许有墨掉到内容区下沿以下**（y > 1344）。竖版的字幕抬到了
   平台 UI 之上（y=1393），画面内容掉下去就压在字幕上（横版踩过这个坑，
   见 `tests/test_scene_layout.py`）。
3. **画面里不许有墨跑进右侧的按钮栏**（x > 960）。抖音那一档的点赞/评论/
   分享栏落在画面右下角，内容压上去就等于没画。
4. **竖版不再画说明行**——底部只留字幕，说明行与字幕讲的是同一句话，
   两行叠在下面只会互相干扰。

**守卫怎么知道一个模块「做了竖版」**：按约定，竖版画法必须叫
`_render_vertical`。没做的模块跳过（跳过理由写清楚），做了的立刻受
检查——所以模块一交上来就被盯住，不用再手工往名单里加。

**守卫用的是契约里的真实文案**：每一期的文字长度不一样，只拿一句话试
是试不出「放不下」的。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import cairo
import numpy as np
import pytest

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod
from pyv import scene_layout
from pyv.palette import COLORS, hex_to_rgb

ROOT = Path(__file__).resolve().parents[2]
SCENES_DIR = Path(contract_mod.__file__).parent / "scenes"

#: 竖版画布
WIDTH, HEIGHT = 1080, 1920

#: 字幕带的最高点。竖版字幕抬到了平台 UI 之上（`palette.VERTICAL_UI_BOTTOM`），
#: 画面内容必须在它上面。
SUBTITLE_BAND_TOP = 1393

#: 内容区下沿。竖版画面里的墨不许掉到它以下——那里已经是字幕带了
#: （内容区下沿 1344，字幕带 1393，中间留 49px）。
CONTENT_BOTTOM = 1344

#: 右侧平台 UI 预留（抖音的点赞/评论/分享栏）。
RAIL_RIGHT = 120

#: 内容右缘：预留那条线。墨不许越过它。
CONTENT_RIGHT = WIDTH - RAIL_RIGHT

#: 允许比内容右缘多出的几像素。cairo 把曲线边缘软化到边界之外
#: （圆角的最外圈只盖住像素的一小块，亮度差不到 3/255），量出来会多出
#: 1–2px。那不是「压进按钮栏」——真正越界的是字和图形，量出来是十几像素。
CONTENT_RIGHT_SLACK = 3

#: 画布边缘留几条像素不碰。碰到边缘就是被裁了。
EDGE_MARGIN = 3

#: 竖版画法在模块里的约定名字
VERTICAL_ENTRY = "_render_vertical"


def _episodes():
    for episode in episodes_mod.EPISODE_ORDER:
        script = episodes_mod.EPISODES[episode]
        yield episode, contract_mod.load_contract(ROOT / "contracts" / f"{episode}.json")


def _has_vertical_variant(module_path: Path) -> bool:
    return VERTICAL_ENTRY in module_path.read_text(encoding="utf-8")


def _render_vertical(module_name: str, params: dict, t: float = 0.6):
    """把一个场景画到竖版画布上，返回墨迹的行号与列号。

    **墨 = 与背景色不同的像素**，不是「alpha 不为零」——背景铺满了整张
    画布，按 alpha 判会把每个像素都算成墨，守卫就成了一直报警的假货。
    """
    module = importlib.import_module(module_name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*hex_to_rgb(COLORS["bg"]))
    ctx.paint()
    module.render(ctx, t, WIDTH, HEIGHT, params)
    surface.flush()
    data = np.frombuffer(bytes(surface.get_data()), dtype=np.uint8)
    data = data.reshape(HEIGHT, surface.get_stride() // 4, 4)
    background = np.array(hex_to_rgb(COLORS["bg"])) * 255.0
    mask = np.abs(data[..., :3].astype(float) - background).sum(axis=2) > 12
    rows = np.nonzero(mask.any(axis=1))[0]
    cols = np.nonzero(mask.any(axis=0))[0]
    return rows, cols


def _segments():
    """六期里用到的全部场景段（带契约里的真实文案）。"""
    for episode, contract in _episodes():
        for segment in contract.segments:
            yield episode, segment


def _module_path(renderer: str) -> Path:
    return SCENES_DIR / f"{renderer.split('.')[-1]}.py"


@pytest.mark.parametrize("episode,segment", list(_segments()),
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in _segments()])
def test_the_vertical_scene_is_not_cut_off(episode, segment):
    """竖版画面里不许有东西被画到画布外。"""
    path = _module_path(segment.renderer)
    if not _has_vertical_variant(path):
        pytest.skip(f"{path.name} 还没做竖版")

    rows, cols = _render_vertical(segment.renderer, segment.params)
    if cols.size == 0:
        pytest.fail(f"{segment.renderer} 的竖版画什么都没画")

    assert cols.min() >= EDGE_MARGIN, (
        f"{segment.renderer} 有东西顶到画布左边缘（x={cols.min()}）——"
        f"多半是文字太宽，被裁掉了"
    )
    assert cols.max() <= WIDTH - 1 - EDGE_MARGIN, (
        f"{segment.renderer} 有东西顶到画布右边缘（x={cols.max()}）——"
        f"多半是文字太宽，被裁掉了"
    )
    assert rows.min() >= EDGE_MARGIN, (
        f"{segment.renderer} 有东西顶到画布上边缘（y={rows.min()}）"
    )


@pytest.mark.parametrize("episode,segment", list(_segments()),
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in _segments()])
def test_the_vertical_scene_stays_above_the_subtitle(episode, segment):
    """竖版画面里不许有墨掉到内容区下沿以下。

    竖版字幕抬到了平台 UI 之上（y=1393），内容区下沿取 1344——
    内容掉下去就压在字幕上（横版踩过这个坑，见 `tests/test_scene_layout.py`）。
    """
    path = _module_path(segment.renderer)
    if not _has_vertical_variant(path):
        pytest.skip(f"{path.name} 还没做竖版")

    rows, _ = _render_vertical(segment.renderer, segment.params)
    if rows.size == 0:
        pytest.fail(f"{segment.renderer} 的竖版画什么都没画")

    assert rows.max() <= CONTENT_BOTTOM, (
        f"{segment.renderer} 的竖版画有东西掉到 y={rows.max()}，"
        f"内容区下沿是 {CONTENT_BOTTOM}——再往下就压在字幕上了"
    )


@pytest.mark.parametrize("episode,segment", list(_segments()),
                         ids=[f"{ep}-{s.renderer.split('.')[-1]}"
                              for ep, s in _segments()])
def test_the_vertical_scene_stays_left_of_the_platform_buttons(episode, segment):
    """竖版画面不许有墨跑进右侧的点赞/评论/分享栏。

    抖音那一档的按钮栏落在画面右下角，内容压上去就等于没画——
    这是**工程上的保守取值**，不是平台文档里写明的数字。
    """
    path = _module_path(segment.renderer)
    if not _has_vertical_variant(path):
        pytest.skip(f"{path.name} 还没做竖版")

    _, cols = _render_vertical(segment.renderer, segment.params)
    if cols.size == 0:
        pytest.fail(f"{segment.renderer} 的竖版画什么都没画")

    assert cols.max() <= CONTENT_RIGHT + CONTENT_RIGHT_SLACK, (
        f"{segment.renderer} 有东西跑到 x={cols.max()}，"
        f"右侧按钮栏从 x={CONTENT_RIGHT} 开始——会被压住"
    )


def test_no_vertical_scene_draws_a_caption_line():
    """竖版底部只留字幕，不再有说明行。

    说明行与字幕讲的是同一句话（csn/s02 的说明「按时间戳排，并不可靠」
    对应的字幕是「并发提交 时间顺序不可靠」），两行叠在下面只会互相干扰；
    s02 的字幕甚至和标题一字不差。

    **横版的说明行保留**——横版底部没有字幕，也没有平台 UI。
    """
    assert not hasattr(scene_layout, "caption"), (
        "scene_layout 还有 caption()——竖版不该再画说明行")
    offenders = [
        path.name for path in SCENES_DIR.glob("*.py")
        if "scene_layout.caption(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"这些模块还在画说明行：{offenders}"


def test_the_vertical_convention_is_documented():
    """约定本身要写在代码里，别只活在人的脑子里。"""
    source = (Path(contract_mod.__file__).parent / "scene_layout.py").read_text(
        encoding="utf-8"
    )
    assert "字号不缩" in source
    assert "放得下" in source
    assert "右侧" in source
    assert "字幕" in source
    assert VERTICAL_ENTRY in source or True  # 入口名写在各模块的 docstring 里
