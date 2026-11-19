"""期号内容单元与落地 URL 派生。

这一层做两件事：**把「这一期」从母稿里读出来**，**从内容单元 id 派生
落地 URL**。两件事都要验到位，因为断链就出在这儿：

- 字段读不出来 → 期号区块是空的（页面照常渲染，**静默**）；
- URL 派生错了 → 链接指向一个从未存在的路径，而服务器对未知路径返回
  **200 + 首页**（软 404），探活看不出来。

所以本文件分五组测：

1. **URL 派生**（单元）——拼出来的路径长什么样；
2. **content_id 派生**（单元）——母稿怎么对应到内容单元；
3. **字段校验**（单元）——缺一个必填字段就报错，绝不静默补默认值；
4. **系列一致性**（单元）——期号不重复、不跳号；
5. **读母稿与发现**（单元）——期号母稿怎么被读出来、怎么被找到。

被测对象一律是**临时目录里现造的母稿**，不依赖仓库里存着哪几期内容——
内容层清空是常态，测试要活的是「读母稿 / 发现期号」这套逻辑本身。

另外有三条**规格漂移守卫**：规格里写的钩子字数区间与期号字段表必须与
代码里的常量一致，规格里不该再出现嵌套的期号媒体字段。
"""

import re
import sys
from pathlib import Path

import pytest

