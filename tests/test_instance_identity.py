"""**全仓库**的身份守卫：框架源码里不许出现站名。

规矩的适用范围 2026-11-19 由 owner 定成「全仓库」——
以前只有站点一个模块守着（site/tests/test_site_config.py），
别的模块没人管，于是实例身份还留在源码里。

**扫描范围**：框架源码（代码文件），**不含**测试夹具、markdown 文档、
构建产物、配置缝本身——站名出现在那些地方是正常的。
"""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 扫哪些后缀（代码）。
#: ⚠️ **`.template` 也在里**——launchd 模板是代码（它带的是要跑的程序），
#: 而且它**确实**写过实例名（Task 14 改的就是它）。
#: 守卫不扫它，就没人拦得住它变回去。
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".js", ".astro", ".css", ".sh",
                   ".template"}

#: 扫哪些目录（相对仓库根）。
SCAN_DIRS = ("tools", "publish", "platforms", "video/pipeline/pyv",
              "video/brand/scripts", "browser/browser")

#: 这些目录不扫：测试、构建产物、内容副本。
SKIP_PARTS = {"tests", "test", "out", "outbox", "dist", "node_modules",
                 "__pycache__", "docs", "content"}


def _instance_tokens() -> list[str]:
    """从各个缝里读出「这个实例叫什么」。"""
    tokens = set()
    site = REPO_ROOT / "platforms" / "blog" / "site" / "data" / "site.json"
    if site.is_file():
        import json
        name = json.loads(site.read_text(encoding="utf-8")).get("name")
        if name:
            tokens.add(name)
    brand = REPO_ROOT / "video" / "config.toml"
    if brand.is_file():
        import tomllib
        data = tomllib.loads(brand.read_text(encoding="utf-8"))
        for key in ("name", "token", "site"):
            value = (data.get("brand") or {}).get(key)
            if value:
                tokens.add(value)
        slug = (data.get("character") or {}).get("slug")
        if slug:
            tokens.add(slug)
    return sorted({t.lower() for t in tokens if len(t) >= 3})


def _framework_sources():
    for rel in SCAN_DIRS:
        root = REPO_ROOT / rel
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES:
                continue
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & SKIP_PARTS:
                continue
            yield path


def test_the_guard_finds_the_instance_name_somewhere():
    """守卫本身要能抓到东西——不然它只是一段没人跑过的代码。"""
    assert _instance_tokens(), "从缝里读不出实例名，守卫无从谈起"


def test_no_framework_source_mentions_the_instance():
    tokens = _instance_tokens()
    offenders = []
    for path in _framework_sources():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in tokens:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}（{token}）")
                break
    assert not offenders, (
        "框架源码里出现了实例身份——它只该待在缝里：\n"
        + "\n".join(offenders)
    )


def test_the_guard_ignores_tests_and_documents():
    """测试夹具与 markdown 里的站名是正常的——守卫不许把它们算成违规。"""
    for path in _framework_sources():
        assert "tests" not in path.parts
        assert path.suffix != ".md"
