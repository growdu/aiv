"""视觉分镜契约的守卫。

**分工原则**：本期内容进契约，版式常量留代码。

这一期（以及以后每一期）的文案、数字、标签都写在期目录里的
`contract.json` 里，场景渲染器不许再写死它们。这组测试盯着三件事：

1. 契约本身是完整的——句子恰好被覆盖一次，每段参数齐全，渲染器都存在；
2. 文案没有回流到代码——场景源码里不再出现契约中的文案；
3. 契约化之后画面没变——逐像素指纹与改造前一致。

第 3 条是关键：把文案搬进契约最容易出的事故是「顺手把画面也改了」，
而画面变了不会有任何报错，只有逐像素比对能发现。

**契约从哪来。** 一期 = 一个目录：磁盘上有期就读期目录里的契约，
没有期就读**夹具期**（`tests/fixtures/fixture/contract.json`）。
结构守卫不依赖磁盘上有没有期。

**逐像素基准的处境**（见 `tests/fixtures/scene_baseline.json`）：
基准是**已删的六期**抓的，那六期的契约不在了，画面没法复现。
所以逐像素那条在「当前契约与基准没有交集」时**跳过并说清楚为什么**，
而不是假装比过了；基准本身的形状（覆盖了哪些场景模块、键的格式）
仍然由测试钉住——新加一个场景模块却没重抓基准，那两条会红。
"""

import ast
import hashlib
import importlib
import json
from pathlib import Path

import cairo
import pytest

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod
from pyv.params import MissingParam, Params

FIXTURES = Path(__file__).parent / "fixtures"
BASELINE = FIXTURES / "scene_baseline.json"

#: 夹具期的契约（磁盘上没有期时读它）。
FIXTURE_CONTRACT = FIXTURES / "fixture" / "contract.json"


def _contract_sources() -> list[tuple[str, Path]]:
    """（标签, 契约路径）列表。

    有期读期目录里的；没有期读夹具期。
    """
    sources = [(slug, episodes_mod.contract_path(slug))
               for slug in episodes_mod.known_eps()]
    sources = [(slug, path) for slug, path in sources if path.is_file()]
    return sources or [("fixture", FIXTURE_CONTRACT)]


#: 每一期的契约。结构与文案守卫生效在**每一期**上。
ALL_CONTRACT_PATHS = [path for _, path in _contract_sources()]
EPISODES = [label for label, _ in _contract_sources()]

# 短于 3 个字符的文案不判：两个汉字的词（"输出"、"并行"）到处都是，
# 拿它当判据只会天天误报。3 个字起才算「一句具体的文案」。
MIN_COPY_LENGTH = 3

#: 基准抓取的时刻。抓基准的脚本与这里必须用同一份，否则键对不上。
BASELINE_TIMES = (0.0, 0.45, 0.9)


def _baseline_key(episode: str, segment, t: float) -> str:
    """基准的键：期号 + 段 id + 渲染器 + 时刻。

    **必须带期号**：`s01_intro` 与 `s06_outro` 多期都在用，而每期的
    `params` 不同（标题文案各不一样）→ 画面不同 → 哈希不同。只按渲染器
    存一份，后面的期就永远比不到。
    """
    return f"{episode}/{segment.id}/{segment.renderer}@{t}"


@pytest.fixture(scope="module")
def contract():
    """当前那一期的契约（第一期；没有期就是夹具期）。"""
    return contract_mod.load_contract(ALL_CONTRACT_PATHS[0])


@pytest.fixture(scope="module")
def all_contracts():
    """每一期的契约，按标签索引。"""
    return {label: contract_mod.load_contract(path)
            for label, path in _contract_sources()}


def _baseline_data() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _baseline_renderers() -> set[str]:
    """基准里出现过的场景模块名。"""
    return {key.split("/")[2].split("@")[0].rsplit(".", 1)[-1]
            for key in _baseline_data()["frames"]}


# ---------------------------------------------------------------- 契约完整性


@pytest.mark.parametrize("episode", EPISODES)
def test_contract_loads_and_has_segments(all_contracts, episode):
    contract = all_contracts[episode]
    assert contract.version == 1
    assert contract.episode
    assert contract.title
    assert contract.segments


@pytest.mark.parametrize("episode", EPISODES)
def test_contract_covers_every_sentence_exactly_once(all_contracts, episode):
    """句子恰好被覆盖一次——漏一句、重一句都不行。

    **「恰好一次」是判据，不是巧合**：漏掉的句子在成片里没有画面，
    重复分配的句子会让同一句配两张图。
    """
    contract = all_contracts[episode]
    seen: list[int] = []
    for segment in contract.segments:
        seen.extend(segment.sentences)
    assert sorted(seen) == list(range(contract.sentence_count)), (
        f"{episode} 的句子没被恰好覆盖一次：{sorted(seen)}"
    )


