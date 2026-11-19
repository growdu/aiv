"""场景模块的守卫。

**分工原则**：本期内容进契约，版式常量留代码。

视频线清空重来之后，磁盘上没有期可读，于是这些用例自己造输入：
形状照场景代码要的来（`tests/scene_params.py`），内容不算数。
守住的是**场景模块自己的逻辑**——画几样东西、什么时候画、
名字从哪儿来、几份数据之间对不对得上。
"""
import importlib
from pathlib import Path

import cairo
import pytest

from pyv import fonts
from scene_params import params_for

SCENES_DIR = Path(__file__).resolve().parents[1] / "pyv" / "scenes"

#: 目录里有的场景模块。**按目录扫**：加一个场景不用改测试，
#: 少一个场景测试立刻发现（下面那条「基准盖住每个模块」也盯这件事）。
SCENE_MODULES = sorted(
    f"pyv.scenes.{path.stem}"
    for path in SCENES_DIR.glob("*.py")
    if path.stem != "__init__"
)


def _params_for(module_name: str) -> dict:
    """这个场景的最小 params（见 `tests/scene_params.py`）。"""
    return params_for(module_name)


@pytest.mark.parametrize("name", SCENE_MODULES)
def test_scene_module_exposes_render(name):
    module = importlib.import_module(name)
    assert callable(module.render)


@pytest.mark.parametrize("name", SCENE_MODULES)
def test_scene_render_draws_something(name):
    module = importlib.import_module(name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
    ctx = cairo.Context(surface)
    module.render(ctx, 0.5, 320, 180, _params_for(name))
    data = surface.get_data()
    assert any(byte != 0 for byte in data)


@pytest.mark.parametrize("name", SCENE_MODULES)
def test_scene_render_handles_endpoints(name):
    module = importlib.import_module(name)
    for t in (0.0, 1.0):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
        ctx = cairo.Context(surface)
        module.render(ctx, t, 320, 180, _params_for(name))


def test_s03_highlights_exactly_one_core():
    import pyv.scenes.s03_cores as s03

    params = _params_for("pyv.scenes.s03_cores")
    highlighted = s03.highlighted_cores(params)
    assert len(highlighted) == 1
    assert 0 <= highlighted[0] < int(params["core_count"])


def test_s04_exposes_the_workers_the_contract_asks_for():
    import pyv.scenes.s04_parallel as s04

    params = _params_for("pyv.scenes.s04_parallel")
    assert s04.worker_count(params) == int(params["worker_count"])
    assert s04.worker_count(params) > 0, "画面上至少要有一个 worker"


def test_s05_bench_draws_a_range_not_a_single_precise_value():
    """压测那组数字是区间（2 到 5 倍），画面不能画成一个精确的单值。

    串行条占 1 倍，实测区间从 2 倍起到 5 倍止——条的长度必须与
    画面上写的那个倍数对得上，否则图和字各说各的。
    """
    import pyv.scenes.s05_bench as s05

    params = _params_for("pyv.scenes.s05_bench")
    marks = s05.scale(1000.0, 120.0)
    unit = marks["unit"]
    assert marks["serial_end"] - marks["x0"] == pytest.approx(unit)
    assert marks["range_x"] - marks["x0"] == pytest.approx(unit * 2)
    assert marks["range_end"] - marks["x0"] == pytest.approx(unit * 5)
    assert marks["range_x"] > marks["serial_end"], "区间必须整体落在串行基线之外"


def test_s05_bench_callout_matches_the_range_it_draws():
    """画面上写的倍数必须与画出来的区间一致。

    区间是场景代码里画死的（2 到 5 倍），倍数是契约给的——
    两边对不上，图和字就各说各话。
    """
    import pyv.scenes.s05_bench as s05

    params = _params_for("pyv.scenes.s05_bench")
    marks = s05.scale(1000.0, 120.0)
    unit = marks["unit"]
    low = (marks["range_x"] - marks["x0"]) / unit
    high = (marks["range_end"] - marks["x0"]) / unit
    assert f"{low:g}" in params["callout"], (
        f"画面上写的 {params['callout']!r} 与画出来的区间 {low:g} 倍对不上"
    )
    assert f"{high:g}" in params["callout"], (
        f"画面上写的 {params['callout']!r} 与画出来的区间 {high:g} 倍对不上"
    )


def test_s05_bench_starts_on_the_same_left_margin_as_its_title():
    """刻度轨道、条与标签要跟标题、说明行在同一条左边距上。

    这一段出过一次版面塌陷：轨道的原点写成了 `unit * TRACK_X`，
    而 `unit` 已经是像素量纲（w*UNIT_W），乘出来是 12 px——
    标签与条贴死画幅左边，标题行却在 w*0.06 处，两样东西不在一条
    左边距上，整张图重心偏左，右侧空出近半幅。

    这条测试量的是**画面上真正落墨的最左像素**，不是常量：
    常量对了、绘制时又乘错一遍，它照样绿。
    """
    import pyv.scenes.s05_bench as s05
    from pyv.palette import COLORS, hex_to_rgb

    w, h = 1920, 1080
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*hex_to_rgb(COLORS["bg"]))
    ctx.paint()
    s05.render(ctx, 0.6, w, h, _params_for("pyv.scenes.s05_bench"))

    bg = bytes(int(round(c * 255)) for c in hex_to_rgb(COLORS["bg"]))
    stride = surface.get_stride()
    data = surface.get_data()

    def leftmost_ink(y0: int, y1: int) -> int:
        for x in range(w):
            for y in range(y0, y1):
                off = y * stride + x * 4
                if data[off:off + 3] != bg:
                    return x
        raise AssertionError(f"y∈[{y0},{y1}) 一行墨都没落")

    title_x = leftmost_ink(90, 160)          # 标题行
    label_x = leftmost_ink(292, 332)         # 「串行解码」标签行
    assert abs(title_x - label_x) <= 2, (
        f"标签落墨在 x={label_x}，标题在 x={title_x}——不在同一条左边距上"
    )
    assert label_x > 40, "标签几乎贴死画幅左边，左边距没有留出来"


