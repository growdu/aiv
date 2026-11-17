"""头条号：把发布包里的图灌进平台草稿箱。

**这个 flow 解决什么。** 2026-11-15 那批 547 篇草稿是「只灌正文、不带图」灌进去的
（见 ``platforms/toutiao/docs/02-试点记录.md`` §R4.D）：草稿里留着切片器的 ``【图N】``
占位符，图得人工补。这一步现在做成脚本：上传图 → 把占位符换成平台自己的
图片节点 → **更新**那一条草稿。

**它更新，不新建。** 保存草稿的请求里带 ``pgc_id`` 就是更新那一条，不带就是
新建一条新的草稿（§R4.B 那个「同一轮会话里连写两篇会覆掉上一条」的坑的另一面）。
所以每一篇都必须先有平台侧的草稿 id——没有就**不做**：新建出来的是另一条草稿，
原草稿还在，人在后台看到的是两篇。

**为什么在页面里发请求，而不是点界面。** 编辑器里一篇篇插图是 40 秒一篇（§R3），
五百多篇要六小时；而平台后台的接口就在页面里（带 cookie），在页面上下文里发
同一个请求是一秒一篇。**请求体的形状是从平台自己发的请求里抓的**（§R5），
不是猜的——猜错的字段名会被平台静默丢掉，然后你看到的是「保存成功了，
但内容不对」。

**它不动账本。** 草稿 id 没变，账本里那条记录也就没变；
``platforms/toutiao/outbox/`` 里的快照仍然是「drafted + 同一个 draft_id」。
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from browser.plan import ToutiaoPlan

__all__ = [
    "MARKER_RE", "ToutiaoConfig", "ToutiaoError", "ToutiaoUploader",
    "UploadedImage", "build_image_node", "build_publish_payload",
    "inject_images",
]

#: 选择器表的默认位置：browser/selectors/toutiao.json。
#: parents[2]——本文件在 browser/browser/flows/ 下，
#: parents[0]=flows、parents[1]=browser 包、parents[2]=browser/ 顶层目录。
DEFAULT_SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors" / "toutiao.json"

#: 正文里的占位符段落：``<p style="...">【图1】</p>``。
#: **只认整段就是占位符的 ``<p>``**——正文里如果哪句话里出现「【图1】」三个字，
#: 那不是图位，不该被替换掉。
MARKER_RE = re.compile(r"<p\b[^>]*>\s*【图(\d+)】\s*</p>")


class ToutiaoError(RuntimeError):
    """头条号流程跑不下去。消息里要说清是哪一步、为什么。"""


# ── 在页面里跑的 JavaScript ─────────────────────────────────────────────
# 为什么不直接用 requests：头条号后台的接口要带页面 cookie，
# 而且平台会对**同源**请求有偏好。在页面上下文里 fetch，cookie 由浏览器带，
# 也不用自己抄 token。
#
# upload：把图片文件变成 multipart 上传（实测走这个接口，见 §R5）。
#
# **字段名是 `image`，不是 `file`**（2026-11-17 实测）：抓编辑器的 multipart
# 报文看到的。写错字段名平台不会说「字段不对」，它会说「无效图片数据」——
# 因为它压根没收到文件。
_JS_UPLOAD = """
async ({url, name, mime, b64}) => {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const file = new File([arr], name, {type: mime});
    const fd = new FormData();
    fd.append('image', file);
    const r = await fetch(url, {method: 'POST', body: fd, credentials: 'include'});
    const text = await r.text();
    try { return JSON.parse(text); } catch (e) { return {code: -1, message: text.slice(0, 200)}; }
}
"""

# publish：存草稿（save=0）或发表（save=1）。字段名与取值都是抓平台自己的
# 请求抄来的，一个字都没改。
_JS_PUBLISH = """
async ({url, fields}) => {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(fields)) body.append(k, v);
    const r = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: body.toString(),
    });
    const text = await r.text();
    try { return JSON.parse(text); } catch (e) { return {code: -1, message: text.slice(0, 200)}; }
}
"""


@dataclass(frozen=True)
class UploadedImage:
    """一张已经传到平台上的图。"""

    url: str
    uri: str
    width: int
    height: int
    mime_type: str = "image/webp"

    @classmethod
    def from_response(cls, payload: dict) -> "UploadedImage":
        """从上传接口的返回里读出图片。

        实测返回（2026-11-17）::

            {"code": 0, "message": "success",
             "data": {"image_uri": "...", "image_url": "...",
                      "image_width": 312, "image_height": 200,
                      "image_format": "webp", "image_mime_type": "image/webp",
                      "image_size": 3060, "image_type": 1, ...}}
        """
        data = (payload or {}).get("data") or {}
        url = data.get("image_url")
        uri = data.get("image_uri")
        if not url or not uri:
            raise ToutiaoError("上传接口没有回图片地址：{}".format(payload))
        return cls(
            url=str(url),
            uri=str(uri),
            width=int(data.get("image_width") or 0),
            height=int(data.get("image_height") or 0),
            mime_type=str(data.get("image_mime_type") or "image/webp"),
        )


def build_image_node(image: UploadedImage) -> str:
    """平台自己的图片节点。

    **这段是抓编辑器保存的内容抄下来的**（2026-11-17，§R5），
    不是一个「差不多」的 HTML：平台存正文时，图片就是这个形状
    （``div.pgc-img`` 里一个 ``img`` 加一个空的图注段落）。
    自己拼一个 ``<img>`` 塞进去，平台会当普通文本处理，图不显示。
    """
    return (
        '<div class="pgc-img">'
        '<img src="{url}" class="" image_type="1" mime_type="{mime}" '
        'web_uri="{uri}" img_width="{width}" img_height="{height}">'
        '<p class="pgc-img-caption"></p>'
        "</div>"
    ).format(
        url=image.url,
        mime=image.mime_type,
        uri=image.uri,
        width=image.width,
        height=image.height,
    )


def inject_images(html: str, images: dict[int, UploadedImage]) -> tuple[str, list[int]]:
    """把正文里的 ``【图N】`` 占位段落换成平台自己的图片节点。

    返回 ``(新正文, 没有图可插的占位符编号)``。

    **没有图的占位符留着。** 草稿里留着「【图7】」是在告诉人这一处还缺图；
    悄悄删掉等于把缺口藏起来——人打开草稿以为图齐了，发表出去才发现少图。
    """
    missing: list[int] = []

    def replace(match: re.Match) -> str:
        number = int(match.group(1))
        image = images.get(number)
        if image is None:
            missing.append(number)
            return match.group(0)
        return build_image_node(image)

    return MARKER_RE.sub(replace, html), sorted(missing)


def _editor_stat(content: str) -> dict:
    """编辑器那三个统计位。

    实测平台发的是 ``{"header": 1, "header-forward-slash": 1, "a_center": 1}``，
    看着像「有没有标题 / 有没有斜杠标题 / 有没有居中段」而不是计数
    （那篇正文里有 4 个 h1，值却是 1）。平台下次打开编辑器时会自己重算，
    这里按同样的口径算一份，别让这一项说谎。
    """
    lowered = content.lower()
    return {
        "header": 1 if re.search(r"<h[1-6]\b", lowered) else 0,
        "header-forward-slash": 1 if "pgc-h-forward-slash" in content else 0,
        "a_center": 1 if re.search(r"text-align\s*:\s*center", lowered) else 0,
    }


def build_publish_payload(
    *,
    title: str,
    content: str,
    word_count: int,
    draft_id: str,
    covers: list | None = None,
    cover_type: int = 2,
    timer_time: str = "",
) -> dict[str, str]:
    """存草稿请求的字段。

    **字段名与取值全部抄自平台自己发的请求**（2026-11-17，§R5），
    不是照着文档猜的。猜错的字段平台会静默丢掉。

    ``word_count`` 是**平台自己的字数口径**（非 ASCII 逐字 + ASCII 每两个折一个），
    由出包时算好放在 ``meta.json`` 里——执行器不重算口径，见
    ``platforms/toutiao/wordcount.py``。

    ``draft_id`` 带上去就是**更新**那一条草稿；不带就是新建一条。
    """
    payload = {
        "source": "29",
        "article_type": "0",
        "pgc_id": str(draft_id),
        "content": content,
        "title": title,
        "save": "0",
        "search_creation_info": json.dumps(
            {"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False
        ),
        "extra": json.dumps(
            {
                "content_source": 100000000402,
                "content_word_cnt": int(word_count),
                "is_multi_title": 0,
                "sub_titles": [],
                "gd_ext": {
                    "entrance": "",
                    "from_page": "publisher_mp",
                    "enter_from": "PC",
                    "device_platform": "mp",
                    "is_message": 0,
                },
                "tuwen_wtt_transfer_switch": "1",
            },
            ensure_ascii=False,
        ),
        "mp_editor_stat": json.dumps(_editor_stat(content), ensure_ascii=False),
        "is_refute_rumor": "0",
        "timer_status": "0",
        "timer_time": timer_time,
        "draft_form_data": json.dumps({"coverType": int(cover_type)}, ensure_ascii=False),
        "pgc_feed_covers": json.dumps(covers or [], ensure_ascii=False),
        "article_ad_type": "3",
        "is_fans_article": "0",
        "govern_forward": "0",
        "praise": "0",
        "disable_praise": "0",
        "tree_plan_article": "0",
        "activity_tag": "0",
        "trends_writing_tag": "0",
        "claim_exclusive": "1",
    }
    return payload


@dataclass
class ToutiaoConfig:
    """接口表 + 行为开关（读自 browser/selectors/toutiao.json）。"""

    origin: str = "https://mp.toutiao.com"
    entry_url: str = "https://mp.toutiao.com/profile_v4/manage/draft"
    upload_path: str = "/spice/image"
    upload_source_body: str = "20020002"
    upload_source_cover: str = "20020003"
    publish_path: str = "/mp/agw/article/publish"
    publish_query: str = "source=mp&type=article&aid=1231&mp_publish_ab_val=0"
    selectors: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "ToutiaoConfig":
        target = Path(path) if path else DEFAULT_SELECTORS_PATH
        if not target.is_file():
            raise ToutiaoError(
                f"接口表不存在：{target}\n"
                "照着 browser/selectors/channels.json 的样子补一张。"
            )
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ToutiaoError(f"接口表读不出来：{error}") from error
        api = raw.get("api") or {}
        return cls(
            origin=str(raw.get("origin") or cls.origin),
            entry_url=str(raw.get("entry_url") or cls.entry_url),
            upload_path=str(api.get("upload") or cls.upload_path),
            upload_source_body=str(api.get("upload_source_body") or cls.upload_source_body),
            upload_source_cover=str(api.get("upload_source_cover") or cls.upload_source_cover),
            publish_path=str(api.get("publish") or cls.publish_path),
            publish_query=str(api.get("publish_query") or cls.publish_query),
            selectors=raw.get("selectors") or {},
        )


class ToutiaoUploader:
    """把发布包里的图灌进平台草稿箱。

    ``page`` 是一个 Playwright 的 page（或者任何有 ``evaluate`` 的东西——
    测试里塞个假的进去）。
    """

    def __init__(self, page, config: ToutiaoConfig | None = None):
        self.page = page
        self.config = config or ToutiaoConfig.load()

    # -- 平台调用 ----------------------------------------------------------

    def upload_image(self, path: Path, *, cover: bool = False) -> UploadedImage:
        """上传一张图，返回平台那边的地址与尺寸。

        实测：``POST /spice/image?upload_source=20020002&aid=1231&device_platform=web``，
        multipart 里带 ``file``。webp 能传（平台原样存原样吐，不转码）。
        """
        data = Path(path).read_bytes()
        source = (
            self.config.upload_source_cover if cover else self.config.upload_source_body
        )
        url = "{}{}?upload_source={}&aid=1231&device_platform=web".format(
            self.config.origin, self.config.upload_path, source
        )
        if cover:
            url += "&need_cover_url=1"
        response = self.page.evaluate(
            _JS_UPLOAD,
            {
                "url": url,
                "name": Path(path).name,
                "mime": _mime_of(path),
                "b64": base64.b64encode(data).decode("ascii"),
            },
        )
        code = (response or {}).get("code")
        if code != 0:
            raise ToutiaoError(
                "图片上传失败（{}）：{}".format(path.name, (response or {}).get("message"))
            )
        return UploadedImage.from_response(response)

    def save_draft(self, payload: dict[str, str]) -> dict:
        """存草稿（``save=0``）。返回平台回的 JSON。

        ``pgc_id`` 在 payload 里 → 更新那一条；不带 → 新建一条。
        """
        url = "{}{}?{}".format(
            self.config.origin, self.config.publish_path, self.config.publish_query
        )
        response = self.page.evaluate(_JS_PUBLISH, {"url": url, "fields": payload})
        code = (response or {}).get("code")
        if code != 0:
            raise ToutiaoError(
                "存草稿失败：{}（err_no={}）".format(
                    (response or {}).get("message"), (response or {}).get("err_no")
                )
            )
        return response or {}

    # -- 一篇文章 ----------------------------------------------------------

    def fill_draft(
        self,
        plan: ToutiaoPlan,
        draft_id: str,
        *,
        images: dict[int, Path] | None = None,
        cover: bool = True,
    ) -> dict:
        """给一条已有的草稿补图。

        ``images`` 是「图号 → 本地文件」。没给的图号，正文里的 ``【图N】``
        占位符原样留着（人会看到还缺图）。

        返回 ``{"uploaded": [...], "missing": [...], "cover": ...}``。
        """
        wanted = images or {}
        uploaded: dict[int, UploadedImage] = {}
        for number in sorted(wanted):
            uploaded[number] = self.upload_image(wanted[number])

        content, missing = inject_images(plan.body_html, uploaded)

        covers: list = []
        cover_type = 2
        if cover and plan.cover is not None:
            cover_image = self.upload_image(plan.cover, cover=True)
            covers = [_cover_entry(cover_image)]
            cover_type = 2

        payload = build_publish_payload(
            title=plan.title,
            content=content,
            word_count=plan.platform_chars,
            draft_id=draft_id,
            covers=covers,
            cover_type=cover_type,
            timer_time=_timer_time(),
        )
        self.save_draft(payload)
        return {
            "uploaded": sorted(uploaded),
            "missing": missing,
            "cover": covers[0]["url"] if covers else None,
        }


def _cover_entry(image: UploadedImage) -> dict:
    """封面条目。

    **形状是抓编辑器存的草稿抄的**（2026-11-17，§R5）——
    平台存的是这样一条::

        {"id": "", "url": "...~tplv-tt-cover-v2.image?...",
         "uri": "tos-cn-i-6w9my0ksvp/...", "ic_uri": "",
         "thumb_width": 1356, "thumb_height": 1056,
         "extra": {"from_content_uri": "", "from_content": "0"}}

    封面走的是 ``upload_source=20020003`` 那个上传口，平台会把它处理成
    自己的封面模板（``tplv-tt-cover-v2``），回来的地址就是成品封面。
    """
    return {
        "id": "",
        "url": image.url,
        "uri": image.uri,
        "ic_uri": "",
        "thumb_width": image.width,
        "thumb_height": image.height,
        "extra": {"from_content_uri": "", "from_content": "0"},
    }


def _mime_of(path: Path) -> str:
    """按扩展名猜 MIME。平台认 jpg/jpeg/png（实测 webp 也行）。"""
    suffix = Path(path).suffix.lower()
    return {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")


def _timer_time() -> str:
    """定时发表那一栏的值。

    实测编辑器发的是「当前时间往后一点」的一个时间戳，格式 ``%Y-%m-%d %H:%M``。
    ``timer_status=0`` 表示没定定时，所以这个值平台不会真的拿来定时；
    但字段不能缺——缺了平台可能按「定时」那一支处理。
    """
    from datetime import datetime, timedelta

    return (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
