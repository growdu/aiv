"""抖音发表流程的测试。

三层：
1. **纯逻辑**——描述怎么拼、字数过不过、平台返回怎么读出作品 id、
   列表里的状态怎么认；
2. **假的驱动**——发布这一步到底点了什么、等的是哪条响应；
3. **真的浏览器**（本地假页面 + 本地服务器）——验那段界面操作：
   文件框、标题框、富文本描述框、字数计数器、点发布等响应。

第 3 层要本地服务器：假页面点「发布」会真的 POST 一个请求，
执行器靠**网络响应**读作品 id，所以那个请求必须真的发出去
（页面里把 fetch 换掉的话，Playwright 收不到响应事件）。
"""

import json
import threading
from pathlib import Path

import pytest

from browser.flows import douyin as dy
from browser.plan import PlanError, find_douyin_plan, load_douyin_plan

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ITEM_ID = "7709123013601463579"


# -- 夹具 -------------------------------------------------------------------


def make_package(tmp_path: Path) -> Path:
    """一个假的抖音发布包（结构照 platforms/douyin/out/<期号>/ 来）。"""
    root = tmp_path / "csn-total-ordering"
    root.mkdir()
    (root / "title.txt").write_text("一个单调递增的号，决定事务的提交顺序", encoding="utf-8")
    (root / "description.txt").write_text("并发提交的时间顺序是乱的。", encoding="utf-8")
    (root / "topics.txt").write_text("#openGauss #逻辑复制 #数据库 #源码", encoding="utf-8")
    (root / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    (root / "cover_3x4.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    (root / "cover_4x3.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    (root / "meta.json").write_text(
        json.dumps({"episode": "csn-total-ordering", "status": "packaged"},
                   ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture
def douyin_server():
    """本地服务器：假页面 + 一个会回 item_id 的发布接口。

    **为什么要服务器而不是 file://**：假页面点「发布」要发一个**真的**
    HTTP 请求，执行器靠网络响应读作品 id；file:// 下发不出去。
    """
    import functools
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # 别把测试日志刷满
            pass

        def do_POST(self):  # noqa: N802 - http.server 的命名
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            body = json.dumps({"status_code": 0, "item_id": ITEM_ID}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    handler = functools.partial(Handler, directory=str(FIXTURES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def douyin_selectors(tmp_path, douyin_server):
    """指向本地假页面的选择器表。"""
    raw = json.loads((Path(__file__).resolve().parents[1] / "selectors" / "douyin.json")
                     .read_text(encoding="utf-8"))
    raw["origin"] = douyin_server
    raw["upload_path"] = "/douyin-upload.html"
    raw["post_path"] = "/douyin-upload.html"
    raw["works_path"] = "/douyin-upload.html"
    target = tmp_path / "douyin-selectors.json"
    target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return target


# -- 纯逻辑 ---------------------------------------------------------------


def test_description_holds_the_body_and_the_topics():
    text = dy.build_description("并发提交的时间顺序是乱的。", ["openGauss", "源码"])
    assert text == "并发提交的时间顺序是乱的。\n#openGauss #源码"


def test_description_without_topics_is_just_the_body():
    assert dy.build_description("只有正文", []) == "只有正文"


def test_description_without_body_is_just_the_topics():
    assert dy.build_description("", ["源码"]) == "#源码"


def test_limits_reject_a_too_long_title():
    problems = dy.check_limits("标" * 31, "正文", [])
    assert any("标题" in problem for problem in problems)


def test_limits_reject_a_too_long_description():
    problems = dy.check_limits("标题", "字" * 1001, [])
    assert any("描述" in problem for problem in problems)


def test_limits_reject_too_many_topics():
    problems = dy.check_limits("标题", "正文", ["a", "b", "c", "d", "e", "f"])
    assert any("话题" in problem for problem in problems)


def test_limits_accept_a_normal_package():
    assert dy.check_limits("一个单调递增的号", "正文", ["源码"]) == []


def test_counters_are_read_by_the_limit():
    assert dy.parse_counters(["18/30", "141 / 1000"]) == {"30": 18, "1000": 141}


def test_create_response_gives_the_item_id():
    payload = {"extra": {"logid": "x"}, "item_id": ITEM_ID, "status_code": 0}
    assert dy.parse_create_response(payload) == ITEM_ID


def test_create_response_refuses_a_failed_publish():
    """平台失败时也会给 item_id——那一条没发出去，不能当已发布。"""
    with pytest.raises(dy.DouyinError):
        dy.parse_create_response({"item_id": ITEM_ID, "status_code": 8})


def test_create_response_needs_an_item_id():
    with pytest.raises(dy.DouyinError):
        dy.parse_create_response({"status_code": 0})


def test_public_url_is_the_douyin_video_link():
    assert dy.public_url(ITEM_ID) == f"https://www.douyin.com/video/{ITEM_ID}"


def test_works_count_comes_from_the_page():
    assert dy.count_works("作品 (2)\n作品合集 (1)") == 2
    assert dy.count_works("作品合集 (1)") == 0


def test_work_status_is_the_word_after_the_title():
    text = ("作品 (2)\n一个单调递增的号，决定事务的提交顺序 并发提交…\n"
            "2026年11月17日 20:54\n审核中\n播放\n")
    assert dy.parse_work_status(text, "一个单调递增的号") == "审核中"


def test_work_status_is_none_when_the_title_is_not_there():
    assert dy.parse_work_status("作品 (1)\n别的作品", "一个单调递增的号") is None


def test_the_default_selectors_file_is_where_the_code_thinks_it_is():
    """默认选择器表的路径必须真的存在。

    挡的是一类很闷的错：路径少算一层目录，程序不报错，
    只是「选择器表不存在」——而那时人已经打开浏览器了。
    """
    assert dy.DEFAULT_SELECTORS_PATH.is_file()
    assert dy.DEFAULT_SELECTORS_PATH.name == "douyin.json"
    assert dy.DEFAULT_SELECTORS_PATH.parent.name == "selectors"


def test_config_reads_the_selectors_table():
    config = dy.DouyinConfig.load()
    assert config.origin == "https://creator.douyin.com"
    assert config.publish_path == "/web/api/media/aweme/create_v2/"
    assert config.limit("title_chars", 30) == 30
    assert config.need("title_input")


def test_plan_reads_the_package(tmp_path):
    plan = load_douyin_plan(make_package(tmp_path))
    assert plan.episode == "csn-total-ordering"
    assert plan.title == "一个单调递增的号，决定事务的提交顺序"
    assert plan.topics == ["openGauss", "逻辑复制", "数据库", "源码"]
    assert plan.video is not None and plan.video.is_file()
    assert plan.cover_vertical is not None and plan.cover_vertical.is_file()
    assert plan.cover_horizontal is not None and plan.cover_horizontal.is_file()
    # 描述框里是「正文 + 换行 + 话题」——标题不进描述框
    assert plan.description_with_topics() == (
        "并发提交的时间顺序是乱的。\n#openGauss #逻辑复制 #数据库 #源码")


def test_find_plan_by_episode(tmp_path):
    root = make_package(tmp_path)
    assert find_douyin_plan(tmp_path, "csn-total-ordering").package_dir == root


def test_find_plan_says_how_to_package(tmp_path):
    make_package(tmp_path)
    with pytest.raises(PlanError) as error:
        find_douyin_plan(tmp_path, "别的")
    assert "douyin.cli package" in str(error.value)


# -- 假的驱动 ---------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeWatcher:
    def __init__(self, response):
        self.response = response

    def wait(self, *, timeout_ms=60000):
        return self.response

    def close(self):
        pass


class FakeDriver:
    """只记住调用，不开浏览器的驱动。"""

    def __init__(self, response=None, body=""):
        self.calls = []
        self.response = response
        self.body = body

    def wait_for(self, selector, *, state="visible", timeout_ms=None):
        self.calls.append(("wait_for", selector))

    def fill(self, selector, text):
        self.calls.append(("fill", text))

    def upload(self, selector, path):
        self.calls.append(("upload", str(path)))

    def body_text(self):
        return self.body

    def click(self, selector):
        self.calls.append(("click", selector))

    def watch_response(self, matcher):
        self.calls.append(("watch", matcher))
        return FakeWatcher(self.response)


class FakePage:
    def __init__(self, driver):
        self.driver = driver
        self.goto_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script):
        return ["18/30", "141 / 1000"]


def test_submit_reads_the_item_id_from_the_publish_response():
    driver = FakeDriver(response=FakeResponse({"status_code": 0, "item_id": ITEM_ID}))
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    assert flow.submit() == ITEM_ID
    kinds = [kind for kind, _ in driver.calls]
    assert kinds == ["watch", "click"]


def test_submit_fails_loudly_when_the_response_never_comes():
    driver = FakeDriver(response=None)
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    with pytest.raises(dy.DouyinError):
        flow.submit()


def test_wait_form_ready_refuses_a_failed_upload():
    driver = FakeDriver(body="上传失败，重新上传")
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    with pytest.raises(dy.DouyinError) as error:
        flow.wait_form_ready(timeout_ms=2000)
    assert "上传失败" in str(error.value)


def test_upload_video_says_so_when_the_cut_is_missing(tmp_path):
    """成片不在就当场报错，别传个空文件上去。

    空文件传上去页面照样出表单，失败要等到平台那边才看得见——
    报错得在这里，不是在那儿。
    """
    driver = FakeDriver()
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    with pytest.raises(dy.DouyinError) as error:
        flow.upload_video(tmp_path / "没有这个.mp4")
    assert "成片不存在" in str(error.value)
    assert not [kind for kind, _ in driver.calls]  # 没往上传


def test_upload_video_says_so_when_the_package_has_no_cut():
    """包里压根没有成片（``plan.video`` 是 None）时也要说人话。"""
    driver = FakeDriver()
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    with pytest.raises(dy.DouyinError) as error:
        flow.upload_video(None)
    assert "没有成片" in str(error.value)
    assert not [kind for kind, _ in driver.calls]  # 没往上传


def test_counters_are_read_from_the_page():
    driver = FakeDriver()
    driver.page = FakePage(driver)
    flow = dy.DouyinFlow(driver, dy.DouyinConfig.load())
    assert flow.read_counters() == {"30": 18, "1000": 141}


# -- 真的浏览器 ------------------------------------------------------------


def test_publish_runs_in_a_real_browser(page, tmp_path, douyin_selectors):
    """真的 Chromium + 本地服务器：走一遍上传 → 填表 → 发表。

    这条验的是最容易写错的地方：文件框的选择器、富文本描述框怎么敲字、
    字数计数器读得对不对、以及**点发布之后能从网络响应里读出作品 id**。
    """
    from browser.driver import PageDriver

    plan = load_douyin_plan(make_package(tmp_path))
    config = dy.DouyinConfig.load(douyin_selectors)
    flow = dy.DouyinFlow(PageDriver(page, timeout_ms=15000), config)

    flow.open_upload()
    flow.upload_video(plan.video)
    flow.wait_form_ready(timeout_ms=30000)
    flow.fill_text(plan.title, plan.description_with_topics())

    counters = flow.read_counters()
    assert counters.get("30") == len(plan.title)
    assert counters.get("1000") == len(plan.description_with_topics())

    item_id = flow.submit(timeout_ms=30000)
    assert item_id == ITEM_ID
    assert dy.public_url(item_id) == f"https://www.douyin.com/video/{ITEM_ID}"