def test_s04_source_and_target_labels_come_from_the_contract():
    """openGauss 的 reader 是独立线程，walsender 单独收口，不能画成一个。

    上一版把来源方标成 `Reader (WALSender)`，与源码拓扑不符。
    **名字是数据，不是代码**：来源方与目标方叫什么，只能由契约给，
    场景源码里不许再写死一个名字。
    """
    import pyv.scenes.s04_parallel as s04

    source = open(s04.__file__, encoding="utf-8").read()
    assert "reader" not in source.lower(), "来源方的名字写死在场景里了"
    assert "walsender" not in source.lower(), "目标方的名字写死在场景里了"

    params = _params_for("pyv.scenes.s04_parallel")
    assert params["source_label"] != params["target_label"], (
        "来源方与目标方不是同一个线程"
    )


def test_s06_uses_personal_avatar_and_no_banned_words():
    import pyv.scenes.s06_outro as s06
    from pyv import character
    from pyv.timeline import BANNED_SUBSTRINGS
    source = open(s06.__file__, encoding="utf-8").read()
    assert "avatar_path" in source, "落版头像必须走统一入口"
    # 头像素材是**用户自带**的：没配就不带——不是错。
    # 场景代码仍然必须走统一入口（上面那句已经钉住了）。
    if character.AVATAR_IMAGE is None:
        pytest.skip("没配落版头像素材")
    assert character.avatar_path() is not None, "配了头像却找不到它"
    for word in BANNED_SUBSTRINGS:
        assert word.lower() not in source.lower(), word


