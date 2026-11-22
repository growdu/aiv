"""站点图片解析的接线守卫：基准是**图片副本**，不再是 ``docs/``。

hexo 侧的图片由 ``tools/build-posts.py`` 搬进 ``source/images/``，
正文里的相对路径由重写器改成 ``/images/<相对路径>``。
站点没有 JS 单测框架——所以这条守卫盯的是**接线**：
搬运的源是图片副本（``content/units/images/``），不是 ``docs/``。
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SITE = REPO_ROOT / "platforms" / "blog" / "site"

BUILD_POSTS = SITE / "tools" / "build-posts.py"


def test_the_site_resolves_images_against_the_image_copy():
    """产物落在 ``source/images/``。"""
    text = BUILD_POSTS.read_text(encoding="utf-8")
    assert 'SITE / "source" / "images"' in text, (
        "build-posts.py 没有把图片落进 source/images/"
    )
