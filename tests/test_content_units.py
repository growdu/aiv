"""内容单元编译器的用例——**全部自己造语料**，不依赖仓库里曾经有过的内容。"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "publish"))

from publishkit.contract import parse_front_matter  # noqa: E402


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
    # 用例的语料都写在顶层（`docs/ep.md`）——顶层没有祖先链，
    # 所以**不用**造 `_index.md`（造了也没人读）。
    docs.mkdir()
    monkeypatch.setattr(module, "DOCS", docs)
    monkeypatch.setattr(module, "CONTENT_UNITS", tmp_path / "content" / "units")
    return module


def _video_pages():
    """按路径加载 tools/build-video-pages.py（文件名带连字符，import 不了）。"""
    spec = importlib.util.spec_from_file_location(
        "build_video_pages", REPO_ROOT / "tools" / "build-video-pages.py")
    module = importlib.util.module_from_spec(spec)
    # ⚠️ **先登记进 sys.modules 再执行**：这个脚本**今天**没有 dataclass
    # （所以不登记也不会炸），但注册上更稳妥——将来它加了 dataclass，
    # dataclass 的类型检查要去 sys.modules[cls.__module__] 取命名空间，
    # 模块没登记就 AttributeError，用例会在夹具阶段就炸，证不了事。
    sys.modules["build_video_pages"] = module
    spec.loader.exec_module(module)
    return module


def test_the_video_permalink_is_the_videos_url():
    """视频页地址统一成 /videos/<id>/——站点现在就是这么发的。"""
    module = _video_pages()
    assert module.permalink("video/row-lock") == "/videos/row-lock/"


def test_the_video_compiler_does_not_hardcode_the_video_prefix():
    """视频编译器不许自己写死 '/videos/'——得从共享规则里取。"""
    text = (REPO_ROOT / "tools" / "build-video-pages.py").read_text(encoding="utf-8")
    assert not re.search(r"""['"`]/videos/""", text), "视频编译器写死了 '/videos/'"


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
    # ⚠️ 这段文本**必须含空格**（控制器裁决 R5）。PyYAML 的 safe_dump **只在空格处折行**，
    # 不含空格的串根本不折 —— 那样这条用例在修之前就绿了，证不了事。
    # 下面的串里既有中文也有 "PostgreSQL"，空格是折行点。
    #
    # 长度取 **100 字**（裁决 F5）：既 >80 列（照样触发折行），又过得了
    # 契约层 `description` 的 150 字上限——产出的是**契约合法**的内容单元，
    # 不是一条过不了 `tools/check-content-contract.py` 的语料。
    long_text = "客户端连上 PostgreSQL 需要哪几样东西，" * 4
    (compiler.DOCS / "ep.md").write_text(
        f"---\ntitle: 一期\ndate: '2026-01-01'\ndescription: {long_text}\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    fields, _ = parse_front_matter(compiler.render(unit))
    assert fields["description"] == long_text


def test_the_compiler_and_the_contract_layer_agree_on_the_episode_fields(compiler):
    """两边对「哪些字段算期号」的口径必须一致——否则编译器传了、契约层不认。"""
    from publishkit import contract
    assert set(compiler.EPISODE_FIELDS) == set(contract.EPISODE_SCALAR_FIELDS) | set(contract.EPISODE_LIST_FIELDS)


def test_an_empty_episode_list_is_not_passed_through(compiler):
    """空列表/空值的期号字段**不要**搬进内容单元——契约层读不了那个形状。

    ``episode_sources: []`` 落盘后，契约层的扁平解析器把 ``[]`` 读成**字符串**
    ``'[]'``，然后报「episode_sources 必须是列表」。
    空的就当「没有这个字段」，别搬。
    """
    (compiler.DOCS / "ep.md").write_text(
        "---\ntitle: 一期\ndate: '2026-01-01'\ndescription: 一期的描述。\n"
        "episode_sources: []\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    assert "episode_sources" not in compiler.render(unit)


def test_a_non_empty_episode_list_survives_the_round_trip(compiler):
    """非空的期号列表**要**搬过去，而且契约层读得到它是列表。"""
    (compiler.DOCS / "ep.md").write_text(
        "---\ntitle: 一期\ndate: '2026-01-01'\ndescription: 一期的描述。\n"
        "episode_sources:\n  - https://a.example/post\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    fields, _ = parse_front_matter(compiler.render(unit))
    assert fields["episode_sources"] == ["https://a.example/post"]


def test_a_multiline_description_survives_as_one_line(compiler):
    """母稿写 ``description: |`` 时，契约层要读得到**整段**。

    契约层的 front matter 解析器是扁平的：只读每个键的**首行**。
    多行标量落盘后它只读到第一行 → 描述被截成半句（跟 ``width`` 无关）。
    """
    (compiler.DOCS / "ep.md").write_text(
        "---\ntitle: 一期\ndate: '2026-01-01'\ndescription: |\n"
        "  第一行描述\n  第二行描述\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    fields, _ = parse_front_matter(compiler.render(unit))
    assert fields["description"] == "第一行描述 第二行描述"


def test_a_full_width_space_inside_a_description_is_kept(compiler):
    """中文稿里的全角空格是排版的一部分——折行不许把它换成半角。

    折行的目的是把多行标量压成**一行**，不是为了改空白字符：
    U+3000（全角空格）被换成 ASCII 空格，字面就变了。
    """
    (compiler.DOCS / "ep.md").write_text(
        "---\ntitle: 一期\ndate: '2026-01-01'\ndescription: 第一行　第二行\n---\n\n正文。\n",
        encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "ep.md")
    fields, _ = parse_front_matter(compiler.render(unit))
    assert fields["description"] == "第一行　第二行"


def test_the_compiler_writes_the_category_ids_next_to_the_category_names(compiler):
    """分类名 → 分类内容单元 id 的映射由编译器算出来写进内容单元。"""
    (compiler.DOCS / "a" / "b").mkdir(parents=True)
    # ⚠️ **两级 `_index.md` 都要有**（裁决 R24）：`read_index_chain` 遇到缺的上级
    # 会抛「目录链断了」（`tools/build-content-units.py:174`）——不是安静地跳过。
    # 而且**每一级只报自己的分类名**：甲来自 `a/_index.md`、乙来自 `a/b/_index.md`，
    # 于是 id 才是 ["a/_index", "a/b/_index"]。
    (compiler.DOCS / "a" / "_index.md").write_text(
        "---\ntitle: 甲\ncascade:\n  categories: [甲]\n---\n\n# 甲\n", encoding="utf-8")
    (compiler.DOCS / "a" / "b" / "_index.md").write_text(
        "---\ntitle: 乙\ncascade:\n  categories: [乙]\n---\n\n# 乙\n", encoding="utf-8")
    # ⚠️ `date` 必须带引号（裁决 R25，同 Task 2 的 R7）：母稿没写日期时编译器
    # 会去问 git，而 `tmp_path` 不是 git 仓库 → 抛「找不到日期」，证不了事。
    (compiler.DOCS / "a" / "b" / "doc.md").write_text(
        "---\ntitle: 一篇\ndate: '2026-01-01'\ndescription: 一篇的描述。\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "a" / "b" / "doc.md")
    assert unit.categories == ["甲", "乙"]
    assert unit.category_ids == ["a/_index", "a/b/_index"]


def test_the_two_category_lists_stay_aligned(compiler):
    """两个列表必须同序同长——错位就会拼出别的分类的地址。

    上级已经报过的分类名**不再重复报**（分类链是去重的），
    所以 id 列表也得跟着去重——否则两个列表会错位
    （分类 2 个、id 3 个）。
    """
    (compiler.DOCS / "a" / "b").mkdir(parents=True)
    (compiler.DOCS / "a" / "_index.md").write_text(
        "---\ntitle: 甲\ncascade:\n  categories: [甲]\n---\n\n# 甲\n", encoding="utf-8")
    (compiler.DOCS / "a" / "b" / "_index.md").write_text(
        "---\ntitle: 乙\ncascade:\n  categories: [甲, 乙]\n---\n\n# 乙\n", encoding="utf-8")
    (compiler.DOCS / "a" / "b" / "doc.md").write_text(
        "---\ntitle: 一篇\ndate: '2026-01-01'\ndescription: 一篇的描述。\n---\n\n正文。\n", encoding="utf-8")
    unit = compiler.build_unit(compiler.DOCS / "a" / "b" / "doc.md")
    assert unit.categories == ["甲", "乙"]
    assert unit.category_ids == ["a/_index", "a/b/_index"]
