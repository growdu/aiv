"""通用渲染器（`pyv/generic/`）的守卫。

**这四个渲染器不进 `pyv/scenes/`**（见 `publish/plans/10-母稿画面资产与通用渲染器.md`
的 D2），所以它们**没有**逐像素基准，也没有 `scenes/` 那两条按目录扫的守卫。
这一套就是它们的守卫——**元素级**的：

| 守卫 | 管什么 |
| --- | --- |
| `test_no_text_overlaps_another_text` | 字压字 |
| `test_every_text_stays_inside_its_block` | 字从自己那块底色上溢出去 |
| `test_every_drawn_character_is_in_the_bundled_font` | 豆腐块 |
| `test_the_..._renderer_says_what_did_not_fit` | 静默截断 |

**为什么元素级就够了**：通用渲染器画的是**母稿里的内容**（代码、表格、
图），母稿不在仓库里（内容不入库），逐像素基准根本抓不出来——母稿一换，
基准就红。能抓的只有「排版关系」：字与字、字与底色、字与字体。

**不许静默**这条是这一层的核心：通用渲染器拿到的内容可能很长（母稿里的
一段长 SQL），放不下就收字号，收到下限还放不下就**在画面上明说**
（「还有几行没画上」）。静默截断的代价是：观众看到一段没有画完的代码，
而**画面照样生成、时长照样对**，没有任何报错。
"""
from __future__ import annotations

import cairo
import pytest

from pyv import draw
from pyv import render as render_mod
from pyv.generic import common
from pyv.generic import gen_card, gen_code, gen_mermaid, gen_table
from pyv.palette import hex_to_rgb
from pyv.params import MissingParam

import scene_probe

#: 两个画幅。
CANVASES = ((1920, 1080), (1080, 1920))

#: 内置字体子集（缺字就红的那一份）由 `pyv.fonts` 指路。

SQL = """SELECT id, name
FROM accounts
WHERE balance > 100
ORDER BY created_at DESC;"""

PY = """def total(rows):
    return sum(row["amount"] for row in rows)"""

TABLE = """| mode | who locks | on conflict |
| --- | --- | --- |
| FOR UPDATE | writer | wait |
| FOR SHARE | reader | deadlock |"""


# ------------------------------------------------------------------ 夹具


def _frame(renderer, params, w, h, monkeypatch):
    """画一帧，把画面上画过的字与底色都记下来。"""
    return scene_probe.probe_frame(renderer, params, 0.5, w, h, monkeypatch)


def _luminance(color: str) -> float:
    r, g, b = hex_to_rgb(color)

    def channel(value: float) -> float:
        if value <= 0.03928:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(first: str, second: str) -> float:
    """两个颜色的对比度（WCAG 的算法）。"""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _holding_color(probe, text) -> str:
    """托着这处字的那块底色（最紧的那块）的颜色。"""
    candidates = [rect for rect in probe.rects if rect.holds(text)]
    assert candidates, f"这处字底下没有底色：{text}"
    return min(candidates, key=lambda rect: rect.area).color


# ------------------------------------------------------------ 通用渲染器


@pytest.mark.parametrize("module,params", [
    (gen_code, {"content": SQL, "lang": "sql"}),
    (gen_code, {"content": PY, "lang": "python"}),
    (gen_table, {"content": TABLE}),
    (gen_card, {"title": "Chapter", "items": ["one", "two"]}),
    (gen_mermaid, {"content": "graph TD\n  A --> B"}),
])
@pytest.mark.parametrize("size", CANVASES)
def test_the_generic_renderers_draw_in_both_canvases(module, params, size,
                                                      monkeypatch):
    """两个画幅都要画得出来——竖版（抖音）是另一个画幅，不是缩放。"""
    w, h = size
    probe = _frame(module.render, params, w, h, monkeypatch)
    assert probe.texts, f"{module.__name__} 在 {w}x{h} 上一处字都没画"


