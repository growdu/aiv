"""骨架 → (口播稿, 字幕表, 视觉契约)。

派生出来的三元组**格式与现在完全一致**：

- 口播稿：一段代码块，**每行一句**（`align.parse_script` 认这个形状）；
- 字幕表：每句一行的表格（`align.parse_subtitle_table` 认这个形状）；
- 契约：`pyv/contract.py` 认识的那个 JSON。

所以 `pyv/align.py` / `pyv/render.py` / `pyv/compose.py` **一行都不用改**——
它们看到的还是老样子。

**母稿引用要当场查**
------------------
段里的 `ref` 指向母稿里的第 `nth` 个 mermaid / 代码 / 表格块。
引用错了（母稿没了、`nth` 超范围）就报错——画面那一环会**静默缺一块**，
而片子里看不出少了什么。母稿解析用 `pyv/motherdoc.py`。

**契约里的 `episode` 是四层期路径**
--------------------------------
骨架的 `episode` 是**文档路径**（`系列/合集/文档`），契约的 `episode` 是
**期路径**（`系列/合集/文档/短档`）——档位在路径里，不在骨架里。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyv import motherdoc
from pyv import skeleton

# video/ 是 pipeline/ 的上一级：pyv/derive.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AIV_ROOT.parent

#: 画面类型 → 通用渲染器模块。
#:
#: 这些渲染器属于「计划二」（母稿画面资产与通用渲染器），还没落地——
#: 契约只是**按名字**引用它们，出片那一步才 import。
GENERIC_RENDERERS = {
    "mermaid": "pyv.scenes.gen_mermaid",
    "code": "pyv.scenes.gen_code",
    "table": "pyv.scenes.gen_table",
    "card": "pyv.scenes.gen_card",
}

#: 要指向母稿里的块的那种画面——它们必须带 `ref`。
REF_KINDS = ("mermaid", "code", "table")


@dataclass(frozen=True)
class Derived:
    """派生出来的三元组。"""

    narration: list[str] = field(default_factory=list)
    subtitles: list[str] = field(default_factory=list)
    contract: dict = field(default_factory=dict)


def _resolve_ref(kind: str, ref: dict) -> motherdoc.Block:
    """把母稿引用解析成真的块。**找不到就报错。**

    `ref.doc` 是相对仓库根的路径（规格 §5.3）；绝对路径也认——
    测试夹具就靠它指到临时目录里的母稿。
    """
    doc = str(ref.get("doc") or "").strip()
    if not doc:
        raise ValueError("母稿引用没有 doc")
    try:
        nth = int(ref.get("nth"))
    except (TypeError, ValueError):
        raise ValueError(f"母稿引用的 nth 不是整数：{ref.get('nth')!r}") from None
    if nth < 1:
        raise ValueError(f"母稿引用的 nth 是 {nth}——从 1 起")

    path = Path(doc)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"母稿不存在：{doc}")

    mother = motherdoc.load_motherdoc(path)
    try:
        return motherdoc.find_block(mother, kind, nth)
    except LookupError as exc:
        raise ValueError(
            f"母稿 {doc} 里没有 {kind} 类的第 {nth} 块"
            f"（该类共 {mother.count(kind)} 块）"
        ) from exc


def _segment_visual(segment: dict) -> tuple[str, dict]:
    """一段的 (renderer, params)。

    母稿引用的段走**通用渲染器**（`gen_mermaid` / `gen_code` / `gen_table`），
    参数里带上 `ref`；`card` 没有母稿引用，`scene` 走手写渲染器。
    """
    sid = str(segment.get("id") or "")
    visual = segment.get("visual")
    if not isinstance(visual, dict):
        raise ValueError(f"段 {sid} 没有 visual")
    kind = str(visual.get("kind") or "")
    if kind not in skeleton.VISUAL_KINDS:
        raise ValueError(
            f"段 {sid} 的 visual.kind 是 {kind!r}，只认 {'、'.join(skeleton.VISUAL_KINDS)}"
        )
    if kind == "scene":
        renderer = str(visual.get("renderer") or "")
        if not renderer:
            raise ValueError(f"段 {sid} 的 kind=scene 但没有 renderer")
        return renderer, dict(visual.get("params") or {})

    renderer = GENERIC_RENDERERS[kind]
    params = dict(visual.get("params") or {})
    if kind in REF_KINDS:
        ref = visual.get("ref")
        if not isinstance(ref, dict) or not ref:
            raise ValueError(f"段 {sid} 的 kind={kind} 但没有 ref")
        _resolve_ref(kind, ref)
        params["ref"] = dict(ref)
    return renderer, params


def _segment_lines(segment: dict, key: str) -> list[str]:
    """取一段的 narration / subtitles（字符串当一句）。"""
    raw = segment.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item) for item in raw]


def derive(source: dict, tier: str) -> Derived:
    """把骨架按档位裁剪，派生出口播稿、字幕表与视觉契约。

    `source` 是 `skeleton.load_skeleton` 读出来的骨架（一个 dict）。
    裁剪只看 `role`（`skeleton.select_segments`），**句子一个字都不改**。
    """
    segments = skeleton.select_segments(source, tier)

    narration: list[str] = []
    subtitles: list[str] = []
    contract_segments: list[dict] = []

    for segment in segments:
        sid = str(segment.get("id") or "")
        renderer, params = _segment_visual(segment)
        lines = _segment_lines(segment, "narration")
        subs = _segment_lines(segment, "subtitles")
        if not lines:
            raise ValueError(f"段 {sid} 没有口播——没有句子的段在时间轴上不出现")
        if not subs:
            raise ValueError(
                f"段 {sid} 没有字幕——口播稿与字幕表的句数必须一样"
            )
        if len(lines) != len(subs):
            raise ValueError(
                f"段 {sid} 的口播 {len(lines)} 句与字幕 {len(subs)} 行不一致"
            )
        # 句子是**跨段连续的全局索引**——契约的 sentences 用它。
        sentences = list(range(len(narration), len(narration) + len(lines)))
        narration.extend(lines)
        subtitles.extend(subs)
        contract_segments.append({
            "id": sid,
            "renderer": renderer,
            "sentences": sentences,
            "params": params,
        })

    doc = str(source.get("episode") or "")
    contract = {
        "version": 1,
        # 契约的 episode 是**四层期路径**（档位在路径里，不在骨架里）
        "episode": f"{doc}/{tier}" if doc else tier,
        "title": str(source.get("title") or ""),
        "segments": contract_segments,
    }
    return Derived(narration=narration, subtitles=subtitles, contract=contract)


def narration_markdown(narration: list[str]) -> str:
    """口播稿小节：代码块里每行一句。

    **连二级标题一起给**——流水线是按「标题里含『口播稿』」找这一节的
    （`align.parse_script`），标题让调用方自己拼容易拼错。
    """
    body = "\n".join(narration)
    heading = f"## 口播稿（{len(narration)} 句，每行一句）"
    return f"{heading}\n\n```\n{body}\n```\n"


def subtitle_table(subtitles: list[str]) -> str:
    """字幕文本小节：每句一行。标题同样一起给（关键字是「字幕文本」）。"""
    lines = ["| # | 字幕 |", "| --- | --- |"]
    for index, text in enumerate(subtitles, start=1):
        lines.append(f"| {index} | {text} |")
    return "## 字幕文本\n\n" + "\n".join(lines) + "\n"
