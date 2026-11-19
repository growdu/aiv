import ast
import json
import os
import subprocess
from pathlib import Path

import cairo
import pytest

from pyv import character
from pyv import render
from pyv.timeline import Scene

PACKAGE = Path(render.__file__).resolve().parent

#: 夹具期的契约（`tests/fixtures/演示系列/演示合集/夹具文档/short/contract.json`）。
FIXTURE_CONTRACT = (Path(__file__).parent / "fixtures" / "演示系列"
                   / "演示合集" / "夹具文档" / "short" / "contract.json")


def _probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,r_frame_rate,codec_name,pix_fmt:format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def test_render_scene_produces_expected_media(tmp_path):
    scene = Scene(id="s01", start=0.0, end=1.0, type="code",
                  subtitle="测试", renderer="sample_scene")
    out = tmp_path / "s01.mp4"
    render.render_scene(scene, out, width=320, height=180, fps=24)
    info = _probe(out)
    stream = info["streams"][0]
    assert stream["width"] == 320
    assert stream["height"] == 180
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert stream["r_frame_rate"] == "24/1"
    assert abs(float(info["format"]["duration"]) - 1.0) < 0.05


def test_render_scene_output_has_non_white_pixels(tmp_path):
    """场景必须真的画了东西，不能是一整块白底。"""
    from PIL import Image
    scene = Scene(id="s01", start=0.0, end=1.0, type="code",
                  subtitle="测试", renderer="sample_scene")
    out = tmp_path / "s01.mp4"
    render.render_scene(scene, out, width=320, height=180, fps=24)
    frame = tmp_path / "frame.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vframes", "1", str(frame)],
        check=True, capture_output=True, text=True)
    pixels = list(Image.open(frame).convert("RGB").getdata())
    assert any(pixel != (255, 255, 255) for pixel in pixels)


def test_render_scene_requires_renderer(tmp_path):
    scene = Scene(id="s01", start=0.0, end=1.0, type="code", subtitle="测试", renderer=None)
    try:
        render.render_scene(scene, tmp_path / "x.mp4", width=64, height=64)
    except ValueError as exc:
        assert "renderer" in str(exc)
    else:
        raise AssertionError("缺少 renderer 时应当报错")


def _contract_params(renderer: str) -> dict:
    """从视觉分镜契约里取出这一段要用的参数。

    场景的文案与数字全在契约里（见 `pyv/contract.py`），测试也照这个口径取，
    不要在测试里另抄一份——抄一份就等于又造了个真相来源。

    磁盘上没有期时读**夹具期**的契约（`tests/fixtures/演示系列/演示合集/夹具文档/short/contract.json`），
    有期时先读期目录里的契约。
    """
    from pyv import contract as contract_mod
    from pyv import episodes as episodes_mod

    paths = [episodes_mod.contract_path(slug)
             for slug in episodes_mod.known_eps()]
    paths.append(FIXTURE_CONTRACT)
    for path in paths:
        if not path.is_file():
            continue
        for segment in contract_mod.load_contract(path).segments:
            if segment.renderer == renderer:
                return dict(segment.params)
    raise AssertionError(f"契约里没有 {renderer} 这一段")


