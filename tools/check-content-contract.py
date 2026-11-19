#!/usr/bin/env python3
"""内容契约闸门：校验所有内容单元是否满足内容契约。

契约的字段表与格式规则在 ``publish/spec/00-架构设计.md`` §4.1 / §4.2，
实现是 ``publish/publishkit/contract.py``——**本文件不重复实现规则**，
它只把规则套到语料上，并把违规清单打出来。

为什么需要它
------------
内容契约是发布层的唯一闸门（规格 §4.1）。但闸门只在**有人调用发布层**
的时候才响：``publishkit.cli schedule candidates`` 会报违规，可它不在
CI 里，违规的标题能一路走到线上。

所以把同一套校验搬进构建流水线：违规即构建失败。

校验对象
--------
默认是 ``content/units/`` 下的内容单元（编译器的产物，也是发布层真正读的
东西）。也可以指到 ``docs/`` 的母稿上——母稿的 front matter 与内容单元
是同一套格式，两边校验的规则相同（缩进标量那处差异见 contract.py 的
模块 docstring，两条路径都会报同一条错，不会分裂）。

用法
----
    python3 tools/build-content-units.py             # 先产出内容单元
    python3 tools/check-content-contract.py          # 校验 content/units
    python3 tools/check-content-contract.py docs/    # 校验母稿

退出码：0 = 没有违规；1 = 有违规（CI 应失败）；2 = 用法或环境错误。
"""

import argparse
import importlib
import sys
from pathlib import Path

# 根 tools/ 的脚本：parents[1] 就是仓库根。
# 路径常量统一从根 tools/paths.py 取——那儿是唯一出处。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from paths import CONTENT_UNITS, REPO_ROOT  # noqa: E402

# publish/ 本身不是 Python 包，publishkit 挂在它下面。
sys.path.insert(0, str(REPO_ROOT / "publish"))

# 动态导入：publishkit 只在 publish/ 这一层路径下可解析，静态分析器看不
# 到这条 sys.path 插入，importlib 是这里唯一不说谎的写法。
_contract = importlib.import_module("publishkit.contract")
parse_front_matter = _contract.parse_front_matter
validate_fields = _contract.validate_fields


def iter_markdown(root: Path):
    """Yield every markdown file under ``root`` (sorted, stable order)."""
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            yield path


def check(root: Path):
    """Return a list of ``(path, violation)`` pairs."""
    problems = []
    for path in iter_markdown(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            problems.append((path, f"读不了：{error}"))
            continue
        fields, _body = parse_front_matter(text)
        for violation in validate_fields(fields):
            problems.append((path, violation))
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-content-contract",
        description="校验内容单元是否满足内容契约（publish/spec/00 §4）。",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(CONTENT_UNITS),
        help="要校验的目录或文件（默认：content/units）",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(
            f"找不到 {root}：先跑 python3 tools/build-content-units.py "
            "产出内容单元。",
            file=sys.stderr,
        )
        return 2

    problems = check(root)
    if not problems:
        count = sum(1 for _ in iter_markdown(root))
        print(f"内容契约通过：{count} 个内容单元，0 违规。")
        return 0

    for path, violation in problems:
        print(f"{path}：{violation}")
    files = len({path for path, _ in problems})
    print(f"\n共 {len(problems)} 处违规，涉及 {files} 个文件。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
