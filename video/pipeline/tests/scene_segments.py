"""场景段的来源：期目录里的契约，或按场景模块合成的一段。

**为什么要有它。** 「哪一段用哪个渲染器、画面上写什么」这件事只存在于
契约里。一期 = 一个目录，磁盘上现在没有期——画面级的守卫（遮挡、溢出、
时序）就没有输入可扫。

所以这里给两种来源：

- **有期**：读期目录里的契约（那才是真在片子上用的文案与数字）；
- **没有期**：按目录里的每个场景模块合成一段，params 取自
  `scene_params.py`——**形状照场景代码要的来，内容不算数**。

「覆盖全部场景模块」这个声称因此不依赖磁盘上有没有期。

**合成的那一份不冒充契约**：它不是 `parse_contract` 出来的，
只是把渲染器与 params 凑齐，好让画面级的守卫有东西可扫。
"""
from __future__ import annotations

from pathlib import Path

from pyv import contract as contract_mod
from pyv import episodes as episodes_mod

import scene_params

#: 场景模块目录。
SCENES_DIR = Path(contract_mod.__file__).parent / "scenes"

#: 夹具期（`tests/fixtures/演示系列/演示合集/夹具文档/short/`）。
FIXTURE_EPISODE_DIR = (Path(__file__).parent / "fixtures" / "演示系列"
                       / "演示合集" / "夹具文档" / "short")
FIXTURE_CONTRACT = FIXTURE_EPISODE_DIR / "contract.json"
FIXTURE_SCRIPT = FIXTURE_EPISODE_DIR / "口播稿.md"


def scene_modules() -> list[str]:
    """目录里的场景模块名（`s01_intro` 这样的），按名字排序。"""
    return sorted(path.stem for path in SCENES_DIR.glob("*.py")
                  if path.stem != "__init__")


def _from_contracts() -> list[tuple[str, contract_mod.Segment]]:
    out: list[tuple[str, contract_mod.Segment]] = []
    for slug in episodes_mod.known_eps():
        path = episodes_mod.contract_path(slug)
        if not path.is_file():
            continue
        contract = contract_mod.load_contract(path)
        for segment in contract.segments:
            out.append((slug, segment))
    return out


def _synthesized() -> list[tuple[str, contract_mod.Segment]]:
    out: list[tuple[str, contract_mod.Segment]] = []
    for module in scene_modules():
        name = f"pyv.scenes.{module}"
        out.append((module, contract_mod.Segment(
            id=module,
            renderer=name,
            sentences=(0,),
            params=scene_params.params_for(name),
        )))
    return out


def segments() -> list[tuple[str, contract_mod.Segment]]:
    """（标签, 段）列表。

    标签是期 slug（来自契约）或场景模块名（合成的那一份）。
    """
    from_contracts = _from_contracts()
    return from_contracts or _synthesized()


def episode_sources() -> list[tuple[str, Path, Path]]:
    """（标签, 契约路径, 口播稿路径）。

    有期就读期目录里的；没有期就读**夹具期**——守卫总得有东西可扫，
    空的输入等于没守。
    """
    out: list[tuple[str, Path, Path]] = []
    for slug in episodes_mod.known_eps():
        contract = episodes_mod.contract_path(slug)
        script = episodes_mod.script_path(slug)
        if contract.is_file() and script.is_file():
            out.append((slug, contract, script))
    if out:
        return out
    return [("fixture", FIXTURE_CONTRACT, FIXTURE_SCRIPT)]


def subtitle_text() -> str:
    """一条真实字幕（字幕表的第一行）。

    **取口播稿里的字幕表**，不取测试自造的文案——自造的字不在生产
    字符集里，内置字体的字形守卫就管不到生产上真正会出现的字。
    """
    from pyv import align

    label, _, script = episode_sources()[0]
    rows = align.parse_subtitle_table(script)
    assert rows, f"{label} 的口播稿里没有字幕"
    return rows[0]


def narration() -> Path | None:
    """一份旁白音频；**没有就返回 None**。

    旁白是**使用者自带的素材**：音色是他们的，授权也是他们的，
    仓库不带着走（见 `tests/test_assets_are_tracked.py`）。

    所以这里**不抛错**。抛错会把「这台机器没素材」说成「流水线坏了」——
    端到端测试看到 None 就跳过，等有素材的机器上再证明「能出片」。
    """
    for slug in episodes_mod.known_eps():
        path = episodes_mod.narration_path(slug)
        if path.is_file():
            return path
    return None


def bgm() -> Path | None:
    """正文铺底那首曲子；没配就返回 None。

    位置在 `video/config.toml` 的 `[assets.music].bed`——曲库是使用者的，
    曲子一首一首地授权。
    """
    from pyv import config as config_mod

    return config_mod.config().music_bed
