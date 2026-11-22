"""抖音版的文案。

抖音的**文案形状取决于走哪条路**——这是 2026-11-15 实测网页后台才分清的：

- **开放平台 API**：标题、正文、话题、@ 全塞在一个 `text` 里（话题靠 `#话题`
  内嵌）。规格 §6.6.3 的三段拼一个字段就是这里做的（`build_text`）。
- **网页后台**（我们这一档实际走的路——个人主体拿不到 API 凭据）：后台是
  **两个独立字段**——「作品标题」（上限 30 字）与「作品描述」（上限 1000 字），
  两个计数器都实测过。所以网页档是分开填两个框（`web_fields`）。

所以这一层有两件事：

1. **拼装**：`build_text`（API 档的一个字段）与 `web_fields`（网页档的两个框）。
2. **拼完再查总量**（`text_chars`，平台写明的硬上限 1000 字）——
   这条**不能**交给 `pyv.epmeta`：它逐字段查，查不出「三段加起来超了」。
   逐字段查的是各自的上限（title 30 / description 500 / 话题 5×15），
   拼起来的总量只有这里能算。

还有一条抖音特有的闸：**文案里不能有站外引流**。抖音禁「过度营销信息与
站外引流」，片尾那种 `example.invalid` 胶囊放进文案就是撞这条（规格 §6.6.4）。
这条也放在这里——它是平台规则，不是元数据格式。

不静默截断：超限与带引流都报错让作者改元数据，不在这里悄悄裁一刀。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pyv import epmeta

# 文案里不许出现的东西。
#
# **拦的是形态，不是白名单。** 「https://example.invalid」和「加V: abc123」长得
# 完全不一样，但性质一样——都是把人引到站外。抖音限流的常见原因就是这个。
# 所以每条规则都按「长什么样」来写（网址长什么样、微信号长什么样），
# 而不是列具体的值（列不完，也不该列）。
#
# 域名那条是唯一的例外：**后缀没法穷举**（`.xyz`、`.icu` 也是真的域名），
# 所以按形态收——「一段词 + 一个点 + 2 到 24 个字母」，
# 再把**肯定不是域名的后缀**放行：文件后缀（正文里写 README.md 是常事）
# 与产品词（gpt-4o.mini 这种模型名）。
#
# 误伤是可能的（比如正文里提到某个开源项目的官网）——真遇到了就把那句话
# 挪到别处去，**不要把闸拆了**：闸拆了之后，下一次就没人拦了。
#
# 「私信」**不在**这张表里：抖音私信是站内功能，不是站外引流。

#: 肯定不是域名的后缀——**文件后缀 + 产品词**。
#:
#: 正文里写文件名、写代码、写模型名是常事，那些点后面的词不是站外引流。
#: （`.mini` 确实是个真域名，但它在正文里出现的时候几乎都是 "gpt-4o.mini"
#: 这种模型名。）
_NOT_A_DOMAIN = (
    r"md|txt|json|ya?ml|toml|ini|conf|cfg|env|log|lock|sum|mod"
    r"|py|js|mjs|cjs|ts|tsx|jsx|html?|css|scss|sass|less|vue|svelte"
    r"|png|jpe?g|gif|webp|bmp|svg|ico|mp[34]|mov|avi|mkv|flac|wav"
    r"|pdf|docx?|xlsx?|pptx?|csv|zip|tar|gz|bz2|xz|7z|rar"
    r"|sh|bash|zsh|fish|go|rs|pyi|c|cc|cpp|cxx|h|hpp|java|kt|swift|rb|php"
    r"|sql|gradle|mk|cmake|dockerfile|makefile"
    r"|mini|max|pro|plus|beta|alpha|preview|nightly"
)

OUTBOUND_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("网址", re.compile(r"https?://|www\.", re.IGNORECASE)),
    ("域名", re.compile(
        r"(?<![A-Za-z0-9_-])[A-Za-z0-9][A-Za-z0-9-]*\."
        r"(?!" + _NOT_A_DOMAIN + r"(?![A-Za-z0-9]))[A-Za-z]{2,24}"
        r"(?![A-Za-z0-9-])",
        re.IGNORECASE)),
    # 微信：「加V」「加vx」「加wx」「微信号」「VX: abc」都是同一件事。
    # 前后用字母数字挡一下：wxPython 这种库名不该被当成微信号。
    ("微信", re.compile(
        r"微\s*信|威\s*信|weixin|wechat"
        r"|(?<![A-Za-z0-9])(?:wx|vx)(?![A-Za-z0-9])"
        r"|加\s*[vVvWxX]",
        re.IGNORECASE)),
    # QQ：「QQ」「扣扣」；后头跟数字是正常的（QQ 号就是数字）。
    ("QQ", re.compile(
        r"(?<![A-Za-z0-9])q\s*q(?![A-Za-z])|扣\s*扣",
        re.IGNORECASE)),
    # 手机号：**不能靠 `\b`**——中文与数字之间没有词边界，
    # 「手机号13800138000」在 `\b1[3-9]\d{9}\b` 下根本匹配不上。
    ("电话", re.compile(
        r"(?<!\d)1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)"
        r"|手\s*机\s*号|电\s*话|联\s*系",
        re.IGNORECASE)),
)

# 拼装 `text` 时的分隔。抖音的文案是一整段，不是几个独立字段。
SEPARATOR = "\n"


@dataclass(frozen=True)
class DouyinCopy:
    """一期在抖音上的文案。

    **`url` 不进文案。** 抖音禁站外引流，所以站点地址只能留在平台之外的地方
    （账号主页、评论区）。这一栏留着是为了跟别的平台的文案形状一致——
    `build_text` 不用它，`check_no_outbound` 也正是靠它不出现来守住那条线。
    """

    title: str
    description: str
    topics: tuple[str, ...]
    cover_at: float
    url: str = ""


def slice_copy(meta: epmeta.EpisodeMeta) -> DouyinCopy:
    """取出抖音版的文案。没配这一段就是配置错误。"""
    section = meta.platform("douyin")
    if section is None:
        raise epmeta.MetaError(
            f"这一期没有配置抖音文案：{meta.episode}")
    return DouyinCopy(
        title=str(section.get("title", "")),
        description=str(section.get("description", "")),
        topics=tuple(str(t) for t in (section.get("topics") or [])),
        cover_at=meta.cover_at,
        url=meta.url,
    )


def topics_line(topics: tuple[str, ...]) -> str:
    """话题拼成一行：#数据库 #内核"""
    return " ".join(f"#{topic}" for topic in topics)


