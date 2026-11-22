"""守住 README 里那个会漂的数字：用例条数。

README 是这套工具的门面，用例条数却每加一条就旧一格。
而且「多少条通过」根本不是稳定口径：
母稿 ``source/_posts`` 不入库，一条 Windows 专属的浏览器位置用例在没有
Windows 的检出里是 ``skipped``，有 Windows 时才会跑。
所以比的是「收集到多少条」，那个数与平台无关。
"""

import re
import subprocess
import sys

README_RELATIVE_PATH = ("platforms", "wechat", "README.md")

TEST_COUNT_PATTERN = re.compile(r"测试：\*\*(\d+)\s*个\*\*")
COLLECTED_PATTERN = re.compile(r"(\d+)\s+tests?\s+collected")


def _readme(repo_root):
    return repo_root.joinpath(*README_RELATIVE_PATH).read_text(encoding="utf-8")


def _collected_count(repo_root):
    """实际收集到的用例条数。

    跑的是 ``--collect-only``：它不执行任何用例，也不碰语料，
    所以这个数与母稿在不在检出里无关——这正是它能当基准的原因。
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "platforms/wechat/tests",
            "--collect-only", "-q", "-p", "no:cacheprovider",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    match = COLLECTED_PATTERN.search(result.stdout)
    assert match, (
        "pytest --collect-only 没有给出收集条数，退出码 {}：\n{}".format(
            result.returncode, result.stdout[-2000:]
        )
    )
    return int(match.group(1))


def test_readme_states_the_real_number_of_tests(repo_root):
    """README 说的用例条数必须等于实际收集到的条数。

    加了用例要回来改这个数——这是这个用例存在的全部理由。
    """
    text = _readme(repo_root)

    matches = TEST_COUNT_PATTERN.findall(text)
    assert len(matches) == 1, (
        "README 里应当只有一处用例条数，实际找到 {} 处".format(len(matches))
    )

    stated = int(matches[0])
    collected = _collected_count(repo_root)
    assert stated == collected, (
        "README 写 {} 个，实际收集到 {} 条 —— 加了用例要回来改这个数".format(
            stated, collected
        )
    )