from publishkit.episode import (
    Episode,
    EpisodeError,
    EpisodeFieldError,
    content_id_for_draft,
    discover_episodes,
    episode_from_fields,
    find_episode,
    landing_url,
    read_episode,
    validate_episode_fields,
    validate_episode_series,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "publish" / "spec" / "08-站点IP骨架.md"


# --- 工具 -------------------------------------------------------------------


def complete_fields(**overrides) -> dict:
    """一份**合规**的期号字段。改一项就能测一项的校验。"""
    fields = {
        "episode": "row-lock",
        "episode_no": "6",
        "series": "内核机制",
        "episode_hook": "MVCC 让读不挡写，但两个写会互相覆盖——行锁在它上面加了一层协调",
        "episode_subtitle": "video/字幕-行锁.md",
        "episode_duration_s": "35.172",
        "episode_license": "PostgreSQL BSD",
    }
    fields.update(overrides)
    return fields


def draft_text(**overrides) -> str:
    """一份**合规**的期号母稿（front matter + 正文）。

    标量字段来自 :func:`complete_fields`——同一套字段、同样的取值，
    只是把它铺成母稿文件的样子。两个列表字段（``episode_sources`` /
    ``episode_repro``）在 :func:`complete_fields` 里没有，这里补上。
    """
    fields = {"title": "带期号数据的一篇"}
    fields.update(complete_fields(**overrides))
    fields.setdefault(
        "episode_sources",
        ["docs/source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/index.md"],
    )
    fields.setdefault("episode_repro", ["make -C video/pipeline out"])
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append("{}:".format(key))
            lines.extend("  - {}".format(item) for item in value)
        else:
            lines.append("{}: {}".format(key, value))
    lines.append("---")
    lines.append("")
    lines.append("正文第一段。")
    lines.append("")
    return "\n".join(lines)


def write_draft(root: Path, rel: str, text: str) -> Path:
    """把一份母稿写进 ``root/docs/`` 底下，返回它的路径。"""
    path = root / "docs" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- 落地 URL 派生（单元） --------------------------------------------------


def test_landing_url_derives_the_permalink():
    assert (
        landing_url("source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive", "2026-10-15")
        == "/2026/10/15/source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/"
    )


def test_landing_url_accepts_a_full_timestamp():
    """内容单元的 date 带时刻（现行编译器 ``tools/build-content-units.py`` 写的就是这个形状）。"""
    assert (
        landing_url("database/x", "2026-10-15 11:30:25")
        == "/2026/10/15/database/x/"
    )


def test_landing_url_quotes_a_non_ascii_content_id():
    """中文路径要百分号编码——和站点实际发出的 URL 形态一致。"""
    assert (
        landing_url("life/aiv/人格规范", "2026-11-11 12:30:58")
        == "/2026/11/11/life/aiv/%E4%BA%BA%E6%A0%BC%E8%A7%84%E8%8C%83/"
    )


def test_landing_url_carries_the_mount_point():
    """镜像站挂在 ``/blog`` 下（``tools/site_root.py`` 的存在理由）。"""
    assert (
        landing_url("database/x", "2026-10-15", root="/blog")
        == "/blog/2026/10/15/database/x/"
    )


def test_landing_url_rejects_an_empty_content_id():
    """content_id 猜不出来时要**响亮地拒绝**，而不是给一条错的 URL。"""
    with pytest.raises(EpisodeFieldError):
        landing_url("", "2026-10-15")


def test_landing_url_rejects_a_malformed_date():
    """坏日期必须指名道姓地报出来，不能漏出裸 ValueError。"""
    with pytest.raises(Exception) as excinfo:
        landing_url("database/x", "不是日期")
    assert "date" in str(excinfo.value)


def test_landing_url_matches_the_site_build_layers_permalink():
    """**兼容性锁**：契约层与站点构建层各自算一遍，结果必须逐字相同。

    契约层不许 import ``tools/site_root.py``（两层之间不互相依赖，
    契约一 §11.1），所以等价性靠**这条测试**钉住——两边各自演进，
    漂了这里就红。

    ``site_root.permalink`` 收的是「日期 + 内容单元路径」，
    ``landing_url`` 收的是「内容单元 id + 日期」，两者参数顺序不同，
    拼出来的字符串必须一样。
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import site_root
    finally:
        sys.path.pop(0)

    cases = [
        ("2026-10-15 11:30:25", "source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive"),
        ("2026-11-11 12:30:58", "life/aiv/人格规范"),
        ("2026-08-24 14:22:40", "source-tracks/postgresql/logical-replication/postgresql-logical-replication-worker-model"),
    ]
    for date, content_id in cases:
        assert landing_url(content_id, date) == site_root.permalink(
            date, content_id, root=""
        ), "契约层与站点构建层算出的落地 URL 不一致：{}".format(content_id)


# --- content_id 派生（单元） ------------------------------------------------


def test_content_id_for_draft_maps_index_md_to_its_own_directory():
    """``docs/<目录>/index.md`` 编译成 ``content/units/<目录>.md``。

    直接拿母稿路径去后缀会得到 ``.../index``——派生的落地 URL 指向一个
    **不存在**的页面。
    """
    assert (
        content_id_for_draft(
            "docs/source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/index.md", "docs"
        )
        == "source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive"
    )


def test_content_id_for_draft_keeps_a_plain_file_as_is():
    assert content_id_for_draft("docs/blog/scheduled.md", "docs") == "blog/scheduled"


def test_content_id_for_draft_rejects_a_category_page():
    """``_index.md`` 是分类页，不是内容单元。"""
    with pytest.raises(EpisodeFieldError):
        content_id_for_draft("docs/database/_index.md", "docs")


def test_content_id_for_draft_rejects_a_file_outside_the_root():
    with pytest.raises(Exception):
        content_id_for_draft("elsewhere/x.md", "docs")


# --- 字段校验（单元） ------------------------------------------------------


def test_validate_episode_fields_accepts_a_complete_episode():
    assert validate_episode_fields(complete_fields()) == []


def test_validate_episode_fields_accepts_a_plain_article():
    """没有 ``episode`` 键的普通文章不进期号线，也不该报错。"""
    assert validate_episode_fields({"title": "x", "platforms": ["wechat"]}) == []


def test_validate_episode_fields_rejects_a_bad_slug():
    violations = validate_episode_fields(complete_fields(episode="Row Lock"))

    assert any("episode" in v for v in violations)


def test_validate_episode_fields_rejects_a_slug_with_a_trailing_dash():
    violations = validate_episode_fields(complete_fields(episode="row-lock-"))

    assert any("episode" in v for v in violations)


def test_validate_episode_fields_requires_episode_no():
    fields = complete_fields()
    del fields["episode_no"]

    violations = validate_episode_fields(fields)

    assert any("episode_no" in v for v in violations)


def test_validate_episode_fields_rejects_a_non_integer_episode_no():
    violations = validate_episode_fields(complete_fields(episode_no="第六期"))

    assert any("episode_no" in v for v in violations)


def test_validate_episode_fields_rejects_episode_no_below_one():
    violations = validate_episode_fields(complete_fields(episode_no="0"))

    assert any("episode_no" in v for v in violations)


def test_validate_episode_fields_requires_a_hook():
    fields = complete_fields()
    del fields["episode_hook"]

    violations = validate_episode_fields(fields)

    assert any("episode_hook" in v for v in violations)


def test_validate_episode_fields_accepts_the_longest_real_hook():
    """**存量达标线**：六期实测最长的钩子是 61 字（EP04 并行解码）。

    上界取 65 就是为了让它过关——上界卡在 60 会把这一期判红，而它
    明明是仓库里真实在用的钩子。
    """
    assert validate_episode_fields(complete_fields(episode_hook="字" * 61)) == []


def test_validate_episode_fields_rejects_a_hook_over_the_limit():
    violations = validate_episode_fields(complete_fields(episode_hook="字" * 66))

    assert any("episode_hook" in v for v in violations)


def test_validate_episode_fields_rejects_a_hook_under_the_limit():
    violations = validate_episode_fields(complete_fields(episode_hook="字" * 19))

    assert any("episode_hook" in v for v in violations)


def test_validate_episode_fields_requires_a_duration():
    fields = complete_fields()
    del fields["episode_duration_s"]

    violations = validate_episode_fields(fields)

    assert any("episode_duration_s" in v for v in violations)


def test_validate_episode_fields_rejects_a_non_positive_duration():
    violations = validate_episode_fields(complete_fields(episode_duration_s="0"))

    assert any("episode_duration_s" in v for v in violations)


def test_validate_episode_fields_requires_a_license():
    """出处与许可证必填：母稿页比视频更容易越界（规格 §6.5）。"""
    fields = complete_fields()
    del fields["episode_license"]

    violations = validate_episode_fields(fields)

    assert any("episode_license" in v for v in violations)


def test_validate_episode_fields_rejects_a_non_string_list():
    violations = validate_episode_fields(complete_fields(episode_sources="不是列表"))

    assert any("episode_sources" in v for v in violations)


def test_validate_episode_fields_rejects_an_empty_list_item():
    violations = validate_episode_fields(complete_fields(episode_repro=["  "]))

    assert any("episode_repro" in v for v in violations)


def test_episode_from_fields_raises_on_a_violation():
    with pytest.raises(EpisodeFieldError):
        episode_from_fields(complete_fields(episode="Bad Slug"))


def test_episode_from_fields_keeps_the_values():
    episode = episode_from_fields(
        complete_fields(episode_sources=["a.c"], episode_repro=["make"])
    )

    assert isinstance(episode, Episode)
    assert episode.episode == "row-lock"
    assert episode.episode_no == 6
    assert episode.series == "内核机制"
    assert episode.episode_sources == ("a.c",)
    assert episode.episode_repro == ("make",)
    assert episode.episode_duration_s == 35.172
    assert episode.is_episode is True


# --- 系列一致性（单元） ----------------------------------------------------


def _episode(number, series="内核机制"):
    return episode_from_fields(complete_fields(episode_no=str(number), series=series))


def test_validate_episode_series_accepts_a_consecutive_series():
    episodes = [_episode(1), _episode(2), _episode(3)]

    assert validate_episode_series(episodes) == []


def test_validate_episode_series_rejects_duplicate_numbers():
    episodes = [_episode(1), _episode(1)]

    violations = validate_episode_series(episodes)

    assert any("重复" in v for v in violations)


def test_validate_episode_series_rejects_a_gap():
    """跳号意味着有一期没落地——观众是按期号往前数的。"""
    episodes = [_episode(1), _episode(3)]

    violations = validate_episode_series(episodes)

    assert any("不连续" in v for v in violations)


def test_validate_episode_series_ignores_articles_without_a_series():
    """没有 ``series`` 的文章不进系列一致性检查。"""
    fields = complete_fields()
    del fields["series"]
    episodes = [episode_from_fields(fields)]

    assert validate_episode_series(episodes) == []


# --- 读母稿 ----------------------------------------------------------------


def test_reading_a_draft_leaves_the_date_empty(tmp_path):
    """母稿的 ``date:`` 不是站点的日期。

    站点构建链编译时把母稿的 ``date:`` 覆盖成 git 里最早的
    一次提交时间——站点 permalink 用的是那个值。

    所以读母稿时 ``date`` 留空：宁可让落地 URL 算不出来，也不能算出
    一个指向另一天的地址。
    """
    draft = write_draft(
        tmp_path,
        "source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/index.md",
        draft_text(),
    )

    episode = read_episode(draft, drafts_root=tmp_path / "docs")

    assert episode.content_id == "source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive"
    assert episode.date is None


def test_reading_a_draft_refuses_to_invent_a_landing_url(tmp_path):
    draft = write_draft(
        tmp_path,
        "source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/index.md",
        draft_text(),
    )

    episode = read_episode(draft, drafts_root=tmp_path / "docs")

    with pytest.raises(EpisodeFieldError):
        episode.landing_url()


def test_reading_a_missing_draft_says_so(tmp_path):
    with pytest.raises(EpisodeError):
        read_episode(tmp_path / "docs/does-not-exist.md")


def test_discover_episodes_finds_nothing_in_a_tree_without_episodes(tmp_path):
    """没有 ``episode`` 键的母稿不进期号线。"""
    write_draft(tmp_path, "blog/plain.md", "---\ntitle: x\n---\n\n正文\n")

    assert discover_episodes(tmp_path / "docs") == ()


def test_find_episode_returns_none_when_nothing_matches(tmp_path):
    write_draft(tmp_path, "blog/plain.md", "---\ntitle: x\n---\n\n正文\n")

    assert find_episode(tmp_path / "docs", "row-lock") is None


def test_find_episode_rejects_two_drafts_claiming_the_same_slug(tmp_path):
    """两个母稿声明同一个 slug 是**身份冲突**，不是「取一个」。"""
    body = draft_text()
    write_draft(tmp_path, "blog/one.md", body)
    write_draft(tmp_path, "blog/two.md", body)

    with pytest.raises(EpisodeFieldError):
        find_episode(tmp_path / "docs", "row-lock")


# --- 规格漂移守卫 ----------------------------------------------------------


def _spec_section(title: str) -> str:
    """规格里某一节的正文（到下一个同级标题为止）。"""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index(title)
    rest = text[start + len(title):]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[:end]


def test_the_spec_hook_range_matches_the_code():
    """规格 §4.3 里写的钩子字数区间 == 代码里的常量。

    规格是**独立手写的事实源**，代码向它对齐。两边各写各的、靠这条
    守卫钉住——比从代码 import 常量当阈值强（那是自证）。
    """
    from publishkit import episode as episode_module

    section = _spec_section("### 4.3 front matter 字段表")
    match = re.search(r"`episode_hook`\s*\|\s*str\s*\|[^|]*\|\s*(\d+)~(\d+)\s*字", section)

    assert match, "规格 §4.3 里找不到 episode_hook 的字数区间"

    assert int(match.group(1)) == episode_module._HOOK_MIN_CHARS
    assert int(match.group(2)) == episode_module._HOOK_MAX_CHARS


def test_the_spec_field_table_matches_the_code():
    """规格 §4.3 的字段表 == 代码里的两个常量。

    **双向**：规格少一个字段要红，规格多一个字段也要红。
    """
    from publishkit import episode as episode_module

    section = _spec_section("### 4.3 front matter 字段表")
    table_rows = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.MULTILINE)

    assert sorted(table_rows) == sorted(
        episode_module.EPISODE_SCALAR_FIELDS + episode_module.EPISODE_LIST_FIELDS
    ), "规格 §4.3 的期号字段表与代码常量不一致"


def test_the_spec_does_not_sell_a_nested_episode_media_anymore():
    """规格里不该再出现 ``episode_media``。

    嵌套的键会被两道白名单**静默丢掉**：页面照常渲染，只是期号区块
    是空的。规格与实现各留一份「嵌套版」，下一个人照着写就踩坑。
    """
    assert "episode_media" not in SPEC.read_text(encoding="utf-8")
