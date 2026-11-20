"""站点图片解析的接线守卫：基准是**图片副本**，不再是 ``docs/``。

站点的图片解析在 ``src/lib/remark-site-links.mjs`` 里（JS），
站点没有 JS 单测框架——所以这条守卫盯的是**接线**：
``astro.config.mjs`` 递给插件的那个基准，必须是图片副本，不是 ``docs/``。
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SITE = REPO_ROOT / "platforms" / "blog" / "site"

ASTRO = SITE / "astro.config.mjs"
PLUGIN = SITE / "src" / "lib" / "remark-site-links.mjs"


def test_the_site_resolves_images_against_the_image_copy():
    """基准是 ``public/images/``——站点不读 ``docs/``。"""
    text = ASTRO.read_text(encoding="utf-8")
    assert "imagesBase" in text, "astro.config.mjs 没有把 imagesBase 递给插件"
    assert "docsBase" not in text, "站点不该再把 docs/ 当成图片基准"
    assert re.search(r"imagesBase:\s*path\.join\([^)]*'public'[^)]*'images'",
                     text), "imagesBase 必须指向 public/images"


def test_the_plugin_resolves_images_against_the_image_base():
    text = PLUGIN.read_text(encoding="utf-8")
    assert "options.imagesBase" in text, "插件没有读 imagesBase 选项"
    assert "docsBase" not in text, "插件不该再拿 docs/ 当基准"
