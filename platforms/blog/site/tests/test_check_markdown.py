"""Markdown 保真闸门（``site/tools/check-markdown.py``）的测试。

这些测试只跟闸门本身过不去的**契约**较劲：规则报不报、报在哪一行、
退出码对不对。仓库里的真实内容会变，所以一条测试都不依赖它——
样本全在 ``tmp_path`` 里现写现用。

跑法（在本模块自己的目录里）::

    python3 -m pytest platforms/blog/site/tests/test_check_markdown.py
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "tools" / "check-markdown.py"


def load_checker():
    """按路径加载闸门模块——它不是包，importlib 是唯一不说谎的写法。"""
    spec = importlib.util.spec_from_file_location("check_markdown", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_checker(*args):
    """跑闸门命令行，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
    )


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_fence_with_content_on_the_line_is_flagged(tmp_path):
    """围栏行上写着内容（```sqlSELECT * FROM foo）——必须是错。"""
    path = write(
        tmp_path,
        "bad.md",
        "# 标题\n\n```sqlSELECT * FROM foo WHERE NOT EXISTS ()\n```\n",
    )
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[fence-lang]" in result.stdout
    assert ":3:" in result.stdout


def test_c_fence_suggests_c(tmp_path):
    """```C 要提示规范写法 c。"""
    path = write(tmp_path, "c.md", "```C\nint main(void) { return 0; }\n```\n")
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[lang-alias]" in result.stdout
    assert "'C'" in result.stdout
    assert "'c'" in result.stdout


def test_table_with_mismatched_columns_is_flagged(tmp_path):
    """表格的行列数对不上——必须是错。"""
    path = write(
        tmp_path,
        "table.md",
        "| 列一 | 列二 |\n| --- | --- |\n| 只有一列 |\n",
    )
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[table-cols]" in result.stdout


def test_clean_file_exits_zero(tmp_path):
    """干净的文件：没有错误，退出码 0。"""
    path = write(
        tmp_path,
        "clean.md",
        "# 标题\n\n"
        "正文。\n\n"
        "```python\nprint('hi')\n```\n\n"
        "| 列一 | 列二 |\n| --- | --- |\n| a | b |\n",
    )
    result = run_checker(str(path))
    assert result.returncode == 0, result.stdout
    assert "errors=0" in result.stdout


def test_bare_fence_is_only_a_warning(tmp_path):
    """没写语言标签的围栏只是提醒，不该让构建失败。"""
    path = write(tmp_path, "bare.md", "```\nplain text\n```\n")
    result = run_checker(str(path))
    assert result.returncode == 0
    assert "warn:" in result.stdout
    assert "[fence-no-lang]" in result.stdout


def test_unclosed_fence_is_flagged(tmp_path):
    """代码块没有闭合。"""
    path = write(tmp_path, "open.md", "```python\nprint('hi')\n")
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[odd-fence]" in result.stdout


def test_mermaid_first_line_must_be_a_diagram_keyword(tmp_path):
    """mermaid 块的第一行不是图类型关键字，mermaid 解析不了。"""
    path = write(
        tmp_path,
        "mermaid.md",
        "```mermaid\ngrpah TB\nA --> B\n```\n",
    )
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[mermaid-first-line]" in result.stdout


def test_mermaid_block_may_not_be_empty(tmp_path):
    """空的 mermaid 块渲染出来是空白。"""
    path = write(tmp_path, "mermaid-empty.md", "```mermaid\n```\n")
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[mermaid-fence]" in result.stdout


def test_empty_code_block_is_flagged(tmp_path):
    """空的代码块。"""
    path = write(tmp_path, "empty.md", "```bash\n```\n")
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[empty-fence]" in result.stdout


def test_indented_fence_is_flagged(tmp_path):
    """缩进 4 格的围栏渲染成缩进代码块，不是围栏。"""
    path = write(tmp_path, "nested.md", "    ```python\n    print('hi')\n")
    result = run_checker(str(path))
    assert result.returncode == 1
    assert "[nested-fence]" in result.stdout


def test_fence_inside_a_list_is_not_a_nested_fence(tmp_path):
    """列表项里的围栏按该项的缩进排版，是合法的。"""
    path = write(
        tmp_path,
        "list.md",
        "- 示例\n\n    ```python\n    print('hi')\n    ```\n",
    )
    result = run_checker(str(path))
    assert result.returncode == 0, result.stdout
    assert "[nested-fence]" not in result.stdout


def test_usage_error_exits_two(tmp_path):
    """路径不存在是用法错误，退出码 2。"""
    result = run_checker(str(tmp_path / "没有这个文件.md"))
    assert result.returncode == 2


def test_max_errors_caps_printing_but_not_the_summary(tmp_path):
    """--max-errors 只截断打印，汇总里的计数始终是真实总数。"""
    path = write(
        tmp_path,
        "many.md",
        "```C\nx\n```\n" * 5,
    )
    result = run_checker(str(path), "--max-errors", "2")
    assert result.returncode == 1
    printed = [line for line in result.stdout.splitlines() if "[lang-alias]" in line]
    assert len(printed) == 2
    assert "lang-alias=5" in result.stdout


def test_alias_table_ships_the_mandated_entries():
    """别名表里必须有约定的那些条目。"""
    checker = load_checker()
    alias_map = checker.load_alias_map()
    for token, canonical in [
        ("C", "c"),
        ("C#", "csharp"),
        ("text", "plaintext"),
        ("cmd", "batch"),
        ("conf", "ini"),
        ("dockfile", "dockerfile"),
        ("mermaind", "mermaid"),
        ("sh", "bash"),
        ("make", "makefile"),
    ]:
        assert alias_map[token] == canonical
    for language in ["c", "cpp", "csharp", "sql", "bash", "python", "ini", "json"]:
        assert alias_map[language] == language
