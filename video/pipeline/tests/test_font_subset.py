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
烧一遍、把品牌片的片头片尾真渲一遍，把画出去的字收齐。源码怎么改
都逃不过它。

品牌片这一条是**补上来的**：它是独立于流水线的一条出字路
（`pyv/brand.py` 只把成片拼进契约，自己不画字）。漏了它的实测后果
就是品牌片上出豆腐块——画面照常生成、时长照常对，没有任何报错。

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

#: 内置字体的两面。**两个字重都要有**——只装常规字重的话，cairo 会
#: **合成**粗体，而合成是各后端自己的做法，两个平台合成出来的不一样
#: （实测轮廓包围盒差 3.14px），跨机版式照样对不上。
SUBSETS = {
    "Regular": FONT_DIR / "AIVSansCJKSC-Regular.otf",
    "Bold": FONT_DIR / "AIVSansCJKSC-Bold.otf",
}

#: **等宽**那一族（代码块用）。**也要查缺字**——代码里的中文注释
#: 一样是画面上的字。
MONO_SUBSET = FONT_DIR / "AIVMonoCJKSC-Regular.otf"

#: **GB 2312-80** 的汉字区与符号区。
#:
#: **为什么要按标准算，而不是按「仓库用到的字符」算**：母稿不在仓库里。
#: 仓库里那篇母稿有 597 个不同的字，其中 **120 个不在**按仓库算出来的
#: 子集里——照仓库算，母稿画出来一半是豆腐块，而且**画面照样生成、
#: 时长照样对**，没有任何报错。
#:
#: 这里**独立复算**一遍（与 `scripts/build_font_subset.py` 里那份各写一份）：
#: GB 2312-80 是**按字节两两解码**的，枚举 0xA1–0xFE × 0xA1–0xFE
#: 就能把汉字区与符号区全部列出来——**不依赖任何外部数据**。
GB2312_LEAD = 0xA1
GB2312_TRAIL = 0xA1
GB2312_LEAD_MAX = 0xFE
GB2312_TRAIL_MAX = 0xFE

#: 常用中英标点——画面上会用到，但不一定出现在任何一份数据里。
EXTRA_PUNCTUATION = "　·—–…、。《》「」『』（）：；？！，－×÷±≤≥≠→←↑↓∵∴√∞°′″¥$%#@&*"

