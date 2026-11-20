"""Draw a cover card for a part that has no picture of its own.

549 of the 766 parts in the draft box had no picture at all -- 71.8%
of them -- so they all wore the same cover that ships with this tool.
The result was a list of several hundred drafts that look alike.

A card gives each one its own face: a two-tone background in a colour
derived from the article's slug, the category, and the topic of the
title.  The topic is the part of the title before its first boundary,
so the card says what the article is about without repeating the whole
title that is printed right above it.

Nothing here is required for publishing.  A machine without a Chinese
font cannot draw a card, and the caller falls back to the cover that
ships with the tool.
"""

from __future__ import annotations

import colorsys
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

__all__ = ["cover_card", "cover_text"]

WIDTH = 900
HEIGHT = 383

# The cover list of an official account is shown at 2.35:1.
_RATIO = WIDTH / HEIGHT

# Windows keeps its fonts in one directory; the name depends on the
# language pack, but these two are there on every Chinese Windows, and
# every Windows has the Latin ones.
_WINDOWS_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # Debian/Ubuntu 的 fonts-noto-cjk 装在这两个目录（容器镜像默认走
    # google-noto-cjk，桌面版发行版走 opentype/noto），两个都留着。
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    # Windows：微软雅黑（msyh.ttc）是中文版 Windows 自带的中文字体，
    # 黑体（simhei.ttf）次之。路径用 WINDIR 拼，不写死 C:。
    str(_WINDOWS_FONTS / "msyh.ttc"),
    str(_WINDOWS_FONTS / "msyhl.ttc"),
    str(_WINDOWS_FONTS / "simhei.ttf"),
    str(_WINDOWS_FONTS / "simsun.ttc"),
)

_FALLBACK_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows 的拉丁字体：arial.ttf 每台都有，segoeui.ttf 次之。
    str(_WINDOWS_FONTS / "arial.ttf"),
    str(_WINDOWS_FONTS / "segoeui.ttf"),
)

def _brand() -> str:
    """The brand word printed in the corner of the card.

    It is the host name of the site, taken from ``SITE_URL`` -- the same
    variable the site build uses.  **Without it there is no brand word**:
    the framework does not invent one.
    """
    url = os.environ.get("SITE_URL", "").strip()
    if not url:
        return ""
    return urlparse(url).netloc

# Bumped when the drawing changes, so that the cards already drawn are
# drawn again instead of being served from the cache.
_CARD_VERSION = 3


def _font(size: int, *, chinese: bool = True):
    """A font of that size, or None when the machine has none."""
    candidates = _FONTS if chinese else _FALLBACK_FONTS
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def _palette(seed: str):
    """Two colours and an accent, derived from the slug.

    The hues stay inside the brand's blue-to-violet range, so the
    cards look like one set even though no two are alike.
    """
    # 配色种子：本地内容指纹，只取第一个字节做色相。
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    hue = (195 + digest[0] % 55) / 360.0
    top = colorsys.hls_to_rgb(hue, 0.17, 0.55)
    bottom = colorsys.hls_to_rgb((hue + 0.035) % 1.0, 0.11, 0.30)
    accent = colorsys.hls_to_rgb((hue + 0.02) % 1.0, 0.58, 0.58)
    return (tuple(int(c * 255) for c in top),
            tuple(int(c * 255) for c in bottom),
            tuple(int(c * 255) for c in accent))


def _wrap(text: str, font, max_width: int) -> list:
    """Break the text into lines that fit.

    Chinese can break between any two characters, but an English word
    should not be broken in half, so words are kept together.  A bracketed
    group is kept together as well: the part number 「（六）」 belongs to
    the title, and a line that ends with 「（六」 while the next one
    starts with 「）」 looks broken.
    """
    lines = []
    current = ""
    for token in _tokens(text):
        candidate = current + token
        if current and font.getlength(candidate) > max_width:
            lines.append(current)
            current = token.lstrip()
        elif not current and font.getlength(token) > max_width:
            # A group that does not fit on a line of its own: break it
            # by characters, because there is nothing else to do.
            for char in token:
                if current and font.getlength(current + char) > max_width:
                    lines.append(current)
                    current = char
                else:
                    current += char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


# The brackets whose group has to stay on one line.
_BRACKETS = {
    "（": "）",
    "(": ")",
    "【": "】",
    "「": "」",
    "《": "》",
}


def _tokens(text: str) -> list:
    """The text as pieces that may not be broken apart."""
    tokens = []
    word = ""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in _BRACKETS:
            if word:
                tokens.append(word)
                word = ""
            closer = _BRACKETS[char]
            end = text.find(closer, index)
            if end < 0:
                # An unbalanced bracket is just a character.
                tokens.append(char)
                index += 1
                continue
            tokens.append(text[index:end + 1])
            index = end + 1
            continue
        if char.isascii() and (char.isalnum() or char in "-_.,:/"):
            word += char
            index += 1
            continue
        if word:
            tokens.append(word)
            word = ""
        tokens.append(char)
        index += 1
    if word:
        tokens.append(word)
    return tokens


def cover_text(title: str, part_index: int = 1, part_total: int = 1,
               limit: int = 18) -> str:
    """The text that goes on the card."""
    from .titles import topic

    head = topic(title, limit=limit)
    if part_total > 1:
        from .split import chinese_number

        head = "{}（{}）".format(head, chinese_number(part_index))
    return head


def cover_card(slug: str, title: str, category: str, out_dir: Path, *,
               part_index: int = 1, part_total: int = 1) -> Path:
    """Draw the cover card of one part and return its path.

    The file name carries a hash of what is drawn, so a card is drawn
    once and re-used until the title or the category changes.
    """
    text = cover_text(title, part_index, part_total)
    # 卡片文件名里的指纹：本地内容指纹，内容变了就该重画。
    # 品牌字样也算内容——它来自环境变量，换了域名就该重画。
    key = hashlib.sha256(
        "{}|{}|{}|{}|{}|{}".format(
            _CARD_VERSION, slug, title, category, text, _brand()).encode("utf-8")
    ).hexdigest()[:12]
    target_dir = Path(out_dir) / "covers"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "{}.png".format(key)
    if target.is_file():
        return target

    big = _font(54)
    small = _font(26)
    tiny = _font(22)
    if big is None or small is None:
        raise RuntimeError("no usable font for the cover card")

    top, bottom, accent = _palette(slug)
    image = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(image)

    # A vertical gradient, drawn band by band.
    for y in range(HEIGHT):
        ratio = y / max(HEIGHT - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=color)

    draw.rectangle([0, 0, 7, HEIGHT], fill=accent)

    margin = 62
    if category:
        draw.text((margin, 52), category, font=small, fill=(176, 192, 210))
    lines = _wrap(text, big, WIDTH - margin * 2)[:2]
    y = 104
    for line in lines:
        draw.text((margin, y), line, font=big, fill=(245, 248, 252))
        y += 68
    brand = _brand()
    if tiny is not None and brand:
        draw.text((margin, HEIGHT - 62), brand, font=tiny, fill=(132, 152, 175))

    image.save(target, "PNG")
    return target