@pytest.mark.parametrize("episode", EPISODES)
def test_every_segment_renderer_exists(all_contracts, episode):
    for segment in all_contracts[episode].segments:
        module = importlib.import_module(segment.renderer)
        assert callable(module.render), segment.renderer


@pytest.mark.parametrize("episode", EPISODES)
def test_every_segment_has_all_required_params(all_contracts, episode):
    """场景声明了必填参数，契约必须一个不缺地给出来。"""
    for segment in all_contracts[episode].segments:
        module = importlib.import_module(segment.renderer)
        required = getattr(module, "REQUIRED", ())
        assert required, f"{segment.renderer} 没有声明 REQUIRED"
        missing = [k for k in required if k not in segment.params]
        assert not missing, f"{segment.id} 缺参数：{missing}"


@pytest.mark.parametrize("episode", EPISODES)
def test_contract_params_are_not_empty_strings(all_contracts, episode):
    """画面上不能出现空文案——那通常是漏填。"""
    for segment in all_contracts[episode].segments:
        for key, value in segment.params.items():
            if isinstance(value, str):
                assert value.strip(), f"{segment.id} 的 {key} 是空串"


# ------------------------------------------------------- 文案不许回流到代码


def _scene_literals(module_name: str) -> list[str]:
    """场景源码里的字符串字面量。

    只取字面量，是因为**字面量才是真正会画到画面上的文本**。
    标识符（`worker_h`）和注释是代码，不是内容——按整份源码做子串匹配，
    值 `worker` 会被 `worker_h` 这种版式变量名误伤。
    """
    module = importlib.import_module(module_name)
    source = getattr(module, "__file__", None)
    if source is None:
        raise AssertionError(f"模块 {module_name} 没有 __file__，读不了源码")
    tree = ast.parse(Path(source).read_text(encoding="utf-8"))
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _param_keys(contract) -> set[str]:
    """所有场景声明的参数键。

    参数键是代码里的标识（`decoder_label`），不是文案，判定时要排除掉——
    否则值 `decoder` 会被参数名误伤。
    """
    keys: set[str] = set()
    for segment in contract.segments:
        module = importlib.import_module(segment.renderer)
        keys.update(getattr(module, "REQUIRED", ()))
    return keys


def _copy_leaks(literals: list[str], params: dict, keys: set[str]) -> list[tuple]:
    """找出字面量里藏着契约文案的地方，返回 (key, value, literal)。"""
    leaks: list[tuple] = []
    values = {v for v in params.values() if isinstance(v, str)}
    for key, value in params.items():
        if not isinstance(value, str) or len(value) < MIN_COPY_LENGTH:
            continue
        for literal in literals:
            # 参数键本身跳过；但万一某个参数值就长成参数键的样子，仍然要查。
            if literal in keys and literal not in values:
                continue
            if value in literal:
                leaks.append((key, value, literal))
    return leaks


@pytest.mark.parametrize("episode", EPISODES)
def test_scene_source_contains_no_episode_copy(all_contracts, episode):
    """契约里的文案不得出现在场景源码里。

    文案写在代码里，就等于又回到了「改一句话要改代码」的老路。

    判定规则：把场景源码解析成 AST，取出所有字符串字面量，
    凡是**包含**契约里那句文案的字面量都算回流——除了参数键本身。
    """
    contract = all_contracts[episode]
    keys = _param_keys(contract)
    for segment in contract.segments:
        literals = _scene_literals(segment.renderer)
        leaks = _copy_leaks(literals, segment.params, keys)
        assert not leaks, (
            f"{segment.renderer} 里写死了契约文案："
            + "；".join(f"{k}={v!r}（命中 {lit!r}）" for k, v, lit in leaks)
            + "，它们应该只存在于契约里"
        )


def test_copy_guard_actually_catches_a_leak(contract):
    """守卫自己也要验：塞一句硬编码文案进去，必须被抓出来。

    没有这条，守卫一旦写坏（比如规则太松到什么都不匹配）就会一直绿着，
    而它恰恰是最该被信任的那条测试。
    """
    segment = contract.segments[0]
    keys = _param_keys(contract)
    value = segment.params["title"]
    leaks = _copy_leaks([f"text(ctx, {value!r})"], segment.params, keys)
    assert leaks, "守卫没抓到硬编码文案，它已经失效了"


@pytest.mark.parametrize("episode", EPISODES)
def test_copy_guard_works_for_every_episode(all_contracts, episode):
    """守卫对每一期都要有效，不只是第一期。"""
    contract = all_contracts[episode]
    keys = _param_keys(contract)
    segment = contract.segments[0]
    value = segment.params["title"]
    leaks = _copy_leaks([f"text(ctx, {value!r})"], segment.params, keys)
    assert leaks, f"{episode} 的文案回流守卫没生效"


