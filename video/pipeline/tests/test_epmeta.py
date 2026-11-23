"""发布元数据的校验：缺一个字段就报错，不静默补默认值。

两条不同的语义必须分开测：

1. **平台整段缺失** = 这一期不发这个平台，合法，跳过。
2. **平台段内缺字段** = 想发但没填全，是配置错误，报错。

混为一谈的后果是：要么逼作者填一堆用不上的字段，
要么让「配了但配漏了」悄悄溜过去。
"""
import copy
import json

import pytest

from pyv import epmeta


def _write(tmp_path, payload):
    """造一期的目录，把发布元数据写进去。

    **`root` 就是期目录本身**（`epmeta.meta_path` 的新语义）：
    元数据落在 `期目录/publish.json`，不再是一堆平铺的 `<期号>.json`。
    """
    root = tmp_path / "episode"
    root.mkdir(parents=True, exist_ok=True)
    path = root / epmeta.PUBLISH_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return root


BASE = {
    "episode": "ep01",
    "title": "标题",
    "cover_at": 3.0,
    # 平台段落在 `platforms` 下面——平台是动态的，顶层摊开的话
    # 「哪些键是平台」这件事就又变成写死的清单了。
    "platforms": {
        "channels": {
            "title": "短标题", "description": "简介", "topics": ["数据库"],
        },
        "bilibili": {
            "title": "标题",
            "description": "简介",
            "tags": ["数据库"],
            "tid": 231,
            "copyright": 1,
            "no_reprint": 1,
        },
    },
}


def _meta(tmp_path, **overrides):
    payload = copy.deepcopy(BASE)
    payload.update(overrides)
    root = _write(tmp_path, payload)
    return epmeta.load_meta("ep01", root=root)


def _errors(findings):
    return [f for f in findings if f.level == epmeta.ERROR]


def test_a_complete_meta_has_no_errors(tmp_path):
    assert _errors(epmeta.check_meta(_meta(tmp_path))) == []


def test_episode_must_match_the_contract(tmp_path):
    findings = _errors(
        epmeta.check_meta(_meta(tmp_path), contract_episode="ep02"))
    assert any(f.rule_id == "epmeta.episode" for f in findings)


def test_missing_title_is_an_error(tmp_path):
    meta = _meta(tmp_path)
    broken = epmeta.EpisodeMeta(episode=meta.episode, title="", cover_at=meta.cover_at)
    assert any(f.rule_id == "epmeta.required"
               for f in _errors(epmeta.check_meta(broken)))


def test_cover_at_beyond_the_duration_is_an_error(tmp_path):
    findings = _errors(
        epmeta.check_meta(_meta(tmp_path, cover_at=30.0), duration=10.0))
    assert any(f.rule_id == "epmeta.cover-at" for f in findings)


def test_cover_at_exactly_at_the_duration_is_allowed(tmp_path):
    """规格说 cover_at ≤ 成片时长——正好落在片尾是合法的，不是越界。"""
    findings = _errors(
        epmeta.check_meta(_meta(tmp_path, cover_at=10.0), duration=10.0))
    assert [f for f in findings if f.rule_id == "epmeta.cover-at"] == []


