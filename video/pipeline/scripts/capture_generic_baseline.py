"""重抓通用渲染器的逐像素基准指纹。

用法（在 `video/pipeline/` 下跑）：

    python3 scripts/capture_generic_baseline.py

**为什么不用真实期目录**：内容不入库（母稿与期目录都不在仓库里），
基准不能靠它们——母稿一换，基准就红。改用**合成夹具**：

- `tests/fixtures/通用母稿.md`：一份合成的母稿，带代码块、表格块、图块；
- `tests/fixtures/通用契约.json`：一份合成的契约，告诉基准「哪几段画面
  要抓、参数是什么」。

**mermaid 的输出钉死**：mermaid-cli 要 npx + Chrome，跨机不一致——
真跑，基准记下来的就不是画面，而是「这台机器的 mermaid 版本」。
所以图的那两条路（贴图 / 降级）都用固定夹具（见 `pyv/baseline.py`）。

**抓取口径与场景基准共用一处**：`pyv/baseline.py`
（帧指纹怎么算、基准绑在字体族与平台上、什么时候该跳过）。

**什么时候该重抓**：通用渲染器的画面**有意**改了之后。基准一红，
先问是不是手滑改了画面；确认是有意的，再跑这个脚本重抓。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from pyv import baseline  # noqa: E402
from pyv import contract as contract_mod  # noqa: E402

FIXTURES = PIPELINE_ROOT / "tests" / "fixtures"
CONTRACT = FIXTURES / "通用契约.json"
BASELINE = FIXTURES / "generic_baseline.json"

NOTE = (
    "通用渲染器的基准指纹。**内容不入库**，所以基准靠**合成夹具**："
    "一份合成的母稿（tests/fixtures/通用母稿.md，带代码 / 表格 / 图块）"
    "加一份合成的契约（tests/fixtures/通用契约.json）。"
    "**mermaid 的输出钉死成固定夹具**——mermaid-cli 要 npx + Chrome，"
    "跨机不一致，真跑记下来的就不是画面而是「这台机器的 mermaid 版本」。"
    "抓取方式：cairo ARGB32，刷 COLORS['bg'] 底色，对整帧字节取 sha256。"
    "**基准绑在字体族与平台上**——换字体、换平台像素就不同，"
    "测试会跳过并说明原因。"
    "键是 画幅/段 id/渲染器@时刻。"
    "重抓脚本：pipeline/scripts/capture_generic_baseline.py"
)


def main() -> None:
    contract = contract_mod.load_contract(CONTRACT)

    with tempfile.TemporaryDirectory() as tmp:
        baseline.stub_mermaid(tmp)
        frames: dict[str, str] = {}
        for canvas in baseline.CANVASES:
            for segment in contract.segments:
                for t in baseline.TIMES:
                    key = baseline.frame_key(canvas, segment.id,
                                             segment.renderer, t)
                    frames[key] = baseline.frame_hash(
                        segment.renderer, segment.params, t,
                        canvas[0], canvas[1])
                    print(f"  {key}  {frames[key][:16]}")

    payload = {
        "note": NOTE,
        "capture": baseline.capture_meta(
            canvases=[f"{w}x{h}" for w, h in baseline.CANVASES],
            times=list(baseline.TIMES),
            mermaid="fixture",
            segments=len(contract.segments),
            contract=CONTRACT.name,
        ),
        "frames": frames,
    }
    baseline.save_baseline(BASELINE, payload)
    print(f"已写入 {BASELINE}（{len(frames)} 帧）")


if __name__ == "__main__":
    main()