# ------------------------------------------------------------ 缺参数要报错


def test_missing_param_raises_with_scene_name(contract):
    segment = contract.segments[0]
    broken = dict(segment.params)
    broken.pop(next(iter(broken)))
    with pytest.raises(MissingParam) as exc:
        Params(broken, segment.id)["__missing__"]
    assert "__missing__" in str(exc.value)


def test_scene_render_rejects_incomplete_params(contract):
    """参数不全时必须当场报错，不能悄悄退回硬编码的旧文案。"""
    segment = contract.segments[0]
    module = importlib.import_module(segment.renderer)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 180)
    ctx = cairo.Context(surface)
    with pytest.raises(MissingParam):
        module.render(ctx, 0.5, 320, 180, {})


def test_render_scene_validates_params_before_rendering(tmp_path, contract):
    """渲染入口也要查参数——不能等渲染到一半才炸。"""
    from pyv import render
    from pyv.timeline import Scene

    scene = Scene(
        id="s01", start=0.0, end=1.0, type="code", subtitle="测试", renderer="pyv.scenes.s01_intro", params={}
    )
    with pytest.raises(MissingParam):
        render.render_scene(scene, tmp_path / "x.mp4", width=320, height=180)


# ------------------------------------------------------------ 逐像素回归


def _without_mascot(monkeypatch) -> None:
    """让形象一律不画。

    基准指纹若带着形象素材抓，素材一改（重新生成形象、加眼镜）基准就红——
    测试会退化成「盯素材的字节」，而不是「盯这次改造有没有改到画面」。
    强制不画，基准才只对**场景代码**负责。

    （形象 PNG 现在是入库的，见 `video/.gitignore` 的放行清单；但基准仍然
    绑在「不画形象」上——基准要盯的是代码，不是素材。）

    落版头像 `avatar.jpg` 是入库的，两边都会画，不受这个开关影响。
    """
    from pyv import character

    def _no_mascot(self) -> None:
        self._mode = "none"

    monkeypatch.setattr(character.Mascot, "_load", _no_mascot)


def _scene_frame_hash(module_name: str, params: dict, t: float) -> str:
    from pyv.palette import COLORS, hex_to_rgb

    module = importlib.import_module(module_name)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*hex_to_rgb(COLORS["bg"]))
    ctx.paint()
    module.render(ctx, t, 1920, 1080, params)
    return hashlib.sha256(bytes(surface.get_data())).hexdigest()


@pytest.fixture
def baseline_frames():
    """基准指纹里的逐帧哈希。

    基准**绑在字体上**：换一款字体，同一段文字的像素就不同，比出来的是
    噪声不是信号。

    基准**也绑在平台上**：macOS 的 cairo 走 CoreText，Linux 走 FreeType，
    栅格化不同 → 同一个字体、同一段文字，像素仍然不同。跨平台比像素是
    拿噪声当信号，所以平台不同就跳过——**跨机的版式由
    `tests/test_layout_fingerprint.py` 守**（比轮廓、坐标与步进宽度，
    那三样来自字体文件与场景代码，与栅格化无关）。

    做成 fixture 而不是每次手动调一次：**要跟基准比像素的测试必须伸手要它**，
    于是「忘了加守卫」这件事不会再发生（跨平台 CI 第一次就抓到了这种漏）。
    """
    import platform

    data = _baseline_data()
    from pyv import fonts

    baseline_font = data["capture"].get("font", "")
    current = fonts.font_family()
    if baseline_font and baseline_font != current:
        pytest.skip(
            f"基准是在「{baseline_font}」下抓的，当前机器是「{current}」——"
            f"跨字体像素本来就不同，这条基准在这里测不出东西"
        )
    baseline_platform = data["capture"].get("platform", "")
    if baseline_platform and baseline_platform != platform.system():
        pytest.skip(
            f"基准是在 {baseline_platform} 上抓的，当前机器是 {platform.system()}——"
            f"cairo 在两边用的栅格化器不同（macOS 走 CoreText，Linux 走 "
            f"FreeType），跨平台比像素是拿噪声当信号。"
            f"跨机的版式由 tests/test_layout_fingerprint.py 守"
        )
    return data["frames"]


def test_the_baseline_keys_are_well_formed():
    """基准的键必须是 `期/段/渲染器@时刻`。

    **键写错了，比对时一条都匹配不上**——守卫看着绿，实际什么都没比。
    """
    data = _baseline_data()
    for key in data["frames"]:
        parts = key.split("/")
        assert len(parts) == 3, f"基准的键不是三段：{key}"
        episode, segment, tail = parts
        assert episode and segment, key
        renderer, _, moment = tail.partition("@")
        assert renderer.startswith("pyv.scenes."), key
        assert float(moment) in BASELINE_TIMES, (
            f"{key} 的时刻不在基准抓取的时刻里：{BASELINE_TIMES}"
        )