def test_a_missing_platform_section_is_only_a_warning(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"].pop("channels")
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = epmeta.check_meta(meta)
    warnings = [f for f in findings if f.level == epmeta.WARNING]
    assert any(f.rule_id == "epmeta.platform-missing" for f in warnings)
    assert _errors(findings) == []


def test_a_missing_field_inside_a_platform_section_is_an_error(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["channels"] = {"title": "短标题", "topics": ["数据库"]}
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.platform-required" for f in findings)


def test_a_title_over_the_limit_is_an_error_and_is_not_truncated(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["channels"] = {
        "title": "字" * 23, "description": "简介", "topics": ["数据库"],
    }
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.text-limit" for f in findings)
    # 不截断：原文一字不动
    assert meta.platform("channels")["title"] == "字" * 23


def test_too_many_topics_is_an_error(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["channels"] = {
        "title": "短标题", "description": "简介",
        "topics": ["一", "二", "三", "四", "五", "六"],
    }
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_a_non_integer_tid_is_an_error(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(BASE["platforms"]["bilibili"], tid="二百三十一")
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.int-field" for f in findings)


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(epmeta.MetaError):
        epmeta.load_meta("ep99", root=tmp_path)


# --- 列表限额：各平台的总限额口径不一样 ------------------------------------


def test_too_many_tags_is_an_error(tmp_path):
    """B站的 `tags_chars` 是**逗号分隔后的总字符数**，不是标签个数。

    规格 §4.3：「英文逗号分隔后总长 < 200 字」。当成个数上限就放过了
    「199 个 1 字标签」这种真实超限的情况。
    """
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(
        BASE["platforms"]["bilibili"],
        tags=["x" * 20] * 11,   # 11 项，单项没超 20 字，但总长 219 > 199
    )
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_a_long_joined_tag_string_is_an_error_even_with_few_tags(tmp_path):
    """标签少但总长超限也要报错——这正是「当成个数上限」漏掉的那一类。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(
        BASE["platforms"]["bilibili"],
        tags=["a" * 20, "b" * 20, "c" * 20, "d" * 20, "e" * 20,
              "f" * 20, "g" * 20, "h" * 20, "i" * 20, "j" * 20],
    )
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_the_joined_length_counts_the_separators(tmp_path):
    """分隔用的逗号也算进总长——平台收到的是拼好的那一串。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(
        BASE["platforms"]["bilibili"], tags=["a" * 20] * 10,
    )
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    # 10 项 × 20 字 + 9 个逗号 = 209 > 199
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_topics_still_use_the_count_limit(tmp_path):
    """视频号的话题上限是**个数**（5 个），口径不能跟着 B站一起改。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["channels"] = {
        "title": "短标题", "description": "简介",
        "topics": ["一", "二", "三", "四", "五", "六"],
    }
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


# --- 抖音：文案三段拼一个 text ----------------------------------------------
#
# 抖音**没有独立的 description 字段**：标题、正文、话题全塞在一个 `text` 里
# （规格 §6.6.3）。这里查各段自己的上限；拼装后的**总长**由 adapter 查
# （`text_chars`，平台写明的硬上限）——epmeta 逐字段查不出「三段加起来超了」。


def _douyin_meta(tmp_path, **overrides):
    payload = copy.deepcopy(BASE)
    section = {"title": "钩子", "description": "正文", "topics": ["数据库"]}
    section.update(overrides)
    payload["platforms"]["douyin"] = section
    root = _write(tmp_path, payload)
    return epmeta.load_meta("ep01", root=root)


def test_a_missing_field_inside_the_douyin_section_is_an_error(tmp_path):
    """配了抖音但没填全 = 配置错误，不是「这一期不发抖音」。

    这两种情况必须分开：整个段缺失只是 warning（合法的「不发」），
    段内缺字段是 error（作者忘了填）。
    """
    meta = _douyin_meta(tmp_path)
    meta.platforms["douyin"].pop("topics")
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.platform-required" for f in findings)


def test_a_douyin_title_over_the_limit_is_an_error(tmp_path):
    meta = _douyin_meta(tmp_path, title="字" * 56)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.text-limit" for f in findings)


def test_a_douyin_description_over_the_limit_is_an_error(tmp_path):
    meta = _douyin_meta(tmp_path, description="字" * 501)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.text-limit" for f in findings)


def test_too_many_douyin_topics_is_an_error(tmp_path):
    """抖音的话题上限是**个数**（5 个）——与视频号同口径，但出处不同。"""
    meta = _douyin_meta(tmp_path, topics=["一", "二", "三", "四", "五", "六"])
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_a_long_douyin_topic_is_an_error(tmp_path):
    """单个话题超长也要拦——个数没超不代表没超长。"""
    meta = _douyin_meta(tmp_path, topics=["x" * 16])
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.list-limit" for f in findings)


def test_a_douyin_section_is_never_required_to_exist(tmp_path):
    """整个抖音段缺失只是 warning——「这一期不发抖音」是合法的。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"].pop("douyin", None)
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = epmeta.check_meta(meta)
    warnings = [f for f in findings if f.level == epmeta.WARNING]
    assert any(f.rule_id == "epmeta.platform-missing" for f in warnings)
    assert _errors(findings) == []


# --- 入库的真实元数据 ------------------------------------------------------
#
# 元数据跟着期走：`video/episodes/<期路径>/publish.json`。


def test_every_stored_episode_passes_the_meta_check():
    """期目录里的 `publish.json` 是**入库的事实**——坏了要在测试里红。

    不是等到出包那天才发现某一期的文案超了限额。
    """
    for slug in epmeta.published_episodes():
        meta = epmeta.load_meta(slug)
        errors = _errors(epmeta.check_meta(meta))
        assert errors == [], (
            f"{slug} 有校验错误：" + "；".join(str(f) for f in errors)
        )


def test_every_stored_episode_carries_a_douyin_section():
    """发了抖音的期都得有抖音文案段。

    「某一期不发抖音」是合法状态，但那是**在事实里记下来的**——
    要跳过某一期，就改这一处并说明，别让「忘了写」混过去。
    """
    for slug in epmeta.published_episodes():
        meta = epmeta.load_meta(slug)
        assert meta.platform("douyin") is not None, (
            f"{slug} 没有 douyin 段——这一期不发抖音的话，在这里明确排除它"
        )


def test_published_episodes_are_found_by_their_publish_json(tmp_path, monkeypatch):
    """有发布元数据的期，就是期目录里放着 `publish.json` 的那些期。"""
    root = tmp_path / "episodes"
    root.mkdir()
    for ep, published in (("系列甲/合集甲/文档乙/short", True),
                          ("系列甲/合集甲/文档甲/mid", True),
                          ("系列甲/合集甲/文档丙/full", False)):
        directory = root / ep
        directory.mkdir(parents=True)
        if published:
            (directory / epmeta.PUBLISH_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(epmeta, "EPISODES_DIR", root)
    assert epmeta.published_episodes() == [
        "系列甲/合集甲/文档乙/short",
        "系列甲/合集甲/文档甲/mid",
    ]


def test_meta_path_points_into_the_episode_dir(tmp_path):
    """默认位置是期目录里的 `publish.json`；给了 root 就是那个目录本身。"""
    ep = "系列甲/合集甲/文档甲/short"
    assert epmeta.meta_path(ep).name == epmeta.PUBLISH_NAME
    assert epmeta.meta_path(ep).parent.name == "short"
    assert epmeta.meta_path(ep).parent.parent.name == "文档甲"
    assert epmeta.meta_path(ep, root=tmp_path) == \
        tmp_path / epmeta.PUBLISH_NAME


# --- 整数字段的取值域 ------------------------------------------------------


def test_an_out_of_domain_copyright_is_an_error(tmp_path):
    """copyright 只认 1（原创）与 2（转载）。3 是平台会拒的值。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(BASE["platforms"]["bilibili"], copyright=3)
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.int-domain" for f in findings)


def test_an_out_of_domain_no_reprint_is_an_error(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(BASE["platforms"]["bilibili"], no_reprint=2)
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.int-domain" for f in findings)


def test_a_reprint_without_a_source_is_an_error(tmp_path):
    """转载必须给 source——平台会拒没有来源的转载（规格 §4.3）。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(BASE["platforms"]["bilibili"], copyright=2, no_reprint=0)
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.conditional-required" for f in findings)


def test_a_reprint_with_a_source_is_fine(tmp_path):
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(
        BASE["platforms"]["bilibili"], copyright=2, no_reprint=0, source="https://example.com/x")
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    assert _errors(epmeta.check_meta(meta)) == []


def test_an_original_needs_no_source(tmp_path):
    """原创（copyright = 1）不要求 source——那是转载才要的字段。"""
    root = _write(tmp_path, BASE)
    meta = epmeta.load_meta("ep01", root=root)
    assert _errors(epmeta.check_meta(meta)) == []


# --- 元数据本身坏了 --------------------------------------------------------


def test_a_non_numeric_cover_at_raises_a_meta_error(tmp_path):
    """`float("x")` 抛的裸 ValueError 会被 CLI 漏成 traceback。"""
    payload = copy.deepcopy(BASE)
    payload["cover_at"] = "第十八秒"
    root = _write(tmp_path, payload)
    with pytest.raises(epmeta.MetaError):
        epmeta.load_meta("ep01", root=root)


def test_broken_json_raises_a_meta_error(tmp_path):
    root = tmp_path / "episode"
    root.mkdir(parents=True, exist_ok=True)
    (root / epmeta.PUBLISH_NAME).write_text("{不是 JSON", encoding="utf-8")
    with pytest.raises(epmeta.MetaError):
        epmeta.load_meta("ep01", root=root)


# --- 退出码声明（[exit]）---------------------------------------------------


def test_the_exit_codes_come_from_the_platform_declaration():
    """退出码从能力声明的 `[exit]` 段读——语义由契约层定死。

    三个视频 adapter 的退出码都走这一个读取器，所以这一条就把它们的
    出处钉住了：改 TOML 就改退出码，不改 Python。
    """
    for platform in ("douyin", "bilibili", "channels"):
        codes = epmeta.load_exit_codes(platform)
        assert codes == {"ok": 0, "usage": 1, "precondition": 2, "failed": 3}


def test_a_missing_exit_section_is_refused_loudly(tmp_path):
    """声明里没有 `[exit]` 段——adapter 的退出码就没有答案，当场报错。"""
    directory = tmp_path / "douyin"
    directory.mkdir()
    (directory / "capability.toml").write_text(
        'id = "douyin"\nname = "抖音"\nkind = "video"\n', encoding="utf-8")

    with pytest.raises(epmeta.MetaError):
        epmeta.load_exit_codes("douyin", platforms_dir=tmp_path)


def test_an_exit_section_with_a_missing_key_is_refused_loudly(tmp_path):
    """四行少一行都不行——「这一档退几」不能只对一半。"""
    directory = tmp_path / "douyin"
    directory.mkdir()
    (directory / "capability.toml").write_text(
        'id = "douyin"\n[exit]\nok = 0\nusage = 1\nfailed = 3\n', encoding="utf-8")

    with pytest.raises(epmeta.MetaError):
        epmeta.load_exit_codes("douyin", platforms_dir=tmp_path)


def test_a_broken_exit_section_is_refused_loudly(tmp_path):
    """写坏的声明当场报错——**三个 reader 在这一点上必须一样**。

    头条与公众号那两个 reader 都拒「多出来的键」与「不是整数的值」；
    视频线这个 reader 原来两样都不拒，于是 ``ok = "0"`` 会让退出码变成
    **字符串**——同一件事在三个平台上表现不同。

    报错信息里要带上是哪个键。
    """
    directory = tmp_path / "douyin"
    directory.mkdir()

    # 1. `[exit]` 段里出现了四个词之外的键。
    (directory / "capability.toml").write_text(
        'id = "douyin"\n[exit]\nok = 0\nusage = 1\nprecondition = 2\n'
        'failed = 3\nbogus = 9\n', encoding="utf-8")
    with pytest.raises(epmeta.MetaError) as unknown:
        epmeta.load_exit_codes("douyin", platforms_dir=tmp_path)
    assert "bogus" in str(unknown.value)

    # 2. 值不是整数（字符串、布尔值都不行）。
    (directory / "capability.toml").write_text(
        'id = "douyin"\n[exit]\nok = "0"\nusage = 1\nprecondition = 2\n'
        'failed = 3\n', encoding="utf-8")
    with pytest.raises(epmeta.MetaError) as not_int:
        epmeta.load_exit_codes("douyin", platforms_dir=tmp_path)
    assert "ok" in str(not_int.value)

    (directory / "capability.toml").write_text(
        'id = "douyin"\n[exit]\nok = true\nusage = 1\nprecondition = 2\n'
        'failed = 3\n', encoding="utf-8")
    with pytest.raises(epmeta.MetaError) as boolean:
        epmeta.load_exit_codes("douyin", platforms_dir=tmp_path)
    assert "ok" in str(boolean.value)


# --- 平台清单是扫出来的，不写死 ----------------------------------------------
#
# 这一层**不认识任何平台名**。平台要什么字段、限额键叫什么，
# 写在平台自己的目录里（`platforms/<plat>/publish-spec.json`），
# 这一层只负责**读它、按它查**。
#
# 写死平台名的后果很具体：加一个平台要改视频线（上游），
# 而「加平台只动 `platforms/`」这条规矩对视频平台就不成立——
# 那条规矩是整个平台层的地基。


def test_specs_are_discovered_from_the_platforms_directory():
    specs = epmeta.load_specs()
    assert set(specs) >= {"channels", "bilibili", "douyin"}
    assert "required" in specs["bilibili"]


def test_every_video_platform_carries_a_publish_spec():
    """每个吃视频的平台都要有一份发布规格。

    少一份的代价很具体：那一期的文案**根本没人查**——
    字段缺了、字数超了，检查器一声不吭，平台当场拒稿。
    """
    import tomllib

    base = epmeta.PLATFORMS_DIR
    video_platforms = set()
    for path in sorted(base.glob("*/capability.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") == "video":
            video_platforms.add(path.parent.name)
    assert video_platforms, "仓库里一个吃视频的平台都没有了？"
    assert video_platforms <= set(epmeta.load_specs())


def test_the_meta_assembles_platform_sections_dynamically(tmp_path):
    meta = epmeta.load_meta("ep01", root=_write(tmp_path, BASE))
    assert set(meta.platforms) == {"channels", "bilibili"}
    assert meta.platform("douyin") is None


def test_a_platform_without_a_publish_spec_is_refused_loudly(tmp_path):
    """配了文案却没有发布规格的平台，当场报错。

    不报错的后果是「配了但没人查」——检查器跳过它，
    平台拒稿的时候我们还不知道自己漏了什么。
    """
    payload = copy.deepcopy(BASE)
    payload["platforms"]["nosuchplat"] = {"title": "标题"}
    root = _write(tmp_path, payload)
    with pytest.raises(epmeta.MetaError) as excinfo:
        epmeta.load_meta("ep01", root=root)
    assert "nosuchplat" in str(excinfo.value)


def test_the_conditional_required_rule_survives_the_json_round_trip(tmp_path):
    """`required_when` 的键是整数，但 JSON 的键只能是字符串。

    规格里写 `{"copyright": {"2": ["source"]}}`——不把 `"2"` 还原成 `2`，
    条件必填就永远不触发：转载没给来源地址，平台当场拒稿，
    而我们的检查器一声不吭。**这道题是这一节存在的理由。**
    """
    payload = copy.deepcopy(BASE)
    payload["platforms"]["bilibili"] = dict(
        BASE["platforms"]["bilibili"], copyright=2, no_reprint=0)
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("ep01", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.conditional-required" for f in findings)


# --- 档位 ------------------------------------------------------------------
#
# **档位是期目录的最后一段**（`video/episodes/<系列>/<合集>/<文档>/<档位>/`），
# 所以档位不用另外登记——路径说了就是。
#
# 平台收哪几档，写在它自己的 `capability.toml` 里。


def test_the_tier_comes_from_the_episode_path(tmp_path):
    root = _write(tmp_path, BASE)
    meta = epmeta.load_meta("系列甲/合集甲/文档甲/mid", root=root)
    assert meta.tier == "mid"


def test_an_unrecognisable_tier_stays_empty(tmp_path):
    """认不出来的档位就是空串——查不了就不判，不猜一个。"""
    root = _write(tmp_path, BASE)
    meta = epmeta.load_meta("ep01", root=root)
    assert meta.tier == ""


def test_a_platform_outside_its_tiers_is_rejected(tmp_path):
    """抖音只收 short 档——给它发 mid 必须报红。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["douyin"] = {
        "title": "钩子", "description": "正文", "topics": ["数据库"]}
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("系列甲/合集甲/文档甲/mid", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert any(f.rule_id == "epmeta.tier-not-allowed" and "douyin" in f.message
               for f in findings)


def test_a_platform_inside_its_tiers_is_accepted(tmp_path):
    """short 档抖音收——合法，就不该有档位 finding。"""
    payload = copy.deepcopy(BASE)
    payload["platforms"]["douyin"] = {
        "title": "钩子", "description": "正文", "topics": ["数据库"]}
    root = _write(tmp_path, payload)
    meta = epmeta.load_meta("系列甲/合集甲/文档甲/short", root=root)
    findings = _errors(epmeta.check_meta(meta))
    assert [f for f in findings if f.rule_id == "epmeta.tier-not-allowed"] == []


def test_the_tiers_come_from_the_platform_declaration():
    """档位清单的出处是平台自己的能力声明，不在这里写死。"""
    assert epmeta.load_tiers("bilibili") == ("short", "mid", "full")
    assert epmeta.load_tiers("douyin") == ("short",)
    assert epmeta.load_tiers("channels") == ("short",)


def test_a_platform_without_declared_tiers_is_not_judged(tmp_path):
    """没声明档位的平台查不了——不判，也不当成「全都收」。"""
    directory = tmp_path / "someplat"
    directory.mkdir()
    (directory / "capability.toml").write_text(
        'id = "someplat"\nkind = "video"\n', encoding="utf-8")
    assert epmeta.load_tiers("someplat", platforms_dir=tmp_path) == ()