@pytest.mark.parametrize("module,params", [
    (gen_code, {"content": SQL, "lang": "sql"}),
    (gen_code, {"content": PY, "lang": "python"}),
    (gen_table, {"content": TABLE}),
    (gen_card, {"title": "Chapter", "subtitle": "sub",
                "items": ["one point", "another point that is longer"]}),
    (gen_mermaid, {"content": "graph TD\n  A --> B"}),
])
@pytest.mark.parametrize("size", CANVASES)
def test_no_text_overlaps_another_text(module, params, size, monkeypatch):
    """字不许压字。

    两行字挨着但没压上是正常的——判据是**墨迹包围盒**相交，
    不是行高相交（行高比墨迹高一大截，挨着的两行会被误判）。
    """
    w, h = size
    probe = _frame(module.render, params, w, h, monkeypatch)
    for index, first in enumerate(probe.texts):
        for second in probe.texts[index + 1:]:
            overlap_x = min(first.x1, second.x1) - max(first.x0, second.x0)
            overlap_y = min(first.y1, second.y1) - max(first.y0, second.y0)
            assert not (overlap_x > 1 and overlap_y > 1), (
                f"两处字压住了：{first} 与 {second}"
            )


@pytest.mark.parametrize("module,params", [
    (gen_code, {"content": SQL, "lang": "sql"}),
    (gen_table, {"content": TABLE}),
    (gen_card, {"title": "Chapter", "items": ["one point", "another one"]}),
])
@pytest.mark.parametrize("size", CANVASES)
def test_every_text_stays_inside_its_block(module, params, size, monkeypatch):
    """字不许从托着它的那块底色上溢出去，也不许跑出画布。

    溢出去的字落在画布白底上——浅色的字压白底就是看不见，
    而画面照样生成、时长照样对。

    **跑出画布也要抓**：场景探针的 `overflows` 只查「字落在哪块底色
    里面」——一个字要是**整块跑到所有底色之外**（比如画到了画布边上），
    它就没有「托着它的底色」，探针一个都报不出来。画布边界是兜底。
    """
    w, h = size
    probe = _frame(module.render, params, w, h, monkeypatch)
    hits = probe.overflows()
    assert not hits, (
        "这些字从自己的底色上溢出去了："
        + "；".join(f"{text}（超出 {over:.1f}px）" for text, _, over in hits)
    )
    for text in probe.texts:
        assert text.x0 >= 0 and text.x1 <= w, (
            f"{text} 跑出画布了（左右 {text.x0:.0f}→{text.x1:.0f}，画布 {w}）"
        )
        assert text.y0 >= 0 and text.y1 <= h, (
            f"{text} 跑出画布了（上下 {text.y0:.0f}→{text.y1:.0f}，画布 {h}）"
        )


def test_every_drawn_character_is_in_the_bundled_font(monkeypatch):
    """画出去的字都要在**内置字体子集**里（不许有豆腐块）。

    内置字体是按「仓库用到的字符」子集化的。母稿里的字来自 `docs/`，
    真实期目录进来时要单独量一遍（计划二的遗留项）；这里量的是
    **通用渲染器自己画的那部分**——系统提示（`+N more lines` 那些）
    与版式标签。
    """
    from fontTools.ttLib import TTFont

    from pyv import fonts

    cmap = TTFont(str(fonts.BUNDLED_REGULAR_PATH)).getBestCmap()
    drawn: set[str] = set()
    original = draw.text

    def recorder(ctx, s, x, y, size, color, anchor="left", bold=False,
                 alpha=1.0, family=None):
        drawn.update(s)
        return None

    monkeypatch.setattr(draw, "text", recorder)
    for module, params in (
        (gen_code, {"content": SQL, "lang": "sql"}),
        (gen_table, {"content": TABLE}),
        (gen_card, {"title": "Chapter", "items": ["one point"]}),
    ):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
        ctx = cairo.Context(surface)
        module.render(ctx, 0.5, 320, 180, params)

    missing = sorted(ch for ch in drawn if ord(ch) not in cmap)
    assert not missing, (
        f"通用渲染器画出了内置字体里没有的字：{missing}——"
        f"跑 scripts/build_font_subset.py 重生成子集"
    )


# -------------------------------------------------------------- 代码块


