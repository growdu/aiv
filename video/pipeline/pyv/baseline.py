"""逐像素基准的**共用口径**。

**为什么共用一处**：场景基准（`tests/fixtures/scene_baseline.json`）与
通用渲染器基准（`tests/fixtures/generic_baseline.json`）如果各写一份
「帧指纹怎么算」「基准绑在什么上」「什么时候该跳过」，过一阵两边就会
不一样——那时候「基准」只是个文件，测不出任何东西。

**基准绑在三样东西上**：

- **字体族**——换一款字体，同一段文字的像素就不同，比出来的是噪声；
- **平台**——macOS 的 cairo 走 CoreText，Linux 走 FreeType，栅格化不同，
  同一个字体、同一段文字，像素仍然不同；
- **栅格化本身**——同一个平台上，cairo / FreeType 的版本不同，画出来的
  像素也不同（抗锯齿的算法随版本变）。所以基准里记一个**栅格化探针**
  （`raster_probe()`：画几个字，取像素的 sha256）：探针对不上就跳过，
  不拿噪声当信号。

跨机的版式由 `tests/test_layout_fingerprint.py` 守（比轮廓、坐标与步进
宽度，那三样来自字体文件与代码，与栅格化无关）。

**帧指纹怎么算**：cairo ARGB32，刷 `COLORS['bg']` 底色，把整帧的字节
取 sha256。**只取字节，不取「看起来一样」**——像素级的判据就该是像素级。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import platform
import subprocess
from pathlib import Path

import cairo

from pyv import draw
from pyv import fonts
from pyv.palette import COLORS, hex_to_rgb

#: 基准抓的画幅：横版 + 竖版（抖音那一档）。
CANVASES = ((1920, 1080), (1080, 1920))

#: 基准抓的时刻。
TIMES = (0.0, 0.45, 0.9)

#: 通用渲染器的**合成契约**：基准抓取与预览都看它。
#:
#: **为什么要共用一份**：看的东西和测的东西不是一回事，就白看了——
#: 预览过了眼，基准却没盖住那一段（或者反过来），两边各说各话。
GENERIC_CONTRACT = (Path(__file__).resolve().parents[1] / "tests" / "fixtures"
                    / "通用契约.json")

#: mermaid 夹具图的标记：源码里有这一行的，画那张夹具图。
FIXTURE_PNG_MARKER = "fixture-png"

#: 基准文件的键：`画幅/段 id/渲染器@时刻`。
def frame_key(canvas: tuple[int, int], segment_id: str, renderer: str,
              t: float) -> str:
    """基准的键。"""
    return f"{canvas[0]}x{canvas[1]}/{segment_id}/{renderer}@{t}"


#: 栅格化探针画的那几个字（ASCII + 汉字）。
RASTER_PROBE_TEXT = "Ab1 字形"


def raster_probe() -> str:
    """**这台机器的栅格化指纹**：画几个字，取像素的 sha256。

    **为什么要有它**：同一段文字，在不同的 cairo / FreeType 版本上
    栅格化出来的像素不一样（抗锯齿的算法随版本变）。基准记的是
    「抓基准那台机器画出来的像素」——换一台机器、换一个版本，比出来的
    是噪声不是信号。探针就是那几笔的指纹：**探针对不上，说明像素没法比**，
    跳过并说清楚为什么，而不是拿噪声当信号。

    **探针走 `draw.text`**（画字只有这一条路）——量的是**画面上真正用的
    那条画法**（同一族字体、同一个关 hinting 的设置）。绕过去自己
    `ctx.show_text` 的话，量到的是另一条路。

    **探针画的是当前在用的那一族**（`fonts.font_family()`）——字体换了
    探针就对不上，这是对的：换了字体的像素本来也不能比。
    """
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 64)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    try:
        draw.text(ctx, RASTER_PROBE_TEXT, 8, 44, 28, "#000000")
    except fonts.MissingGlyphs:
        # 兜底的字体连这几个字都没有——那就只画 ASCII（探针照样能比）。
        draw.text(ctx, "Ab1", 8, 44, 28, "#000000")
    return hashlib.sha256(bytes(surface.get_data())).hexdigest()



def render_frame(module_name: str, params: dict, t: float,
                width: int = 1920, height: int = 1080) -> cairo.ImageSurface:
    """画一帧（**底色已刷**），把画布交出去。

    **预览也走这里**：预览图要看的，就是基准量的那张画布——底色、
    尺寸、画法都一样。预览另起一套画法，看的就是另一张图。
    """
    module = importlib.import_module(module_name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*hex_to_rgb(COLORS["bg"]))
    ctx.paint()
    module.render(ctx, t, width, height, params)
    return surface


def frame_hash(module_name: str, params: dict, t: float,
               width: int = 1920, height: int = 1080) -> str:
    """画一帧，取整帧字节的 sha256。

    **底色要刷**：cairo 的新画布是全透明的，直接哈希的话，帧与帧之间
    只差「画了什么」——那是对的（我们要比的就是画出来的东西），
    但空帧的哈希会跟任何一张同尺寸的空画布一样，比较时看不出「什么都没画」。
    """
    surface = render_frame(module_name, params, t, width, height)
    return hashlib.sha256(bytes(surface.get_data())).hexdigest()


def captured_from() -> str:
    """抓基准时的 git 提交（短 hash）。"""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unknown"
    return f"{sha}（重抓于本脚本）"


def capture_meta(**fields) -> dict:
    """基准的元信息：**字体族与平台是绑在基准上的**。

    换字体或换平台，同一段内容的像素就不同——那时候这条基准比的是
    噪声，不是信号。测试据此跳过（并说明原因）。
    """
    meta = {
        "font": fonts.font_family(),
        "mono_font": fonts.BUNDLED_MONO_FAMILY,
        "platform": platform.system(),
        "raster_probe": raster_probe(),
        "captured_from": captured_from(),
    }
    meta.update(fields)
    return meta


def skip_reason(payload: dict) -> str:
    """这条基准在当前机器上**能不能用**；能用就返回空串。

    不能用就返回**为什么**——跳过要说明原因，不能只跳。
    """
    meta = payload.get("capture", {})

    baseline_font = meta.get("font", "")
    current = fonts.font_family()
    if baseline_font and baseline_font != current:
        return (f"基准是在「{baseline_font}」下抓的，当前机器是「{current}」——"
                f"跨字体像素本来就不同，这条基准在这里测不出东西")

    baseline_mono = meta.get("mono_font", "")
    if baseline_mono and not fonts.mono_family_resolves():
        return (f"基准是在等宽「{baseline_mono}」下抓的，当前机器没装这一族"
                f"（python3 scripts/install_font.py）——"
                f"代码块的像素跟基准对不上")

    baseline_platform = meta.get("platform", "")
    if baseline_platform and baseline_platform != platform.system():
        return (f"基准是在 {baseline_platform} 上抓的，当前机器是 "
                f"{platform.system()}——cairo 在两边用的栅格化器不同"
                f"（macOS 走 CoreText，Linux 走 FreeType），跨平台比像素是"
                f"拿噪声当信号。跨机的版式由 "
                f"tests/test_layout_fingerprint.py 守")

    baseline_probe = meta.get("raster_probe", "")
    if baseline_probe:
        current_probe = raster_probe()
        if baseline_probe != current_probe:
            return (f"基准是在另一套栅格化下抓的（探针对不上：基准 "
                    f"{baseline_probe[:12]}，当前 {current_probe[:12]}）——"
                    f"cairo / FreeType 版本不同，同一段文字画出来的像素就不同，"
                    f"比出来的是噪声不是信号")
    return ""


def save_baseline(path: str | Path, payload: dict) -> None:
    """写基准文件。"""
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_baseline(path: str | Path) -> dict:
    """读基准文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---- mermaid 的输出钉死（基准抓取专用） --------------------------------

