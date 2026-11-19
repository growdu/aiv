#!/usr/bin/env python3
"""抓布局指纹。

**抓的是与栅格化无关的量**（坐标、字号、步进宽度、轮廓包围盒）——
它们直接来自字体文件与场景代码，所以 macOS 与 Linux 上抓出来的
数值应该一致（实测：步进与 hmtx 差 ≤ 0.056px，轮廓与字形数据逐项相等）。

**必须在装了内置字体的情况下抓**：抓的时候用的哪款字体，基准就只对
那款字体成立。脚本会检查当前解析到的族名，不是内置的那份就拒绝抓。

用法：

    python3 scripts/capture_layout_fingerprint.py

产出：

    tests/fixtures/layout_fingerprint.json
"""
from __future__ import annotations

import importlib
import json
import platform
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AIV_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from pyv import contract as contract_mod  # noqa: E402
from pyv import episodes as episodes_mod  # noqa: E402
from pyv import fingerprint, fonts  # noqa: E402

FIXTURE = PIPELINE_ROOT / "tests" / "fixtures" / "layout_fingerprint.json"


def _segments():
    """所有期契约里的全部视觉段。"""
    for episode in episodes_mod.known_eps():
        contract = contract_mod.load_contract(
            episodes_mod.contract_path(episode))
        for segment in contract.segments:
            yield episode, segment


def capture() -> dict:
    """跑一遍全部视觉段，收集指纹。"""
    frames: dict[str, list] = {}
    for episode, segment in _segments():
        module = importlib.import_module(segment.renderer)
        for canvas, width, height in fingerprint.CANVASES:
            for t in fingerprint.TIMES:
                key = f"{episode}/{segment.id}/{canvas}@{t}"
                frames[key] = fingerprint.collect_segment(
                    module, segment.params, width, height, t)
    return frames


def _dump(meta: dict, frames: dict) -> str:
    """写出 fixture：**一帧一行**。

    用 `json.dumps(indent=1)` 的话，每个数字各占一行——三千多条指纹
    就是两万多个行尾，体积凭空多三成，而且 diff 全是噪音。改成一行一帧，
    体积小一半，diff 时一帧一行照样看得清。
    """
    head = json.dumps(meta, ensure_ascii=False, indent=2)
    head = head[: head.rindex("}")].rstrip().rstrip(",")
    items = list(frames.items())
    lines = [head + ',', ' "frames": {']
    for index, (key, value) in enumerate(items):
        tail = "," if index < len(items) - 1 else ""
        lines.append(
            f"  {json.dumps(key, ensure_ascii=False)}: "
            f"{json.dumps(value, ensure_ascii=False)}{tail}"
        )
    lines.append(" }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    family = fonts.font_family()
    if family != fonts.BUNDLED_FAMILY:
        raise SystemExit(
            f"当前在用的字体是「{family}」，不是内置的那份"
            f"「{fonts.BUNDLED_FAMILY}」。\n"
            f"抓出来的指纹只对抓的时候用的那款字体成立——"
            f"先装上内置字体再抓：\n"
            f"  cd video/pipeline && python3 scripts/install_font.py"
        )

    frames = capture()
    meta = {
        "note": (
            "跨机布局指纹：坐标、字号、步进宽度、轮廓包围盒。\n"
            "这四类量直接来自字体文件与场景代码，**与栅格化后端无关**——"
            "逐像素基准在 macOS 与 Linux 之间不可比（CoreText ≠ FreeType），\n"
            "但版式一致是可以量的。采集脚本 `scripts/capture_layout_fingerprint.py`，\n"
            "比对 `tests/test_layout_fingerprint.py`，容差写死在测试里。"
        ),
        "capture": {
            "font": family,
            "platform": platform.system(),
            "canvases": [name for name, _, _ in fingerprint.CANVASES],
            "times": list(fingerprint.TIMES),
            "segments": len(frames),
        },
    }
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(_dump(meta, frames), encoding="utf-8")
    items = sum(len(v) for v in frames.values())
    print(f"已写入 {FIXTURE}")
    print(f"{len(frames)} 帧，{items} 条文字指纹，"
          f"{FIXTURE.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
