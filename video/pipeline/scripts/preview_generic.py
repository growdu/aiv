"""把通用渲染器的画面渲成 PNG，用来肉眼核对版式。

**为什么要有这一步**：逐像素基准只能告诉你「变了」，告诉不了你
「变得好不好看」。配色、留白、字号、行距这些是**看**出来的，不是测出来的。

**看的就是基准量的那张画布**：走 `pyv.baseline.render_frame`（同一个底色、
同一套画法），看的与测的是同一张图——另起一套画法，看的就是另一张图。

**合成契约**：真实期目录与母稿都不在仓库里（内容不入库），所以预览看的
是合成的那几段（`tests/fixtures/通用契约.json`），与逐像素基准**同一份**
（见 `pyv/baseline.py` 的 `GENERIC_CONTRACT`）。

**画面不入库**：预览是产物，默认落在**仓库外**（系统临时目录）；即使落在
仓库里，PNG 也不许被跟踪（`tests/test_assets_are_tracked.py` 盯着）。

用法（在 `video/pipeline/` 下跑）：

    python3 scripts/preview_generic.py
    python3 scripts/preview_generic.py --out /tmp/preview
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from pyv import baseline  # noqa: E402
from pyv import contract as contract_mod  # noqa: E402

#: 预览图的默认落点：**仓库外**（系统临时目录）。
DEFAULT_OUT = Path(tempfile.gettempdir()) / "aiv-preview-generic"

#: 预览的时刻。通用渲染器不做动画，几个时刻画出来一样——留一个位置，
#: 以后通用渲染器真做起动画来，这里不用改。
TIMES = (0.0,)


def render_png(renderer: str, params: dict, t: float, width: int, height: int,
               out_path: Path) -> Path:
    """画一帧写成 PNG。"""
    surface = baseline.render_frame(renderer, params, t, width, height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(out_path))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="通用渲染器的预览图")
    parser.add_argument("--contract", default=str(baseline.GENERIC_CONTRACT),
                        help="用哪份契约（默认：合成夹具，与基准同一份）")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="PNG 落在哪（默认：仓库外的临时目录）")
    args = parser.parse_args()

    contract = contract_mod.load_contract(args.contract)
    out_dir = Path(args.out)

    with tempfile.TemporaryDirectory() as tmp:
        # **mermaid 的输出钉死**：预览要看的是版式，不是这台机器的
        # mermaid-cli 版本。
        baseline.stub_mermaid(tmp)
        for width, height in baseline.CANVASES:
            for segment in contract.segments:
                for t in TIMES:
                    name = f"{width}x{height}_{segment.id}.png"
                    path = render_png(segment.renderer, segment.params, t,
                                      width, height, out_dir / name)
                    print(f"  {path}")


if __name__ == "__main__":
    main()
