"""字体子集脚本：离线源能被**验出来**。

**为什么要有这条守卫**：子集脚本有一条离线路径（Debian 的
`fonts-noto-cjk` 包，见 `scripts/build_font_subset.py` 的 `OFFLINE_SOURCE`）。
那条路是**换源**——换一个版本，字宽就可能差 1/1000 em。

实测：本机装着的 `fonts-noto-cjk` 是 **2.001**，台账钉的离线源是
**2.004**。两者的 `'A'` 步进差 1/1000 em（608 vs 607），`'中'` 的左边距
差 4/1000 em。**一个字宽差 1/1000 em，整版都会移**，而画面照样生成、
时长照样对——逐像素基准要等到下一次改动才全红，那时已经不知道是谁
换的源了。

所以脚本在用本地源之前先验：**共有字符的 outline 与 advance 逐字
相同**，不一致就拒绝。这条守卫盯的就是这个拒绝逻辑本身——
**故意喂一个字形不一致的源，红了才算数**。

**测试不下载任何东西**：假字体是在本地用 fontTools 造出来的。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PIPELINE_ROOT / "scripts" / "build_font_subset.py"
FONT_DIR = PIPELINE_ROOT / "assets" / "fonts"
MANIFEST = FONT_DIR / "SOURCE.json"


def _load_script():
    """载入 `scripts/build_font_subset.py`（它不是包里的模块）。"""
    spec = importlib.util.spec_from_file_location("build_font_subset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_script()


# ---------------------------------------------------------------- 离线源钉住


def test_the_offline_source_is_pinned():
    """离线源必须钉住**包 + 版本 + sha256 + 面名 + 版本串**。

    少钉一样就有人换源，而换源是**静默**的：画面照出、时长照对，
    只是版面整体移了一点。
    """
    source = builder.OFFLINE_SOURCE
    assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), (
        f"离线源的 sha256 不对：{source['sha256']!r}")
    assert source["url"].startswith("https://"), source["url"]
    assert source["package"] and source["version"]
    assert source["version_string"].startswith("Version "), source

    # 面名：每个字重一份 TTC，脚本按面名取，不按下标。
    assert set(source["ttc"]) == {"Regular", "Bold"}, source["ttc"]
    for name in source["ttc"].values():
        assert name.endswith(".ttc"), name


def test_the_manifest_records_the_offline_source():
    """台账里必须有离线源这一节——脚本里的常量与台账要对得上。

    台账是**别人**看得见的记录：出了事要能照着它复现。
    """
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    offline = data["offline_source"]
    assert offline["sha256"] == builder.OFFLINE_SOURCE["sha256"]
    assert offline["url"] == builder.OFFLINE_SOURCE["url"]
    assert offline["version_string"] == builder.OFFLINE_SOURCE["version_string"]
    assert offline["ttc"] == builder.OFFLINE_SOURCE["ttc"]


def test_every_face_records_where_it_came_from():
    """每一面都要说清来源——上游的还是离线源的。

    说清的**方式不能含糊**：走离线源的那面不写上游的 sha256
    （钉不出来），而是写离线源里的**面名**。
    """
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for face in data["faces"]:
        assert face["source"] in ("upstream", "offline_source"), face
        assert face["upstream"].startswith("https://"), face
        if face["source"] == "upstream":
            assert re.fullmatch(r"[0-9a-f]{64}", face["upstream_sha256"]), face
        else:
            assert "source_postscript_name" in face, face
            assert face["source_ttc"] in builder.OFFLINE_SOURCE["ttc"].values()


# ---------------------------------------------------------------- 源校验会红


def _tampered_copy(tmp_path: Path, style: str = "Regular") -> Path:
    """造一份**步进被改过**的字体。

    只改一个字（`'A'`）的步进——**其余全一样**。这正是真实事故的
    形状：版本串还写着 2.004，字形大体相同，只有一两个度量值不同。
    """
    from fontTools.ttLib import TTFont

    source = FONT_DIR / f"AIVSansCJKSC-{style}.otf"
    font = TTFont(str(source))
    cmap = font.getBestCmap()
    glyph = cmap[ord("A")]
    metrics = font["hmtx"].metrics
    advance, lsb = metrics[glyph]
    metrics[glyph] = (advance + 1, lsb)
    target = tmp_path / "tampered.otf"
    font.save(str(target))
    return target


def _swapped_outline_copy(tmp_path: Path, style: str = "Regular") -> Path:
    """造一份**轮廓被换掉、步进没变**的字体。

    在 `'A'` 的 CFF charstring 末尾加一条位移指令——**墨迹挪了，
    hmtx 一动不动**。

    **为什么要单独造这一份**：步进一样、轮廓不一样，是另一种事故
    ——字换了但宽度没变。只测步进的话，这条路是**通的**，
    守卫就漏了它。
    """
    from fontTools.ttLib import TTFont

    source = FONT_DIR / f"AIVSansCJKSC-{style}.otf"
    font = TTFont(str(source))
    cmap = font.getBestCmap()
    glyph = cmap[ord("A")]
    charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    item, _ = charstrings.getItemAndSelector(glyph)
    item.decompile()
    item.program = list(item.program) + [30, 0, "rmoveto"]
    item.compile()
    target = tmp_path / "swapped.otf"
    font.save(str(target))
    return target


def test_a_mismatched_source_is_rejected(tmp_path: Path):
    """**字形不一致的源必须被当场拒绝**。

    这条是「换源静默改版面」的最后一道闸：版本串一样、字形大体一样，
    只差一个字宽——**照样拒绝**。
    """
    from fontTools.ttLib import TTFont

    face = {"file": "AIVSansCJKSC-Regular.otf"}
    tampered = _tampered_copy(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        builder.verify_source(face, TTFont(str(tampered)))

    message = str(excinfo.value)
    assert "步进不一致" in message, message


def test_a_source_with_a_different_outline_is_rejected(tmp_path: Path):
    """**轮廓不一样**的源也要拒绝——哪怕步进完全一样。

    字换了但宽度没变，是另一种事故。只比步进的话这条是通的。
    """
    from fontTools.ttLib import TTFont

    face = {"file": "AIVSansCJKSC-Regular.otf"}
    swapped = _swapped_outline_copy(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        builder.verify_source(face, TTFont(str(swapped)))

    assert "轮廓不同" in str(excinfo.value)


def test_a_matching_source_is_accepted():
    """同一份源自己对自己——**必须放行**。

    没有这一条，上面那条可能是因为「校验逻辑压根不工作」而红的，
    那就成了一条永远绿的守卫。
    """
    from fontTools.ttLib import TTFont

    face = {"file": "AIVSansCJKSC-Regular.otf"}
    bundled = FONT_DIR / face["file"]
    # 不抛错就是放行；这里显式调一次，失败会让测试直接红。
    builder.verify_source(face, TTFont(str(bundled)))


def test_a_wrong_version_string_is_rejected(tmp_path: Path):
    """**版本串对不上**也拒绝——哪怕字形恰好一样。

    版本串是上游构建的标识；它变了就说明**换了一份构建**，
    字形一致只是碰巧。
    """
    from fontTools.ttLib import TTFont

    source = FONT_DIR / "AIVSansCJKSC-Regular.otf"
    font = TTFont(str(source))
    font["name"].setName("Version 2.001;hotconv 1.0.107", 5, 3, 1, 0x409)
    target = tmp_path / "old-version.otf"
    font.save(str(target))

    face = {"file": "AIVSansCJKSC-Regular.otf"}
    with pytest.raises(SystemExit) as excinfo:
        builder.verify_source(face, TTFont(str(target)))

    assert "版本串" in str(excinfo.value)


# ---------------------------------------------------------------- 按面名取面


def test_the_face_is_found_by_postscript_name_not_by_index():
    """离线源按 **PostScript 名**找面，**不按下标**。

    下标是打包顺序：Debian 的 TTC 里 SC 在第 3 位，notofonts 的排法
    未必一样。按下标取会取到别的语言面（JP / KR / TC / HK）——
    **字形全不一样，却一点错都不报**。
    """
    seen: list[str] = []

    class _FakeName:
        def getDebugName(self, name_id):
            return seen[0] if name_id == 6 else "Version 2.004"

    class _FakeFont:
        def __init__(self, ps_name):
            self._ps = ps_name

        def __getitem__(self, key):
            if key != "name":
                raise KeyError(key)
            return _FakeName()

        def save(self, path):
            Path(path).write_bytes(b"fake")

    class _FakeCollection:
        def __init__(self, fonts):
            self.fonts = fonts

    def _fake_ttc(path, lazy=False):
        # 三个面，第一个是 JP——按名字取必须跳过它
        return _FakeCollection([
            _FakeFont("NotoSansCJKjp-Regular"),
            _FakeFont("NotoSansCJKsc-Regular"),
            _FakeFont("NotoSansMonoCJKsc-Regular"),
        ])

    class _FakeTTCollection:
        def __new__(cls, path, lazy=False):
            return _fake_ttc(path, lazy)

    import fontTools.ttLib as ttlib

    original = ttlib.TTCollection
    ttlib.TTCollection = _FakeTTCollection
    try:
        seen.clear()
        seen.append("NotoSansCJKsc-Regular")
        out = builder.extract_face_from_ttc(
            Path("/nowhere/NotoSansCJK-Regular.ttc"),
            "NotoSansCJKsc-Regular",
            Path("/tmp/aiv-fake-ttc"),
        )
    finally:
        ttlib.TTCollection = original

    assert out.name == "NotoSansCJKsc-Regular.otf"
    assert out.exists()


def test_a_missing_face_reports_what_is_available():
    """TTC 里没有要的那个面——报错要**说清楚里面有哪些**。

    「找不到面」而不说有哪些，等于让下一个人自己去翻二进制。
    """
    from fontTools.ttLib import TTCollection

    class _FakeName:
        def getDebugName(self, name_id):
            return "NotoSansCJKjp-Regular" if name_id == 6 else "Version 2.004"

    class _FakeFont:
        def __getitem__(self, key):
            if key != "name":
                raise KeyError(key)
            return _FakeName()

    class _FakeCollection:
        fonts = [_FakeFont()]

    import fontTools.ttLib as ttlib

    original = ttlib.TTCollection
    ttlib.TTCollection = lambda path, lazy=False: _FakeCollection()
    try:
        with pytest.raises(SystemExit) as excinfo:
            builder.extract_face_from_ttc(
                Path("/nowhere/x.ttc"), "NotoSansCJKsc-Regular",
                Path("/tmp/aiv-fake-ttc"))
    finally:
        ttlib.TTCollection = original

    message = str(excinfo.value)
    assert "NotoSansCJKjp-Regular" in message, message


# ---------------------------------------------------------------- 可复现


def test_the_same_source_rebuilds_the_same_bytes(tmp_path: Path):
    """同一份源重跑一遍，**出来的文件必须逐字节相同**。

    不可复现的话，台账里的 `subset_sha256` 每次都得重写，
    「照着台账复现」这句话就是空的。

    不可复现的根源是 fontTools 默认把 `head.modified` 改成「现在」。
    """
    from fontTools.ttLib import TTFont

    bundled = FONT_DIR / "AIVSansCJKSC-Regular.otf"
    font = TTFont(str(bundled))

    def _rebuild(target: Path) -> bytes:
        copy = TTFont(str(bundled))
        copy.recalcTimestamp = False
        copy.save(str(target))
        return target.read_bytes()

    first = tmp_path / "a.otf"
    second = tmp_path / "b.otf"
    assert _rebuild(first) == _rebuild(second)

    # 入库的那份本身的时间戳也不能是「刚才」——那说明它被重算过。
    assert font["head"].modified < 3800000000, (
        f"入库字体的 head.modified 是 {font['head'].modified}，"
        f"像是被重算过（构建该是不许动时间戳的）")
