"""头条号补图流程的测试。

三层：
1. 纯逻辑（占位符怎么换成图片节点、请求体长什么样）——不碰浏览器；
2. 假的页面（上传与存草稿各被调用了几次、参数对不对）；
3. **真的浏览器**（本地假页面 + 替身 fetch）——验那段 JS 胶水代码：
   base64 → File → FormData、URLSearchParams，这些是最容易写错的地方。
"""

import json
from pathlib import Path

import pytest

from browser.flows import toutiao as tt
from browser.plan import PlanError, find_toutiao_plan, load_toutiao_plan

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "toutiao-api.html"


def make_package(tmp_path: Path) -> Path:
    """一个假的头条号发布包。

    照着 toutiao 出的包的结构（``platforms/toutiao/publish.py``）：
    title.txt 两行、article.html、images/NN.webp、cover.webp、meta.json。
    """
    root = tmp_path / "ai-demo"
    (root / "images").mkdir(parents=True)
    (root / "title.txt").write_text("探针标题\n摘要一行", encoding="utf-8")
    (root / "article.html").write_text(
        '<h2>小节</h2><p>正文</p>'
        '<p style="margin:16px 0;text-align:center;color:#999999;">【图1】</p>'
        "<p>结尾</p>"
        '<p style="margin:16px 0;text-align:center;color:#999999;">【图2】</p>',
        encoding="utf-8",
    )
    (root / "images" / "01.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 fake")
    (root / "cover.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 cover")
    (root / "meta.json").write_text(
        json.dumps(
            {
                "content_id": "ai/demo",
                "platform": "toutiao",
                "title": "探针标题",
                "digest": "摘要一行",
                "body_chars": 20,
                "platform_chars": 12,
                "images": [
                    {"number": 1, "file": "images/01.webp", "source": "images/a.png"},
                    {"number": 2, "file": None, "source": "https://example.com/b.png"},
                ],
                "cover": "cover.webp",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


# -- 纯逻辑 ---------------------------------------------------------------


def test_load_plan_reads_the_package(tmp_path):
    plan = load_toutiao_plan(make_package(tmp_path))
    assert plan.content_id == "ai/demo"
    assert plan.title == "探针标题"
    assert plan.digest == "摘要一行"
    assert plan.platform_chars == 12
    assert plan.cover is not None and plan.cover.name == "cover.webp"
    # 图 1 有文件，图 2 是外链（没有文件）
    assert plan.image_paths() == {1: plan.package_dir / "images" / "01.webp"}
    assert plan.missing_images() == [2]


def test_load_plan_says_the_package_is_missing(tmp_path):
    with pytest.raises(PlanError):
        load_toutiao_plan(tmp_path / "nope")


def test_find_plan_by_content_id(tmp_path):
    root = make_package(tmp_path)
    plan = find_toutiao_plan(tmp_path, "ai/demo")
    assert plan.package_dir == root


def test_find_plan_explains_how_to_package(tmp_path):
    make_package(tmp_path)
    with pytest.raises(PlanError) as error:
        find_toutiao_plan(tmp_path, "ai/别的")
    assert "packages-only" in str(error.value)


def test_image_node_is_the_platform_markup():
    image = tt.UploadedImage(
        url="https://img.example/x~tplv-obj.image",
        uri="tos-cn-i-test/abc",
        width=2386,
        height=1198,
    )
    node = tt.build_image_node(image)
    assert node.startswith('<div class="pgc-img">')
    assert 'web_uri="tos-cn-i-test/abc"' in node
    assert 'img_width="2386"' in node
    assert 'img_height="1198"' in node
    assert "<p class=\"pgc-img-caption\"></p>" in node


def test_inject_images_replaces_the_marker():
    html = '<p>前</p><p style="text-align:center;">【图1】</p><p>后</p>'
    image = tt.UploadedImage(url="https://img/x", uri="tos/x", width=10, height=5)
    out, missing = tt.inject_images(html, {1: image})
    assert "【图1】" not in out
    assert 'class="pgc-img"' in out
    assert out.startswith("<p>前</p>")
    assert out.endswith("<p>后</p>")
    assert missing == []


def test_inject_images_keeps_markers_without_an_image():
    """没有图的占位符要留着——草稿里留着「【图2】」是在告诉人还缺图。"""
    html = '<p style="text-align:center;">【图1】</p><p style="text-align:center;">【图2】</p>'
    image = tt.UploadedImage(url="https://img/x", uri="tos/x", width=10, height=5)
    out, missing = tt.inject_images(html, {1: image})
    assert "【图2】" in out
    assert "【图1】" not in out
    assert missing == [2]


def test_inject_images_ignores_marker_text_inside_a_paragraph():
    """正文里提到「【图1】」不是图位，不能被换掉。"""
    html = "<p>这里说的【图1】是上一段那张</p>"
    image = tt.UploadedImage(url="https://img/x", uri="tos/x", width=10, height=5)
    out, missing = tt.inject_images(html, {1: image})
    assert out == html
    assert missing == []


def test_publish_payload_has_the_platform_fields():
    payload = tt.build_publish_payload(
        title="探针标题",
        content="<h2>小节</h2><p>正文</p>",
        word_count=414,
        draft_id="7708375734762340907",
        covers=[],
        cover_type=2,
        timer_time="2026-11-17 22:59",
    )
    assert payload["save"] == "0"
    assert payload["pgc_id"] == "7708375734762340907"
    assert payload["source"] == "29"
    assert payload["title"] == "探针标题"
    extra = json.loads(payload["extra"])
    assert extra["content_word_cnt"] == 414
    assert json.loads(payload["draft_form_data"]) == {"coverType": 2}
    assert json.loads(payload["pgc_feed_covers"]) == []


def test_publish_payload_carries_the_cover():
    covers = [tt._cover_entry(tt.UploadedImage(
        url="https://img/x~tplv-tt-cover-v2.image", uri="tos/x", width=1356, height=1056))]
    payload = tt.build_publish_payload(
        title="t", content="<p>x</p>", word_count=1, draft_id="1", covers=covers)
    stored = json.loads(payload["pgc_feed_covers"])
    assert len(stored) == 1
    assert stored[0]["thumb_width"] == 1356
    assert stored[0]["extra"] == {"from_content_uri": "", "from_content": "0"}


def test_config_reads_the_selectors_table():
    config = tt.ToutiaoConfig.load()
    assert config.upload_path == "/spice/image"
    assert config.publish_path == "/mp/agw/article/publish"
    assert config.upload_source_body == "20020002"


# -- 假的页面 -------------------------------------------------------------


class FakePage:
    """只记住调用，不发网络请求的页面。"""

    def __init__(self, upload_code=0):
        self.calls = []
        self.upload_code = upload_code

    def evaluate(self, script, argument):
        if "b64" in argument:
            self.calls.append(("upload", argument))
            code = self.upload_code
            return {
                "code": code,
                "message": "success" if code == 0 else "挂了",
                "data": {
                    "image_uri": "tos-cn-i-test/uri",
                    "image_url": "https://img.example/x~tplv-obj.image",
                    "image_width": 312,
                    "image_height": 200,
                    "image_mime_type": "image/webp",
                },
            }
        self.calls.append(("publish", argument))
        return {"code": 0, "data": {"content": "ok"}}


def test_uploader_uploads_the_images_then_saves(tmp_path):
    page = FakePage()
    plan = load_toutiao_plan(make_package(tmp_path))
    uploader = tt.ToutiaoUploader(page)
    result = uploader.fill_draft(plan, "7708375734762340907", images=plan.image_paths())

    kinds = [kind for kind, _ in page.calls]
    assert kinds == ["upload", "upload", "publish"]
    # 两次上传：正文图 + 封面
    assert "b64" in page.calls[0][1]
    # 存草稿的请求里带草稿 id —— 带 id 才是更新那一条
    fields = page.calls[-1][1]["fields"]
    assert fields["pgc_id"] == "7708375734762340907"
    assert fields["save"] == "0"
    assert 'class="pgc-img"' in fields["content"]
    assert result["uploaded"] == [1]
    assert result["missing"] == [2]
    assert result["cover"]


def test_uploader_reports_a_failed_upload(tmp_path):
    page = FakePage(upload_code=500)
    plan = load_toutiao_plan(make_package(tmp_path))
    uploader = tt.ToutiaoUploader(page)
    with pytest.raises(tt.ToutiaoError):
        uploader.fill_draft(plan, "7708375734762340907", images=plan.image_paths())
    # 上传失败就不该再发存草稿
    assert [kind for kind, _ in page.calls] == ["upload"]


def test_uploader_can_skip_the_cover(tmp_path):
    page = FakePage()
    plan = load_toutiao_plan(make_package(tmp_path))
    uploader = tt.ToutiaoUploader(page)
    result = uploader.fill_draft(plan, "1", images=plan.image_paths(), cover=False)
    assert result["cover"] is None
    fields = page.calls[-1][1]["fields"]
    assert json.loads(fields["pgc_feed_covers"]) == []


# -- 草稿 id ---------------------------------------------------------------


def _outbox(tmp_path: Path, payload: dict) -> Path:
    root = tmp_path / "outbox"
    root.mkdir(exist_ok=True)
    (root / "ai-demo__toutiao.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return root


def test_draft_id_is_read_from_the_snapshot(tmp_path):
    from browser.cli import _toutiao_draft_id

    root = _outbox(tmp_path, {"content_id": "ai/demo", "draft_id": "7708375734762340907",
                              "status": "drafted"})
    assert _toutiao_draft_id(root, "ai/demo") == "7708375734762340907"


def test_draft_id_refuses_when_the_snapshot_has_none(tmp_path):
    """没有草稿 id 就不能补图——新建出来的是另一条草稿，原草稿还在。"""
    from browser.cli import _toutiao_draft_id

    root = _outbox(tmp_path, {"content_id": "ai/demo", "status": "packaged"})
    with pytest.raises(PlanError) as error:
        _toutiao_draft_id(root, "ai/demo")
    assert "pgc_id" in str(error.value)


def test_draft_id_says_which_article_is_missing(tmp_path):
    from browser.cli import _toutiao_draft_id

    root = _outbox(tmp_path, {"content_id": "ai/别的", "draft_id": "1"})
    with pytest.raises(PlanError) as error:
        _toutiao_draft_id(root, "ai/demo")
    assert "ai/demo" in str(error.value)


# -- 真的浏览器 ------------------------------------------------------------


def test_uploader_runs_in_a_real_browser(page, tmp_path):
    """真的 Chromium + 替身 fetch：验那段 JS 胶水代码。

    这段最容易写错：base64 解回二进制、拼成 File、塞进 FormData；
    发请求时字段要按 application/x-www-form-urlencoded 编码。
    """
    page.goto(FIXTURE.as_uri())
    plan = load_toutiao_plan(make_package(tmp_path))
    uploader = tt.ToutiaoUploader(page)
    uploader.fill_draft(plan, "7708375734762340907", images=plan.image_paths())

    calls = page.evaluate("() => window.__calls")
    assert [call["kind"] for call in calls] == ["upload", "upload", "publish"]

    upload = calls[0]
    assert upload["filename"] == "01.webp"
    assert upload["type"] == "image/webp"
    assert upload["size"] > 0

    publish = calls[-1]
    assert publish["fields"]["pgc_id"] == "7708375734762340907"
    assert publish["fields"]["save"] == "0"
    assert 'class="pgc-img"' in publish["fields"]["content"]
