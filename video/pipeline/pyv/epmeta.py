"""每期的发布元数据：这一期在各个平台怎么自我介绍。

**入库的是事实**：元数据要评审、要版本化，所以进期目录
`video/episodes/<系列>/<合集>/<文档>/<档位>/publish.json`。
**不入库的是产物**：成片、发布包都留本机。

元数据只回答「这一期叫什么、封面取哪一帧、各平台的文案是什么」，
不回答「怎么发」——那是 adapter 的事。

平台段落里**缺一个字段就报错**，绝不静默补默认值：
补出来的默认值看起来能用，但它会让「作者忘了写」变得无声无息。

**这一层不认识任何平台。** 平台要什么字段、限额键叫什么名字，
写在平台自己的目录里（`platforms/<plat>/publish-spec.json`），
这一层只负责**读它、按它查**。写死平台名的后果很具体：
加一个平台要改视频线（上游），而「加平台只动 `platforms/`」这条规矩
对视频平台就不成立——那条规矩是整个平台层的地基。
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# video/ 是 pipeline/ 的上一级：pyv/epmeta.py → pyv → pipeline → video
AIV_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AIV_ROOT.parent
#: 发布元数据跟着期走：video/episodes/<系列>/<合集>/<文档>/<档位>/publish.json
EPISODES_DIR = AIV_ROOT / "episodes"
PUBLISH_NAME = "publish.json"
# 能力声明是契约层的数据文件。pyv 只**读**它，不 import 契约层的任何包。
# 声明住在平台自己的目录里：platforms/<plat>/capability.toml
PLATFORMS_DIR = REPO_ROOT / "platforms"
#: 发布规格：每个平台一份，住在它自己的目录里。
#: 形状（键名与取值域）见 `_normalize_spec`。
PUBLISH_SPEC_NAME = "publish-spec.json"

ERROR = "error"
WARNING = "warning"

# --- 发布规格：每个平台一份 --------------------------------------------------
#
# **规格是什么**：一个平台发一篇视频要哪些字段、每个字段对应能力声明里的
# 哪个限额键、哪些字段是整数、整数能取哪些值、什么条件下另一个字段必填。
#
# **它住在哪**：`platforms/<plat>/publish-spec.json`——**平台自己的目录里**。
# 这一层只读它，不认识任何平台名。
#
# **列表限额的总限额怎么量，各平台不一样**，所以口径写进规格而不是靠键名猜：
#
# - 视频号 `topics_max`：话题**个数**的上限（5 个）。
# - B站 `tags_chars`：标签**英文逗号分隔后的总字符数**上限（199 字）。
# - 抖音 `topics_max`：话题**个数**的上限（5 个）——平台没文档化上限，
#   这条是我们的编辑预算，性质同视频号但出处不同（规格 §6.6.3）。
#
# 搞混的后果是方向相反的：视频号会把 5 个超长话题放过（真正该拦的是字数），
# B站会把 199 个标签放过（真正该拦的是总长）。规格 §4.3 有各自的定义。
#
# `measure` 有两个值：
# - `count` —— 量**个数**（话题几个）；
# - `joined` —— 量**拼好之后**的总字符数（分隔符也算进去）。

#: 规格里必须有的键。缺一个就是这份规格写坏了，当场报错。
_SPEC_KEYS = (
    "required",
    "text_limits",
    "list_limits",
    "int_fields",
    "int_domains",
    "required_when",
)

#: 列表限额里必须有的键。
_LIST_KEYS = ("total", "item", "measure")


class MetaError(ValueError):
    """发布元数据本身坏了（文件读不了、不是对象）。"""


def _normalize_spec(platform: str, raw: dict, path: Path) -> dict:
    """把一份发布规格整理成检查器要的形状。

    **JSON 的键是字符串**：``{"copyright": {"2": ["source"]}}`` 里的 ``2``
    是档位值（整数），不还原成整数，条件必填就永远不触发——
    转载没给来源地址，平台当场拒稿，而我们的检查器一声不吭。
    """
    missing = [key for key in _SPEC_KEYS if key not in raw]
    if missing:
        raise MetaError(f"发布规格缺：{'、'.join(missing)}（{path}）")

    required = raw["required"]
    if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required):
        raise MetaError(f"发布规格的 required 必须是字符串数组：{path}")

    text_limits = raw["text_limits"]
    if not isinstance(text_limits, dict):
        raise MetaError(f"发布规格的 text_limits 必须是表：{path}")

    list_limits = raw["list_limits"]
    if not isinstance(list_limits, dict):
        raise MetaError(f"发布规格的 list_limits 必须是表：{path}")
    for field_name, spec in list_limits.items():
        if not isinstance(spec, dict):
            raise MetaError(f"发布规格的 list_limits.{field_name} 必须是表：{path}")
        missing = [key for key in _LIST_KEYS if key not in spec]
        if missing:
            raise MetaError(
                f"发布规格的 list_limits.{field_name} 缺：{'、'.join(missing)}（{path}）")
        if spec["measure"] not in ("count", "joined"):
            raise MetaError(
                f"发布规格的 list_limits.{field_name}.measure 必须是 count 或 "
                f"joined，实际是 {spec['measure']!r}（{path}）")
        if spec["measure"] == "joined" and "separator" not in spec:
            raise MetaError(
                f"发布规格的 list_limits.{field_name} 用 joined 量长，"
                f"必须写清 separator（{path}）")

    int_fields = raw["int_fields"]
    if not isinstance(int_fields, list) or not all(
            isinstance(item, str) for item in int_fields):
        raise MetaError(f"发布规格的 int_fields 必须是字符串数组：{path}")

    int_domains = raw["int_domains"]
    if not isinstance(int_domains, dict):
        raise MetaError(f"发布规格的 int_domains 必须是表：{path}")

    required_when: dict[str, dict] = {}
    for field_name, mapping in raw["required_when"].items():
        if not isinstance(mapping, dict):
            raise MetaError(
                f"发布规格的 required_when.{field_name} 必须是表：{path}")
        entries: dict = {}
        for key, others in mapping.items():
            try:
                needed: object = int(key)
            except (TypeError, ValueError):
                needed = key
            if not isinstance(others, list):
                raise MetaError(
                    f"发布规格的 required_when.{field_name}.{key} 必须是数组：{path}")
            entries[needed] = tuple(others)
        required_when[field_name] = entries

    return {
        "required": tuple(required),
        "text_limits": dict(text_limits),
        "list_limits": {
            name: dict(spec) for name, spec in list_limits.items()},
        "int_fields": tuple(int_fields),
        "int_domains": {
            name: tuple(values) for name, values in int_domains.items()},
        "required_when": required_when,
    }


@lru_cache(maxsize=8)
def _specs_at(base: Path) -> dict:
    """扫一个 ``platforms/`` 目录下的发布规格。"""
    specs: dict[str, dict] = {}
    if not base.is_dir():
        return specs
    for path in sorted(base.glob(f"*/{PUBLISH_SPEC_NAME}")):
        platform = path.parent.name
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise MetaError(
                f"发布规格不是合法 JSON：{path}（{error}）") from error
        if not isinstance(raw, dict):
            raise MetaError(f"发布规格必须是对象：{path}")
        specs[platform] = _normalize_spec(platform, raw, path)
    return specs


def load_specs(platforms_dir: Path | None = None) -> dict[str, dict]:
    """扫 ``platforms/*/publish-spec.json``，返回 {平台 id: 规格}。

    **缺文件就跳过那个平台**——不是每个平台都有视频发布规格
    （文档类平台没有）。这份表就是「哪些平台吃视频」的唯一真相。
    """
    base = Path(platforms_dir) if platforms_dir is not None else PLATFORMS_DIR
    return dict(_specs_at(base))


@dataclass(frozen=True)
class Finding:
    """一条检查结果。"""

    rule_id: str
    level: str
    message: str
    target: str = ""

    def __str__(self) -> str:
        where = f"[{self.target}] " if self.target else ""
        return f"{where}{self.rule_id} {self.message}"


@dataclass(frozen=True)
class EpisodeMeta:
    """一期的发布元数据。

    **平台段落是动态的**：`platforms` 是 {平台 id: 文案段}，
    平台清单来自 `platforms/*/publish-spec.json`，不写死在这里。
    """

    episode: str
    title: str
    cover_at: float
    url: str = ""
    platforms: dict = field(default_factory=dict)
    tier: str = ""
    path: Path | None = None

    def platform(self, name: str) -> dict | None:
        """某个平台的文案段落；没配就是 None（那一期不发这个平台）。"""
        return self.platforms.get(name)


def meta_path(episode: str, root: Path | None = None) -> Path:
    """发布元数据的路径。

    默认落在期目录里：`video/episodes/<系列>/<合集>/<文档>/<档位>/publish.json`。
    `root` 给定时，当成**期目录本身**（测试与外部调用走这条）。
    """
    base = Path(root) if root else EPISODES_DIR / episode
    return base / PUBLISH_NAME


def published_episodes() -> list[str]:
    """磁盘上已有发布元数据的期（期路径），按期路径排序。

    **期根在这里说了算**：扫描走 `episodes.known_eps_at(EPISODES_DIR)`，
    免得扫描用一套根、取文件用另一套根。
    """
    from pyv import episodes as episodes_mod

    return sorted(
        ep for ep in episodes_mod.known_eps_at(EPISODES_DIR)
        if (EPISODES_DIR / ep / PUBLISH_NAME).is_file()
    )


def resolve_tier(episode: str, root: Path | None = None,
                 explicit: str | None = None) -> str:
    """这一期是哪一档。

    **档位是期目录的最后一段**（`video/episodes/<系列>/<合集>/<文档>/<档位>/`），
    所以档位不用另外登记——路径说了就是。
    认不出来的时候返回空串（查不了就不判，而不是猜一个）。
    """
    if explicit:
        return explicit
    from pyv import episodes as episodes_mod

    candidates = [episode.rsplit("/", 1)[-1]]
    if root is not None:
        candidates.append(Path(root).name)
    for candidate in candidates:
        if candidate in episodes_mod.TIERS:
            return candidate
    return ""


def load_meta(episode: str, tier: str | None = None, root: Path | None = None,
              platforms_dir: Path | None = None) -> EpisodeMeta:
    """读一期的发布元数据。

    `publish.json` 的形状：

    ```json
    {
      "episode": "<期路径>",
      "title": "标题",
      "cover_at": 3.0,
      "url": "https://...",
      "platforms": {"<平台 id>": {"title": "..."}}
    }
    ```

    **平台段落在 `platforms` 下面**，不摊在顶层——平台是动态的，
    顶层摊开的话，「哪些键是平台」这件事就又变成写死的清单了。
    """
    path = meta_path(episode, root)
    if not path.is_file():
        raise MetaError(f"发布元数据不存在：{path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MetaError(f"发布元数据不是合法 JSON：{path}（{error}）") from error
    if not isinstance(raw, dict):
        raise MetaError(f"发布元数据必须是对象：{path}")

    sections = raw.get("platforms", {})
    if not isinstance(sections, dict):
        raise MetaError(f"发布元数据的 platforms 段必须是表：{path}")
    specs = load_specs(platforms_dir)
    platforms: dict[str, dict] = {}
    for name, section in sections.items():
        if not isinstance(section, dict):
            raise MetaError(f"平台 {name!r} 的文案段必须是表：{path}")
        if name not in specs:
            raise MetaError(
                f"平台 {name!r} 没有发布规格"
                f"（platforms/{name}/{PUBLISH_SPEC_NAME}）：{path}")
        platforms[name] = section

    # cover_at 写成非数字时要说人话——`float("x")` 抛的裸 ValueError
    # 会被 CLI 漏出去变成 traceback，而 CLI 只认 MetaError。
    try:
        cover_at = float(raw.get("cover_at", -1.0))
    except (TypeError, ValueError) as error:
        raise MetaError(
            f"cover_at 必须是数字，实际 {raw.get('cover_at')!r}：{path}") from error
    return EpisodeMeta(
        episode=str(raw.get("episode", "")),
        title=str(raw.get("title", "")),
        cover_at=cover_at,
        url=str(raw.get("url", "")),
        platforms=platforms,
        tier=resolve_tier(episode, root, tier),
        path=path,
    )


def load_limits(platform: str, platforms_dir: Path | None = None) -> dict:
    """读平台能力声明的 [limits] 段。"""
    base = Path(platforms_dir) if platforms_dir else PLATFORMS_DIR
    path = base / platform / "capability.toml"
    if not path.is_file():
        raise MetaError(f"能力声明不存在：{path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data.get("limits", {}) or {}


def load_tiers(platform: str, platforms_dir: Path | None = None) -> tuple[str, ...]:
    """读平台能力声明的顶层 `tiers`——这个平台收哪几档。

    **空元组 = 这个平台没声明档位**，不是「全都收」：
    契约层把 `tiers` 的取值域封闭成 `short` / `mid` / `full`，
    声明里写了哪几档就是哪几档，没写就查不了（不判，不猜）。
    """
    base = Path(platforms_dir) if platforms_dir else PLATFORMS_DIR
    path = base / platform / "capability.toml"
    if not path.is_file():
        raise MetaError(f"能力声明不存在：{path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tiers = data.get("tiers", []) or []
    if not isinstance(tiers, list) or not all(
            isinstance(item, str) for item in tiers):
        raise MetaError(f"能力声明的 tiers 不是字符串数组：{path}")
    return tuple(tiers)


def scoped_loader(loader, platforms_dir: Path | str | None):
    """把一个读取器绑到某个 ``platforms/`` 目录上。

    adapter 的 ``platforms_dir`` 参数就是干这个的：测试与外部调用可以把
    能力声明指到别处。读器的签名统一是 ``(platform)``，
    这里补上第二个参数。
    """
    if platforms_dir is None:
        return loader
    base = Path(platforms_dir)

    def load(platform: str):
        return loader(platform, base)

    return load


#: [exit] 段的四个键——退出码的词汇。**契约层定义**
#: （publish/publishkit/exit_codes.py），这里只认这四个名字。
EXIT_KEYS = ("ok", "usage", "precondition", "failed")


def load_exit_codes(platform: str, platforms_dir: Path | None = None) -> dict[str, int]:
    """读平台能力声明的 [exit] 段。

    退出码的**语义**由契约层定死（publish/publishkit/exit_codes.py），
    声明写在平台自己的能力声明里——接缝是**文件**，不是 import。

    段缺了、缺键、多了没听说过的键、值不是整数，当场报错：adapter 的退出码
    是它与调用方之间的契约，一份写坏的声明（比如 ``ok = "0"``）会让这一档
    退成**字符串**——三个 reader 在这一点上必须一样。
    """
    base = Path(platforms_dir) if platforms_dir else PLATFORMS_DIR
    path = base / platform / "capability.toml"
    if not path.is_file():
        raise MetaError(f"能力声明不存在：{path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = data.get("exit", {}) or {}
    if not isinstance(table, dict):
        raise MetaError(f"能力声明的 [exit] 段不是表：{path}")
    missing = [key for key in EXIT_KEYS if key not in table]
    if missing:
        raise MetaError(
            f"能力声明的 [exit] 段缺：{'、'.join(missing)}（{path}）")
    unknown = [key for key in table if key not in EXIT_KEYS]
    if unknown:
        raise MetaError(
            f"能力声明的 [exit] 段出现未知字段 exit."
            f"{'、'.join(unknown)}（{path}）")
    codes: dict[str, int] = {}
    for key in EXIT_KEYS:
        value = table[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise MetaError(
                f"能力声明的 [exit].{key} 不合法：不是整数（{path}）")
        codes[key] = value
    return codes


def check_meta(meta: EpisodeMeta, contract_episode: str | None = None,
               duration: float | None = None,
               limits_loader=load_limits, tiers_loader=load_tiers,
               specs_loader=load_specs) -> list[Finding]:
    """校验一期元数据。返回的 Finding 里 level=error 的必须先改。

    **平台清单只有一个来源**：`platforms/*/publish-spec.json`。
    这一层不认识任何平台名——加一个平台不用改视频线。
    """
    findings: list[Finding] = []
    target = meta.episode or (meta.path.name if meta.path else "")

    if not meta.episode:
        findings.append(Finding("epmeta.episode", ERROR, "缺少 episode", target))
    elif contract_episode and meta.episode != contract_episode:
        findings.append(Finding(
            "epmeta.episode", ERROR,
            f"元数据的 episode 是 {meta.episode!r}，契约里是 {contract_episode!r}",
            target))

    if not meta.title:
        findings.append(Finding("epmeta.required", ERROR, "缺少 title", target))

    if meta.cover_at < 0:
        findings.append(Finding("epmeta.cover-at", ERROR,
                                "缺少 cover_at 或取值为负", target))
    elif duration is not None and meta.cover_at > duration:
        findings.append(Finding(
            "epmeta.cover-at", ERROR,
            f"cover_at {meta.cover_at:.3f}s 超出成片时长 {duration:.3f}s", target))

    specs = specs_loader()
    for platform in sorted(specs):
        section = meta.platform(platform)
        if section is None:
            findings.append(Finding(
                "epmeta.platform-missing", WARNING,
                f"没有配置 {platform} 的文案，这一期不发这个平台", target))
            continue
        findings.extend(_check_platform(
            platform, section, specs[platform], limits_loader,
            tiers_loader, meta.tier, target))
    # 配了文案却没有发布规格的平台：规格是这一层唯一的平台清单，
    # 清单外的东西查不了——放过去等于不查。
    for platform in sorted(meta.platforms):
        if platform not in specs:
            findings.append(Finding(
                "epmeta.unknown-platform", ERROR,
                f"平台 {platform} 没有发布规格（{PUBLISH_SPEC_NAME}）", target))
    return findings


def _check_platform(platform, section, spec, limits_loader, tiers_loader,
                    tier, target):
    findings: list[Finding] = []
    for key in spec["required"]:
        if key not in section or section[key] in (None, ""):
            findings.append(Finding(
                "epmeta.platform-required", ERROR,
                f"{platform} 的文案缺少 {key!r}", target))
    if findings:
        # 缺字段的时候先报缺字段，别同时报出一堆长度错误。
        return findings

    # 档位闸：这个平台收哪几档，写在它自己的能力声明里。
    # 不含这一档就别出包——平台会拒，白跑一趟。
    if tier:
        try:
            tiers = tiers_loader(platform)
        except MetaError as exc:
            findings.append(Finding("epmeta.tiers", ERROR, str(exc), target))
        else:
            if tiers and tier not in tiers:
                findings.append(Finding(
                    "epmeta.tier-not-allowed", ERROR,
                    f"{platform} 只收 {'、'.join(tiers)} 档，"
                    f"这一期是 {tier} 档", target))

    try:
        limits = limits_loader(platform)
    except MetaError as exc:
        findings.append(Finding("epmeta.limits", ERROR, str(exc), target))
        return findings

    for field_name, limit_key in spec["text_limits"].items():
        limit = limits.get(limit_key)
        if limit is None:
            findings.append(Finding(
                "epmeta.limits", ERROR,
                f"{platform} 的能力声明缺少 limits.{limit_key}", target))
            continue
        value = str(section.get(field_name, ""))
        if len(value) > limit:
            findings.append(Finding(
                "epmeta.text-limit", ERROR,
                f"{platform} 的 {field_name} 有 {len(value)} 字，超过上限 {limit}",
                target))

    for field_name, list_spec in spec["list_limits"].items():
        total_limit = limits.get(list_spec["total"])
        item_limit = limits.get(list_spec["item"])
        if total_limit is None or item_limit is None:
            findings.append(Finding(
                "epmeta.limits", ERROR,
                f"{platform} 的能力声明缺少 {list_spec['total']} / {list_spec['item']}",
                target))
            continue
        items = section.get(field_name) or []
        if not isinstance(items, list):
            findings.append(Finding(
                "epmeta.platform-required", ERROR,
                f"{platform} 的 {field_name} 必须是列表", target))
            continue
        # 总限额怎么量，各平台不一样（见 publish-spec.json 的说明）。
        if list_spec["measure"] == "count":
            total = len(items)
            total_text = f"{total} 项"
        else:
            joined = list_spec["separator"].join(str(item) for item in items)
            total = len(joined)
            total_text = f"{total} 字（逗号分隔后）"
        if total > total_limit:
            findings.append(Finding(
                "epmeta.list-limit", ERROR,
                f"{platform} 的 {field_name} 共 {total_text}，超过上限 {total_limit}",
                target))
        for item in items:
            if len(str(item)) > item_limit:
                findings.append(Finding(
                    "epmeta.list-limit", ERROR,
                    f"{platform} 的 {field_name} 里 {item!r} 有 {len(str(item))} 字，"
                    f"超过单项上限 {item_limit}", target))

    for field_name in spec["int_fields"]:
        value = section.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            findings.append(Finding(
                "epmeta.int-field", ERROR,
                f"{platform} 的 {field_name} 必须是整数，实际 {value!r}", target))
            continue
        allowed = spec["int_domains"].get(field_name)
        if allowed is not None and value not in allowed:
            findings.append(Finding(
                "epmeta.int-domain", ERROR,
                f"{platform} 的 {field_name} 只能是 {list(allowed)} 之一，"
                f"实际 {value!r}", target))

    # 条件必填：B站转载（copyright = 2）必须给 source。
    for field_name, mapping in spec["required_when"].items():
        value = section.get(field_name)
        for needed_value, other_fields in mapping.items():
            if value != needed_value:
                continue
            for other in other_fields:
                if not str(section.get(other) or "").strip():
                    findings.append(Finding(
                        "epmeta.conditional-required", ERROR,
                        f"{platform} 的 {field_name} = {needed_value} 时必须给 "
                        f"{other}（平台会拒没有来源的转载）", target))
    return findings