def test_the_baseline_covers_every_scene_module():
    """基准里的渲染器集合必须等于目录里的场景模块集合。

    照 `tests/test_scene_overlap.py::test_every_scene_module_is_covered`
    的写法：集合相等，不是子集。新加一个模块却没进任何一期契约，
    基准就扫不到它——守卫覆盖不到的那部分，坏了也不会红。
    """
    in_baseline = _baseline_renderers()
    scenes_dir = Path(contract_mod.__file__).parent / "scenes"
    on_disk = {
        path.stem for path in scenes_dir.glob("*.py")
        if path.stem != "__init__"
    }
    assert in_baseline == on_disk, (
        f"基准没盖住全部场景模块：目录有基准没有 {sorted(on_disk - in_baseline)}；"
        f"基准有目录没有 {sorted(in_baseline - on_disk)}"
    )


def test_the_baseline_covers_every_renderer_in_use(all_contracts):
    """当前契约用到的每个场景模块都要在基准里。

    **这是「重抓基准」的信号**：新加一期、契约里用了新场景模块，
    而基准还没重抓——这条就红。
    """
    used = {segment.renderer.split(".")[-1]
            for contract in all_contracts.values()
            for segment in contract.segments}
    missing = used - _baseline_renderers()
    assert not missing, (
        f"基准里没有这些场景模块的帧：{sorted(missing)}——"
        f"重抓：python3 scripts/capture_scene_baseline.py"
    )


def test_contract_driven_rendering_is_pixel_identical(all_contracts, monkeypatch,
                                                      baseline_frames):
    """契约化之后，画面必须与改造前一模一样。

    基准指纹是「文案还写死在场景代码里」时抓的。把文案搬进契约最容易出的
    事故就是顺手把画面也改了——而画面变了不会有任何报错，只有逐像素比对能发现。

    **覆盖当前每一期的每一段**：基准按段抓，键带期号与段 id。

    **基准里没有当前这一期时跳过并说清楚**：基准是**已删的六期**抓的，
    那六期的契约不在了，画面复现不出来。没有交集就不是「比过了」，
    是「比不了」——这里明说，不装作绿。
    """
    _without_mascot(monkeypatch)
    baseline = baseline_frames
    compared = 0
    for episode, contract in all_contracts.items():
        for segment in contract.segments:
            for t in BASELINE_TIMES:
                key = _baseline_key(episode, segment, t)
                if key not in baseline:
                    continue
                compared += 1
                actual = _scene_frame_hash(segment.renderer, segment.params, t)
                assert actual == baseline[key], f"{key} 的画面变了：文案搬进契约不该动到画面"
    if not compared:
        pytest.skip(
            "逐像素基准里没有当前任何一期的帧：基准是已删的六期抓的，"
            "那些契约不在了，画面复现不出来。"
            "重抓（先修脚本：它还指着旧路径 video/contracts/）："
            "python3 scripts/capture_scene_baseline.py"
        )


def test_pixel_baseline_excludes_local_mascot_asset(contract, all_contracts,
                                                     monkeypatch, baseline_frames):
    """基准指纹里不含本机的形象素材。

    基准必须与形象素材无关：素材一改（重新生成形象）基准就红，等于把测试
    绑死在素材的字节上，而它本该盯的是「代码有没有改画面」。
    这条测试盯住「基准与素材无关」这个前提本身。
    """
    from pyv import character

    data = _baseline_data()
    assert data["capture"]["mascot"] == "none", "基准必须是在不画形象时抓的"
    assert data["capture"]["times"] == list(BASELINE_TIMES)

    # 帧数由基准自己的键推出来：每个（期, 段, 时刻）一条。
    triples = {
        (key.split("/")[0], key.split("/")[1], key.split("/")[2].partition("@")[2])
        for key in data["frames"]
    }
    assert len(data["frames"]) == len(triples), (
        "基准里有重复的键——同一段同一时刻存了两份"
    )

    # 主工作区里形象素材是在的：有它也必须对得上「不画形象」的基准，
    # 说明素材确实没进比较。
    if not character.STATIC_IMAGE.is_file():
        pytest.skip("本机没有形象素材，这条前提无从验证")
    segment = next(s for s in contract.segments
                   if s.renderer == "pyv.scenes.s01_intro")
    key = _baseline_key(contract.episode, segment, 0.45)
    if key not in baseline_frames:
        pytest.skip(
            f"基准里没有 {key}（基准是已删的六期抓的）——"
            f"这条前提要等基准重抓才能验"
        )
    _without_mascot(monkeypatch)
    assert _scene_frame_hash("pyv.scenes.s01_intro", segment.params, 0.45) == baseline_frames[key]
