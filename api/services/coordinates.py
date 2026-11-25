"""坐标选项：给界面做下拉框用的目录树。

**目录即接口**——分类、二级内容、系列、合集都只存在于目录里，
不另存一张登记表。这里把草稿箱与母稿层的树并起来，
界面上就能只让选**已经存在**的坐标。

**只返回目录名。** 站名、品牌名、平台名一个都没有——它们在缝里。
"""
from __future__ import annotations

from pathlib import Path

#: 视频线的期路径是四层：系列 / 合集 / 文档 / 档位。
#: **档位是固定的**（三档），所以那棵树截到三层。
EPISODE_DEPTH = 3

#: 文档流的深度**不写死**——仓库的深度就是仓库的深度。
#: 这个数只是递归的护栏，不是规则。
DOCUMENT_DEPTH = 8


def _dirs(root: Path) -> list[str]:
    """一层里的目录名。`_` 开头的是保留名空间——**不算分类**。"""
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and not p.name.startswith("_"))


def _merge(left: list[dict], right: list[dict]) -> list[dict]:
    """两棵树并起来——同名的节点，children 也并。"""
    by_name = {node["name"]: node for node in left}
    for node in right:
        existing = by_name.get(node["name"])
        if existing is None:
            by_name[node["name"]] = {"name": node["name"],
                                     "children": list(node["children"])}
        else:
            existing["children"] = _merge(existing["children"],
                                          node["children"])
    return sorted(by_name.values(), key=lambda node: node["name"])


def _tree(root: Path, depth: int) -> list[dict]:
    """一层树：每个目录一个节点，children 是下一层。"""
    if depth <= 0:
        return []
    return [{"name": name, "children": _tree(root / name, depth - 1)}
            for name in _dirs(root)]


def document_tree(*roots: Path) -> list[dict]:
    """文档流的目录树（分类 → 二级内容 → …）。

    **并起来**：草稿箱里的分类与母稿层里的分类都要能选——
    只在草稿箱里有的分类是「还没写」，只在母稿层里有的分类是
    「已经过了审」，两种都得能接着写。
    """
    tree: list[dict] = []
    for root in roots:
        tree = _merge(tree, _tree(Path(root), DOCUMENT_DEPTH))
    return tree


def episode_tree(*roots: Path) -> list[dict]:
    """视频流的目录树（系列 → 合集 → 文档）。

    **截到三层**——档位是固定的三档，不进树。
    """
    tree: list[dict] = []
    for root in roots:
        tree = _merge(tree, _tree(Path(root), EPISODE_DEPTH))
    return tree
