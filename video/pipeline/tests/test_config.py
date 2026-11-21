"""视频线的品牌文案不许写死在脚本里——它来自 video/config.toml。"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "video" / "brand" / "scripts"

#: 实例名（站名 / 品牌词）——源码里一个字都不许有。
INSTANCE_NAME = "growdu"

#: 品牌文案——这些字面量只该出现在 ``video/config.toml`` 里。
#: （片头副标题、片尾大字与落版胶囊都是**使用者的**文案，不是框架的。）
BRAND_COPY = ("分享技术之美", "订阅关注", "点赞支持", "感谢观看")


def _python_literals(path: Path) -> str:
    """Python 脚本里的**全部**字符串字面量，按出现顺序拼成一段文字。

    注释不算（AST 看不见注释）。
    **拼成一段**而不是逐个比对，是为了抓住**被拆开**的文案——
    前半句在一个字面量里、后半句在下一个
    （``f"{tagline} · 分享"`` 后面紧跟着 ``"技术之美"``）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parts: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts.append((node.lineno, node.col_offset, node.value))
    parts.sort(key=lambda item: (item[0], item[1]))
    return "".join(value for _, _, value in parts)


def _shell_code(path: Path) -> str:
    """shell 脚本里**引号内**的字符串，按出现顺序拼成一段。

    只取引号里的：注释里的话不是文案——
    ``# 片尾：提示音落在「点赞支持」收尾处`` 这种行尾注释会让判据永远红。
    """
    text = path.read_text(encoding="utf-8")
    return "".join(re.findall(r"""["']([^"']*)["']""", text))


def test_the_brand_scripts_have_no_hardcoded_instance_name():
    """框架源码里不许出现实例名——换一套品牌只改配置，不改代码。

    今天写死的是两个脚本：``make_audio.sh`` 的片头片尾两句，
    ``render.sh`` 的底板名 / 成片名 / 回显。
    """
    offenders = [
        path.name
        for path in sorted(SCRIPTS.iterdir())
        if path.suffix in {".py", ".sh"}
        and INSTANCE_NAME in path.read_text(encoding="utf-8").lower()
    ]
    assert not offenders, f"这些脚本里写死了实例名：{offenders}"


def test_the_brand_scripts_have_no_hardcoded_brand_copy():
    """品牌文案也不许写死——片头副标题、片尾大字与落版胶囊都归配置管。

    Python 脚本扫**字符串字面量**（AST，注释不算）；
    shell 脚本扫**引号里的字符串**（注释不算）。
    两边都**拼成一段**再比对——被拆开的文案也算写死。
    """
    offenders: list[str] = []
    for path in sorted(SCRIPTS.iterdir()):
        if path.suffix == ".py":
            chunk = _python_literals(path)
        elif path.suffix == ".sh":
            chunk = _shell_code(path)
        else:
            continue
        if any(copy in chunk for copy in BRAND_COPY):
            offenders.append(path.name)
    assert not offenders, f"这些脚本里写死了品牌文案：{offenders}"


def test_the_brand_config_provides_the_copy_the_scripts_read():
    """配置里得真有这些文案——否则搬完了等于没搬。

    而且占位符得**已经替换掉**：成句里不该还留着 ``{brand}`` / ``{site}``。
    """
    from pyv.config import load as load_config

    cfg = load_config()
    assert cfg.brand_intro_line and cfg.brand_outro_line
    assert cfg.brand_share_suffix and cfg.brand_outro_title
    assert len(cfg.brand_outro_labels) == 2
    assert "{brand}" not in cfg.brand_intro_line
    assert "{site}" not in cfg.brand_outro_line
    # 药丸那句话要拆成两段——断点由 emphasis 给出，
    # 所以 emphasis 必须是 suffix 的**尾巴**（否则拆出来会重复一段）。
    assert cfg.brand_share_emphasis
    assert cfg.brand_share_suffix.endswith(cfg.brand_share_emphasis)
    assert cfg.brand_intro_line == (
        "深入数据库，分享技术之美。Growdu，与你一起探索数据库的无边世界。"
    )
    assert cfg.brand_outro_line == (
        "感谢观看。访问 Growdu.cn，订阅关注，点赞支持。"
    )
