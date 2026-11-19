"""内容单元编译器的用例——**全部自己造语料**，不依赖仓库里曾经有过的内容。"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "publish"))


def _compiler():
    """按路径加载 tools/build-content-units.py（文件名带连字符，import 不了）。"""
    spec = importlib.util.spec_from_file_location(
        "build_content_units", REPO_ROOT / "tools" / "build-content-units.py")
    module = importlib.util.module_from_spec(spec)
    # ⚠️ 必须**先登记进 sys.modules 再执行**：编译器里有
    # `from __future__ import annotations` 和一个 dataclass，dataclass 的类型检查
    # 要去 sys.modules[cls.__module__] 取命名空间——模块没登记就 AttributeError，
    # 用例会在夹具阶段就炸，证不了事。
    sys.modules["build_content_units"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def compiler(tmp_path, monkeypatch):
    module = _compiler()
    docs = tmp_path / "docs"
    (docs / "a").mkdir(parents=True)
    (docs / "a" / "_index.md").write_text(
        "---\ntitle: 甲\ncascade:\n  categories: [甲]\n---\n\n# 甲\n", encoding="utf-8")
    monkeypatch.setattr(module, "DOCS", docs)
    monkeypatch.setattr(module, "CONTENT_UNITS", tmp_path / "content" / "units")
    return module


def test_an_episode_field_reaches_the_content_unit(compiler):
    """期号字段今天被静默丢掉——页面照常渲染，期号区块却是空的。"""
    (compiler.DOCS / "ep.md").write_text(
        "---\ntitle: 一期\ndate: '2026-01-01'\ndescription: 一期的描述。\nepisode: row-lock\n"
        "episode_no: 3\nseries: 数据库内核\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    rendered = compiler.render(unit)
    assert "episode: row-lock" in rendered
    assert "episode_no: 3" in rendered
    assert "series: 数据库内核" in rendered


def test_a_long_description_survives_the_round_trip(compiler):
    """80 字以上的 description 不能被折行截断（今天真会）。"""
    from publishkit.contract import parse_front_matter
    # ⚠️ 这段文本**必须含空格**（控制器裁决 R5）。PyYAML 的 safe_dump **只在空格处折行**，
    # 不含空格的串根本不折 —— 那样这条用例在修之前就绿了，证不了事。
    # 下面的串里既有中文也有 "PostgreSQL"，空格是折行点。
    long_text = "客户端连上 PostgreSQL 需要哪几样东西，" * 12
    (compiler.DOCS / "ep.md").write_text(
        f"---\ntitle: 一期\ndate: '2026-01-01'\ndescription: {long_text}\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    fields, _ = parse_front_matter(compiler.render(unit))
    assert fields["description"] == long_text


def test_the_compiler_and_the_contract_layer_agree_on_the_episode_fields(compiler):
    """两边对「哪些字段算期号」的口径必须一致——否则编译器传了、契约层不认。"""
    from publishkit import contract
    assert set(compiler.EPISODE_FIELDS) == set(contract.EPISODE_SCALAR_FIELDS) | set(contract.EPISODE_LIST_FIELDS)
