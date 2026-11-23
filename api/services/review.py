"""两条线的审校归一成一张表。

**信号不是门禁**（全局约束 11）：命中的信号**不影响** `gate`。
`gate` 只看**审校记录的状态**——那是人写下的进度。

- 文档流：`tools/review-check.py` 的信号只有 `warn` 与 `info`，
  所以文档流的 `counts["error"]` **恒为 0**。
- 视频流：`pyv/cli.py::cmd_review` 恒返回 0（注释原文「信号不是门禁」）。

**这一层不发明闸。** 它只把两条线的信号搬进同一张表。
"""
from __future__ import annotations

from pathlib import Path

from .paths import REPO_ROOT

SEVERITIES = ("error", "warn", "info")

#: 文档线的状态词表（review/INDEX.md 的表头那一行）。
DOC_STATES = ("待审", "审校中", "建议中", "已确认", "已合入")

#: 视频线的状态词表（video/review/README.md §5 的模板）。
VIDEO_STATES = ("待审", "已出信号", "已看帧", "建议中", "已确认", "已合入")

#: 过了这两档就不再挡人。
PASSING_STATES = ("已确认", "已合入")


def _counts(signals: list[dict]) -> dict:
    """按信号的 severity 数一遍。

    **不抄输入里的 counts**——两条线的算法不一定一样，抄了就对不上。
    """
    counts = {"error": 0, "warn": 0, "info": 0}
    for signal in signals:
        severity = signal.get("severity")
        if severity in counts:
            counts[severity] += 1
    return counts


def _front_matter_status(path: Path) -> str | None:
    """读一份审校记录 front matter 里的 `status:`。读不到 → `None`。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


def _episode_status(path: Path) -> str | None:
    """读一期视频的 `review.md` 里那一行 `- 状态：`。

    **只认顶格的 `- 状态：`**——「优先修改」里缩进的那几行是**逐条**的状态
    （待改 / 已改 / 已合入），不是这一期的状态。
    """
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- 状态："):
            value = line[len("- 状态："):].strip()
            # 模板里写的是「待审 / 已出信号 / …」，取第一个。
            return value.split("/")[0].strip()
    return None


def document_gate(doc_id: str, *, repo_root: Path = REPO_ROOT) -> dict:
    """文档流的门：只看审校记录的状态。

    记录在 `review/<doc_id>.md`（`doc_id` = `docs/` 下的相对路径去掉 `.md`）。
    """
    record = Path(repo_root) / "review" / f"{doc_id.strip('/')}.md"
    status = _front_matter_status(record)
    if status is None:
        return {"status": "待审", "blocking": True,
                "reason": "还没有审校记录"}
    blocking = status not in PASSING_STATES
    return {
        "status": status,
        "blocking": blocking,
        "reason": f"审校记录的状态是 {status}" if blocking else "",
    }


def episode_gate(episode: str, *, repo_root: Path = REPO_ROOT) -> dict:
    """视频流的门：只看这一期 `review.md` 的状态。"""
    record = Path(repo_root) / "video" / "episodes" / episode.strip("/") / "review.md"
    status = _episode_status(record)
    if status is None:
        return {"status": "待审", "blocking": True,
                "reason": "这一期还没有 review.md"}
    blocking = status not in PASSING_STATES
    return {
        "status": status,
        "blocking": blocking,
        "reason": f"审校记录的状态是 {status}" if blocking else "",
    }


def normalize_document_report(raw: dict, *, doc_id: str, path: str,
                              repo_root: Path = REPO_ROOT) -> dict:
    """把 `tools/review-check.py --json` 的输出归一成统一形状。

    输入形状：`{"docs": [{"source", "pillar", "slug", "kind", "title",
    "stats", "depth", "depth_ok", "signals": [...]}]}`，
    信号的字段是 `{rule, severity, line, excerpt, detail}`。

    归一的差别只有两处：补 `layer: "document"`；`target` 由 `line` 派生。
    """
    docs = (raw or {}).get("docs") or []
    entry = None
    for doc in docs:
        if doc.get("source") == path or doc.get("slug") == doc_id:
            entry = doc
            break
    if entry is None and len(docs) == 1:
        entry = docs[0]

    signals = []
    for raw_signal in (entry or {}).get("signals") or []:
        line = raw_signal.get("line")
        signals.append({
            "rule": raw_signal.get("rule", ""),
            "layer": "document",
            "severity": raw_signal.get("severity", "info"),
            "target": f"第 {line} 行" if line is not None else "",
            "line": line,
            "excerpt": raw_signal.get("excerpt", ""),
            "detail": raw_signal.get("detail", ""),
        })

    return {
        "subject": {"kind": "document", "id": doc_id, "path": path},
        "layer": "document",
        "counts": _counts(signals),
        "signals": signals,
        "notes": [],
        "gate": document_gate(doc_id, repo_root=repo_root),
    }


def normalize_pyv_report(raw: dict, *, subject: dict,
                         repo_root: Path = REPO_ROOT) -> dict:
    """把 `pyv.cli review text|video --json` 的输出归一成统一形状。

    输入形状：`{"episode", "layer", "counts", "signals": [...], "notes": [...]}`，
    信号的字段是 `{rule, layer, severity, target, excerpt, detail}`
    （**没有 line**——视频线的位置是「第 3 句」这种语义位置）。
    """
    signals = []
    for raw_signal in (raw or {}).get("signals") or []:
        signals.append({
            "rule": raw_signal.get("rule", ""),
            "layer": raw_signal.get("layer", (raw or {}).get("layer", "")),
            "severity": raw_signal.get("severity", "info"),
            "target": raw_signal.get("target", ""),
            "line": None,
            "excerpt": raw_signal.get("excerpt", ""),
            "detail": raw_signal.get("detail", ""),
        })

    kind = subject.get("kind")
    if kind == "episode":
        gate = episode_gate(subject.get("id", ""), repo_root=repo_root)
    else:
        gate = {"status": "待审", "blocking": True, "reason": "不认识的对象"}

    return {
        "subject": dict(subject),
        "layer": (raw or {}).get("layer", ""),
        "counts": _counts(signals),
        "signals": signals,
        "notes": list((raw or {}).get("notes") or []),
        "gate": gate,
    }
