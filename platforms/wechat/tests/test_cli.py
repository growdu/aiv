"""公众号的退出码语义：**用法错 = 1，缺前置条件 = 2，做事失败 = 3。**

公众号的退出码以前是各写各的：用法错是 argparse 默认的 2（抛出去），
「找不到」是 1，「被拒」也是 2。契约层把四个码定死之后
（`publish/publishkit/exit_codes.py`），这里钉住其中两档。
"""
from wechat.cli import main


def test_a_usage_error_exits_with_one():
    """命令写错 = 用法错 = 1（argparse 默认退 2，要改）。"""
    assert main(["__no_such_command__"]) == 1


def test_a_missing_article_is_a_precondition_failure(tmp_path):
    """文章不存在 = 缺前置条件 = 2（以前退 1，`EXIT_NOT_FOUND` 现在归到「前置条件」）。"""
    assert main(["convert", "no-such-slug",
                 "--posts-dir", str(tmp_path)]) == 2


def test_an_invalid_max_length_is_a_usage_error(tmp_path, capsys):
    """正文上限写错了 = 用法错 = 1（不是 2）。

    ``--max-length`` 给的不是正整数（``WX_MAX_LENGTH`` 环境变量给坏了也一样），
    是**参数/配置写错了**——契约层那张表里这一档是 1。
    """
    code = main(["convert", "no-such-slug",
                 "--posts-dir", str(tmp_path),
                 "--max-length", "-1"])
    assert code == 1
    # 断的是**上限**这一条报错，不是 argparse 的用法错（那也退 1，但理由不同）。
    assert "正文上限" in capsys.readouterr().err


def test_the_exit_codes_come_from_the_declaration():
    """退出码从能力声明的 `[exit]` 段读——语义由契约层定死。

    写死在 Python 里的那四个数字，改 TOML 就改不动了。
    """
    from wechat.capability import default_capability_path, load_exit_codes
    from wechat.cli import (EXIT_API_ERROR, EXIT_NOT_FOUND, EXIT_OK,
                            EXIT_REJECTED, EXIT_USAGE)

    codes = load_exit_codes(default_capability_path())
    assert codes == {"ok": 0, "usage": 1, "precondition": 2, "failed": 3}
    assert (EXIT_OK, EXIT_USAGE, EXIT_NOT_FOUND, EXIT_REJECTED,
            EXIT_API_ERROR) == (codes["ok"], codes["usage"], codes["precondition"],
                                codes["precondition"], codes["failed"])
