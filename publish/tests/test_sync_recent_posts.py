"""404 页的「最近发布」链接必须真的指向一篇文章。

**病根**：``tools/sync-hexo.py`` 生成 ``source/recent-posts.json`` 时拼的
URL 是 ``/{cat}/{slug}/``，而站点真实的 permalink 是
``/:year/:month/:day/:title/``（``_config.yml`` 的 ``permalink``）。

形态不匹配 → 404 页上那几条链接**每一条都是死的**。而 404 页是站内
链接失效时唯一的导流出口，出口自己是死的，等于没有出口。

顺带修掉一个同源的毛病：原代码只拿 ``{cat}/{slug}`` 拼路径，
``docs/db/nested/deep.md`` 这种多一层的文章会被拼成 ``/db/deep/``——
目录中间那层掉了。

这条测试用 ``test_sync_exclusions.py`` 那套办法：造一小份语料，
**真的跑一遍** ``tools/sync-hexo.py``，然后看它吐出来的
``recent-posts.json``。
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "tools" / "sync-hexo.py"


def load_sync_module():
    """Load ``tools/sync-hexo.py`` as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("sync_hexo_recent_posts", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_corpus(root: Path, drafts) -> None:
    for rel, text in drafts.items():
        path = root / "docs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    shutil.copy(REPO_ROOT / "_config.matery.yml", root / "_config.matery.yml")


def run_sync(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "sync-hexo.py 失败：\n{}\n{}".format(
        result.stdout, result.stderr
    )


DRAFT = "---\ntitle: {title}\n---\n\n{body}\n"

CORPUS = {
    "db/postgresql.md": DRAFT.format(title="PostgreSQL", body="数据库正文。"),
    "db/nested/deep.md": DRAFT.format(title="深挖", body="多一层目录的文章。"),
    "cluster/paxos.md": DRAFT.format(title="Paxos", body="共识协议正文。"),
}


def read_recent_posts(root: Path):
    path = root / "source" / "recent-posts.json"
    assert path.exists(), "sync 没有写出 source/recent-posts.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- 集成：真的跑一遍 sync-hexo.py ---------------------------------------


def test_recent_post_urls_carry_the_date_and_the_whole_path(tmp_path):
    """URL 必须是 ``/YYYY/MM/DD/<完整路径>/``——跟站点真实 permalink 一个形态。

    语料里的文章没有 git 历史，``git_date`` 会退回 2024-01-01，
    所以日期是确定的。
    """
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    posts = read_recent_posts(tmp_path)
    urls = {post["url"] for post in posts}

    assert urls == {
        "/2024/01/01/db/postgresql/",
        "/2024/01/01/db/nested/deep/",
        "/2024/01/01/cluster/paxos/",
    }, urls


def test_every_recent_post_url_points_at_a_generated_post(tmp_path):
    """每条 URL 都得有一个真的被 sync 生成出来的文章页对应。

    这条是给「拼 URL」这件事兜底：拼出来的东西看着像那么回事，
    实际上站点里根本没有那个页面，就还是死链。

    期望的 URL 按站点的 permalink 规则算：``/:year/:month/:day/:title/``，
    日期取文章自己的 front matter（语料没有 git 历史，一律 2024-01-01）。
    """
    build_corpus(tmp_path, CORPUS)
    run_sync(tmp_path)

    posts = read_recent_posts(tmp_path)
    posts_root = tmp_path / "source" / "_posts"
    generated = set()
    for path in posts_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        date = re.search(r"^date:\s*([0-9]{4})-([0-9]{2})-([0-9]{2})", text, re.M)
        rel = path.relative_to(posts_root).as_posix()
        slug = os.path.splitext(rel)[0]
        generated.add("/{}/{}/{}/{}/".format(date.group(1), date.group(2), date.group(3), slug))

    for post in posts:
        assert post["url"] in generated, (
            "{} 指向一个不存在的文章页；生成出来的是 {}".format(
                post["url"], sorted(generated)
            )
        )


def test_the_url_carries_the_site_root_prefix():
    """镜像站挂在 ``/blog/`` 下，URL 必须带上挂载点。

    ``site_root.permalink`` 是这件事的既有约定（落地页、文章交叉链接
    都走它），404 页的链接不能例外——不然镜像站上这 6 条链接照样是死的。
    """
    module = load_sync_module()

    assert module._permalink("2024-01-01 00:00:00", "db/postgresql", root="/blog") == (
        "/blog/2024/01/01/db/postgresql/"
    )
    assert module._permalink("2024-01-01 00:00:00", "db/postgresql", root="") == (
        "/2024/01/01/db/postgresql/"
    )
