"""Rasterise an SVG so that WeChat can take it.

WeChat accepts JPG and PNG only, and Pillow cannot read an SVG at all.
The corpus carries SVG files -- a logical decoding frame diagram, a
pile of Ubuntu theme icons -- and an article that shows one of them
could not be drafted at all.

A headless Chrome is already on this machine: the mermaid renderer
uses one to draw the diagrams.  The same browser draws the picture,
and the PNG it leaves behind is cached, so the drawing is done once.

Nothing here is required.  A machine without a browser keeps the old
behaviour: the SVG is reported as an unusable image and the article
that carries it is skipped.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import chrome as chrome_module

__all__ = ["rasterise", "svg_size"]

RENDER_TIMEOUT = chrome_module.RENDER_TIMEOUT

# The picture is drawn at its own size and then scaled down by the
# image preparation, so this is only a ceiling for the absurd ones.
MAX_RENDER_WIDTH = 2400
MAX_RENDER_HEIGHT = 2400

_SVG_ROOT = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_VIEWBOX = re.compile(
    r"viewBox\s*=\s*\"([\d.\-]+)[, ]+([\d.\-]+)[, ]+([\d.\-]+)[, ]+([\d.\-]+)\"")


def _find_chrome() -> str | None:
    """The browser that draws the picture, or ``None`` when there is none.

    Kept as a module-level name because the callers -- and the tests --
    ask this module where the browser is.
    """
    return chrome_module.find_chrome()


def _root_attributes(text: str) -> dict:
    match = _SVG_ROOT.search(text)
    if not match:
        return {}
    return {name.lower(): value for name, value in _ATTR.findall(match.group(0))}


def _length(value: str | None) -> int | None:
    """A length in pixels, ignoring the units we cannot use."""
    if not value:
        return None
    value = value.strip()
    match = re.match(r"^([\d.]+)", value)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    return int(number) if number > 0 else None


def svg_size(path: Path) -> tuple:
    """The size to draw the SVG at: ``(width, height)`` in pixels.

    The root element's own ``width`` and ``height`` win.  When it has
    none -- which is the usual case for a drawing exported from a
    vector editor -- the ``viewBox`` is used, which is the drawing's
    own coordinate system and therefore its true shape.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    attributes = _root_attributes(text)

    width = _length(attributes.get("width"))
    height = _length(attributes.get("height"))

    if width and height:
        return width, height

    box = _VIEWBOX.search(text)
    if box:
        box_width = _length(box.group(3))
        box_height = _length(box.group(4))
        if box_width and box_height:
            return box_width, box_height

    return width or 1200, height or 900


def rasterise(path: Path, out_dir: Path) -> Path:
    """Draw an SVG to a PNG and return the path of the PNG.

    The file name carries a hash of the drawing, so the picture is
    drawn once and re-used until the SVG changes.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("svg not found: {}".format(path))

    chrome = _find_chrome()
    if not chrome:
        raise ValueError(
            "SVG 需要浏览器才能转成 PNG，但这台机器上没有找到 Chrome: {}".format(path))

    width, height = svg_size(path)
    width = min(width, MAX_RENDER_WIDTH)
    height = min(height, MAX_RENDER_HEIGHT)

    # 缓存键：本地内容指纹，不是签名。
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    key = digest.hexdigest()[:16]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "{}.png".format(key)
    if target.is_file() and target.stat().st_size > 0:
        return target

    ok, detail = chrome_module.screenshot(
        chrome, target, width, height, path, timeout=RENDER_TIMEOUT)
    if not ok:
        raise ValueError("SVG 转 PNG 失败: {} —— {}".format(path, detail))

    return target
