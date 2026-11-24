"""根工具层的术语规则读取器。

**规则只有一份**：仓库根的 `rules/terminology.json`。根 `tools/terminology_rules.py`
是它在工具层的读取器——审校检查器 `tools/review-check.py` 读它，
层与层之间共享的是**文件**，不是 import（见 `rules/README.md`）。

这些用例守的是**读取器这一层**：文件在哪儿、词表长什么样、文件坏了怎么报错。
判据本身在 `review/specs/2026-11-24-术语纪律与反造词.md`——那是人读的。

跑法（根级测试）::

    cd /work/ai/blog && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json

import pytest

from terminology_rules import (
    REQUIRED_KEYS,
    WORD_TABLES,
    load_terminology,
    rules_path,
)


def test_the_rules_file_is_the_one_in_the_repo_root():
    """规则文件就是仓库根那一份（不是各层目录里另抄的一份）。"""
    assert rules_path().name == "terminology.json"
    assert rules_path().parent.name == "rules"
    assert rules_path().is_file()


def test_the_word_tables_are_loaded():
    rules = load_terminology()
    assert "管线" in rules["banned"]
    assert "心智模型" in rules["banned"]
    assert "沉淀" in rules["soft"]
    assert "起步与全景" in rules["bad_names"]
    assert "一文读懂" in rules["title_words"]
    assert "深入" in rules["title_words_soft"]
    for table in WORD_TABLES:
        for word, advice in rules[table].items():
            assert isinstance(advice, str), f"{table}/{word} 的说明不是字符串"


def test_the_file_is_valid_json_with_the_required_keys():
    data = json.loads(rules_path().read_text(encoding="utf-8"))
    for key in REQUIRED_KEYS:
        assert key in data, f"规则文件缺键：{key}"


def test_a_rules_file_without_the_required_keys_is_refused(tmp_path):
    bad = tmp_path / "terminology.json"
    bad.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_terminology(bad)


def test_a_missing_rules_file_gives_a_friendly_error(tmp_path):
    """读不到规则文件要有**能看懂的消息**（带路径），不是裸的 FileNotFoundError。"""
    missing = tmp_path / "nope.json"
    with pytest.raises(ValueError) as exc:
        load_terminology(missing)
    assert "nope.json" in str(exc.value)


def test_a_broken_json_gives_a_friendly_error(tmp_path):
    bad = tmp_path / "terminology.json"
    bad.write_text("{不是 JSON", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_terminology(bad)
    assert "terminology.json" in str(exc.value)


def test_a_word_table_that_is_not_a_mapping_is_refused(tmp_path):
    bad = tmp_path / "terminology.json"
    bad.write_text(json.dumps({"version": 1, "banned": ["管线"],
                               "soft": {}, "bad_names": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_terminology(bad)