def test_the_code_renderer_highlights_the_keywords(monkeypatch):
    """关键字与普通字要**颜色不同**——高亮没生效等于没高亮。

    实测踩过的坑：pygments 的 token 打印出来是 `Token.Keyword`，
    按字符串查表永远查不到，于是每一段代码都是同一种深色——
    高亮「看着像没生效」，而画面、时长、退出码全对。
    """
    probe = _frame(gen_code.render, {"content": SQL, "lang": "sql"},
                   1920, 1080, monkeypatch)
    colors = {text.label: text.color for text in probe.texts}
    assert "SELECT" in colors, f"关键字没画出来：{colors}"
    assert "id" in colors, f"普通字没画出来：{colors}"
    assert colors["SELECT"] != colors["id"], (
        "关键字与普通字一个颜色——高亮没生效"
    )


def _draw_calls(monkeypatch, module, params, w, h) -> list[tuple]:
    """这一帧每一次 `draw.text` 的 `(字, x, 基线 y)`。

    **不漏掉纯空格的调用**：场景探针（`tests/scene_probe.py`）会跳过
    `s.strip()` 为空的调用——那是它要的（「一块空白」不算一处字），
    但这里要的恰恰是那些空格：**空格丢了就是「SELECTid」**。
    """
    calls: list[tuple] = []

    def recorder(ctx, s, x, y, size, color, anchor="left", bold=False,
                 alpha=1.0, family=None):
        calls.append((s, x, y))
        return None

    monkeypatch.setattr(draw, "text", recorder)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    module.render(ctx, 0.5, w, h, params)
    return calls


def _lines_from_calls(calls: list[tuple]) -> list[str]:
    """把画出去的字按行拼回去。"""
    rows: dict[int, list] = {}
    for label, x, y in calls:
        rows.setdefault(round(y), []).append((x, label))
    return ["".join(label for _, label in sorted(items))
            for _, items in sorted(rows.items())]


def test_the_code_renderer_keeps_every_character(monkeypatch):
    """一个字都不许丢——**空格也算字**。

    实测踩过的坑：按「墨迹宽度」排版（`text_extents().width` 是墨迹
    包围盒，行尾那个空格一个字宽都不占），「SELECT id, name」就排成
    「SELECTid, name」——每一段单独看都没错，逐帧看图才发现。
    """
    calls = _draw_calls(monkeypatch, gen_code,
                        {"content": SQL, "lang": "sql"}, 1920, 1080)
    drawn = _lines_from_calls(calls)
    for line in SQL.split("\n"):
        if not line.strip():
            continue
        assert line in drawn, f"这一行拼不回去了：{line!r}（画出来的是 {drawn}）"


def test_the_code_renderer_keeps_the_gap_after_every_space(monkeypatch):
    """空格要**留出空隙**——不只是「画了一个空格」。

    实测踩过的坑：按「墨迹宽度」推进游标（`text_extents().width` 是
    墨迹包围盒，空格的墨迹宽是 0），「SELECT id」就排成「SELECTid」。

    **光看画出去的字看不出来**（每一段都对），要量**位置**：空格那一段
    与下一段之间必须留得出空隙。阈值写成字面量（字号的 10%）。
    """
    calls = _draw_calls(monkeypatch, gen_code,
                        {"content": SQL, "lang": "sql"}, 1920, 1080)
    rows: dict[int, list] = {}
    for label, x, y in calls:
        rows.setdefault(round(y), []).append((x, label))
    gaps = 0
    for items in rows.values():
        items.sort()
        for (x, label), (next_x, _) in zip(items, items[1:]):
            if label == " ":
                gaps += 1
                assert next_x - x >= 0.1 * common.BASE_SIZE, (
                    f"空格后面没有空隙（{next_x - x:.1f}px）——"
                    f"「SELECT id」被排成了「SELECTid」"
                )
    assert gaps, "这一帧里一个空格都没有——夹具没画出来，查守卫本身"


