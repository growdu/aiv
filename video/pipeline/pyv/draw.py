"""通用绘图原语。"""
from __future__ import annotations

import math

import cairo

from pyv import fonts
from pyv.palette import hex_to_rgb


def _set_source(ctx: cairo.Context, color: str, alpha: float = 1.0) -> None:
    r, g, b = hex_to_rgb(color)
    ctx.set_source_rgba(r, g, b, alpha)


def rounded_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float,
                 r: float, color: str, alpha: float = 1.0) -> None:
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()
    _set_source(ctx, color, alpha)
    ctx.fill()


def stroke_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float,
                r: float, color: str, width: float = 4.0, alpha: float = 1.0) -> None:
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()
    _set_source(ctx, color, alpha)
    ctx.set_line_width(width)
    ctx.stroke()


def arrow(ctx: cairo.Context, x1: float, y1: float, x2: float, y2: float,
          color: str, width: float = 6.0, head: float = 22.0,
          alpha: float = 1.0) -> None:
    _set_source(ctx, color, alpha)
    ctx.set_line_width(width)
    ctx.move_to(x1, y1)
    ctx.line_to(x2, y2)
    ctx.stroke()
    angle = math.atan2(y2 - y1, x2 - x1)
    for sign in (1, -1):
        a = angle + sign * math.radians(150)
        ctx.move_to(x2, y2)
        ctx.line_to(x2 + head * math.cos(a), y2 + head * math.sin(a))
    ctx.stroke()


def text(ctx: cairo.Context, s: str, x: float, y: float, size: float,
         color: str, anchor: str = "left", bold: bool = False,
         alpha: float = 1.0, family: str | None = None) -> None:
    """绘制一行文字，anchor 取 left / center / right。

    `family` 给了就画那一族（代码块用等宽那族）；不给就用当前解析到的
    中文字体。**不给就不给**——族名写死在调用点上的话，跨机器就对不上。

    **画之前查缺字**：字画不出来（豆腐块）就**当场报错**——
    成片里的一段方框比一次报错难懂得多。
    """
    fonts.check_glyphs(s, family)
    _set_source(ctx, color, alpha)
    fonts.select_font(ctx, family=family, bold=bold)
    ctx.set_font_size(size)
    width = ctx.text_extents(s).width
    if anchor == "center":
        x -= width / 2
    elif anchor == "right":
        x -= width
    ctx.move_to(x, y)
    ctx.show_text(s)


def text_width(ctx: cairo.Context, s: str, size: float,
               bold: bool = False, family: str | None = None) -> float:
    """量一行字的宽度。

    **也要走 `fonts.select_font`**：不选字体的话，量的是 ctx 上「上一个」
    字体，而且 hinting 没关——在 Linux 上量出来的宽度会跟 macOS 对不上。

    `bold` 要跟着画的时候一致：粗体的字宽不一样，量细体、画粗体，
    就会把「放不下」量成「放得下」。

    `family` 也要跟着画的时候一致：量一族、画另一族，宽度对不上。
    """
    fonts.select_font(ctx, family=family, bold=bold)
    ctx.set_font_size(size)
    return ctx.text_extents(s).width


def text_box_width(ctx: cairo.Context, labels, size: float,
                   bold: bool = False, padding: float = 12.0) -> float:
    """按最长的那一行字，反算一个能把它装下的框有多宽。

    **给的是「字 + 两侧留白」的宽度**，不是字宽本身。

    为什么要有这个：芯片的宽度常常是写死的比例，而操作名（INSERT /
    UPDATE / COMMIT）是数据——写死的宽度遇上更长的字，字就溢出芯片。
    溢出去的笔画落在芯片旁边的底色上，等于看不见：白字压浅灰底是
    1.05:1，读出来是「OMMIT」加半个 T。

    **字要放得下就加宽框，不缩字**：同一行里的芯片是同一件事的几种
    说法，字号必须一样，缩字会让这一行字号参差。
    """
    if not labels:
        return 0.0
    widest = max(text_width(ctx, str(label), size, bold=bold) for label in labels)
    return widest + 2 * padding
