"""视频线的项目配置——框架与内容之间那道缝。

**框架不带内容。** 立绘、曲库、品牌片这些是「出片必需的输入」，
但它们属于**用这套框架的人**：版权是他们的，口味是他们的，
换一个人用这套流水线，这些东西全都不一样。

所以仓库里只留**接口**——一份配置声明「我的素材在哪」：

```toml
# video/config.toml
[brand]
name = "Your Name"

[assets.mascot]
image = "character/mascot.png"   # 立绘（透明底 PNG）

[assets.music]
dir   = "music/tracks"           # 曲库目录
bed   = "music/tracks/bed.wav"   # 正文铺底那首

[assets.brand]
clips = "brand/clips"           # 品牌片（片头/片尾）
audio = "brand/audio"           # 品牌成品音轨
```

配置文件默认在 `video/config.toml`；用环境变量 `VIDEO_CONFIG` 可以指到别处
（同一个仓库里跑两套片子时用得上）。
**相对路径按配置文件所在目录解析**，绝对路径照用。

**素材缺失不是错误。** 没配就是没配：形象不画、品牌片不带、BGM 不铺，
流水线照样出片——这是「媒体产物不入库」的老规矩，在通用平台里更重要。
**配置里写明了路径但文件不在**才是问题：那说明配错了，`make doctor`
会把「配了但没有」和「压根没配」分开报出来。

**内置字体不在配置里**：它是**规则级**的东西（两台机器用同一份字体文件，
跨机的版式才一致），跟着仓库走。
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# video/ 是 pipeline/ 的上一级：pyv/config.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]

#: 配置文件名（放在 video/ 下）
CONFIG_NAME = "config.toml"

#: 环境变量：指到别的配置文件
ENV_VAR = "VIDEO_CONFIG"


def _as_path(base: Path, value: str | None) -> Path | None:
    """配置里的路径 → 绝对路径。空值 = 没配。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate)


@dataclass(frozen=True)
class Config:
    """一份项目配置。所有路径都是绝对路径。"""

    #: 配置文件本身（没找到配置时是 None）
    path: Path | None
    #: 相对路径的解析基准：配置文件所在目录；没有配置文件时是 video/
    base: Path
    #: 品牌名（落版、片尾字幕用）
    brand_name: str
    #: 品牌词：画面里出现它就算品牌标识
    brand_token: str
    #: 片头副标题
    brand_tagline: str
    #: 片尾落版（通常是站点地址）
    brand_site: str
    #: 立绘（透明底 PNG）。没配或文件不在 = 不画形象
    mascot: Path | None
    #: 无标牌立绘（平台判「过度营销信息」时换这份）
    mascot_plain: Path | None
    #: 落版头像
    avatar: Path | None
    #: 曲库目录（用户自带，不入库）
    music_dir: Path
    #: 正文铺底那首曲子
    music_bed: Path | None
    #: 曲库授权台账（入库——它记的是授权事实）
    music_library: Path
    #: 品牌片目录（片头/片尾 mp4）
    brand_clips: Path
    #: 品牌成品音轨目录
    brand_audio: Path
    #: 品牌片头尾的时间窗配置
    brand_windows: Path
    #: 品牌片片头的英文标语（留空 = 品牌片不画标语）
    brand_intro_tagline: str
    #: 品牌片片尾的副标题
    brand_outro_subtitle: str
    #: 品牌片片尾的旁白
    brand_outro_narration: str
    #: 角色形象的文件名前缀（形象图/姿态图的产物名）
    character_slug: str
    #: 角色外观描述：写进形象生成 prompt 的那一段。**参数，由使用者定**
    character_look: str
    #: 形象生成的原型参考图（使用者自己的原画/照片）。没配 = 不跑生成流程
    character_source: Path | None
    #: 配置里**写明了但文件不在**的路径（doctor 拿它区分「配错」与「没配」）
    declared_missing: list[tuple[str, Path]] = field(default_factory=list)
    #: 成片片头旁白（`{brand}` 已换成品牌名）。没配 = 空串
    brand_intro_line: str = ""
    #: 成片片尾旁白（`{site}` 已换成片尾落版地址）。没配 = 空串
    brand_outro_line: str = ""
    #: 片头药丸那句话的后缀（自带「· 」，拼标语不用再补分隔符）
    brand_share_suffix: str = ""
    #: 药丸里那段金字：白字/金字的**断点**由它给出。必须是 share_suffix 的尾巴
    brand_share_emphasis: str = ""
    #: 片尾落版的大字（不是胶囊标签，所以单独一项）
    brand_outro_title: str = ""
    #: 片尾落版的两条胶囊标签（标签条数固定，落版胶囊行只有三项：站点 + 这两条）
    brand_outro_labels: tuple[str, ...] = ()


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"配置文件读不了：{path}（{exc}）") from exc