def test_the_code_renderer_says_how_many_lines_did_not_fit(monkeypatch):
    """太长时要在画面上**明说**还差几行，不许静默截断。"""
    long_code = "\n".join(f"SELECT col_{index} FROM t_{index};" for index in
                          range(80))
    probe = _frame(gen_code.render, {"content": long_code, "lang": "sql"},
                   1920, 1080, monkeypatch)
    notices = [text.label for text in probe.texts if "more lines" in text.label]
    assert notices, "放不下的行没被说出来——静默截断了"
    assert notices[0].startswith("+"), notices[0]


# --------------------------------------------------------------- 表格


def test_the_table_renderer_draws_every_column(monkeypatch):
    probe = _frame(gen_table.render, {"content": TABLE}, 1920, 1080, monkeypatch)
    labels = {text.label for text in probe.texts}
    for name in ("mode", "who locks", "on conflict"):
        assert name in labels, f"表头少了 {name}：{labels}"
    assert "FOR UPDATE" in labels
    assert "deadlock" in labels


def test_a_long_cell_does_not_reach_the_next_column(monkeypatch):
    """某一列的字太长，**不许压到邻列**。

    判据用墨迹：右边界不许越过下一列的左边界。
    """
    table = ("| a | b |\n| --- | --- |\n"
             "| a very long cell value here | short |")
    probe = _frame(gen_table.render, {"content": table}, 1920, 1080, monkeypatch)
    cells = {text.label: text for text in probe.texts}
    left = cells["a very long cell value here"]
    right = cells["short"]
    assert left.x1 <= right.x0 + 1, (
        f"左边那格伸到右边那格上去了：{left} 与 {right}"
    )


def test_the_table_renderer_says_how_many_rows_did_not_fit(monkeypatch):
    rows = "\n".join(f"| r{index} | v{index} |" for index in range(60))
    table = f"| a | b |\n| --- | --- |\n{rows}"
    probe = _frame(gen_table.render, {"content": table}, 1920, 1080, monkeypatch)
    notices = [text.label for text in probe.texts if "rows" in text.label]
    assert notices, "放不下的行没被说出来——静默截断了"
    assert notices[0].startswith("+"), notices[0]


# --------------------------------------------------------------- 卡片


def test_the_card_renderer_draws_the_title_and_the_items(monkeypatch):
    probe = _frame(gen_card.render,
                   {"title": "Chapter 3", "items": ["first point", "second"]},
                   1920, 1080, monkeypatch)
    labels = {text.label for text in probe.texts}
    assert "Chapter 3" in labels
    assert "first point" in labels
    assert "second" in labels


def test_an_empty_item_list_still_draws_the_title(monkeypatch):
    """空列表就是「章节卡」——不炸。"""
    probe = _frame(gen_card.render, {"title": "Chapter 3"}, 1920, 1080,
                   monkeypatch)
    assert "Chapter 3" in {text.label for text in probe.texts}


def test_the_card_renderer_shrinks_the_font_when_the_items_do_not_fit(
        monkeypatch):
    """要点装不下就收字号——不许压出去。"""
    items = [f"point number {index} with a long tail" for index in range(40)]
    probe = _frame(gen_card.render, {"title": "Chapter", "items": items},
                   1920, 1080, monkeypatch)
    sizes = [text.size for text in probe.texts if text.label.startswith("point")]
    assert sizes, "要点没画出来"
    assert min(sizes) < common.BASE_SIZE, (
        f"要点没收字号（{min(sizes)}）——要么压出去，要么被截掉"
    )


def test_the_card_text_is_readable_on_its_own_block(monkeypatch):
    """**字与底色必须有对比度**——深底深字是读不出来的。

    实测踩过的坑：整张卡涂成深色，要点却用深色的正文色——
    逐帧看图才发现「一条都读不出来」，而画面、时长、退出码全对。
    """
    probe = _frame(gen_card.render,
                   {"title": "Chapter 3", "subtitle": "sub",
                    "items": ["first point", "second point"]},
                   1920, 1080, monkeypatch)
    for text in probe.texts:
        background = _holding_color(probe, text)
        ratio = _contrast(text.color, background)
        assert ratio >= 4.5, (
            f"{text} 的对比度只有 {ratio:.2f}（{text.color} on "
            f"{background}）——读不出来"
        )


