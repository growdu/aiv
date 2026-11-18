"""抖音（创作者中心）：传成片 → 填标题与描述 → 发表。

**这一档只能走网页后台。** 抖音开放平台的内容发布能力（scope
``video.create.bind``）要求**党政机关或事业单位**主体，个人主体批不下来
（见 ``platforms/douyin/capability.toml``），所以没有 API 凭据可用，
跟视频号一样是浏览器自动化。

**它做的是「上传 + 填表 + 点发表」，不碰封面。** 2026-11-17 实测：抖音的封面
编辑器是画布式的（fabric canvas + ReactCrop），传上去的图进不了画布，槽位一直
停在「选择封面」——**这不是能靠选择器绕过去的问题**，所以这一档不设封面，
平台用成片里的帧当默认封面（后台的「发文助手」会提示「横/竖双封面缺失」，
那是建议，不是拦截）。人工补封面走「内容管理 → 编辑作品」。

**为什么用界面而不是自己发请求。** 头条号那档能自己发请求，是因为它的发布接口
是「填一堆字段」的表单；而抖音的 create_v2 请求体是页面状态序列化出来的，
猜不出形状——而且点一下「发布」平台自己会发，**我们能抓到它的返回**
（``status_code`` 与 ``item_id``），这就够了。

**它不改账本。** 作品 id 拿到之后，由人（或另一步）跑
``python3 -m douyin.cli mark published <期号> --url <链接>`` 回填；
执行器不 import adapter（adapter 也不该知道执行器的事）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from browser.driver import ActionError, PageDriver

__all__ = [
    "DEFAULT_SELECTORS_PATH",
    "DouyinConfig",
    "DouyinError",
    "DouyinFlow",
    "build_description",
    "check_limits",
    "count_works",
    "parse_counters",
    "parse_create_response",
    "parse_work_status",
    "public_url",
]

#: 选择器表的默认位置：browser/selectors/douyin.json。
DEFAULT_SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors" / "douyin.json"

#: 作品状态关键词（内容管理列表里每条作品后面的那个状态）。
#:
#: **「审核未通过」比「未通过」长**，所以比的是位置不是集合顺序：
#: 谁先出现在标题后面，谁就是这条的状态。
STATUS_KEYWORDS = ("已发布", "审核中", "审核未通过", "未通过", "已下架", "已删除")

#: 作品列表里的条数：「作品 (2)」。
_WORKS_COUNT_RE = re.compile(r"作品\s*\((\d+)\)")

#: 计数器：「18/30」与「141 / 1000」（两个空格的写法平台也用）。
_COUNTER_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


class DouyinError(RuntimeError):
    """抖音流程跑不下去。消息里要说清是哪一步、为什么。"""


@dataclass
class DouyinConfig:
    """接口表 + 行为开关（读自 browser/selectors/douyin.json）。"""

    origin: str = "https://creator.douyin.com"
    upload_path: str = "/creator-micro/content/upload"
    post_path: str = "/creator-micro/content/post/video?enter_from=publish_page"
    works_path: str = "/creator-micro/content/manage?tab=works"
    publish_path: str = "/web/api/media/aweme/create_v2/"
    limits: dict = field(default_factory=dict)
    selectors: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "DouyinConfig":
        target = Path(path) if path else DEFAULT_SELECTORS_PATH
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise DouyinError(f"选择器表不存在：{target}") from error
        except json.JSONDecodeError as error:
            raise DouyinError(f"选择器表不是合法 JSON：{target}（{error}）") from error
        return cls(
            origin=raw.get("origin", cls.origin),
            upload_path=raw.get("upload_path", cls.upload_path),
            post_path=raw.get("post_path", cls.post_path),
            works_path=raw.get("works_path", cls.works_path),
            publish_path=raw.get("publish_path", cls.publish_path),
            limits=dict(raw.get("limits") or {}),
            selectors=dict(raw.get("selectors") or {}),
        )

    def need(self, key: str) -> list[str]:
        """取一组选择器；没有就是配置错了，当场报错。"""
        value = self.selectors.get(key)
        if not value:
            raise DouyinError(f"选择器表里没有 selectors.{key}")
        return list(value)

    def limit(self, key: str, default: int) -> int:
        return int(self.limits.get(key, default))


# -- 纯逻辑 ---------------------------------------------------------------


def build_description(description: str, topics: list[str], *,
                      separator: str = "\n") -> str:
    """描述框里要填的那一段：正文 + 换行 + 话题。

    **抖音的网页后台是两个框**（实测 2026-11-15）：「作品标题」与「作品描述」，
    各自带字数计数器。**标题不进描述框**——照着开放平台文档把整段 ``text`` 贴进
    描述框，标题会在正文里重复一遍。话题不是独立字段，只能以 ``#话题`` 的形式
    写进描述框里（输入框旁边的「#添加话题」也是这个意思）。
    """
    tags = " ".join(f"#{topic}" for topic in topics)
    if not tags:
        return description
    if not description:
        return tags
    return f"{description}{separator}{tags}"


def check_limits(title: str, description: str, topics: list[str],
                 limits: dict | None = None) -> list[str]:
    """文案过不过平台的上限。返回问题清单（空=没问题）。

    **超限一律报错，不静默截断。** 让作者改元数据，而不是悄悄裁一刀
    （与 ``platforms/douyin/contract.py`` 的口径一致）。
    """
    rules = {"title_chars": 30, "description_chars": 1000,
             "topics_max": 5, "topic_chars": 15}
    rules.update(limits or {})

    problems: list[str] = []
    if len(title) > rules["title_chars"]:
        problems.append(
            f"标题 {len(title)} 字，超过平台上限 {rules['title_chars']} 字")
    if len(description) > rules["description_chars"]:
        problems.append(
            f"描述 {len(description)} 字，超过平台上限 {rules['description_chars']} 字")
    if len(topics) > rules["topics_max"]:
        problems.append(
            f"话题 {len(topics)} 个，超过我们自己的口径 {rules['topics_max']} 个")
    for topic in topics:
        if len(topic) > rules["topic_chars"]:
            problems.append(
                f"话题「{topic}」{len(topic)} 字，超过 {rules['topic_chars']} 字")
    return problems


def parse_counters(raw: list[str]) -> dict[str, int]:
    """把页面上的计数器读成「上限 → 已填」。

    实测抖音的计数器长这样：``18/30``（标题）与 ``141 / 1000``（描述）——
    空格有时有有时没有，所以按正则拆，不按固定位置。
    """
    counters: dict[str, int] = {}
    for item in raw:
        match = _COUNTER_RE.search(item or "")
        if match:
            counters[match.group(2)] = int(match.group(1))
    return counters


def parse_create_response(payload: dict) -> str:
    """从发布接口的返回里读出作品 id。

    实测返回（2026-11-17）::

        {"extra": {...}, "item_id": "7709123013601463579", "status_code": 0}

    **``status_code`` 不是 0 就当失败**——平台这时也会给一个 item_id，
    但那条作品是没发出去的（没过审或者被拦），不能拿它当「已发布」。
    """
    data = payload or {}
    code = data.get("status_code")
    if code != 0:
        raise DouyinError(f"发布失败：平台返回 status_code={code}")
    item_id = str(data.get("item_id") or "").strip()
    if not item_id:
        raise DouyinError("发布返回里没有 item_id")
    return item_id


def public_url(item_id: str) -> str:
    """作品 id → 公开链接。

    实测（2026-11-15）：后台「内容管理 → 作品」的详情页地址是
    ``creator-micro/work-management/work-detail/<作品id>?enter_from=content``，
    对应的公开链接就是 ``https://www.douyin.com/video/<作品id>``（GET 返回 200）。
    """
    return f"https://www.douyin.com/video/{item_id}"


def count_works(text: str) -> int:
    """内容管理里有几条作品（「作品 (2)」里的那个数）。"""
    match = _WORKS_COUNT_RE.search(text or "")
    return int(match.group(1)) if match else 0


def parse_work_status(text: str, title: str) -> str | None:
    """某条作品的状态（标题后面最近的那个状态词）。

    找不到标题就返回 None——**没找到不等于「已发布」**。
    """
    index = (text or "").find(title or "")
    if index < 0:
        return None
    tail = text[index:]
    best: tuple[int, str] | None = None
    for keyword in STATUS_KEYWORDS:
        position = tail.find(keyword)
        if position >= 0 and (best is None or position < best[0]):
            best = (position, keyword)
    return best[1] if best else None


# -- 流程 -----------------------------------------------------------------


class DouyinFlow:
    """在抖音创作者中心上传并发表一条作品。"""

    def __init__(self, driver: PageDriver, config: DouyinConfig | None = None) -> None:
        self.driver = driver
        self.config = config or DouyinConfig.load()

    # -- 页面 ---------------------------------------------------------------

    def open_upload(self) -> None:
        """打开上传页。"""
        url = f"{self.config.origin}{self.config.upload_path}"
        self.driver.page.goto(url, wait_until="domcontentloaded")
        self.driver.page.wait_for_timeout(2000)

    def upload_video(self, path: Path | str | None) -> None:
        """把成片喂给上传框。

        **成片不在就当场报错**——不然传上去的是个空文件，
        页面照样出表单，失败要等到平台那边才看得见。
        """
        if path is None:
            raise DouyinError("发布包里没有成片（video.mp4）")
        target = Path(path)
        if not target.is_file():
            raise DouyinError(f"成片不存在：{target}")
        self.driver.upload(self.config.need("video_file_input"), target)

    def wait_form_ready(self, *, timeout_ms: int = 180000) -> None:
        """等上传页变成「可以填表」的样子。

        **不能只等标题框出现。** 实测：表单会先出来，随后视频上传失败时
        页面右上角出现「上传失败，重新上传」——那时候表单也在，但发不出去。
        所以这里同时盯两件事：标题框出现 **且** 页面上没有「上传失败」。
        """
        title_selector = self.config.need("title_input")
        self.driver.wait_for(title_selector, state="visible", timeout_ms=timeout_ms)

        import time

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            body = self.driver.body_text()
            if "上传失败" in body:
                raise DouyinError(
                    "视频上传失败了（页面右上角写着「上传失败，重新上传」）。"
                    "**不要在这张表单上点发布**——重新上传一次再填表。")
            if "上传成功" in body:
                return
            time.sleep(1.0)
        # 没有明确成功提示也不算失败：成片已经传上去了（分片请求全是 200）。

    def fill_text(self, title: str, description: str) -> None:
        """填标题与描述。

        ``description`` 是**描述框里的整段**（正文 + 换行 + 话题），
        用 :func:`build_description` 拼好再传进来。
        """
        title_selector = self.config.need("title_input")
        self.driver.wait_for(title_selector, state="visible")
        self.driver.fill(title_selector, title)
        self.fill_description(description)

    def fill_description(self, description: str) -> None:
        """把「正文 + 话题」整段敲进描述框。

        **描述框必须逐字敲。** 它是富文本编辑器（editor-kit），
        ``fill()`` / ``insert_text()`` 都不生效——只有真实的按键事件
        才会让编辑器收下文字、才会把 ``#话题`` 变成话题标签。
        """
        editor = self.config.need("description_editor")
        self.driver.wait_for(editor, state="visible")
        locator = self.driver.page.locator(editor[0]).first
        locator.click()
        locator.press_sequentially(description, delay=8)

    def read_counters(self) -> dict[str, int]:
        """读页面上的字数计数器（上限 → 已填）。"""
        raw = self.driver.page.evaluate(
            """() => Array.from(document.querySelectorAll('*'))
                .filter(e => e.children.length === 0
                          && /^\\s*\\d+\\s*\\/\\s*\\d+\\s*$/.test(e.innerText || ''))
                .map(e => (e.innerText || '').trim())"""
        )
        return parse_counters(raw)

    def submit(self, *, timeout_ms: int = 60000) -> str:
        """点「发布」，等平台把作品 id 发回来。

        **先挂监听再点。** 平台的请求很快就回来了——监听挂晚了就永远等不到。
        """
        watcher = self.driver.watch_response(
            lambda url: self.config.publish_path in url)
        try:
            self.driver.click(self.config.need("publish_button"))
            response = watcher.wait(timeout_ms=timeout_ms)
        finally:
            watcher.close()
        if response is None:
            raise DouyinError(
                f"点了发布，但没等到平台的发布响应（{self.config.publish_path}）。"
                "**别再点一次发布**——去「内容管理 → 作品」看一眼有没有多出来一条。")
        try:
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise DouyinError(f"发布响应不是 JSON：{error}") from error
        return parse_create_response(payload)

    def open_works(self) -> None:
        """打开内容管理的作品列表。"""
        url = f"{self.config.origin}{self.config.works_path}"
        self.driver.page.goto(url, wait_until="domcontentloaded")
        self.driver.page.wait_for_timeout(3000)

    def read_works(self) -> dict:
        """读内容管理：作品条数 + 页面文字（用来判状态）。"""
        text = self.driver.body_text()
        return {"count": count_works(text), "text": text}

    def verify_published(self, title: str) -> str | None:
        """回读确认这条作品在平台上，并给出它的状态。"""
        self.open_works()
        works = self.read_works()
        return parse_work_status(works["text"], title)
