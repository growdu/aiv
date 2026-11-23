"""**死路径守卫**：仓库里不许再指向已经搬走的目录。

**背景**
------
2026-11-17 的目录重构把两处东西搬进了 `platforms/`：

| 旧路径 | 现在住哪 |
| --- | --- |
| `publish/capabilities/<平台>.toml` | `platforms/<平台>/capability.toml` |
| `publish/outbox/<id>__<平台>.json` | `platforms/<平台>/outbox/` |

搬完之后，**文档里还留着旧路径**不会立刻出事——
出事的是**读者照着它去找文件**：那个目录已经不存在了，
人要么以为「这东西没了」，要么自己建一个同名目录，把真相拆成两份。

所以这里立一条守卫：**除了计划类文档（历史记录，刻意保留），
仓库里不许有任何文件提到那两棵已经搬走的树。**

**为什么只守这两棵，不守 `weixin/` 与 `aiv/`**
------------------------------------------------
`weixin/` 与 `aiv/` 这两个旧名**在文档里大量作为「迁移对照」出现**——
`publish/deploy/README.md` 的旧→新对照表、`publish/spec/` 里的历史规格、
测试夹具里的旧 slug。把它们也扫进来，只会得到一长串「正常的历史提及」。

真正危险的那一面——**代码里还引用旧目录**——已经有人守着：
`platforms/wechat/tests/test_tools_paths.py` 静态扫 `tools/`，
谁再写 `weixin/out` 就红。

**跑法**（根级验收）::

    cd . && python3 -m pytest tests/ -q
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 已经搬走的两棵树。指向它们的引用全是死路。
DEAD_TREES = ("publish/outbox", "publish/capabilities")

#: 这些目录**不扫**：它们记的就是搬迁前的仓库（设计稿、计划稿、上游历史计划）。
#: 改它们等于改历史——历史里那两个路径确实长那样。
EXCLUDED_PREFIXES = (
    "review/plans",
    "review/specs",
    "publish/plans",
    "docs/blog",
    "video/pipeline/plans",
    "video/review/plans",
    "video/review/specs",
)

#: 构建产物与依赖：不扫（也不入库）。
SKIP_DIR_NAMES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dist", "build", "out", ".worktrees",
    ".remember",
}

#: 允许提到死路径的文件 → 理由。
#: ⚠️ **留空是有意的**：今天仓库里没有一处需要提到它们。
#: 将来真有历史记录要留（例如「试点记录」里写着那时的路径），
#: 在这里加一行**并写清理由**——空白的理由等于没理由。
HISTORICAL_WHITELIST: dict[str, str] = {}

#: 守卫自己：它当然得**写出**那两个字才能找它们。
GUARD_FILE = "tests/test_stale_paths.py"


def _walk(root: Path):
    """走一遍仓库，产出**入库范围内的**文本文件（相对路径）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root)
        # 目录级剪枝：别进构建产物与依赖，也别进计划类文档目录
        dirnames[:] = [
            name for name in sorted(dirnames)
            if name not in SKIP_DIR_NAMES
            and not str(rel_dir / name).replace(os.sep, "/").startswith(
                EXCLUDED_PREFIXES)
        ]
        for name in sorted(filenames):
            yield rel_dir / name


def _offenders(pattern: str, root: Path = REPO_ROOT) -> list[str]:
    """哪些文件第几行提到了 ``pattern``。"""
    hits: list[str] = []
    for rel in _walk(root):
        rel_str = str(rel).replace(os.sep, "/")
        if rel_str.startswith("content/units"):
            continue  # 构建产物（AGENTS.md 禁碰）
        if rel_str == GUARD_FILE:
            continue  # 守卫自己（它得写出那两个字才能找它们）
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制或读不动：不是我们要扫的东西
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern in line:
                hits.append(f"{rel_str}:{lineno}: {line.strip()}")
    return hits


def test_the_dead_trees_are_really_dead():
    """被守着的这两棵树**必须真的不在了**。

    守卫守的是「已经搬走的目录」——要是哪天它们又被搬回来，
    这条守卫就该跟着退役，而不是继续拦着谁。
    """
    for tree in DEAD_TREES:
        assert not (REPO_ROOT / tree).exists(), (
            f"{tree}/ 又回来了——守卫该改口径了（或者它根本没搬走）"
        )


def test_no_file_points_at_a_dead_tree():
    """仓库里不许有文件指着那两棵搬走的树。

    **白名单只放历史记录**，并且每个都要写清理由。
    """
    for tree in DEAD_TREES:
        hits = [h for h in _offenders(tree)
                if h.split(":", 1)[0] not in HISTORICAL_WHITELIST]
        assert not hits, (
            f"这些文件还指着已经不存在的 {tree}/：\n" + "\n".join(hits)
            + "\n（读者会照着它去找文件——那个目录不存在）"
        )


def test_the_whitelist_itself_is_honest():
    """白名单里的每一项都要**说得清理由**，而且那一处**真的还在**。

    两条都要：
    - 没写理由的白名单 = 没写理由的例外 = 迟早变成一堆积土；
    - 文件里已经没有那个字了，白名单就该删掉——留着是误导。
    """
    for path, reason in HISTORICAL_WHITELIST.items():
        assert reason.strip(), f"白名单 {path} 没写理由"
        for tree in DEAD_TREES:
            hits = [h for h in _offenders(tree) if h.split(":", 1)[0] == path]
            assert hits, (
                f"白名单里的 {path} 已经不提 {tree}/ 了——把它从白名单里删掉"
            )


def test_the_guard_would_catch_a_stale_reference(tmp_path):
    """守卫自己**要能抓到东西**——不然它只是一段没人跑过的代码。

    拿一个临时目录试：里面放一句「指向 `publish/outbox/` 的话」，
    守卫必须把它挑出来。
    """
    (tmp_path / "notes.md").write_text(
        "快照写到 publish/outbox/ 里。\n", encoding="utf-8")
    hits = _offenders("publish/outbox", root=tmp_path)
    assert len(hits) == 1, f"守卫没抓到临时树里的死路径：{hits}"
    assert "notes.md:1" in hits[0]
