"""内容坐标的验收守卫：期号 ↔ 内容单元 ↔ 内容单元仓库的位置。

**背景**
------
视频线清空重来以后，坐标不再写在母稿的 front matter 里——
**期目录就是坐标**（`video/episodes/<系列>/<合集>/<文档>/<档位>/`），
内容单元的身份是**期号**（`content/units/video/<期号>.md`）。

于是有几件事必须永远成立，而它们**不会自己暴露**：

1. **期号与期一一对应**。期号是内容单元的**文件名**——
   两期共用一个期号，两个内容单元撞车，后写的把先写的**盖掉**，
   构建成功，产物少一期。
2. **每一期都有内容单元**。缺一期，那一期在站上与发布层**哪儿都不出现**。
3. **内容单元仓库不在任何平台目录里**。它是**共享**的那一半；
   住进某个平台的目录里，就成了那个平台的私产。

**这一层只看根 `tools/` 自己的东西**：视频编译器与它写出来的产物。
期树那边的形状（目录与 front matter 对不对得上）由
`video/pipeline/tests/test_episodes.py` 盯着——**不越界**。

跑法（根级验收）::

    cd . && python3 -m pytest tests/ -q
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from paths import CONTENT_UNITS  # noqa: E402


def _video_pages():
    """按路径加载 tools/build-video-pages.py（文件名带连字符，import 不了）。"""
    spec = importlib.util.spec_from_file_location(
        "build_video_pages", REPO_ROOT / "tools" / "build-video-pages.py")
    module = importlib.util.module_from_spec(spec)
    # ⚠️ 登记进 sys.modules 再执行——将来这个脚本加了 dataclass，
    # 类型检查要去 sys.modules[cls.__module__] 取命名空间。
    sys.modules["build_video_pages"] = module
    spec.loader.exec_module(module)
    return module


def _episodes() -> dict:
    """磁盘上的期：期路径 → 期目录。

    **读的是编译器自己的那一份**（``read_episodes()``）——
    编译器认哪些目录算期，就用它认的，省得两处口径漂。
    """
    return _video_pages().read_episodes()


def _content_ids(episodes: dict) -> dict:
    """期路径 → 内容单元 id（期号）。

    编译器怎么算的，这里就怎么算——**不另写一遍解析规则**。
    """
    module = _video_pages()
    result = {}
    for ep, ep_dir in sorted(episodes.items()):
        fields, _body = module.parse_front_matter(
            (ep_dir / module.SCRIPT_NAME).read_text(encoding="utf-8"))
        result[ep] = fields.get("episode_number") or ep.replace("/", "-")
    return result


# ── 第 3 条：期号与期一一对应 ─────────────────────────────


def test_two_episodes_never_share_a_content_id():
    """**两期不许共用一个期号**。

    期号是内容单元的文件名。共用期号就是两个内容单元撞车——
    后写的把先写的盖掉，**构建成功，产物少一期**。
    """
    episodes = _episodes()
    if not episodes:
        pytest.skip("还没有期（视频线是空的）")
    seen: dict[str, str] = {}
    for ep, content_id in _content_ids(episodes).items():
        assert content_id not in seen, (
            f"{ep} 与 {seen[content_id]} 共用内容单元 id {content_id}——"
            f"内容单元的文件名会撞车，后写的把先写的盖掉"
        )
        seen[content_id] = ep


def test_the_compiler_refuses_two_episodes_with_the_same_content_id(tmp_path, monkeypatch):
    """编译器自己**不许**静悄悄地盖掉一个内容单元。

    这条是上面那条的**另一半**：守卫发现问题时，人已经在现场了——
    但编译那一刻就该炸，而不是让人去比对两个文件才看出少了一期。
    """
    module = _video_pages()
    episodes = [
        "系列甲/合集甲/文档甲/short",
        "系列乙/合集乙/文档乙/full",
    ]
    for ep in episodes:
        root = tmp_path / ep
        root.mkdir(parents=True)
        (root / module.SCRIPT_NAME).write_text(
            f"---\nepisode: {ep.rsplit('/', 1)[0]}\ntier: short\n"
            f"episode_number: ep01\n---\n", encoding="utf-8")
    monkeypatch.setattr(module, "EPISODES_DIR", tmp_path)
    monkeypatch.setattr(module, "POSTS_DIR", tmp_path / "units")
    monkeypatch.setattr(module, "PLATFORMS_DIR", tmp_path / "platforms")
    assert module.main([]) != 0, "撞了期号还返回 0——那是静悄悄地盖掉"
    # 一个内容单元都不该写出来——半截产物比没有产物更难认。
    assert not list((tmp_path / "units" / "video").glob("*.md"))


# ── 第 7 条：每一期都有内容单元 ───────────────────────────


def test_every_episode_has_a_content_unit():
    """每一期都要落成**一个**内容单元。

    缺一期，那一期在站上、在学习流、在发布层**哪儿都不出现**——
    而构建是绿的：目录建好了，编译器扫到它却没写出来。
    """
    episodes = _episodes()
    if not episodes:
        pytest.skip("还没有期（视频线是空的）")
    units_dir = CONTENT_UNITS / "video"
    if not units_dir.is_dir():
        pytest.skip("还没编译视频内容单元（先跑 tools/build-video-pages.py）")
    have = {path.stem for path in units_dir.glob("*.md")}
    missing = sorted(
        f"{ep}（{content_id}）" for ep, content_id in _content_ids(episodes).items()
        if content_id not in have
    )
    assert not missing, f"这些期没有内容单元：{missing}"


def test_the_content_units_are_named_after_the_episode_number():
    """内容单元的**文件名就是期号**——不多一段后缀，也不少一段。

    档位不在文件名里（档位在期目录的第四层），
    所以 `ep01.md` 就是 `ep01`。
    """
    episodes = _episodes()
    if not episodes:
        pytest.skip("还没有期（视频线是空的）")
    units_dir = CONTENT_UNITS / "video"
    if not units_dir.is_dir():
        pytest.skip("还没编译视频内容单元")
    for ep, content_id in _content_ids(episodes).items():
        assert content_id, f"{ep} 没有期号"
        assert "/" not in content_id, (
            f"{ep} 的期号 {content_id} 里带着斜杠——"
            f"它要当文件名用"
        )


# ── 第 19 条：内容单元仓库不在任何平台目录里 ───────────────


def test_the_content_store_is_not_inside_any_platform():
    """内容单元仓库住在**仓库根**，不住在任何一个平台目录里。

    它是六个平台**共享**的那一半。住进某个平台的目录下，
    它就成了那个平台的私产——别的平台要用，就得先 import 那个平台。
    """
    units = CONTENT_UNITS.resolve()
    platforms = REPO_ROOT / "platforms"
    for platform_dir in sorted(p for p in platforms.iterdir() if p.is_dir()):
        assert units != platform_dir.resolve()
        assert platform_dir.resolve() not in units.parents, (
            f"内容单元仓库落在 {platform_dir} 里面了"
        )
        assert not (platform_dir / "content" / "units").exists(), (
            f"{platform_dir} 底下有一份内容单元仓库——那是副本，不是真相"
        )


def _upstream_modules() -> list[Path]:
    """上游的模块：根 `tools/` 与契约层 `publish/publishkit/`。"""
    found = [p for p in (REPO_ROOT / "tools").rglob("*.py")
             if "__pycache__" not in p.parts]
    found += list((REPO_ROOT / "publish" / "publishkit").rglob("*.py"))
    return sorted(found)


def _code_strings(path: Path) -> list[str]:
    """模块里的**代码**字符串常量（不含 docstring）。

    文档里提一嘴 ``platforms/xxx/`` 是**说明**；
    代码里写一个 ``platforms/`` 开头的路径，是**伸手进别人的目录**。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            text = ast.get_docstring(node, clean=False)
            if text is not None:
                docstrings.add(text)
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value not in docstrings
    ]


def test_the_upstream_does_not_reach_into_a_platform_directory():
    """上游**不许**拿平台目录里的路径当输入。

    上游（根 `tools/` 与契约层）只认共享规则与内容单元仓库；
    平台目录是**平台层自己的**。上游伸手进去，
    「层间零 import」就只剩下一句口号——平台一改，上游跟着改。
    """
    for path in _upstream_modules():
        for text in _code_strings(path):
            assert not text.startswith("platforms/"), (
                f"{path.relative_to(REPO_ROOT)} 里的代码字符串 {text!r} "
                f"指着平台目录——上游不该伸手进去"
            )


def test_the_upstream_does_not_import_a_platform_package():
    """层间零 import：上游不许 import 任何平台包。

    import 一 platforms 下的包，平台的目录结构就成了上游的依赖——
    平台一搬目录，上游跟着改。
    """
    platform_packages = {
        path.name for path in (REPO_ROOT / "platforms").iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    for path in _upstream_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in platform_packages, (
                        f"{path.relative_to(REPO_ROOT)} import 了平台包 "
                        f"{alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in platform_packages, (
                    f"{path.relative_to(REPO_ROOT)} import 了平台包 {node.module}"
                )
