"""外链图下载的测试。

**不联网**：用本地 HTTP 服务假装是图床。
验三件事：
- 默认**不下载**（出包不依赖网络，这条不能被悄悄改掉）；
- 显式要下载时，下载来的图真的打进包里了；
- 下不到的图仍然算「要人工处理」，不是让整篇失败。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from toutiao.assets import AssetUnreachable, fetch_remote_asset
from toutiao.capability import default_capability_path, load_capability
from toutiao.publish import write_package

CAP = load_capability(default_capability_path())


def _article(body="【图1】\n\n段落。", images=(), content_id="db/postgresql/demo"):
    from toutiao.contract import ToutiaoArticle

    return ToutiaoArticle(
        content_id=content_id,
        title="演示标题",
        digest="摘要",
        body=body,
        images=tuple(images),
        title_truncated=False,
        body_truncated=False,
        dropped_links=0,
        notes=(),
    )


def _images_root(tmp_path):
    """The image repository root -- the same shape as the real one."""
    root = tmp_path / "content" / "units" / "images"
    root.mkdir(parents=True)
    return root


@pytest.fixture
def picture_server():
    """一个假图床：``/a.png`` 给一张 PNG，``/missing.png`` 给 404。"""
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (1200, 900), (10, 20, 30)).save(buffer, "PNG")
    payload = buffer.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802 -- BaseHTTPRequestHandler 的约定
            if self.path == "/a.png":
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{}".format(server.server_port)
    finally:
        server.shutdown()
        server.server_close()


def test_fetch_remote_asset_downloads_a_picture(picture_server):
    data = fetch_remote_asset(picture_server + "/a.png")
    with Image.open(__import__("io").BytesIO(data)) as image:
        assert image.size == (1200, 900)


def test_fetch_remote_asset_says_when_it_cannot_download(picture_server):
    with pytest.raises(AssetUnreachable):
        fetch_remote_asset(picture_server + "/missing.png")


def test_remote_images_are_not_downloaded_by_default(tmp_path, picture_server):
    """默认不下载：出包不依赖网络，这条不能被悄悄改掉。"""
    images_root = _images_root(tmp_path)
    article = _article(images=(picture_server + "/a.png",))
    result = write_package(article, CAP, tmp_path / "out", images_root, "https://growdu.cn")
    assert not (result.package_dir / "images" / "01.webp").exists()
    readme = (result.package_dir / "README.md").read_text(encoding="utf-8")
    assert "需人工下载" in readme


def test_fetch_remote_packs_the_downloaded_picture(tmp_path, picture_server):
    """显式要下载时，下载来的图真的打进包里了。"""
    images_root = _images_root(tmp_path)
    article = _article(images=(picture_server + "/a.png",))
    result = write_package(article, CAP, tmp_path / "out", images_root, "https://growdu.cn",
                           fetch_remote=True)
    packed = result.package_dir / "images" / "01.webp"
    assert packed.is_file()
    with Image.open(packed) as image:
        assert image.format == "WEBP"
    meta = json.loads((result.package_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["images"][0]["file"] == "images/01.webp"
    readme = (result.package_dir / "README.md").read_text(encoding="utf-8")
    assert "需人工下载" not in readme


def test_a_picture_that_cannot_be_downloaded_stays_a_human_job(tmp_path, picture_server):
    """下不到的图不算失败 —— 这一篇照样能发，只是少一张图。"""
    images_root = _images_root(tmp_path)
    article = _article(images=(picture_server + "/missing.png",))
    result = write_package(article, CAP, tmp_path / "out", images_root, "https://growdu.cn",
                           fetch_remote=True)
    assert result.status == "packaged"
    assert not (result.package_dir / "images" / "01.webp").exists()
    readme = (result.package_dir / "README.md").read_text(encoding="utf-8")
    assert "需人工下载" in readme