def _dig(data: dict, *keys: str) -> dict:
    """逐层取表，缺了就当空表。"""
    node = data
    for key in keys:
        if not isinstance(node, dict):
            return {}
        node = node.get(key, {})
    return node if isinstance(node, dict) else {}


def _text(table: dict, key: str, default: str = "") -> str:
    value = table.get(key, default)
    return str(value).strip() if value is not None else default


def _list(table: dict, key: str) -> tuple[str, ...]:
    """配置里的数组 → 字符串元组。不是列表就当空；空串元素丢掉。

    非字符串元素先 `str()` 再 strip，免得 TOML 里写了数字就静默通过。
    """
    value = table.get(key)
    if not isinstance(value, (list, tuple)):
        return ()
    items = []
    for element in value:
        text = str(element).strip()
        if text:
            items.append(text)
    return tuple(items)


def _fill(text: str, *, brand: str, site: str) -> str:
    """占位符替换：``{brand}`` → 品牌名，``{site}`` → 片尾落版地址。

    替换只在这里做一份——shell 与 Python 拿到的是同一句成话。
    """
    return text.replace("{brand}", brand).replace("{site}", site)


def build(data: dict, *, path: Path | None, base: Path) -> Config:
    """把一份 TOML 数据装配成 Config。"""
    brand = _dig(data, "brand")
    character = _dig(data, "character")
    mascot = _dig(data, "assets", "mascot")
    avatar = _dig(data, "assets", "avatar")
    music = _dig(data, "assets", "music")
    brand_assets = _dig(data, "assets", "brand")

    music_dir = _as_path(base, _text(music, "dir")) or (base / "music" / "tracks")
    brand_clips = _as_path(base, _text(brand_assets, "clips")) or (base / "brand" / "clips")
    brand_audio = _as_path(base, _text(brand_assets, "audio")) or (base / "brand" / "audio")

    config = Config(
        path=path,
        base=base,
        brand_name=_text(brand, "name", "Your Name"),
        brand_token=_text(brand, "token", "yourbrand"),
        brand_tagline=_text(brand, "tagline", "Your Tagline"),
        brand_site=_text(brand, "site", "example.com"),
        mascot=_as_path(base, _text(mascot, "image")),
        mascot_plain=_as_path(base, _text(mascot, "plain")),
        avatar=_as_path(base, _text(avatar, "image")),
        music_dir=music_dir,
        music_bed=_as_path(base, _text(music, "bed")),
        music_library=_as_path(base, _text(music, "library")) or (base / "music" / "library.json"),
        brand_clips=brand_clips,
        brand_audio=brand_audio,
        brand_windows=_as_path(base, _text(brand_assets, "windows")) or (base / "brand" / "brand_windows.json"),
        brand_intro_tagline=_text(brand, "intro_tagline"),
        brand_outro_subtitle=_text(brand, "outro_subtitle")
        or f"{_text(brand, 'name', 'Your Name')} · {_text(brand, 'tagline', 'Your Tagline')}",
        brand_outro_narration=_text(brand, "outro_narration"),
        character_slug=_text(character, "slug", "mascot"),
        brand_intro_line=_fill(
            _text(brand, "intro_line"),
            brand=_text(brand, "name", "Your Name"),
            site=_text(brand, "site", "example.com"),
        ),
        brand_outro_line=_fill(
            _text(brand, "outro_line"),
            brand=_text(brand, "name", "Your Name"),
            site=_text(brand, "site", "example.com"),
        ),
        brand_share_suffix=_text(brand, "share_suffix"),
        brand_share_emphasis=_text(brand, "share_emphasis"),
        brand_outro_title=_text(brand, "outro_title"),
        brand_outro_labels=_list(brand, "outro_labels"),
        character_look=_text(character, "look"),
        character_source=_as_path(base, _text(character, "source")),
    )
    return config


def load(path: str | Path | None = None) -> Config:
    """读配置。没指定就找 `video/config.toml`；再没有就返回默认配置。"""
    if path is not None:
        target = Path(path).expanduser()
        if not target.is_file():
            raise FileNotFoundError(f"配置文件不存在：{target}")
        return build(_load_toml(target), path=target, base=target.parent)

    env = os.environ.get(ENV_VAR)
    if env:
        target = Path(env).expanduser()
        if not target.is_file():
            raise FileNotFoundError(
                f"{ENV_VAR} 指到了 {target}，但那个文件不存在"
            )
        return build(_load_toml(target), path=target, base=target.parent)

    default = AIV_ROOT / CONFIG_NAME
    if default.is_file():
        return build(_load_toml(default), path=default, base=default.parent)
    return build({}, path=None, base=AIV_ROOT)


_CACHE: Config | None = None


def config() -> Config:
    """进程内缓存的配置。"""
    global _CACHE
    if _CACHE is None:
        _CACHE = load()
    return _CACHE


def reset() -> None:
    """丢掉缓存（测试里改完配置要调）。"""
    global _CACHE
    _CACHE = None
