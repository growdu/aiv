"""重定向页生成器的三条硬规矩（tools/sync-hexo.py）。

一是**旧 URL 必须还在**：文章换了目录、分类改了名，旧链接要能跳到新地方，
所以生成器在旧路径上放一个 meta refresh 的静态页。

二是**日期段要对得上**：重定向页默认落在新文件的日期段上（文章搬家时
日期不变）；旧 URL 的日期跟新文件对不上时（合并两篇逐字节相同的重复
文章就会碰上），键里可以带一段日期，照它写。

三是**产物必须传得上去**：GitHub 的 upload-artifact / upload-pages-artifact
拒绝含文件名非法字符（``: * ? " < > |``）的路径 —— 一个带冒号的目录就能让
整个部署断在那里。2026-11-17 的 Deploy Hexo 就是这么断的：旧分类
「PostgreSQL 源码修炼之路:内核深度拆解专题」生成出来的目录带了冒号，
连着两个 push 没上成线。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_TOOL = REPO_ROOT / "tools" / "sync-hexo.py"

#: 文件名里不能有的字符（Windows NTFS 与 GitHub artifact 的共同限制）
INVALID = ':*?"<>|'


@pytest.fixture(scope="module")
def sync():
    """Import ``tools/sync-hexo.py`` as a module.

    Its ``main()`` is guarded by ``if __name__ == '__main__'``, so importing
    it only defines functions -- it does not rewrite ``source/``.
    """
    spec = importlib.util.spec_from_file_location("sync_hexo_under_test", SYNC_TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_hexo_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def out_dir(sync, tmp_path, monkeypatch):
    """把生成目录指到临时目录，并清空重定向表。"""
    monkeypatch.setattr(sync, "SRC", str(tmp_path))
    monkeypatch.setattr(sync, "REDIRECTS", {})
    monkeypatch.setattr(sync, "CATEGORY_REDIRECTS", {})
    return tmp_path


def test_category_redirect_page_is_written_at_the_old_url(sync, out_dir):
    sync.CATEGORY_REDIRECTS["旧分类"] = "源码主线/新分类"
    written = sync.write_category_redirects()
    assert written == 1
    page = out_dir / "categories" / "旧分类" / "index.md"
    assert page.is_file()
    assert "/categories/" in page.read_text(encoding="utf-8")


def test_category_redirect_with_an_illegal_filename_char_is_skipped(sync, out_dir):
    """旧分类名带冒号 —— 那个目录过不了 artifact 上传，宁可不发。"""
    sync.CATEGORY_REDIRECTS["PostgreSQL 源码修炼之路:内核深度拆解专题"] = "源码主线/PostgreSQL"
    written = sync.write_category_redirects()
    assert written == 0
    assert not (out_dir / "categories").exists()


@pytest.mark.parametrize("bad", list(INVALID))
def test_no_illegal_char_ever_reaches_a_directory_name(sync, out_dir, bad):
    """每个非法字符都要被拦下来 —— 不是只拦冒号。"""
    sync.CATEGORY_REDIRECTS[f"分类{bad}名字"] = "源码主线/新分类"
    assert sync.write_category_redirects() == 0
    assert not (out_dir / "categories").exists()


def test_article_redirect_with_an_illegal_filename_char_is_skipped(sync, out_dir, monkeypatch):
    """文章重定向的旧路径也一样 —— 拦在同一个地方。"""
    monkeypatch.setattr(sync, "_redirect_target_file", lambda p: "docs/somewhere/index.md")
    monkeypatch.setattr(sync, "git_date", lambda p: "2026-01-02")
    sync.REDIRECTS["旧路径:带冒号"] = "新路径"
    assert sync.write_redirects() == 0
    assert not (out_dir / "2026").exists()


def test_redirect_with_a_dated_key_lands_on_the_old_date(sync, out_dir, monkeypatch):
    """键里带日期的重定向：页面落在**旧 URL 当初的日期段**上。

    合并两篇逐字节相同的重复文章时，合并后的那篇只有一个日期 ——
    另一个旧 URL 的日期段跟它对不上。不带日期的键会落在错的地址上，
    真正的旧地址就 404 了；键里带上日期才落得准。
    """
    monkeypatch.setattr(sync, "_redirect_target_file", lambda p: "docs/merged/index.md")
    monkeypatch.setattr(sync, "git_date", lambda p: "2022-06-13 16:14:13")
    sync.REDIRECTS["2022/10/25/cluster/raft/旧文章"] = "merged/新文章"
    assert sync.write_redirects() == 1
    page = out_dir / "2022" / "10" / "25" / "cluster" / "raft" / "旧文章" / "index.md"
    assert page.is_file()
    # 指向的是新文章自己的地址
    assert "/2022/06/13/merged/" in page.read_text(encoding="utf-8")


def test_redirect_without_a_date_still_uses_the_new_files_date(sync, out_dir, monkeypatch):
    """普通键不受影响 —— 页面照旧落在新文件的日期段上。"""
    monkeypatch.setattr(sync, "_redirect_target_file", lambda p: "docs/merged/index.md")
    monkeypatch.setattr(sync, "git_date", lambda p: "2022-06-13 16:14:13")
    sync.REDIRECTS["cluster/raft/旧文章"] = "merged/新文章"
    assert sync.write_redirects() == 1
    assert (out_dir / "2022" / "06" / "13" / "cluster" / "raft" / "旧文章"
            / "index.md").is_file()
