"""内置字体子集：来源钉住、缺字就红。

**为什么要有这条守卫**：内置字体是按「仓库用到的字符」子集化的。
新一期加了新字、或者改了契约里的文案，而没重跑
`scripts/build_font_subset.py`——那台机器上的画面就会多出豆腐块，
而**画面照样生成、时长照样对**，没有任何报错。

所以这里有四类：

1. **来源钉住**：台账记着上游 URL、版本与 sha256；
2. **文件对得上**：子集文件的 sha256 与台账一致（手改台账改不动文件）；
3. **缺字就红（静态）**：子集的 cmap 必须盖住仓库用到的每一个字符。
4. **缺字就红（运行时）**：把每个场景**真正画出来**、把每条字幕
   **真正烧上去**，收齐画上去的每一个字，再核对一遍。

第 3 条里的字符集是**独立复算**的——与
`scripts/build_font_subset.py` 里的那份各写一份，故意不共用代码。
共用一份的话，提取逻辑写错了两边一起错，这条守卫就永远绿着。

**为什么还要第 4 条**：静态提取靠的是「画字模块列表」，而真正画字的
路径可能绕开它——某个场景从别的模块引了一个画字助手，那个助手里的
文案就既不在列表里、也没被静态提取扫到。第 4 条不看源码，**看画面**：
它把 36 个视觉段在两个画幅、若干时刻都真画一遍、把真实字幕稿逐条
烧一遍，把画出去的字收齐。源码怎么改都逃不过它。

**两条都验过会红**：把「关」（只在字幕里出现）与「缓」（场景与字幕
都有）从子集里挖掉，两条缺字守卫都报红。
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from pathlib import Path

import cairo
import pytest

from pyv import fonts

AIV_ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = AIV_ROOT / "pipeline" / "assets" / "fonts"
MANIFEST = FONT_DIR / "SOURCE.json"
SUBSET = FONT_DIR / "AIVSansCJKSC-Regular.otf"

#: 常用中英标点——画面上会用到，但不一定出现在任何一份数据里。
EXTRA_PUNCTUATION = "　·—…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*"

#: 字符从哪来：**代码与数据**里所有会被画出来的地方。
#:
#: - 契约（画面文案的唯一来源）、字幕稿（烧进画面的字幕）
#: - 画字模块里的字符串字面量（场景里写死的少量文案）
#:
#: **不含**散文（`aiv/*.md` 里的规范与文档、plans 下的设计文档）——
#: 它们永远不会到画面上。
#:
#: **不含** `pyv/` 下只往终端打字的那批模块（doctor、cli、align、
#: persona、timeline……）——它们的中文不上画面，收进来还得为
#: `pyv/fonts.py` 的探针字符 `U+E000` 这类字形预留位置，而上游
#: 字体里根本没有那些字。
DRAWING_MODULES = (
    "pipeline/pyv/scenes/*.py",
    "pipeline/pyv/subtitle.py",
    "pipeline/pyv/layout.py",
    "pipeline/pyv/components.py",
    "pipeline/pyv/scene_layout.py",
)

#: 运行时探针采样几个时刻。
#:
#: 一段动画的中间态才有话说——只采首帧末帧，动画中途才冒出来的字
#: 就漏了。五个点够把「进场 / 到位 / 退场」都盖住。
PROBE_TIMES = (0.0, 0.25, 0.5, 0.75, 1.0)

#: 两个画幅。
CANVASES = ((1920, 1080), (1080, 1920))


def _drawable_literals(source: str) -> list[str]:
    """会画到画面上的字符串字面量（docstring 不算）。

    **用 ast，不用正则**：正则扫原始文本会跨过引号边界，把注释里
    的字符也捞进来——子集里混进根本不会上画面的符号，还得为它换字体。

    **排除 docstring**：docstring 是散文，不是画面文案。场景模块的
    docstring 里提到但**没有真画出来**的符号（例如「排队那一格画一个叉」
    ——那个叉是线条画的，不依赖字体）不该进字体。
    """
    tree = ast.parse(source)

    prose: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        prose.add(id(node.body[0].value))

    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in prose]


def _drawable(ch: str) -> bool:
    """这个字符会不会被画出来。

    排除控制字符与变体选择符——后者只修饰前面的字符，本身永远不画
    （字幕稿里 `⚠️` 带的就是一个 U+FE0F）。
    """
    code = ord(ch)
    if code < 32:
        return False
    if 0xFE00 <= code <= 0xFE0F:
        return False
    if 0xE0100 <= code <= 0xE01EF:
        return False
    return True


def _repo_chars() -> set[str]:
    """仓库里会被画到画面上的字符（静态复算）。

    与 `scripts/build_font_subset.py` 里的那份**各写一份**：共用一份
    的话，提取逻辑写错了两边一起错，缺字守卫就永远绿着。

    来源：六期契约的全部字符串值（画面文案的唯一来源）、六份字幕稿、
    画字模块里的字符串字面量、基础 ASCII 与常用标点。
    """
    chars: set[str] = set()

    def put(text: str) -> None:
        for ch in text:
            if _drawable(ch):
                chars.add(ch)

    def visit(node) -> None:
        if isinstance(node, str):
            put(node)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for value in node.values():
                visit(value)

    for path in sorted((AIV_ROOT / "contracts").glob("*.json")):
        visit(json.loads(path.read_text(encoding="utf-8")))

    for path in sorted(AIV_ROOT.glob("字幕-*.md")):
        put(path.read_text(encoding="utf-8"))

    for pattern in DRAWING_MODULES:
        for path in sorted(AIV_ROOT.glob(pattern)):
            for literal in _drawable_literals(path.read_text(encoding="utf-8")):
                put(literal)

    put("".join(chr(i) for i in range(32, 127)))
    put(EXTRA_PUNCTUATION)
    return chars


def _drawn_chars() -> set[str]:
    """把**真正画出去**的字收齐。

    **不看源码，看画面**：两条出字的路都走一遍。

    1. **场景**：36 个视觉段 × 两个画幅 × 五个时刻，拦下每一次画字。
    2. **字幕**：真实字幕稿 → 真实 `SubtitleBurner` → 真实 `wrap_line`
       → 拦在 `_outlined_text`——那是**切好行之后**真正落到画面上的
       那一行。

    **为什么字幕要单独拦**：字幕不经过 `draw.text`，它自己走
    `ctx.text_path`。只拦 `draw.text` 的话，字幕上的字一个都收不到
    （实测：把「关」从子集里挖掉，静态守卫报红、只拦 `draw.text` 的
    运行时探针却一声不吭——「关」只在字幕里出现过）。

    场景模块在导入时把 `draw.text` 绑成了自己的属性
    （`from pyv.draw import text`），所以只补 `pyv.draw` 不够，
    每个用到的模块都要单独补一遍。
    """
    from pyv import align
    from pyv import contract as contract_mod
    from pyv import draw, episodes as episodes_mod
    from pyv import subtitle as subtitle_mod
    from pyv.timeline import SubtitleEvent, SubtitleStyle

    seen: set[str] = set()

    def recorder(ctx, s, x, y, size, color, anchor="left", bold=False,
                 alpha=1.0):
        seen.update(s)
        return None

    def recorder_line(ctx, s, x, baseline, fill_color, outline_color,
                      outline_width):
        seen.update(s)
        return None

    original_draw_text = draw.text
    original_outlined = subtitle_mod._outlined_text
    draw.text = recorder
    subtitle_mod._outlined_text = recorder_line
    try:
        # 1. 场景
        for episode in episodes_mod.EPISODE_ORDER:
            contract = contract_mod.load_contract(
                AIV_ROOT / "contracts" / f"{episode}.json")
            for segment in contract.segments:
                module = importlib.import_module(segment.renderer)
                bound = getattr(module, "text", None)
                if bound is not None:
                    module.text = recorder
                try:
                    for width, height in CANVASES:
                        for t in PROBE_TIMES:
                            surface = cairo.ImageSurface(
                                cairo.FORMAT_ARGB32, width, height)
                            ctx = cairo.Context(surface)
                            module.render(ctx, t, width, height, segment.params)
                            del surface, ctx
                finally:
                    if bound is not None:
                        module.text = bound

        # 2. 字幕
        style = SubtitleStyle(primary="#000000", outline="#FFFFFF")
        for episode in episodes_mod.EPISODE_ORDER:
            texts = align.parse_subtitle_table(
                episodes_mod.script_path(episode))
            events = [
                SubtitleEvent(start=float(index), end=float(index) + 1.0,
                              text=text)
                for index, text in enumerate(texts)
            ]
            burner = subtitle_mod.SubtitleBurner(events, style)
            for width, height in CANVASES:
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
                ctx = cairo.Context(surface)
                for event in events:
                    burner.draw(ctx, event.start + 0.5, width, height)
                del surface, ctx
    finally:
        draw.text = original_draw_text
        subtitle_mod._outlined_text = original_outlined
    return seen


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _cmap() -> dict:
    from fontTools.ttLib import TTFont

    return TTFont(str(SUBSET)).getBestCmap()


# ---------------------------------------------------------------- 存在与来源


def test_the_bundled_font_is_present():
    assert SUBSET.is_file(), f"内置字体不在：{SUBSET}"
    assert MANIFEST.is_file(), f"字体出处台账不在：{MANIFEST}"


def test_the_manifest_pins_the_upstream_source():
    """出处台账必须钉住版本与 sha256——不然换一份字体没人知道。"""
    data = _manifest()
    assert data["family"] == fonts.BUNDLED_FAMILY
    assert data["license"] == "SIL Open Font License 1.1"
    assert re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
    assert data["upstream"].startswith("https://")
    assert data["version"]


def test_the_subset_file_matches_the_recorded_hash():
    """子集文件的 sha256 必须与台账一致。

    有这一条，手改台账里的 `chars` 之类的字段也没用——文件对不上。
    """
    assert _sha256(SUBSET) == _manifest()["subset_sha256"], (
        "子集文件与台账对不上——重跑 scripts/build_font_subset.py"
    )


# ---------------------------------------------------------------- 缺字守卫


def test_the_subset_covers_every_character_we_draw():
    """**缺字就红**（静态）：新一期加了新字而没重跑子集脚本 → CI 红。

    没有这条守卫，手工维护的字符集必然漂；有了它，字符集只能是
    脚本算出来的。
    """
    cmap = _cmap()
    missing = sorted(ch for ch in _repo_chars() if ord(ch) not in cmap)
    assert not missing, (
        f"内置字体缺 {len(missing)} 个字：{missing[:20]}——"
        f"跑 scripts/build_font_subset.py 重生成子集"
    )


def test_the_subset_covers_every_character_the_scenes_actually_draw():
    """**缺字就红**（运行时）：看画面，不看源码。

    静态提取靠的是「画字模块列表」，而画字的路径可能绕开它——
    某个场景从别的模块引了个画字助手，那个助手里的文案既不在列表里，
    也没被静态提取扫到。这条不看源码：**把 36 个视觉段真画一遍**，
    把画出去的字收齐，再核对子集盖不盖得住。
    """
    cmap = _cmap()
    drawn = _drawn_chars()
    missing = sorted(ch for ch in drawn if ord(ch) not in cmap)
    assert not missing, (
        f"场景画出了 {len(missing)} 个内置字体里没有的字：{missing[:20]}——"
        f"跑 scripts/build_font_subset.py 重生成子集"
    )


def test_the_runtime_probe_actually_sees_the_text():
    """**探针自己得看得见字**，不然它只是一段永远绿的代码。

    拦 `draw.text` 的钩子哪天坏了（属性名变了、场景改成绕开
    `draw.text`），这条守卫会安静地收不到任何字、然后永远绿着。
    """
    drawn = _drawn_chars()
    assert drawn, "探针一个字都没收到——它没拦到画字，守卫是瞎的"
    # 契约里的文案一定在画面上：标题「关注数据库内核的独立开发者」…
    assert any("一" <= ch <= "鿿" for ch in drawn), (
        f"探针只收到了非汉字，拦的可能是错的东西：{sorted(drawn)[:20]}"
    )


def test_every_visual_segment_is_covered_by_the_runtime_probe():
    """运行时探针声称覆盖全部视觉段——那就钉住这个声称。

    少扫了一个场景，那个场景画出去的字就没人管了。

    **36 段 / 26 个模块**：同一期里有几段复用同一个场景模块（换个
    参数画同一套版式），所以段数比模块数多。两个数都钉住——
    段数变了是契约变了，模块数变了是场景目录变了。
    """
    from pyv import contract as contract_mod
    from pyv import episodes as episodes_mod

    segments = []
    for episode in episodes_mod.EPISODE_ORDER:
        contract = contract_mod.load_contract(
            AIV_ROOT / "contracts" / f"{episode}.json")
        segments.extend(segment.renderer for segment in contract.segments)

    modules = {name.split(".")[-1] for name in segments}
    on_disk = {path.stem for path in
               (AIV_ROOT / "pipeline" / "pyv" / "scenes").glob("*.py")
               if path.stem != "__init__"}

    assert len(segments) == 36, f"视觉段数变了：{len(segments)}"
    assert modules == on_disk, (
        f"契约里用到的场景模块与目录里的对不上："
        f"目录有契约没用 {sorted(on_disk - modules)}；"
        f"契约用了目录没有 {sorted(modules - on_disk)}"
    )
    assert len(modules) == 26, f"场景模块数变了：{len(modules)}"


# ---------------------------------------------------------------- 体积与族名


def test_the_subset_is_small():
    """子集的意义在于小。超了说明提取范围写宽了。"""
    size = SUBSET.stat().st_size
    assert size < 2 * 1024 * 1024, f"子集 {size} 字节，太大了"


def test_the_bundled_family_name_is_unique():
    """内置族名不能跟系统里任何字体重名。

    重名了 fontconfig 就在两份之间二选一，机器之间就不一致了。
    """
    assert fonts.BUNDLED_FAMILY == "AIV Sans CJK SC"
    assert fonts.BUNDLED_FAMILY not in fonts.FALLBACK_FAMILIES
    assert fonts.BUNDLED_FAMILY not in {
        "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC",
    }
