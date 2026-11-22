"""根工具层的 URL 形状读取器。

**规则只有一份**：仓库根的 `rules/urls.json`。根 `tools/url_rules.py`
是它在工具层的读取器——平台层与站点工具都读它，根 `tools/` 不反向
import 平台层（见 `rules/README.md`）。

这些用例守的是**读取器这一层**：地址怎么拼、规则文件坏了怎么报错。
拼出来的地址与站点（TypeScript）、契约层（Python）**逐字相同**。

跑法（根级测试）::

    cd /work/ai/blog-wt && python3 -m pytest tests/ -q
"""

from __future__ import annotations

import pytest

from url_rules import doc_url, load_rules, rules_path, unit_url, video_url


def test_the_rules_file_is_the_one_in_the_repo_root():
    """规则文件就是仓库根那一份（不是站点目录里另抄的一份）。"""
    assert rules_path().name == "urls.json"
    assert rules_path().parent.name == "rules"
    assert rules_path().is_file()


def test_the_urls_come_from_the_shared_rules():
    assert doc_url("source-tracks/postgresql/x") == "/docs/source-tracks/postgresql/x/"
    assert doc_url("source-tracks/_index") == "/docs/source-tracks/"
    assert video_url("video/row-lock") == "/videos/row-lock/"


def test_the_unit_url_switches_on_the_kind():
    assert unit_url("video/row-lock", "video") == "/videos/row-lock/"
    assert unit_url("source-tracks/_index", "category") == "/docs/source-tracks/"
    assert unit_url("a/b", "document") == "/docs/a/b/"


def test_a_rules_file_without_the_required_keys_is_refused(tmp_path):
    bad = tmp_path / "urls.json"
    bad.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


def test_a_missing_rules_file_gives_a_friendly_error(tmp_path):
    """读不到规则文件要有**能看懂的消息**（带路径），不是裸的 FileNotFoundError。"""
    missing = tmp_path / "nope.json"
    with pytest.raises(ValueError) as exc:
        load_rules(missing)
    assert "nope.json" in str(exc.value)