# ------------------------------------------------------------- mermaid


def _fake_asset(tmp_path, error=None):
    """一份假的 mermaid 产物：有 PNG 或者只有失败原因。"""
    from pathlib import Path

    from pyv import mermaid

    if error is None:
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        ctx = cairo.Context(image)
        ctx.set_source_rgb(0.1, 0.4, 0.8)
        ctx.paint()
        png = tmp_path / "graph.png"
        image.write_to_png(str(png))
        return mermaid.MermaidAsset(key="k", source="graph TD\n  A --> B",
                                    png=Path(png))
    return mermaid.MermaidAsset(key="k", source="graph TD\n  A --> B",
                                png=None, error=error)


def test_the_mermaid_renderer_pastes_the_png(tmp_path, monkeypatch):
    """有 PNG 就贴进画面（等比缩放、居中）。"""
    asset = _fake_asset(tmp_path)
    monkeypatch.setattr(gen_mermaid, "asset_for", lambda source: asset)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
    ctx = cairo.Context(surface)
    gen_mermaid.render(ctx, 0.5, 1920, 1080, {"content": "graph TD\n  A --> B"})
    surface.flush()
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    # 图是蓝色的，画面上就该有那一块蓝。
    # **内存里是 BGRA**（cairo 的 ARGB32 小端序）：第 0 个字节是蓝。
    blues = 0
    for y in range(0, 1080, 4):
        row = data[y * stride:(y + 1) * stride]
        for x in range(0, 1920, 4):
            pixel = row[x * 4:x * 4 + 3]
            if pixel[0] > 150 and pixel[2] < 80:
                blues += 1
    assert blues > 100, "PNG 没贴进画面"


def test_the_mermaid_renderer_degrades_visibly(tmp_path, monkeypatch):
    """渲染不出来时，画面上要**看得见**地降级：源码 + 失败原因。

    静默跳过会让观众看到一段没有画面的旁白，而成片照样生成、
    时长照样对——这是规格 §6.2 点名的失败模式。
    """
    asset = _fake_asset(tmp_path, error="mermaid-cli not found")
    monkeypatch.setattr(gen_mermaid, "asset_for", lambda source: asset)

    probe = _frame(gen_mermaid.render, {"content": "graph TD\n  A --> B"},
                   1920, 1080, monkeypatch)
    labels = " | ".join(text.label for text in probe.texts)
    assert "graph TD" in labels, f"画面上没有图表源码：{labels}"
    assert "mermaid-cli not found" in labels, f"画面上没有失败原因：{labels}"


# ---------------------------------------------------------------- 接线


def test_the_generic_renderer_names_are_importable():
    """契约按名字点名就要能用——名字错了当场报错，不许静默。"""
    from pyv import derive

    for kind, name in derive.GENERIC_RENDERERS.items():
        module = render_mod.load_renderer(name)
        assert callable(module.render), f"{kind} 的 {name} 没有 render"
        assert isinstance(module.REQUIRED, tuple), f"{kind} 的 {name} 没有 REQUIRED"


def test_a_missing_renderer_is_an_error_not_a_silent_skip():
    try:
        render_mod.load_renderer("pyv.generic.gen_does_not_exist")
    except ValueError as exc:
        assert "gen_does_not_exist" in str(exc)
    else:
        raise AssertionError("渲染器不存在时应当报错")


def test_a_renderer_without_content_refuses_to_draw_a_blank_panel(monkeypatch):
    """拿不到内容就报错——不许画一个空面板当画面。

    空面板的画面是「有画面但没有内容」：观众看到一段空白，
    而画面照样生成、时长照样对。
    """
    for module in (gen_code, gen_table, gen_mermaid):
        try:
            module.render(cairo.Context(
                cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)), 0.5, 320, 180,
                {})
        except MissingParam:
            continue
        except Exception as exc:  # noqa: BLE001 - 报错就行，但要看得懂
            raise AssertionError(f"{module.__name__} 报的错看不懂：{exc}")
        raise AssertionError(f"{module.__name__} 没有内容也画了画面")
