"""批量出包（``convert --all``）与草稿记账（``mark drafted``）的用例。

两件事：

- **批量出包**：整个语料一次性出包，不是一篇一篇敲。
- **草稿记账**：草稿**真的**建在平台上了，账要写对。

草稿这一档是 2026-11-15 才有的：``save=0``（存草稿）分支从「一律 7050」
变成了「保存成功」（见 docs/02-试点记录.md §R4）。在那之前这个档位根本
不存在，``mark`` 只认 ``published``。所以这一档的用例是**后加的**，
不是「补上漏掉的」。

**没有一条用例碰网络，也没有一条碰仓库**：所有落盘位置都指到临时目录。
"""

import json

from PIL import Image

from toutiao.cli import EXIT_ERROR, EXIT_INELIGIBLE, EXIT_OK, EXIT_USAGE, main
from toutiao.state import StateStore


def _corpus(tmp_path, count=3):
    """一个一次性的语料：``count`` 篇能发，外加一篇切不出内容的。

    图片放在 ``source/images/``，母稿里写 ``images/demo.png`` —— 与
    ``test_cli.py`` 里的那套布局一样。
    """
    site = tmp_path / "source"
    posts = site / "_posts" / "db"
    posts.mkdir(parents=True)
    image = site / "images" / "demo.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (1200, 900), (10, 20, 30)).save(image, "PNG")
    for index in range(count):
        (posts / "p{}.md".format(index)).write_text(
            "---\ntitle: 演示{}\ndate: 2026-01-01\n---\n\n"
            "第一段结论。\n\n"
            "![图](images/demo.png)\n\n"
            "第二段。\n".format(index),
            encoding="utf-8",
        )
    # 切不出内容的那一篇：正文只剩一段代码。
    (posts / "bad.md").write_text(
        "---\ntitle: 无内容\ndate: 2026-01-01\n---\n\n"
        "```python\nprint('hi')\n```\n",
        encoding="utf-8",
    )
    return posts


def _args(tmp_path, *extra):
    """一条**不碰仓库**的命令行。"""
    return list(extra) + [
        "--posts-dir", str(tmp_path / "source" / "_posts"),
        "--out-dir", str(tmp_path / "out"),
        "--outbox-dir", str(tmp_path / "outbox"),
        "--state-file", str(tmp_path / "out" / "state.json"),
    ]


# --- convert --all ------------------------------------------------------


def test_convert_all_packages_every_eligible_post(tmp_path):
    """一篇不落：每篇能发的都要有发布包。"""
    _corpus(tmp_path, count=3)
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK

    packages = sorted(p.name for p in (tmp_path / "out").iterdir() if p.is_dir())
    assert packages == ["db-p0", "db-p1", "db-p2"]
    for name in packages:
        assert (tmp_path / "out" / name / "article.html").is_file()


