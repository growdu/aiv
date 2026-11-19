"""期号内容单元：这一期是什么，落在哪儿。

母稿（``docs/`` 下的 md）是唯一真相（``publish/spec/00-架构设计.md`` §三
不变量一）。期号是母稿的一个**属性**——不是另一篇文章，也不是另一个站点。
这一层只做两件事：

1. 把「这一期」的字段从母稿 front matter 里读出来并校验；
2. 从内容单元 id **派生**落地 URL。

两个 id，一件事
---------------
一篇期号文章身上有**两个** id，它们各管一头：

============================  =========================================
``content_id``                博客侧的内容单元 id = 相对 ``content/units/``
                              的路径去后缀（``database/postgresql-row-lock-
                              deep-dive``）。**落地 URL 由它派生。**
``episode``                   AIV 侧的期号 slug（``row-lock``）。它是契约、
                              旁白、时间轴、片段目录、成片文件名的共同主键
                              （契约六 §4.1），也是**跨平台索引的连接键**。
============================  =========================================

它们靠母稿 front matter 里的 ``episode:`` 字段连在一起。发布侧不需要再造
一套编号，站点侧也不需要。

为什么落地 URL 必须派生、不能手写
----------------------------------
2026-11-14 实测（历史实测，量的是**某一期**上的东西）：当时那几期的
``video/publish/<EP>.json`` 里，**多数期**的 ``url`` 指向站上的一条**非期号页**
路径（``https://<站点地址>/<该篇地址>``），那个路径返回
**200 + 首页正文**（服务端对任何未知路径软 404 回首页）；剩下**一期**指向
一篇母稿，而不是期号页。

手写常量有三条必然失效的路径：slug 改了忘了改、母稿换了路径忘了改、
期号页还没生成就先把链接发出去了。**第三条已经发生。**

所以 ``url`` 从 manifest 里删掉，改为从 ``content_id`` 派生。

字段为什么全是扁平的
--------------------
front matter 的格式规则（契约一 §4.2）只允许扁平的 ``key: value`` 与单层的
``key:`` + ``  - item`` 列表，嵌套仅 ``cascade:`` 允许。两道透传白名单
（``tools/build-content-units.py`` 的 ``EPISODE_FIELDS`` 与本层的
``PASSTHROUGH_FIELDS``）都是按**扁平的键名**认字段的。

所以期号字段是一组扁平键，**没有** ``episode_media:`` 这种嵌套结构——
嵌套字典在契约层的 front matter 解析器里读不出来（``episode_media:`` 会变成
一个空列表，嵌套的键被拍平到顶层）：页面照常渲染，只是期号区块是空的。
这正是「展示元数据通道是断的」那种故障（契约一 §2.2）的翻版。

> ✅ **现状（2026-11-19）**：编译器那份白名单（``tools/build-content-units.py``
> 的 ``EPISODE_FIELDS``）**含** ``episode:*``——期号字段现在**过得去了**，
> 编译器把这 9 个字段搬进内容单元，不再被静默丢掉。搬的时候有两处加工：
> **空值不搬**（空列表 / 空值落盘后契约层读不成），
> **多行标量压成一行**（契约层的解析器只读每个键的首行）。
> **但嵌套结构仍然过不去**：白名单里的字段写成字典，编译器会照搬，
> 落盘成嵌套 YAML，契约层读不成；白名单外的字段（比如 ``episode_media:``）
> 编译器不搬。那是**另一条**路，不在这次修复的范围里。

「在哪看」为什么不进 front matter
---------------------------------
9 个字段只回答「**这一期是什么**」：身份（期号 / 系列）、内容事实
（钩子 / 字幕 / 时长 / 许可证）、可追溯性（源码路径 / 复现命令）。

「**在哪看**」（平台链接）是**发布动作的产物**：发布流程把链接写进
``platforms/<平台>/outbox/<EP>__<平台>.json`` 的 ``published_url``。

它不进 front matter，理由与 §五.2「落地 URL 必须派生」同源：

- 母稿是**内容真相**（不变量一）。把发布产物抄进母稿，就是新造一类
  **手写常量**——而手写常量正是 §5.1 刚消灭掉的东西；
- 平台重发会换链接。两处都写必然漂：母稿里的旧链接指向已失效的地址，
  而且**没人会发现**，因为页面照常渲染。

期号页的「在 B站看」按钮原由构建期汇总的
``platforms/blog/site/source/_data/podcast_index.json``
提供（commit 6 落地），它读的是 outbox 快照。
⚠️ 2026-11-18 的站点重做撤掉了整条 Hexo 链路，``source/_data/`` 已经不存在，
期号页的平台链接**现在还没有数据源**。

为什么不需要一条「兼容性锁」
---------------------------
站点的 URL 形状与这里的落地地址读的是**同一份共享规则**——仓库根的
``rules/urls.json``（契约层的读取器是 ``publish/publishkit/urls.py``，
站点的是 ``urls.ts``）。规则是**数据**不是代码，两层之间不互相 import
（契约一 §11.1 的接缝原则），接缝是那份文件。

既然是同一份规则，就不必再靠一条测试盯住两边不漂移：改规则就一起改。
（Hexo 时代那条锁盯的是 ``tools/site_root.py`` 拼出来的字符串——那个
模块已经退役。）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path

from . import PublishKitError
from . import urls
from .contract import (
    EPISODE_LIST_FIELDS,
    EPISODE_SCALAR_FIELDS,
)
from .schedule import content_id_for

__all__ = [
    # 从 contract.py 转出——常量住在最底层那一层，这里只做转出，
    # 调用方只认一个名字。
    "EPISODE_LIST_FIELDS",
    "EPISODE_SCALAR_FIELDS",
    "EPISODE_SLUG_RE",
    "Episode",
    "EpisodeError",
    "EpisodeFieldError",
    "EpisodeFileError",
    "content_id_for_draft",
    "discover_episodes",
    "episode_from_fields",
    "find_episode",
    "landing_url",
    "read_episode",
    "validate_episode_fields",
    "validate_episode_series",
]


#: 期号 slug 的形状。
#:
#: 契约六 §4.1 规定内容单元 id = 期号 slug；那个 slug 已经贯穿契约、旁白、
#: 时间轴、片段目录与成片文件名，所以这里不另造编号。
EPISODE_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

#: 一句话钩子的字数区间。
#:
#: **下界 20 是内容质量线**，不是存量达标线：低于 20 字装不下
#: 「这一期讲什么 + 反常识在哪」两件事，而《人格规范》§5.4 要求钩子
#: 给出机制而不是结论。
#:
#: **上界 65 来自真实分布**：2026-11-14 实测六期口播稿的主钩子为
#: 34 / 35 / 38 / 39 / 46 / **61** 字（``video/字幕-*.md`` 的「主钩子」行）。
#: 取 65 = 存量最大值 61 再留 4 字余量，六期**全部达标**；再长就折成
#: 三行以上，期号头会被撑高，读者只看到前半句。
#:
#: 这个区间是**规格 §4.3 的独立事实源**——``publish/tests/test_episode.py``
#: 里有一条漂移守卫断言「规格里写的 20~65 == 代码里的常量」，
#: 改了一边不改另一边会红。
_HOOK_MIN_CHARS = 20
_HOOK_MAX_CHARS = 65

#: 期号的最小编号。
_EPISODE_NO_MIN = 1

_INT_RE = re.compile(r"^[0-9]+$")
_FLOAT_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")

#: 「没有传 date」的哨兵。``None`` 是一个**有意义的**取值（母稿读的场合，
#: 这一期就是没有可用日期），所以不能拿它当默认值。
_UNSET = object()


class EpisodeError(PublishKitError):
    """Base class for episode errors."""


class EpisodeFieldError(EpisodeError):
    """The episode front matter violates the contract."""


class EpisodeFileError(EpisodeError):
    """The master draft could not be read."""


@dataclass(frozen=True)
class Episode:
    """One episode, as the master draft declares it."""

    path: Path | None
    content_id: str
    episode: str
    episode_no: int | None
    series: str | None
    episode_hook: str | None
    episode_sources: tuple
    episode_repro: tuple
    episode_subtitle: str | None
    episode_duration_s: float | None
    episode_license: str | None
    date: str | None

    @property
    def is_episode(self) -> bool:
        """A master draft joins the episode line by carrying ``episode``."""
        return bool(self.episode)

    def landing_url(self) -> str:
        """This episode's landing URL, derived from its content id.

        地址的**形状**不再由这一层决定——它读共享规则
        （``rules/urls.json``），与站点逐字相同。

        但 ``date`` 仍是「**已编译成内容单元**」的标记：母稿读出来的期号
        没有 ``date``（编译器还没跑过），这一期的落地地址**还不存在**——
        所以这时响亮地拒绝，而不是给一条指向别处的地址。
        """
        if not self.content_id:
            raise EpisodeFieldError(
                "期号 {!r} 还没有 content_id，算不出落地 URL".format(self.episode)
            )
        if not self.date:
            raise EpisodeFieldError(
                "期号 {!r} 还没编译成内容单元，算不出落地 URL".format(self.episode)
            )
        return landing_url(self.content_id)


# --- 字段校验 ---------------------------------------------------------------


def _text(fields: dict, key: str):
    value = fields.get(key)
    return value if isinstance(value, str) else None


def _validate_slug(fields: dict) -> list:
    value = fields.get("episode")
    if value is None:
        return []
    if not isinstance(value, str):
        return ["episode 必须是字符串"]
    if not EPISODE_SLUG_RE.match(value.strip()):
        return [
            "episode {!r} 不是合法的期号 slug（小写字母、数字、连字符）".format(value)
        ]
    return []


def _validate_episode_no(fields: dict) -> list:
    value = fields.get("episode_no")
    if value is None:
        # 有 episode 就必须有期号——期号页上要显示「EP0X」。
        if fields.get("episode") is not None:
            return ["有 episode 就必须写 episode_no"]
        return []
    if not isinstance(value, str) or not _INT_RE.match(value.strip()):
        return ["episode_no 必须是整数，实际是 {!r}".format(value)]
    number = int(value.strip())
    if number < _EPISODE_NO_MIN:
        return ["episode_no {} 小于 {}".format(number, _EPISODE_NO_MIN)]
    return []


def _validate_series(fields: dict) -> list:
    value = fields.get("series")
    if value is None:
        return []
    if not isinstance(value, str) or not value.strip():
        return ["series 必须是非空字符串"]
    return []


def _validate_hook(fields: dict) -> list:
    value = fields.get("episode_hook")
    if value is None:
        if fields.get("episode") is not None:
            return ["有 episode 就必须写 episode_hook"]
        return []
    if not isinstance(value, str):
        return ["episode_hook 必须是字符串"]
    text = value.strip()
    if len(text) < _HOOK_MIN_CHARS or len(text) > _HOOK_MAX_CHARS:
        return [
            "episode_hook {} 字，应在 {}~{} 字之间".format(
                len(text), _HOOK_MIN_CHARS, _HOOK_MAX_CHARS
            )
        ]
    return []


def _validate_duration(fields: dict) -> list:
    value = fields.get("episode_duration_s")
    if value is None:
        if fields.get("episode") is not None:
            return ["有 episode 就必须写 episode_duration_s（成片实测时长）"]
        return []
    if not isinstance(value, str) or not _FLOAT_RE.match(value.strip()):
        return ["episode_duration_s 必须是正数，实际是 {!r}".format(value)]
    if float(value.strip()) <= 0:
        return ["episode_duration_s 必须大于 0，实际是 {!r}".format(value)]
    return []


def _validate_license(fields: dict) -> list:
    """出处与许可证：有 ``episode`` 就必须写。

    母稿页比视频更容易越界——它可以贴更多代码、更具体的行号。
    《运营手册》§8.1 的判断标准是「这个信息在官网 / 公开仓库 / 公开演讲里
    已经出现过，我讲它没问题」。所以期号页必须写清「这一期讲的是谁的什么、
    依据哪份公开材料」（规格 §6.5）。
    """
    value = fields.get("episode_license")
    if value is None:
        if fields.get("episode") is not None:
            return ["有 episode 就必须写 episode_license（出处与许可证）"]
        return []
    if not isinstance(value, str):
        return ["episode_license 必须是字符串"]
    if not value.strip():
        return ["episode_license 不能是空字符串"]
    return []


def _validate_string_list(fields: dict, key: str) -> list:
    value = fields.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        return ["{} 必须是列表".format(key)]
    violations = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            violations.append("{} 的元素必须是非空字符串".format(key))
    return violations


def validate_episode_fields(fields: dict) -> list:
    """Check episode front-matter fields against the episode contract.

    Returns **all** violations (never raises) so the linter can report
    them in one pass; :func:`episode_from_fields` turns a non-empty list
    into an error.
    """
    if not isinstance(fields, dict):
        raise EpisodeFieldError(
            "front matter 必须是映射，实际是 {}".format(type(fields).__name__)
        )

    violations = []
    violations.extend(_validate_slug(fields))
    violations.extend(_validate_episode_no(fields))
    violations.extend(_validate_series(fields))
    violations.extend(_validate_hook(fields))
    violations.extend(_validate_duration(fields))
    violations.extend(_validate_license(fields))
    violations.extend(_validate_string_list(fields, "episode_sources"))
    violations.extend(_validate_string_list(fields, "episode_repro"))
    return violations


def validate_episode_series(episodes) -> list:
    """Check a whole series: numbers unique and consecutive.

    * ``episodes`` is an iterable of :class:`Episode`.
    * Returns violations; empty means the series is well-formed.

    两件事必须成立：同一系列里期号**不重复**，且从 1 开始**连续**。
    跳号意味着有一期没落地——而观众是按期号往前数的，跳号会被当成
    「那期不见了」。
    """
    by_series: dict = {}
    for item in episodes:
        if not getattr(item, "series", None):
            continue
        by_series.setdefault(item.series, []).append(item)

    violations = []
    for series, items in sorted(by_series.items()):
        numbers = [i.episode_no for i in items if i.episode_no is not None]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            violations.append(
                "系列 {!r} 的期号重复：{}".format(
                    series, "、".join(map(str, duplicates))
                )
            )
        unique = sorted(set(numbers))
        if unique and unique != list(range(1, len(unique) + 1)):
            violations.append(
                "系列 {!r} 的期号不连续：{}".format(series, "、".join(map(str, unique)))
            )
    return violations


# --- 落地 URL 派生 ----------------------------------------------------------


def landing_url(content_id: str) -> str:
    """The landing URL of an episode, derived -- never hand-written.

    ``= <共享规则的 doc_prefix> + <content_id>``——形状由仓库根的
    ``rules/urls.json`` 决定，契约层的读取器是 :mod:`publishkit.urls`：

    >>> landing_url("source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive")
    '/docs/source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/'

    **日期不进地址**：地址的形状只有一份规则说了算，站点与契约层读的是
    同一份 ``rules/urls.json``，逐字相同。

    这里**只拼地址，不检查日期**——它没有 date 可查。「这一期到底编译
    出来没有」是 :meth:`Episode.landing_url` 管的（``date`` 是那个标记）。
    """
    if not isinstance(content_id, str) or not content_id.strip():
        raise EpisodeFieldError("content_id 不能为空")
    return urls.doc_url(content_id.strip())


# --- 母稿 → content_id -----------------------------------------------------


def content_id_for_draft(path, drafts_root) -> str:
    """内容单元 id：**母稿**路径（相对 ``docs/``）去后缀。

    与 :func:`publishkit.schedule.content_id_for` 的区别只有一处，但它
    是**必需**的：母稿 ``docs/<目录>/index.md`` 要变成它所在的目录本身。

    ==========================================  ==========================================
    母稿                                        内容单元 id
    ==========================================  ==========================================
    ``docs/database/postgresql-row-lock-        ``source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive``
    deep-dive/index.md``
    ``docs/blog/scheduled.md``                  ``blog/scheduled``
    ==========================================  ==========================================

    直接拿母稿路径去后缀会得到 ``source-tracks/postgresql/transaction-mvcc/postgresql-row-lock-deep-dive/index``，
    派生的落地 URL 指向一个**不存在**的页面——所以这一条不能省。

    ⚠️ **这条特判是旧链路口径**。现行编译器 ``tools/build-content-units.py``
    **同构拷贝**目录树（``docs/<目录>/index.md`` → ``content/units/<目录>/index.md``，
    内容单元 id 是 ``<目录>/index``），钉住母稿派生值与编译产物等价的集成用例
    随 ``sync-hexo.py`` 一起删了。两侧现在对不上，见
    ``review/specs/2026-11-19-整体架构与模块边界.md`` §五 第 9 条。
    """
    root = Path(drafts_root).resolve()
    relative = Path(path).resolve().relative_to(root)
    if relative.name == "_index.md":
        raise EpisodeFieldError("{} 是分类页，不是内容单元".format(path))
    if relative.name == "index.md":
        parent = relative.parent
        if str(parent) in (".", ""):
            raise EpisodeFieldError(
                "{} 在内容根目录的第一层，没有可用的内容单元 id".format(path)
            )
        relative = parent.parent / (parent.name + ".md")
    return relative.with_suffix("").as_posix()


def discover_episodes(drafts_root) -> tuple:
    """读出全部**期号**母稿。

    只返回带 ``episode`` 键的母稿——没有这个键的普通文章不进期号线。
    母稿是唯一真相，所以「哪些文章是一期」只由 front matter 决定，
    **没有第二张表**。

    带 ``episode`` 键但**字段写错**的母稿会**报错**，不会被跳过：
    跳过等于「这一期悄悄消失了」，而观众是按期号往前数的。
    """
    from .contract import parse_front_matter

    root = Path(drafts_root)
    if not root.is_dir():
        raise EpisodeFileError("找不到母稿目录：{}".format(root))

    episodes = []
    for path in sorted(root.rglob("*.md")):
        if path.name == "_index.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fields, _body = parse_front_matter(text)
        if not fields.get("episode"):
            continue  # 不是期号
        episodes.append(read_episode(path, drafts_root=root))
    return tuple(episodes)


def find_episode(drafts_root, slug: str) -> Episode | None:
    """按期号 slug 找到那一期的母稿；找不到返回 ``None``。

    找不到就返回 ``None``，**不猜**：一个 slug 对应一篇母稿，是母稿自己
    声明的，不是推出来的。

    两个母稿声明同一个 slug 时**报错**——那不是「取一个」，那是内容
    单元身份冲突，落地 URL 会指向其中一篇、另一篇从此没有地址。
    """
    matches = [e for e in discover_episodes(drafts_root) if e.episode == slug]
    if len(matches) > 1:
        raise EpisodeFieldError(
            "期号 slug {!r} 有 {} 篇母稿声明它：{}".format(
                slug, len(matches), "、".join(str(m.path) for m in matches)
            )
        )
    return matches[0] if matches else None


# --- 构造 -------------------------------------------------------------------


def episode_from_fields(
    fields: dict, *, path=None, content_id=None, date=_UNSET
) -> Episode:
    """Build an :class:`Episode` from parsed front-matter fields.

    Raises :class:`EpisodeFieldError` when the fields violate the contract.

    ``date`` 默认取 front matter 里的 ``date``；传 ``None`` 表示「这一期
    没有可用的日期」（母稿读的场合——见 :func:`read_episode`）。
    """
    violations = validate_episode_fields(fields)
    if violations:
        where = "{} ".format(path) if path is not None else ""
        raise EpisodeFieldError(
            "{}不满足期号契约：{}".format(where, "；".join(violations))
        )

    def text(key):
        value = fields.get(key)
        return value.strip() if isinstance(value, str) else None

    def number(key):
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return float(value.strip()) if "." in value else int(value.strip())
        return None

    def string_list(key):
        value = fields.get(key)
        return tuple(value) if isinstance(value, list) else ()

    episode = text("episode")
    # content_id **不猜**。`Path(path).stem` 对 `database/xxx.md` 只给出
    # `xxx`——少了目录那一段，派生出来的落地 URL 就指向另一个页面。
    # 猜错比空着更糟：空着时 landing_url() 会响亮地拒绝，猜错时它安静地
    # 给出一条错的 URL。调用方要么显式传 content_id，要么给 posts_root。
    resolved_content_id = content_id or ""

    return Episode(
        path=Path(path) if path is not None else None,
        content_id=resolved_content_id or "",
        episode=episode or "",
        episode_no=number("episode_no"),
        series=text("series"),
        episode_hook=text("episode_hook"),
        episode_sources=string_list("episode_sources"),
        episode_repro=string_list("episode_repro"),
        episode_subtitle=text("episode_subtitle"),
        episode_duration_s=number("episode_duration_s"),
        episode_license=text("episode_license"),
        date=text("date") if date is _UNSET else date,
    )


def read_episode(path, posts_root=None, drafts_root=None) -> Episode:
    """Read one master draft and return its episode fields.

    母稿可以是 ``docs/`` 下的原稿，也可以是 ``content/units/`` 下的内容单元
    ——两者的 front matter 是同一套。

    两个 root 各自对应一种内容单元 id 的算法，**不能混用**：

    - ``posts_root``（``content/units/``）：由
      :func:`publishkit.schedule.content_id_for` 算；
    - ``drafts_root``（``docs/``）：由 :func:`content_id_for_draft` 算
      ——``index.md`` 要变成它所在的目录本身（见那条函数的说明）。

    两个都不给时 ``content_id`` 是空字符串——**不猜**
    （见 :func:`episode_from_fields`）。

    **日期只有内容单元才有。**
    ``tools/build-content-units.py`` 编译时，母稿写了 ``date:`` 就用它，
    没写才取 git 里最早的一次提交时间——内容单元里存的是那个值。
    所以读母稿时 ``date`` 留空，读内容单元时才取它的 ``date``。

    **没有** ``episode`` 键的母稿不是一期。它仍然被读出来（``episode`` 为空
    字符串、``is_episode`` 为 False），因为这一层是**全体文章**都要经过的
    闸门，不该只对期号文章生效。
    """
    from .contract import parse_front_matter

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise EpisodeFileError("母稿文件不存在：{}".format(path)) from exc
    except OSError as exc:
        raise EpisodeFileError("母稿文件读不了：{}（{}）".format(path, exc)) from exc

    content_id = ""
    # date 只有内容单元有：母稿的 date 会被构建覆盖成 git 最早提交日。
    date = None
    if posts_root is not None:
        try:
            content_id = content_id_for(path, posts_root)
        except ValueError as exc:
            # Path.relative_to 抛的是裸 ValueError——契约层只抛
            # PublishKitError 这一族（publishkit/__init__.py 的约定），
            # 这里换成自己的异常类型。
            raise EpisodeFieldError(
                "{} 不在 {} 底下，算不出 content_id".format(path, posts_root)
            ) from exc
    elif drafts_root is not None:
        try:
            content_id = content_id_for_draft(path, drafts_root)
        except ValueError as exc:
            raise EpisodeFieldError(
                "{} 不在 {} 底下，算不出 content_id".format(path, drafts_root)
            ) from exc

    fields, _body = parse_front_matter(text)
    if posts_root is not None:
        date = fields.get("date")
    return episode_from_fields(fields, path=path, content_id=content_id, date=date)