def build_text(copy: DouyinCopy) -> str:
    """三段拼成平台要的那一个 `text`（**开放平台 API 档**）。

    顺序：标题、正文、话题。抖音信息流只露前几十个字，所以钩子在最前面。

    话题用 `#话题` 内嵌——抖音**没有**独立的话题字段，井号就是它的标记方式。

    **网页后台不走这条**：那边是标题与描述两个框，用 `web_fields`。
    """
    parts = [copy.title, copy.description]
    topics = topics_line(copy.topics)
    if topics:
        parts.append(topics)
    return SEPARATOR.join(part for part in parts if part)


def web_fields(copy: DouyinCopy) -> tuple[str, str]:
    """网页后台要填的**两个字段**：作品标题、作品描述。

    **标题进标题框，正文与话题进描述框。**

    话题跟着描述走——网页后台的描述框里内嵌 `#话题` 会被抖音识别成
    **真话题**（2026-11-15 实测：在描述框里敲 `#开源`，后台立刻弹出
    该话题的热度与关联话题），所以话题不必另找地方放。

    与 `build_text` 的区别只有一处，但那一处正是最容易犯的错：
    **标题不进描述框**。照着开放平台文档把整段 `text` 贴进描述框，
    标题会在正文里重复一遍。
    """
    description = copy.description
    topics = topics_line(copy.topics)
    if topics:
        description = f"{description}{SEPARATOR}{topics}" if description else topics
    return copy.title, description


def check_text_length(text: str, limits: dict) -> list[str]:
    """拼装后的 `text` 不能超过平台写明的上限。

    `limits` 是 `platforms/douyin/capability.toml` 的 `[limits]` 段。
    缺 `text_chars` 就**不查**——能力声明被改坏时，宁可不查也不要瞎报。

    这条量的是**开放平台 API 那个 `text` 字段**（三段拼起来的整段）。
    网页后台是标题与描述两个框，分别有各自的计数器——标题那 30 字由
    `pyv.epmeta` 按 `title_chars` 卡，描述那 1000 字比这条宽，
    所以这条闸在两条路径上都够用。
    """
    limit = limits.get("text_chars")
    if not isinstance(limit, int) or limit <= 0:
        return []
    if len(text) <= limit:
        return []
    return [
        f"拼装后的文案有 {len(text)} 字，超过平台上限 {limit} 字"
        f"（开放平台那一个 text 字段装下标题、正文、话题）"
    ]


def check_no_outbound(text: str) -> list[str]:
    """文案里不许有站外引流。"""
    problems = []
    for label, pattern in OUTBOUND_RULES:
        found = pattern.search(text)
        if found:
            problems.append(
                f"文案里出现了疑似站外引流（{label}）：{found.group(0)!r}"
                f"——抖音禁站外引流与过度营销（规格 §6.6.4）"
            )
    return problems
