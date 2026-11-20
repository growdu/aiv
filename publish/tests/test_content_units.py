"""I2：内容单元 ↔ 契约层。

这条接口以前靠约定——钉它的用例随 hexo 时代的 sync-hexo.py 一起删了。
现在照今天的编译器重写一条：**真跑一遍编译器**，比对两边看到的 id 集合。
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_the_compiler(docs: Path, units: Path) -> None:
    """真跑一遍编译器（子进程，跟 CI 里跑的同一条命令）。"""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build-content-units.py")],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "AIV_DOCS": str(docs), "AIV_CONTENT_UNITS": str(units)},
    )
    # ⚠️ 失败时要把编译器的 stderr 带上：`capture_output=True` 会把它吃掉，
    # 只剩一个 `CalledProcessError`——看不出是缺依赖、语料坏了，还是编译器崩了。
    assert result.returncode == 0, result.stderr


def test_the_contract_layer_sees_exactly_the_units_the_compiler_produced(tmp_path):
    docs = tmp_path / "docs"
    (docs / "a").mkdir(parents=True)
    # ⚠️ 语料三样都要给：**date**（编译器拿不到就抛 CompileError，见裁决 R7）、
    # **description**（没有描述编译器也抛 CompileError）、
    # 分类页的 **cascade.categories**。
    # ⚠️ 分类页的 `date` 也要给：它拿不到日期时是去问 git 的
    # （`tmp_path` 不是 git 仓库 → 查不到历史 → 抛 CompileError）。
    (docs / "a" / "_index.md").write_text(
        "---\ntitle: 甲\ndate: '2026-01-01'\ndescription: 甲的描述。\n"
        "cascade:\n  categories: [甲]\n---\n\n# 甲\n", encoding="utf-8")
    (docs / "a" / "doc.md").write_text(
        "---\ntitle: 一篇\ndate: '2026-01-01'\ndescription: 一篇的描述。\n---\n\n正文。\n", encoding="utf-8")
    units = tmp_path / "content" / "units"
    _run_the_compiler(docs, units)

    from publishkit.schedule import discover_units
    found, errors = discover_units(units)
    assert not errors, f"契约层读出了坏单元：{errors}"
    produced = {p.relative_to(units).with_suffix("").as_posix()
                for p in units.rglob("*.md")}
    # ⚠️ 先钉住「编译器确实产出了这两篇」——不然两边**同时为空**时，
    # 下面那条相等断言会**空过**，而这正是这条用例要守的那条接口。
    assert produced == {"a/_index", "a/doc"}
    assert {u.content_id for u in found} == produced