def fixture_png(path: str | Path) -> Path:
    """画一张**确定**的夹具图并写成 PNG。

    **为什么不用真跑 mermaid-cli**：它要 npx + Chrome，跨机不一致——
    真跑，基准记下来的就不是画面，而是「这台机器的 mermaid 版本」。
    这里画一张固定的图，两边（抓基准与守卫）画出来完全一样。
    """
    target = Path(path)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 160)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0.16, 0.29, 0.53)
    ctx.rectangle(20, 20, 200, 40)
    ctx.fill()
    ctx.set_source_rgb(0.42, 0.47, 0.53)
    ctx.rectangle(20, 80, 140, 24)
    ctx.fill()
    ctx.rectangle(20, 116, 90, 24)
    ctx.fill()
    surface.write_to_png(str(target))
    return target


def stub_mermaid(directory: str | Path) -> None:
    """把 mermaid 的输出**钉死**（基准抓取专用）。

    - 源码里带 `fixture-png` 的 → 画那张夹具图（**贴图那条路**）；
    - 其余的 → 按「渲染失败」降级（**降级那条路**）。

    两条路都被基准盖住：改坏了任一条，基准都会红。
    """
    from pyv import mermaid
    from pyv.generic import gen_mermaid

    png = fixture_png(Path(directory) / "夹具图.png")

    def asset_for(source: str):
        if FIXTURE_PNG_MARKER in source:
            return mermaid.MermaidAsset(key="fixture", source=source,
                                        png=png, error=None)
        return mermaid.MermaidAsset(key="fixture", source=source,
                                    png=None, error="fixture failure")

    gen_mermaid.asset_for = asset_for
