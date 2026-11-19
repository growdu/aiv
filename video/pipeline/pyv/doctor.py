"""环境自检：这台机器能不能跑出片。

**跑之前先自检**，比跑到一半炸掉省时间得多。自检分四组：

* **环境**——Python 版本、第三方库、ffmpeg/ffprobe、字体
* **素材**——出片必需的旁白、BGM、形象素材在不在
* **可选工具**——`mcode-tools`（只有重新合成旁白、重新生成形象才需要）
* **入口**——Makefile 的常用目标

缺什么就报什么，并给出**可执行的修复命令**（不是「请安装依赖」这种废话）。

跑法：

    make doctor
    python -m pyv.cli doctor
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

AIV_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]

ERROR = "error"
WARNING = "warning"
INFO = "info"

#: Python 最低版本：3.11 起才有 tomllib（能力声明文件是 toml）
MIN_PYTHON = (3, 11)

#: 第三方库 → pip 包名（导入名和安装名不一致的写在这里）
THIRD_PARTY = (
    ("cairo", "pycairo"),
    ("numpy", "numpy"),
    ("PIL", "Pillow"),
    ("scipy", "scipy"),
)

#: 出片必需的媒体素材：**由配置声明**。
#:
#: 素材是用户自带的（版权是他们的，口味是他们的），框架只认位置。
#: 所以这里不再有硬编码的路径清单——位置在 `video/config.toml` 里。
#:
#: **没配不是错**（没有就是没有，流水线会降级）；
#: **配了但文件不在才是错**（配错了，要指出来）。
ASSET_KINDS = (
    # (名字, 配置里的取法, 缺了算多严重)
    ("形象立绘", "mascot", INFO),
    ("无标牌立绘", "mascot_plain", INFO),
    ("落版头像", "avatar", INFO),
    ("正文铺底 BGM", "music_bed", ERROR),
    ("品牌片目录", "brand_clips", WARNING),
    ("品牌音轨目录", "brand_audio", WARNING),
)


@dataclass(frozen=True)
class Check:
    """一条自检结论。"""

    group: str
    name: str
    level: str
    ok: bool
    detail: str
    fix: str = ""

    @property
    def mark(self) -> str:
        return {ERROR: "✗", WARNING: "!", INFO: "·"}.get(self.level, "·")


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PYTHON
    return Check(
        "环境", "Python", ERROR if not ok else INFO, ok, version,
        fix="" if ok else f"需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 及以上",
    )


def _check_imports() -> list[Check]:
    checks: list[Check] = []
    for module_name, package in THIRD_PARTY:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - 任何导入失败都算缺
            checks.append(Check(
                "环境", module_name, ERROR, False, f"导入失败：{exc}",
                fix=f"pip install {package}",
            ))
            continue
        version = getattr(module, "__version__", None) or (
            getattr(module, "version", None) or "已安装"
        )
        checks.append(Check("环境", module_name, INFO, True, str(version)))
    return checks


def _ffmpeg_encoders() -> str:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout or ""


def _check_ffmpeg() -> list[Check]:
    checks: list[Check] = []
    for tool, fix in (("ffmpeg", "sudo apt-get install -y ffmpeg"),
                      ("ffprobe", "sudo apt-get install -y ffmpeg")):
        path = shutil.which(tool)
        checks.append(Check(
            "环境", tool, INFO if path else ERROR, bool(path),
            path or "没找到", fix="" if path else fix,
        ))
    if not shutil.which("ffmpeg"):
        return checks

    encoders = _ffmpeg_encoders()
    for name, keyword, fix in (
        ("H.264 编码", "libx264", "换个带 libx264 的 ffmpeg（Debian/Ubuntu 的官方包自带）"),
        ("AAC 编码", " aac ", "换个带原生 aac 编码器的 ffmpeg"),
    ):
        present = keyword in encoders
        checks.append(Check(
            "环境", name, INFO if present else ERROR, present,
            "可用" if present else "不可用", fix="" if present else fix,
        ))
    return checks


def _check_font() -> Check:
    from pyv import fonts

    font = fonts.resolve_font()
    return Check(
        "环境", "中文字体", INFO if font.resolves else ERROR, font.resolves,
        font.label, fix="" if font.resolves else fonts.INSTALL_HINT,
    )


def _check_assets() -> list[Check]:
    """配置里声明的素材在不在。

    **没配与配错要分开报**：
    - 没配（路径为空）= 素材是用户自带的，没有就是没有 → 降级，不算错；
    - 配了但文件不在 = 配错了 → 照配置的严重度报，并说清怎么改。
    """
    from pyv import config as config_mod

    cfg = config_mod.config()
    checks: list[Check] = []
    for label, attribute, level in ASSET_KINDS:
        path = getattr(cfg, attribute)
        if path is None:
            checks.append(Check(
                "素材", label, INFO, True,
                "没配（这一项不参与出片）", fix="",
            ))
            continue
        present = path.is_dir() if attribute in ("brand_clips", "brand_audio") \
            else path.is_file()
        checks.append(Check(
            "素材", label, INFO if present else level, present,
            str(path) if present else f"配了但找不到：{path}",
            fix="" if present else
            f"改 {cfg.path or '配置'} 里的 [assets.*]，或把素材放到位",
        ))
    return checks


def _check_narrations() -> list[Check]:
    """每一期的旁白 mp3。缺了就跑不了那一期的 align/render/compose。"""
    from pyv import episodes

    checks: list[Check] = []
    for ep in episodes.known_eps():
        narration = episodes.narration_path(ep)
        present = narration.is_file()
        script = episodes.script_path(ep)
        checks.append(Check(
            "素材", f"{ep} 的旁白", INFO if present else ERROR, present,
            "已就位" if present else "缺：这一期的旁白",
            fix="" if present else
            f"合成：python3 video/voice/scripts/synthesize_narration.py "
            f"--script {script} --out {narration}",
        ))
    return checks


def _check_mcode_tools() -> Check:
    path = shutil.which("mcode-tools")
    return Check(
        "可选工具", "mcode-tools", INFO, True,
        path or "未安装（只有重新合成旁白 / 重新生成形象才需要）",
        fix="" if path else "见 mcode-tools-master skill 的安装说明",
    )


def _check_episodes() -> list[Check]:
    """每一期的口播稿与契约都在（这两样是入库的，必须齐）。"""
    from pyv import episodes

    checks: list[Check] = []
    eps = episodes.known_eps()
    if not eps:
        checks.append(Check(
            "素材", "video/episodes/", INFO, True,
            "还没有期：新建 video/episodes/<系列>/<合集>/<文档>/<档位>/ "
            "就是一个新的一期",
            fix="",
        ))
        return checks
    for ep in eps:
        script = episodes.script_path(ep)
        contract = episodes.contract_path(ep)
        missing = [str(p) for p in (script, contract) if not p.is_file()]
        checks.append(Check(
            "素材", f"{ep} 的稿件与契约", INFO if not missing else ERROR,
            not missing,
            "已就位" if not missing else f"缺：{'、'.join(missing)}",
            fix="" if not missing else f"git checkout -- video/episodes/{ep}/",
        ))
    return checks


def _check_bundled_font() -> Check:
    """仓库内置的字体子集装没装。

    **这是「跨机版式一致」的前提**：两台机器用同一份字体文件，
    步进宽度与 `fit_size` 的收字号结果才一致。没装就用系统字体，
    画面照样能出——但跨机的像素/版式就没有保证了。

    **粗体也要认得**：只认得常规字重的话，cairo 会**合成**粗体，
    而合成是各后端自己的做法——两个平台合成出来的不一样（实测轮廓
    包围盒差 3.14px），跨机版式照样对不上。
    """
    from pyv import fonts

    bundled = all(path.is_file() for path in fonts.BUNDLED_PATHS)
    resolved = fonts.family_resolves(fonts.BUNDLED_FAMILY)
    bold = fonts.bold_face_resolves()
    if resolved and bold:
        note = f"已就位（{fonts.BUNDLED_FAMILY}，含粗体）"
    elif resolved:
        note = "常规字重认得，但**粗体没认到**——cairo 会合成粗体，跨机版式对不上"
    elif bundled:
        note = "在仓库里但没装进 OS 的字体目录"
    else:
        note = "仓库里没有这份子集"
    return Check(
        "环境", "内置字体", INFO if (resolved and bold) else WARNING,
        resolved and bold,
        note, fix="" if (resolved and bold) else
        "cd video/pipeline && python3 scripts/install_font.py",
    )


def run_checks() -> list[Check]:
    """跑完全部自检，返回结论列表。"""
    checks: list[Check] = [_check_python()]
    checks.extend(_check_imports())
    checks.extend(_check_ffmpeg())
    checks.append(_check_font())
    checks.append(_check_bundled_font())
    checks.extend(_check_episodes())
    checks.extend(_check_assets())
    checks.extend(_check_narrations())
    checks.append(_check_mcode_tools())
    return checks


def format_report(checks: list[Check]) -> str:
    lines: list[str] = []
    group = ""
    for check in checks:
        if check.group != group:
            group = check.group
            lines.append("")
            lines.append(f"== {group} ==")
        lines.append(f"  {check.mark} {check.name:<44} {check.detail}")
        if not check.ok and check.fix:
            lines.append(f"      → {check.fix}")
    errors = sum(1 for c in checks if not c.ok and c.level == ERROR)
    warnings = sum(1 for c in checks if not c.ok and c.level == WARNING)
    lines.append("")
    if errors:
        lines.append(f"FAIL {errors} 项硬性缺失、{warnings} 项告警——先补齐硬性缺失")
    else:
        lines.append(f"OK 环境就绪（{warnings} 项告警）")
    return "\n".join(lines)


def main() -> int:
    checks = run_checks()
    print(format_report(checks))
    return 1 if any(not c.ok and c.level == ERROR for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