@pytest.mark.parametrize("module_name", ["pyv.scenes.s01_intro", "pyv.scenes.s06_outro"])
def test_mascot_scenes_render_without_pose(module_name):
    """片头/片尾场景在移除 2D 部件动画后仍要能画出来。

    这两个场景以前靠 `pose=Pose(...)` 让角色挥手/点头。2D 形象与部件切分移除后，
    形象只剩静帧 + 位移/缩放/淡入——场景里的调用必须同步改掉，
    否则渲染时直接 TypeError。
    """
    import importlib

    scene = importlib.import_module(module_name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
    ctx = cairo.Context(surface)
    scene.render(ctx, 0.5, 320, 180, _contract_params(module_name))
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    painted = any(data[y * stride:(y + 1) * stride][3::4] for y in range(180))
    assert painted, f"{module_name} 画出来是空画面"


def test_clip_is_stale_when_the_character_asset_changes(tmp_path, monkeypatch):
    """换了形象素材，已经渲染好的片段必须作废重渲。

    只看 Python 模块的修改时间发现不了素材换掉了——角色重新生成、
    戴眼镜、换配色，模块一个字节没动，片段却还是旧形象。
    """
    asset = tmp_path / "mascot.png"
    asset.write_bytes(b"not-really-a-png")
    monkeypatch.setattr(character, "STATIC_IMAGE", asset)
    scene = Scene(id="s01", start=0.0, end=1.0, type="code",
                  subtitle="测试", renderer="sample_scene")
    out = tmp_path / "s01.mp4"
    out.write_bytes(b"old clip")

    fresh = max(render.newest_source_mtime(scene), asset.stat().st_mtime) + 10
    os.utime(out, (fresh, fresh))
    assert render.clip_is_fresh(out, scene), "片段比所有输入都新，应该复用"

    stale = asset.stat().st_mtime - 1
    os.utime(out, (stale, stale))
    assert not render.clip_is_fresh(out, scene), \
        "素材比片段新，片段必须作废重渲"


# -------------------------------------------------- 重渲染输入清单


def _imported_pyv_modules(source: str) -> set[str]:
    """源码里 import 的 `pyv.*` 模块名。

    `from pyv import components` 与 `from pyv.draw import text` 两种写法
    都要认：前者 import 的是模块本身，后者 import 的是模块里的东西。
    """
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module == "pyv":
                out.update(f"pyv.{alias.name}" for alias in node.names)
            elif node.module.split(".")[0] == "pyv":
                out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "pyv":
                    out.add(alias.name)
    return out


def _modules_the_renderer_uses() -> set[str]:
    """渲染入口（传递地）用到的 `pyv` 模块的文件名。

    起点是三个：`render.py`（渲染入口）、`subtitle.py`（字幕烧录，
    由 `render.py` 的 `burner` 参数传进来，不是 import 进来的）、
    以及全部场景模块（`render.py` 用 `importlib` 动态 import 它们，
    静态扫不到）。

    **场景模块自己不在结果里**：改一个场景不该作废其它场景的片段，
    场景自己的源码由 `newest_source_mtime` 单独算。
    """
    roots = ["render.py", "subtitle.py"]
    roots += sorted(f"scenes/{path.name}"
                    for path in (PACKAGE / "scenes").glob("*.py"))
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = PACKAGE / name
        if not path.exists():
            continue
        for module in _imported_pyv_modules(path.read_text(encoding="utf-8")):
            candidate = "/".join(module.split(".")[1:]) + ".py"
            if candidate.startswith("scenes/") or candidate in seen:
                continue
            queue.append(candidate)
    return {name for name in seen if not name.startswith("scenes/")}


def test_the_render_input_list_covers_every_module_the_renderer_uses():
    """渲染入口用到的每个模块都必须在重渲染输入清单里。

    **漏登记的症状是「改了它，画面没变」**：片段因为「比渲染输入新」
    被当成没过期直接复用，**而且没有任何报错**。

    这条守卫**独立扫一遍源码**（不复用生产代码的推导逻辑）：从渲染
    入口出发把 `pyv.*` 的 import 递归收齐，跟清单对照。清单少一个
    就红。
    """
    missing = sorted(_modules_the_renderer_uses()
                     - set(render.RENDER_INPUT_MODULES))
    assert not missing, (
        f"这些模块会影响画面，但不在 RENDER_INPUT_MODULES 里：{missing}\n"
        f"改了它们，片段会被当成「没过期」直接复用——画面还是旧的。"
    )


def test_a_layout_change_makes_the_clip_stale(tmp_path):
    """**行为上的判据**：改了版式层，片段必须作废。

    清单里写着不算数——得真的会因为它变陈旧。这条把 `layout.py` 的
    修改时间推到片段之后，`clip_is_fresh` 必须返回 False。
    """
    layout_module = PACKAGE / "layout.py"
    original = layout_module.stat().st_mtime
    scene = Scene(id="s01", start=0.0, end=1.0, type="code",
                  subtitle="测试", renderer="sample_scene")
    out = tmp_path / "s01.mp4"
    out.write_bytes(b"old clip")
    try:
        fresh = render.newest_source_mtime(scene) + 10
        os.utime(out, (fresh, fresh))
        assert render.clip_is_fresh(out, scene), "片段比所有输入都新，应该复用"

        changed = fresh + 10
        os.utime(layout_module, (changed, changed))
        assert not render.clip_is_fresh(out, scene), (
            "layout.py 比片段新，片段必须作废重渲——"
            "它不在 RENDER_INPUT_MODULES 里？"
        )
    finally:
        os.utime(layout_module, (original, original))
