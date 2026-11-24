"""逐像素基准的**共用口径**。

**为什么共用一处**：场景基准（`tests/fixtures/scene_baseline.json`）与
通用渲染器基准（`tests/fixtures/generic_baseline.json`）如果各写一份
「帧指纹怎么算」「基准绑在什么上」「什么时候该跳过」，过一阵两边就会
不一样——那时候「基准」只是个文件，测不出任何东西。

**基准绑在两样东西上**：

- **字体族**——换一款字体，同一段文字的像素就不同，比出来的是噪声；
- **平台**——macOS 的 cairo 走 CoreText，Linux 走 FreeType，栅格化不同，
  同一个字体、同一段文字，像素仍然不同。

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

from pyv import fonts
from pyv.palette import COLORS, hex_to_rgb

#: 基准抓的画幅：横版 + 竖版（抖音那一档）。
CANVASES = ((1920, 1080), (1080, 1920))

#: 基准抓的时刻。
TIMES = (0.0, 0.45, 0.9)

#: mermaid 夹具图的标记：源码里有这一行的，画那张夹具图。
FIXTURE_PNG_MARKER = "fixture-png"

#: 基准文件的键：`画幅/段 id/渲染器@时刻`。
def frame_key(canvas: tuple[int, int], segment_id: str, renderer: str,
              t: float) -> str:
    """基准的键。"""
    return f"{canvas[0]}x{canvas[1]}/{segment_id}/{renderer}@{t}"


def frame_hash(module_name: str, params: dict, t: float,
               width: int = 1920, height: int = 1080) -> str:
    """画一帧，取整帧字节的 sha256。

    **底色要刷**：cairo 的新画布是全透明的，直接哈希的话，帧与帧之间
    只差「画了什么」——那是对的（我们要比的就是画出来的东西），
    但空帧的哈希会跟任何一张同尺寸的空画布一样，比较时看不出「什么都没画」。
    """
    module = importlib.import_module(module_name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*hex_to_rgb(COLORS["bg"]))
    ctx.paint()
    module.render(ctx, t, width, height, params)
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
