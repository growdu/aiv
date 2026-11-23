"""作业调的命令必须与命令行手敲等价（反目标 A3）。

**cwd 规则不一样**：`make` 在 `video/pipeline/`，平台出包在 `platforms/`。
"""
from __future__ import annotations

from api.services import commands


def test_the_document_review_runs_from_the_repo_root_with_an_explicit_docs_root():
    command = commands.document_review("docs/a/b.md")
    assert command.cwd == commands.REPO_ROOT
    assert command.argv[:3] == ["python3", "tools/review-check.py", "docs/a/b.md"]
    assert "--docs-root=docs/" in command.argv


def test_the_video_review_runs_from_the_pipeline_dir():
    command = commands.video_review_text("系列/合集/文档/short")
    assert command.cwd == commands.PIPELINE_DIR
    assert command.argv[:3] == ["python3", "-m", "pyv.cli"]


def test_the_video_build_runs_make_all_with_the_episode_coordinate():
    command = commands.video_build("系列/合集/文档/short")
    assert command.argv == ["make", "EP=系列/合集/文档/short", "all"]
    assert command.cwd == commands.PIPELINE_DIR


def test_the_vertical_build_produces_the_vertical_cut():
    command = commands.video_vertical("系列/合集/文档/short")
    assert command.argv == ["make", "EP=系列/合集/文档/short", "vertical"]


def test_the_platform_package_runs_from_the_platforms_dir():
    """**出包的 cwd 必须是 platforms/**——包是靠 cwd 在 sys.path 里找到的。"""
    command = commands.platform_package("douyin", "系列/合集/文档/short")
    assert command.cwd == commands.PLATFORMS_DIR
    assert command.argv == ["python3", "-m", "douyin.cli", "package", "系列/合集/文档/short"]


def test_the_rebuild_order_is_documents_then_video_then_site():
    """CI 的次序：文档单元 → 视频单元 → 站点。"""
    assert commands.document_units_rebuild().argv == ["python3", "tools/build-content-units.py"]
    assert commands.video_units_rebuild().argv == ["python3", "tools/build-video-pages.py"]
    assert commands.site_build().argv == ["npm", "run", "build"]
    assert commands.site_build().cwd == commands.SITE_DIR


def test_the_align_paths_are_relative_to_the_pipeline_dir():
    """align 的路径**用相对形式**，与 Makefile 的变量逐字一致。"""
    command = commands.video_align("系列/合集/文档/short")
    assert command.cwd == commands.PIPELINE_DIR
    assert command.argv[:4] == ["python3", "-m", "pyv.cli", "align"]
    assert "../episodes/系列/合集/文档/short/narration.mp3" in command.argv
    assert "../episodes/系列/合集/文档/short/口播稿.md" in command.argv


def test_the_command_never_mentions_the_repo_directory_name():
    """命令里不许出现仓库目录名——换个克隆目录就不叫这个名字了。"""
    for command in (commands.document_review("docs/a/b.md"),
                    commands.video_build("a/b/c/short"),
                    commands.platform_package("douyin", "a/b/c/short")):
        assert "blog" not in " ".join(command.argv)