def test_convert_all_writes_a_snapshot_per_article(tmp_path):
    _corpus(tmp_path, count=2)
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK

    snapshots = sorted(p.name for p in (tmp_path / "outbox").glob("*.json"))
    assert snapshots == ["db-p0__toutiao.json", "db-p1__toutiao.json"]
    payload = json.loads(
        (tmp_path / "outbox" / "db-p0__toutiao.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "packaged"
    assert payload["content_id"] == "db/p0"


def test_convert_all_reports_the_ineligible_post(tmp_path, capsys):
    """切不出内容的那一篇要**说出来**：不能少发几篇而不吭声。"""
    _corpus(tmp_path, count=2)
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK

    out = capsys.readouterr().out
    assert "无内容" in out
    assert "2" in out


def test_convert_all_exits_two_when_nothing_could_be_packaged(tmp_path):
    """一篇都发不出去时，退出码是 2 —— 不能「成功地什么都没做」。"""
    posts = tmp_path / "source" / "_posts" / "db"
    posts.mkdir(parents=True)
    (posts / "bad.md").write_text(
        "---\ntitle: 无内容\ndate: 2026-01-01\n---\n\n"
        "```python\nprint('hi')\n```\n",
        encoding="utf-8",
    )
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_INELIGIBLE


def test_convert_all_is_idempotent(tmp_path, capsys):
    """第二遍不重出包：内容没变就是没变。"""
    _corpus(tmp_path, count=2)
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK
    capsys.readouterr()

    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK
    out = capsys.readouterr().out
    assert "内容未变" in out


def test_convert_without_a_slug_is_a_usage_error(tmp_path, capsys):
    """既没给 slug 也没给 --all：这是用法错误，不是「成功」。"""
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert")) == EXIT_USAGE


def test_convert_all_keeps_an_article_that_is_already_drafted(tmp_path):
    """草稿已经建在平台上了，内容没变就不能重出包把它记成「待上传」。

    重出包会把快照从 ``drafted`` 写回 ``packaged`` —— 那就等于把
    「草稿已在平台上」这件事从账上抹掉了。
    """
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK

    snapshot = tmp_path / "outbox" / "db-p0__toutiao.json"
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["status"] = "drafted"
    payload["draft_id"] = "7708369671304528425"
    snapshot.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert main(_args(tmp_path, "convert", "--all")) == EXIT_OK
    after = json.loads(snapshot.read_text(encoding="utf-8"))
    assert after["status"] == "drafted"
    assert after["draft_id"] == "7708369671304528425"


# --- mark drafted -------------------------------------------------------


def test_mark_drafted_records_the_draft_id(tmp_path):
    """草稿建在平台上了，账要写对。"""
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert", "db/p0")) == EXIT_OK

    draft_id = "7708369671304528425"
    code = main(
        _args(tmp_path, "mark", "drafted", "db/p0", "--draft-id", draft_id)
    )
    assert code == EXIT_OK

    payload = json.loads(
        (tmp_path / "outbox" / "db-p0__toutiao.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "drafted"
    assert payload["draft_id"] == draft_id
    # 草稿不是已发布：公开链接必须还是空的。
    assert payload["published_url"] is None

    state = StateStore(tmp_path / "out" / "state.json").get("db/p0")
    assert state.status == "drafted"
    assert state.object_id == draft_id


def test_mark_drafted_without_a_draft_id_is_refused(tmp_path):
    """没有平台侧的草稿 id，就没凭据说「草稿已在平台上」。"""
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert", "db/p0")) == EXIT_OK

    assert main(_args(tmp_path, "mark", "drafted", "db/p0")) == EXIT_USAGE


def test_mark_published_still_refuses_to_be_marked_as_drafted(tmp_path):
    """两档不能混：没有公开链接就不算「已发布」。"""
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert", "db/p0")) == EXIT_OK

    code = main(
        _args(tmp_path, "mark", "published", "db/p0",
              "--draft-id", "7708369671304528425")
    )
    assert code == EXIT_USAGE


def test_mark_drafted_of_an_article_without_a_package_is_refused(tmp_path):
    """没出包就没有快照可改。"""
    _corpus(tmp_path, count=1)
    code = main(
        _args(tmp_path, "mark", "drafted", "db/p0",
              "--draft-id", "7708369671304528425")
    )
    assert code == EXIT_USAGE


def test_a_drafted_article_is_not_republished_by_a_changed_body(tmp_path):
    """改了正文就要重新出包 —— 平台上的那份草稿已经旧了。

    不改就不改：内容没变时重出包会把「草稿已在平台上」从账上抹掉。
    """
    _corpus(tmp_path, count=1)
    assert main(_args(tmp_path, "convert", "db/p0")) == EXIT_OK
    assert main(
        _args(tmp_path, "mark", "drafted", "db/p0",
              "--draft-id", "7708369671304528425")
    ) == EXIT_OK

    post = tmp_path / "source" / "_posts" / "db" / "p0.md"
    post.write_text(
        post.read_text(encoding="utf-8").replace("第二段。", "第二段改了。"),
        encoding="utf-8",
    )

    assert main(_args(tmp_path, "convert", "db/p0")) == EXIT_OK
    payload = json.loads(
        (tmp_path / "outbox" / "db-p0__toutiao.json").read_text(encoding="utf-8")
    )
    # 重新出包 = 这一篇要重新走一遍流程：平台上的草稿已经旧了。
    assert payload["status"] == "packaged"