#: 字符从哪来：**代码与数据**里所有会被画出来的地方。
#:
#: - 契约（画面文案的唯一来源）、字幕稿（烧进画面的字幕）
#: - 画字模块里的字符串字面量（场景里写死的少量文案）
#:
#: **不含**散文（`video/*.md` 里的规范与文档、plans 下的设计文档）——
#: 它们永远不会到画面上。
#:
#: **不含** `pyv/` 下只往终端打字的那批模块（doctor、cli、align、
#: persona、timeline……）——它们的中文不上画面，收进来还得为
#: `pyv/fonts.py` 的探针字符 `U+E000` 这类字形预留位置，而上游
#: 字体里根本没有那些字。
#:
#: **品牌片算不算？算。** `brand/scripts/render_brand.py` 把中文文案
#: 直接画到画面上（「深入数据库 · 分享技术之美」「感谢观看」……）。
#: 它不在列表里的实测后果就是品牌片出现豆腐块——画面照常生成、
#: 时长照常对，没有任何报错，只有盯着字才看得见。
DRAWING_MODULES = (
    "pipeline/pyv/scenes/*.py",
    "pipeline/pyv/generic/*.py",
    "pipeline/pyv/subtitle.py",
    "pipeline/pyv/layout.py",
    "pipeline/pyv/components.py",
    "pipeline/pyv/scene_layout.py",
    "brand/scripts/render_brand.py",
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


def _episode_contracts() -> list[Path]:
    """磁盘上各期的契约（`video/episodes/<期路径>/contract.json`）。"""
    from pyv import episodes as episodes_mod

    return [episodes_mod.contract_path(slug)
            for slug in episodes_mod.known_eps()
            if episodes_mod.contract_path(slug).is_file()]


def _episode_scripts() -> list[Path]:
    """磁盘上各期的口播稿（`video/episodes/<期路径>/口播稿.md`）。"""
    from pyv import episodes as episodes_mod

    return [episodes_mod.script_path(slug)
            for slug in episodes_mod.known_eps()
            if episodes_mod.script_path(slug).is_file()]


def _probe_modules() -> list[str]:
    """探针要画的场景模块：目录里有的每一个。

    **按目录扫**：加一个场景不用改这里；少一个场景，探针立刻瞎掉——
    下面那条「探针盖住每个场景模块」的守卫盯着这件事。
    """
    scenes_dir = AIV_ROOT / "pipeline" / "pyv" / "scenes"
    return [f"pyv.scenes.{path.stem}"
            for path in sorted(scenes_dir.glob("*.py"))
            if path.stem != "__init__"]


def _repo_chars() -> set[str]:
    """仓库里会被画到画面上的字符（静态复算）。

    与 `scripts/build_font_subset.py` 里的那份**各写一份**：共用一份
    的话，提取逻辑写错了两边一起错，缺字守卫就永远绿着。

    来源：磁盘上各期的契约（画面文案的唯一来源）与口播稿（烧进画面的字幕）、
    画字模块里的字符串字面量、基础 ASCII 与常用标点。

    **夹具期不算**：它是测试输入，不是入库的内容——产品要画的字
    不含它。（真要画它，缺字守卫会报红，那时的正确动作是重跑
    `scripts/build_font_subset.py`。）
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

    for path in _episode_contracts():
        visit(json.loads(path.read_text(encoding="utf-8")))

    for path in _episode_scripts():
        put(path.read_text(encoding="utf-8"))

    for pattern in DRAWING_MODULES:
        for path in sorted(AIV_ROOT.glob(pattern)):
            for literal in _drawable_literals(path.read_text(encoding="utf-8")):
                put(literal)

    put("".join(chr(i) for i in range(32, 127)))
    put(EXTRA_PUNCTUATION)
    return chars


def _load_brand_render():
    """载入 `brand/scripts/render_brand.py`（品牌片的渲染入口）。

    它不在 pipeline 包里，按路径载入——跟 `tests/test_glasses.py`
    载入素材脚本一个路子。
    """
    import importlib.util
    import sys

    path = AIV_ROOT / "brand" / "scripts" / "render_brand.py"
    spec = importlib.util.spec_from_file_location("render_brand", path)
    module = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules：模块里的 dataclass 机制要回查
    # sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _drawn_chars() -> set[str]:
    """把**真正画出去**的字收齐。

    **不看源码，看画面**：所有出字的路都走一遍。

    1. **场景**：目录里每个场景模块 × 两个画幅 × 五个时刻，拦下每一次画字。
       画面内容用测试自造的最小 params（`tests/scene_params.py`）——
       磁盘上没有期时，探针盯的仍然是**场景代码画出来的字**。
    2. **字幕**：各期的口播稿 → 真实 `SubtitleBurner` → 真实 `wrap_line`
       → 拦在 `_outlined_text`——那是**切好行之后**真正落到画面上的
       那一行。
    3. **品牌片**：真实 `render_brand.py` 的片头 / 片尾各渲五个时刻，
       拦在它自己的 `text()` 上。品牌片是**独立于流水线的一条出字路**
       （`pyv/brand.py` 只是把成片拼进契约，不画字），不单独扫它，
       它的中文文案就没人管——实测漏过一次，品牌片上出了豆腐块。

    **为什么字幕要单独拦**：字幕不经过 `draw.text`，它自己走
    `ctx.text_path`。只拦 `draw.text` 的话，字幕上的字一个都收不到
    （实测：把「关」从子集里挖掉，静态守卫报红、只拦 `draw.text` 的
    运行时探针却一声不吭——「关」只在字幕里出现过）。

    场景模块在导入时把 `draw.text` 绑成了自己的属性
    （`from pyv.draw import text`），所以只补 `pyv.draw` 不够，
    每个用到的模块都要单独补一遍。
    """
    from PIL import Image

    from pyv import align
    from pyv import draw
    from pyv import subtitle as subtitle_mod
    from pyv.timeline import SubtitleEvent, SubtitleStyle
    from scene_params import params_for

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
        # 1. 场景：每个场景模块都画一遍
        for module_name in _probe_modules():
            module = importlib.import_module(module_name)
            bound = getattr(module, "text", None)
            if bound is not None:
                module.text = recorder
            try:
                for width, height in CANVASES:
                    for t in PROBE_TIMES:
                        surface = cairo.ImageSurface(
                            cairo.FORMAT_ARGB32, width, height)
                        ctx = cairo.Context(surface)
                        module.render(ctx, t, width, height,
                                      params_for(module_name))
                        del surface, ctx
            finally:
                if bound is not None:
                    module.text = bound

        # 2. 字幕：各期的口播稿 → 真实 SubtitleBurner → 真实 wrap_line
        #    → 拦在 `_outlined_text`
        style = SubtitleStyle(primary="#000000", outline="#FFFFFF")
        for script in _episode_scripts():
            texts = align.parse_subtitle_table(script)
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

        # 3. 品牌片：真实渲染入口，拦它自己的 text()
        brand = _load_brand_render()
        original_brand_text = brand.text
        brand.text = recorder
        try:
            background = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
            character = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
            for renderer in (brand.render_intro_frame, brand.render_outro_frame):
                for t in PROBE_TIMES:
                    renderer(t, background, character, 0.9)
            del character
        finally:
            brand.text = original_brand_text
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


def _cmap(style: str) -> dict:
    from fontTools.ttLib import TTFont

    return TTFont(str(SUBSETS[style])).getBestCmap()


def _mono_cmap() -> dict:
    from fontTools.ttLib import TTFont

    return TTFont(str(MONO_SUBSET)).getBestCmap()


def _gb2312_chars() -> set[str]:
    """**GB 2312-80 全集**（独立复算）。

    汉字区与符号区都是**两字节 GB2312 编码**，首字节 0xA1–0xFE、
    次字节 0xA1–0xFE。逐个解码，解不出来的（空码位）跳过。
    """
    chars: set[str] = set()
    for lead in range(GB2312_LEAD, GB2312_LEAD_MAX + 1):
        for trail in range(GB2312_TRAIL, GB2312_TRAIL_MAX + 1):
            try:
                chars.add(bytes((lead, trail)).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    return chars


# ---------------------------------------------------------------- 存在与来源


def test_the_bundled_font_is_present():
    for style, path in SUBSETS.items():
        assert path.is_file(), f"内置字体（{style}）不在：{path}"
    assert MONO_SUBSET.is_file(), f"内置等宽字体不在：{MONO_SUBSET}"
    assert MANIFEST.is_file(), f"字体出处台账不在：{MANIFEST}"


def test_the_manifest_pins_the_upstream_source():
    """出处台账必须钉住版本与 sha256——不然换一份字体没人知道。"""
    data = _manifest()
    assert data["family"] == fonts.BUNDLED_FAMILY
    assert data["mono_family"] == fonts.BUNDLED_MONO_FAMILY
    assert data["license"] == "SIL Open Font License 1.1"
    assert data["version"]

    # **三面**：正文的 Regular / Bold + 等宽的 Regular。
    faces = data["faces"]
    assert [(face["family"], face["style"]) for face in faces] == [
        ("AIV Sans CJK SC", "Regular"),
        ("AIV Sans CJK SC", "Bold"),
        ("AIV Mono CJK SC", "Regular"),
    ], faces
    for face in faces:
        assert face["upstream"].startswith("https://"), face
        assert re.fullmatch(r"[0-9a-f]{64}", face["subset_sha256"]), face
        assert face["subset_bytes"] > 0, face
        # 走上游的那两面钉上游 sha256；走离线源的那面钉离线源里的面名。
        if face["source"] == "upstream":
            assert re.fullmatch(r"[0-9a-f]{64}", face["upstream_sha256"]), face
        else:
            assert face["source"] == "offline_source", face
            assert face["source_postscript_name"], face
            assert face["source_ttc"], face


def test_the_manifest_records_the_offline_source():
    """台账里要钉住**离线源**——上游 CDN 连不上的机器靠它重建。"""
    data = _manifest()
    offline = data["offline_source"]
    assert re.fullmatch(r"[0-9a-f]{64}", offline["sha256"]), offline
    assert offline["url"].startswith("https://"), offline
    assert offline["version_string"].startswith("Version "), offline
    assert set(offline["ttc"]) == {"Regular", "Bold"}, offline


def test_the_subset_file_matches_the_recorded_hash():
    """子集文件的 sha256 必须与台账一致。

    有这一条，手改台账里的 `chars` 之类的字段也没用——文件对不上。
    """
    for face in _manifest()["faces"]:
        path = FONT_DIR / face["file"]
        assert path.is_file(), f"台账里记的文件不在：{path}"
        assert _sha256(path) == face["subset_sha256"], (
            f"子集文件 {face['file']} 与台账对不上——"
            f"重跑 scripts/build_font_subset.py"
        )


def test_both_weights_are_really_different_faces():
    """两个字重必须是**两份不同的真字形**，不能是同一份。

    粗体字形跟常规字形长得一样，等于没装粗体——而 cairo 会**合成**
    一份来顶，跨机版式就又对不上了（实测轮廓差 3.14px）。

    判据用**轮廓包围盒**：两个字重的 'A' 墨迹范围必然不同；
    合成粗体是在常规字形上「加粗」，包围盒会变，但步进不变——
    所以这里比轮廓，不比步进。
    """
    cairo = pytest.importorskip("cairo")
    from pyv import fonts as fonts_mod

    extents = {}
    for style in ("Regular", "Bold"):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        ctx = cairo.Context(surface)
        fonts_mod.select_font(
            ctx, fonts_mod.BUNDLED_FAMILY, bold=(style == "Bold"))
        ctx.set_font_size(44)
        ctx.new_path()
        ctx.move_to(0, 60)
        ctx.text_path("A")
        extents[style] = ctx.path_extents()
        ctx.new_path()
    assert extents["Regular"] != extents["Bold"], (
        "两个字重的轮廓一模一样——粗体没装上，cairo 只能合成"
    )


# ---------------------------------------------------------------- 缺字守卫


def test_the_subset_covers_the_whole_gb2312_standard():
    """**内置字体必须盖住 GB 2312-80 全集**。

    **为什么要按标准算**：母稿（`docs/` 里的文章）不在本仓库，
    仓库里那篇母稿有 **120 个字**不在按仓库算出来的子集里——
    照仓库算，母稿画出来一半是豆腐块，而且**画面照样生成、
    时长照样对**，没有任何报错。

    **判据在 CI 里跑得动**：GB 2312-80 是两字节编码，
    枚举 0xA1–0xFE × 0xA1–0xFE 就是全集，**不依赖外部数据**。

    **三面都要盖住**：正文的两个字重与等宽那一面。代码块里的
    中文注释一样是画面上的字。
    """
    standard = _gb2312_chars()
    assert len(standard) > 7000, (
        f"GB 2312-80 全集只有 {len(standard)} 个字——枚举口径不对")

    for style in SUBSETS:
        cmap = _cmap(style)
        missing = sorted(ch for ch in standard if ord(ch) not in cmap)
        assert not missing, (
            f"内置字体（{style}）缺 GB 2312-80 里的 {len(missing)} 个字："
            f"{missing[:20]}——跑 scripts/build_font_subset.py 重生成子集"
        )

    mono = _mono_cmap()
    missing = sorted(ch for ch in standard if ord(ch) not in mono)
    assert not missing, (
        f"内置等宽字体缺 GB 2312-80 里的 {len(missing)} 个字："
        f"{missing[:20]}——跑 scripts/build_font_subset.py 重生成子集"
    )


def test_the_subset_covers_every_character_we_draw():
    """**缺字就红**（静态）：新一期加了新字而没重跑子集脚本 → CI 红。

    没有这条守卫，手工维护的字符集必然漂；有了它，字符集只能是
    脚本算出来的。**两个字重都要查**——少一个是豆腐块。
    """
    for style in SUBSETS:
        cmap = _cmap(style)
        missing = sorted(ch for ch in _repo_chars() if ord(ch) not in cmap)
        assert not missing, (
            f"内置字体（{style}）缺 {len(missing)} 个字：{missing[:20]}——"
            f"跑 scripts/build_font_subset.py 重生成子集"
        )


def test_the_subset_covers_every_character_the_scenes_actually_draw():
    """**缺字就红**（运行时）：看画面，不看源码。

    静态提取靠的是「画字模块列表」，而画字的路径可能绕开它——
    某个场景从别的模块引了个画字助手，那个助手里的文案既不在列表里，
    也没被静态提取扫到。这条不看源码：**把 36 个视觉段真画一遍**，
    把画出去的字收齐，再核对子集盖不盖得住。
    """
    drawn = _drawn_chars()
    for style in SUBSETS:
        cmap = _cmap(style)
        missing = sorted(ch for ch in drawn if ord(ch) not in cmap)
        assert not missing, (
            f"场景画出了 {len(missing)} 个内置字体（{style}）里没有的字："
            f"{missing[:20]}——跑 scripts/build_font_subset.py 重生成子集"
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
    """运行时探针声称覆盖全部场景模块——那就钉住这个声称。

    少扫了一个场景，那个场景画出去的字就没人管了。

    **按目录扫**：探针画的模块集合必须等于 `pyv/scenes/` 里的模块集合。
    磁盘上有期时，契约里用到的模块也要在探针的覆盖范围里。
    """
    from pyv import contract as contract_mod
    from pyv import episodes as episodes_mod

    probed = {name.split(".")[-1] for name in _probe_modules()}
    on_disk = {path.stem for path in
               (AIV_ROOT / "pipeline" / "pyv" / "scenes").glob("*.py")
               if path.stem != "__init__"}
    assert probed == on_disk, (
        f"探针画的场景模块与目录里的对不上："
        f"目录有探针没画 {sorted(on_disk - probed)}；"
        f"探针画了目录没有 {sorted(probed - on_disk)}"
    )

    used = set()
    for slug in episodes_mod.known_eps():
        contract = contract_mod.load_contract(
            episodes_mod.contract_path(slug))
        used.update(segment.renderer.split(".")[-1]
                    for segment in contract.segments)
    assert used <= probed, (
        f"契约里用到的场景模块探针没画：{sorted(used - probed)}"
    )


# ---------------------------------------------------------------- 体积与族名


def test_the_subset_is_small():
    """子集的意义在于小。超了说明提取范围写宽了。

    **上限是 GB 2312-80 全集的自然结果**：6763 个汉字的字形本身
    就要 3 MB 上下（实测每面 3.4–3.5 MB）。这个上限定在 5 MiB——
    再大就不是「按标准算」而是「提取范围写宽了」。
    """
    for style, path in SUBSETS.items():
        size = path.stat().st_size
        assert size < 5 * 1024 * 1024, f"子集（{style}）{size} 字节，太大了"
    size = MONO_SUBSET.stat().st_size
    assert size < 5 * 1024 * 1024, f"等宽子集 {size} 字节，太大了"


def test_the_bundled_family_name_is_unique():
    """内置族名不能跟系统里任何字体重名。

    重名了 fontconfig 就在两份之间二选一，机器之间就不一致了。
    """
    assert fonts.BUNDLED_FAMILY == "AIV Sans CJK SC"
    assert fonts.BUNDLED_FAMILY not in fonts.FALLBACK_FAMILIES
    assert fonts.BUNDLED_FAMILY not in {
        "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC",
    }