@pytest.mark.parametrize("name", SCENE_MODULES)
def test_scene_source_has_no_banned_words(name):
    from pyv.timeline import BANNED_SUBSTRINGS
    module = importlib.import_module(name)
    source = open(module.__file__, encoding="utf-8").read()
    for word in BANNED_SUBSTRINGS:
        assert word.lower() not in source.lower(), (name, word)


def _glyph_pixels(ch: str, size: int = 40) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size * 2, size * 2)
    ctx = cairo.Context(surface)
    ctx.select_font_face(fonts.font_family(), cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.set_source_rgb(0, 0, 0)
    ctx.move_to(4, size)
    ctx.show_text(ch)
    surface.flush()
    return bytes(surface.get_data())


def _is_missing_glyph(ch: str) -> bool:
    """字体没有该字形时会画成同一个豆腐块，可据此比对。"""
    return _glyph_pixels(ch) == _glyph_pixels("")


@pytest.mark.parametrize("name", SCENE_MODULES)
def test_every_character_in_scene_source_is_renderable(name, monkeypatch):
    """当前字体缺字形时会静默画成豆腐块，必须提前拦住。"""
    module = importlib.import_module(name)
    original = module.text
    drawn: list[str] = []

    def spy(ctx, s, *args, **kwargs):
        drawn.append(s)
        return original(ctx, s, *args, **kwargs)

    monkeypatch.setattr(module, "text", spy)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
    ctx = cairo.Context(surface)
    module.render(ctx, 0.5, 320, 180, _params_for(name))

    assert drawn, "场景应当至少画出一行文字"
    for s in drawn:
        for ch in s:
            if ch.isspace():
                continue
            assert not _is_missing_glyph(ch), (
                f"{name} 画的字符 {ch!r} 不在当前字体里，会渲染成豆腐块"
            )


# ------------------------------------------------------ 提交顺序那一段的两幕


def test_s02_mixed_ranks_follow_the_commit_order():
    """时间轴上的名次由契约里的提交顺序决定，不由编号决定。"""
    import pyv.scenes.s02_mixed as s02

    params = _params_for("pyv.scenes.s02_mixed")
    ranks = s02.commit_ranks(params)
    ids = [str(x) for x in params["txn_ids"]]
    order = [str(x) for x in params["commit_order"]]
    assert sorted(ranks) == list(range(len(ids)))
    for index, txn_id in enumerate(ids):
        assert ranks[index] == order.index(txn_id)


def test_s02_mixed_commit_order_is_not_the_id_order():
    """这一段讲的就是「先后是乱的」——提交顺序必须真的和编号顺序不同。"""
    params = _params_for("pyv.scenes.s02_mixed")
    assert [str(x) for x in params["commit_order"]] != [
        str(x) for x in params["txn_ids"]
    ]


def test_s03_counter_numbers_strictly_increase():
    import pyv.scenes.s03_counter as s03

    params = _params_for("pyv.scenes.s03_counter")
    values = [int(v) for v in s03.csn_sequence(params)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_s03_counter_reading_starts_before_the_first_number():
    """计数器先显示起始值，发一个号才跳一次。"""
    import pyv.scenes.s03_counter as s03

    params = _params_for("pyv.scenes.s03_counter")
    readings = s03.counter_reading(params)
    assert readings[0] == str(params["counter_value"])
    assert readings[1:] == [str(v) for v in params["csn_values"]]


def _drawn_texts(monkeypatch, module, params, t, width, height):
    """渲染一帧，返回这一帧画出去的文字。

    场景模块在导入时把 `draw.text` 绑成了自己的属性，竖版还多走一层
    `scene_layout.line`（它调的是 `scene_layout` 自己的 `text`）——
    两处都要拦。
    """
    from pyv import scene_layout

    original = module.text
    drawn: list[str] = []

    def spy(ctx, s, *args, **kwargs):
        drawn.append(s)
        return original(ctx, s, *args, **kwargs)

    monkeypatch.setattr(module, "text", spy)
    monkeypatch.setattr(scene_layout, "text", spy)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    module.render(ctx, t, width, height, params)
    return drawn


@pytest.mark.parametrize("canvas", [(1920, 1080), (1080, 1920)],
                         ids=["横版", "竖版"])
def test_s03_counter_shows_the_initial_reading_before_the_first_claim(
        monkeypatch, canvas):
    """**起始读数要真的在画面上**——第一笔取号之前，计数器停在那儿。

    **行为上的判据**：把场景渲染出来，看画出去的字。

    早先第一笔取号排在 t=0，起始读数一帧都留不住——
    `counter_reading()` 的第 0 位永远不出现，「计数器本来是 100」
    这件事观众根本看不到。序列本身对（上面那条测试盯着），缺的是
    **让第 0 位露个脸的时间窗**。
    """
    import pyv.scenes.s03_counter as s03

    params = _params_for("pyv.scenes.s03_counter")
    width, height = canvas
    initial = str(params["counter_value"])
    first = str(params["csn_values"][0])

    # 第一笔取号之前：起始读数在画面上，第一个号还不在
    drawn = _drawn_texts(monkeypatch, s03, params, 0.0, width, height)
    assert initial in drawn, (
        f"起始读数 {initial} 没出现在画面上——第一笔取号太早了，"
        f"起始值一帧都留不住"
    )
    assert first not in drawn, (
        f"第一笔取号之前画面上不该有 {first}"
    )

    # 第一笔取号那一刻：起始读数让位给发出去的那个号
    drawn_after = _drawn_texts(
        monkeypatch, s03, params, s03.claim_times(len(params["txn_ids"]))[0],
        width, height)
    assert first in drawn_after, f"取号之后画面上该有 {first}"
    assert initial not in drawn_after, (
        f"取号之后起始读数 {initial} 该让位了"
    )


def test_s03_counter_claims_do_not_start_at_zero():
    """第一笔取号不能排在 t=0——那一段是留给起始读数的。"""
    import pyv.scenes.s03_counter as s03

    moments = s03.claim_times(3)
    assert moments[0] > 0, "第一笔取号排在 0，起始读数没有时间窗"
    assert moments == sorted(moments), "取号时刻必须递增"
    assert s03.issued_count(0.0, 3) == 0
    assert s03.issued_count(moments[0] - 0.001, 3) == 0
    assert s03.issued_count(moments[0], 3) == 1
    assert s03.issued_count(moments[-1], 3) == 3


def test_s05_layers_reads_the_count_from_the_contract():
    """层数是契约给的；层号、层名、层角色三份必须一样长。

    三份长短不一的话，画面上会出现「有层号没层名」的半截层——
    数字对不上，画就散了。
    """
    import pyv.scenes.s05_layers as s05

    params = _params_for("pyv.scenes.s05_layers")
    assert s05.layer_count(params) == len(params["layer_ids"])
    assert len(params["layer_ids"]) == len(params["layer_names"]) \
        == len(params["layer_roles"])
    assert s05.layer_count(params) > 0


def test_s02_and_s03_tell_the_same_story():
    """s02 说「谁先 commit 是乱的」，s03 必须按同一个领取顺序发号。

    两段画面用的是同一组事务：如果 s03 的发号顺序跟 s02 的提交顺序对不上，
    观众会看到「最后 commit 的事务拿到了最小的号」这种自相矛盾的画面。
    """
    mixed = _params_for("pyv.scenes.s02_mixed")
    counter = _params_for("pyv.scenes.s03_counter")
    assert [str(x) for x in counter["txn_ids"]] == [
        str(x) for x in mixed["commit_order"]
    ]


# ------------------------------------------------------ 其余几期的场景


def test_wal_interleave_and_reorder_buffer_tell_the_same_story():
    """s02 画的交错与 s03 画的归并必须是同一组 WAL 记录。

    两段画的是同一个举例：s02 里 T1 的记录被别的事务隔开，
    s03 里就要按同一组记录落进槽里。换了记录，观众会看到对不上的画面。
    """
    interleave = _params_for("pyv.scenes.s02_wal_interleave")
    buffer = _params_for("pyv.scenes.s03_reorder_buffer")
    assert buffer["records"] == interleave["records"]
    assert buffer["txn_ids"] == interleave["txn_ids"]


def test_emit_ends_with_a_commit():
    """s05 发出去的那一组，必须以提交记录收尾。

    整组发出的触发条件就是「攒到该事务的提交记录出现」——
    组里没有提交记录，这张图就在讲一件不存在的事。
    """
    import pyv.scenes.s05_emit as s05

    params = _params_for("pyv.scenes.s05_emit")
    ops = s05.emit_slot(params)
    assert ops, "契约里必须指定要发出去的那一组"
    assert ops[-1] == params["commit_op"], "整组的最后一块必须是提交记录"


def test_spill_keeps_some_changes_in_memory():
    """落盘不能把内存清空——画面要看出「一部分落了盘，一部分还在内存」。"""
    params = _params_for("pyv.scenes.s04_spill")
    assert 0 < int(params["spill_count"]) < len(params["chips"]), \
        "既要画出搬走的，也要画出留在内存里的"


def test_scheduler_respects_the_dependency_edges():
    """分发顺序与提交顺序都必须满足依赖图。

    s04 画了 T1 → T2 的依赖，s05 就不能先分发 T2 再分发 T1。
    顺序错了的图比没有图更糟。
    """
    dag = _params_for("pyv.scenes.s04_dependency_dag")
    scheduler = _params_for("pyv.scenes.s05_scheduler")
    edges = [(str(row[0]), str(row[1])) for row in dag["edges"]]
    dispatch = [str(row[0]) for row in scheduler["dispatch"]]
    commit = [str(x) for x in scheduler["commit_order"]]

    assert set(dispatch) == set(dag["nodes"]), "分发要覆盖图上的每个节点"
    assert set(commit) == set(dag["nodes"]), "提交要覆盖图上的每个节点"

    dispatch_pos = {txn: index for index, txn in enumerate(dispatch)}
    commit_pos = {txn: index for index, txn in enumerate(commit)}
    for src, dst in edges:
        assert dispatch_pos[src] < dispatch_pos[dst], \
            f"{src} 必须排在 {dst} 前面才能分发"
        assert commit_pos[src] < commit_pos[dst], \
            f"{src} 必须先提交，{dst} 才能提交"


def test_conflict_key_has_all_three_parts():
    """冲突判据是三要素：表、索引、键值。少一个就判不准。"""
    params = _params_for("pyv.scenes.s03_conflict_key")
    assert len(params["key_parts"]) == len(params["key_values"]) == 3
    assert params["hot_index"] >= 0


def test_conflicting_transactions_share_the_same_row():
    """画出来的两条事务必须真的改到同一行，否则「冲突」无从谈起。"""
    dag = _params_for("pyv.scenes.s04_dependency_dag")
    conflict = _params_for("pyv.scenes.s03_conflict_key")
    notes = dict(zip((str(x) for x in dag["nodes"]),
                     (str(x) for x in dag["node_notes"])))
    assert notes[str(conflict["txn_a"])] == notes[str(conflict["txn_b"])], \
        "被画成冲突的两条事务必须指向同一行"


def test_ddl_pipeline_has_exactly_five_steps():
    """结构化 DDL 的五步是社区讨论里的划分，一步都不能多、不能少。"""
    params = _params_for("pyv.scenes.s04_ddl_pipeline")
    assert len(params["steps"]) == 5
    for name, desc in params["steps"]:
        assert name and desc, "每一步都要有名字和说明"


def test_shortfalls_are_four():
    """「4 条做不到的事」是口播里的数字，画面上就得是四张卡片。"""
    params = _params_for("pyv.scenes.s03_shortfalls")
    assert len(params["shortfalls"]) == 4
