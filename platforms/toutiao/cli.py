"""Command line entry point for the Toutiao adapter.

    scan              list the corpus and what can go to Toutiao
    convert <slug>   slice one post and write the publish package
    convert --all    slice the whole corpus and write every package
    publish <slug>   package it, and upload once the API permission exists
    mark <state>     record what a human did in the editor
    status            show the recorded state of every article

Every path these commands touch can be pointed somewhere else --
``--posts-dir``, ``--out-dir``, ``--outbox-dir``, ``--state-file`` -- so a
run never has to write into the repository.  The shared options work on
either side of the command name.

Two things this module refuses to do quietly:

- a corrupt state file is announced on stderr and turns the exit code
  into ``EXIT_ERROR``.  An unreadable state reads as "nothing was ever
  published", and that is exactly how an article gets published twice;
- a post that cannot go to Toutiao says why and exits with
  ``EXIT_INELIGIBLE`` instead of exiting successfully with nothing done.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .capability import default_capability_path, load_capability
from .contract import slice_post
from .mdparse import discover, discover_unsupported, load_post
from .notify import build_message, send
from .publish import PackageResult, snapshot_name, write_package, write_snapshot
from .state import StateStore, fingerprint, needs_publish

# platforms/toutiao/ 下的入口脚本：parents[2] 就是仓库根。
# 路径常量统一从根 tools/paths.py 取——那儿是唯一出处。
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from paths import SITE_POSTS  # noqa: E402

__all__ = [
    "EXIT_ERROR", "EXIT_INELIGIBLE", "EXIT_OK", "EXIT_USAGE", "main",
]

#: The exit codes are the contract with whoever runs the command:
#: ``0`` success, ``1`` a bad argument or a bad configuration, ``2`` this
#: post is not eligible for Toutiao, ``3`` an interface, a write or a
#: source-parsing error.
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INELIGIBLE = 2
EXIT_ERROR = 3

# 文章目录：站点拿到的那份内容单元副本（`platforms/blog/site/source/_posts/`）。
# **不是** `content/units/`——图片按「文章目录的上一级」解析，
# 图片还住在站点的 `source/images/` 里（它们进内容单元仓库是下一个模块的事）。
DEFAULT_POSTS_DIR = SITE_POSTS
DEFAULT_OUT_DIR = _REPO_ROOT / "platforms" / "toutiao" / "out"
DEFAULT_OUTBOX_DIR = _REPO_ROOT / "platforms" / "toutiao" / "outbox"
DEFAULT_CAPABILITY = default_capability_path()
DEFAULT_STATE_FILE = _REPO_ROOT / "platforms" / "toutiao" / "out" / "state.json"

#: The value of every shared option when it was not given.  The options
#: are attached to the top-level parser *and* to every subcommand, so
#: they work before the command name as well as after it; argparse's
#: ``SUPPRESS`` keeps an option that was not given out of the namespace
#: entirely, because otherwise the subcommand's own default would
#: overwrite the value that was given before the command name.
_DEFAULTS = {
    "posts_dir": DEFAULT_POSTS_DIR,
    "out_dir": DEFAULT_OUT_DIR,
    "outbox_dir": DEFAULT_OUTBOX_DIR,
    "capability": DEFAULT_CAPABILITY,
    "state_file": DEFAULT_STATE_FILE,
    "source_url": "https://growdu.cn",
    "notify": "",
    "notify_key": "",
}

#: Where the scheduler says the snapshot belongs.  The scheduling layer
#: (spec 06 §5.4) may put its state directory somewhere else than the
#: repository default, and it tells the adapter through this variable.
OUTBOX_DIR_ENV = "PUBLISH_OUTBOX_DIR"


def _default_outbox_dir() -> Path:
    """Where the snapshot goes when ``--outbox-dir`` was not given.

    ``PUBLISH_OUTBOX_DIR`` wins over the repository default; the command
    line option wins over both.

    Why the adapter has to honour it: the snapshot **is** the publish
    layer's idempotency key.  If the scheduler points its state directory
    somewhere else and the adapter keeps writing to the repository
    default, the scheduler looks for the key where it is not, reports
    "success", and has no record that this article was already sent --
    so the next weekly run sends it again.  The failure is silent, which
    is the worst kind: sending twice is worse than sending late.
    """
    value = os.environ.get(OUTBOX_DIR_ENV, "").strip()
    return Path(value) if value else DEFAULT_OUTBOX_DIR

#: What each recorded status means.  ``drafted`` is the one that gets
#: misread: it means a draft exists on the platform and a human still has
#: to publish it -- not that the article was never sent.
_STATUS_TEXT = {
    "packaged": "packaged（待人工上传）",
    "drafted": "drafted（待人工发表）",
    "published": "published（已发布）",
}

#: 草稿档在快照里挂的理由。**不能写成「已发布」**：草稿在后台的草稿箱里，
#: 人点下「确认发布」之前它没有公开链接，站点索引也是按这个理由显示的。
DRAFTED_REASON = "草稿已在头条号后台的草稿箱里，等人工补图并发表"


class _ConfigError(Exception):
    """A configuration problem: a bad argument or a bad declaration.

    It is a separate type so that ``main()`` can tell it apart from a
    failure that happened while doing the work, and answer with the
    matching exit code.
    """


def _capability(path: Path):
    """Load the platform declaration, or refuse it as a configuration error.

    The declaration is configuration, not content: a broken TOML file is
    the exit code for a bad configuration (``EXIT_USAGE``), not the exit
    code for a broken post.
    """
    try:
        return load_capability(path)
    except (OSError, ValueError) as error:
        raise _ConfigError("能力声明读取失败：{}".format(error)) from error


def _inside(path: Path, root: Path) -> bool:
    """Is ``path`` inside ``root``?

    Used to keep a slug from pointing out of the posts directory: the
    command reads files, and it should only read the ones it was pointed
    at.
    """
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _resolve_post(posts_dir: Path, slug: str):
    """Find one post by slug, tolerating a missing ``.md``.

    The slug is a path inside the site (``db/postgresql/demo``).  A slug
    that points outside the posts directory is not followed.
    """
    posts_dir = Path(posts_dir)
    if not posts_dir.is_dir():
        raise FileNotFoundError(
            "找不到 {}。先跑 `python3 tools/build-content-units.py` 产出内容单元，"
            "再跑 `python3 platforms/blog/site/tools/sync-content.py` 同步进站点。"
            .format(posts_dir)
        )
    direct = posts_dir / (slug + ".md")
    if not _inside(direct, posts_dir):
        return None
    if direct.is_file():
        return load_post(direct, posts_dir)
    matches = sorted(posts_dir.rglob(slug + ".md"))
    if matches:
        return load_post(matches[0], posts_dir)
    return None


def _report_quarantine(store: StateStore) -> bool:
    """Announce that the state file was broken and has been set aside.

    Returns ``True`` when a broken file was found.  A corrupt state file
    reads as "nothing was ever published" unless somebody says so, and
    that is how an article gets published twice: the run has to announce
    it, and the exit code has to say the run was not clean.
    """
    if store.quarantined is None:
        return False
    print(
        "状态文件损坏，已隔离到 {}，本次按空状态处理，"
        "发过的文章可能被再发一遍，请人工核对".format(store.quarantined),
        file=sys.stderr,
    )
    return True


def cmd_scan(args) -> int:
    """List the corpus and say which posts can go to Toutiao."""
    capability = _capability(args.capability)
    try:
        posts = discover(args.posts_dir)
    except FileNotFoundError as error:
        # 目录不存在：错误消息里已经带了「先产出内容单元再同步进站点」的指引。
        print("扫描失败：{}".format(error), file=sys.stderr)
        return EXIT_USAGE
    except ValueError as error:
        # 母稿坏掉（front matter 没闭合）：消息里带着出错的文件路径。
        print("扫描失败：{}".format(error), file=sys.stderr)
        return EXIT_ERROR
    ok = 0
    print("共 {} 篇\n".format(len(posts)))
    for post in posts:
        result = slice_post(post, capability.limits, args.source_url)
        if result.article is None:
            print("  ✗ {} —— {}".format(post.title, result.reason))
            continue
        notes = "；".join(result.article.notes)
        print("  ✓ {}{}".format(
            result.article.title,
            "（{}）".format(notes) if notes else "",
        ))
        ok += 1
    print("\n可发 {} / {} 篇".format(ok, len(posts)))

    # 母稿格式不支持的文件要显式说出来，不能静默漏掉。
    unsupported = discover_unsupported(args.posts_dir)
    if unsupported:
        print("\n另有 {} 个母稿格式不支持，已跳过：".format(len(unsupported)))
        for path in unsupported:
            print("  - {}".format(path))
    return EXIT_OK


def _package_and_record(args, capability, article, store):
    """出包、写快照、记状态。

    返回 ``(package, snapshot, state)``。**内容没变时 package 与 snapshot
    都是 None**：那不是失败，是这一篇已经处理过了（``needs_publish()``
    说了算）。把「跳过」与「失败」分开，是这一层唯一要小心的地方。

    草稿档（``drafted``）在这一步**不碰**：已经在平台上的草稿，它的快照
    写的是 ``drafted``；重出包会把那份记录写回 ``packaged``，等于把
    「草稿已在平台上」从账上抹掉。内容变了才重出包——那时平台上的草稿
    已经旧了，本来就该重走一遍。

    ``--packages-only`` 走的是另一条路：**只出包，不写快照、不碰状态**。
    它解决的是一个具体的问题——发布包是本地产物（``platforms/toutiao/out/`` 在
    .gitignore 里），清一次就没了；但账本里那篇仍然是「drafted」，
    ``convert`` 认定「内容没变、跳过」，于是包再也回不来。
    要给已在平台上的草稿补图，就得先把包重新生出来，而这一步
    **不能动账**：动了账，「草稿已在平台上」这件事就被抹掉了。
    """
    fp = fingerprint(article.body)
    if getattr(args, "packages_only", False):
        # 只出包：指纹门在这里不起作用——包没了就得重出，与内容变没变无关。
        package = write_package(
            article, capability, args.out_dir, args.posts_dir, args.source_url,
            fetch_remote=getattr(args, "fetch_remote", False),
        )
        return package, None, store.get(article.content_id)

    state = store.get(article.content_id)
    if not needs_publish(fp, state):
        return None, None, state

    package = write_package(
        article, capability, args.out_dir, args.posts_dir, args.source_url,
        fetch_remote=getattr(args, "fetch_remote", False),
    )
    snapshot = write_snapshot(package, args.outbox_dir)

    state.fingerprint = fp
    state.status = package.status
    state.package_dir = str(package.package_dir)
    store.save(article.content_id, state)
    return package, snapshot, state


def _convert(args) -> tuple:
    """Slice one post and write the package.  Returns ``(code, package)``.

    The package is ``None`` when there was nothing to package: the post
    does not exist, does not qualify, or is already packaged unchanged.
    """
    capability = _capability(args.capability)
    post = _resolve_post(args.posts_dir, args.slug)
    if post is None:
        print("找不到文章: {}".format(args.slug), file=sys.stderr)
        return EXIT_USAGE, None

    result = slice_post(post, capability.limits, args.source_url)
    if result.article is None:
        print("不能发到头条号：{}".format(result.reason), file=sys.stderr)
        return EXIT_INELIGIBLE, None

    store = StateStore(args.state_file)
    # 先把状态文件读一遍：坏掉的话它这时就被隔离了，下面才报得出来。
    store.all()
    broken = _report_quarantine(store)

    try:
        package, snapshot, state = _package_and_record(
            args, capability, result.article, store
        )
    except ValueError as error:
        print("不能发到头条号：{}".format(error), file=sys.stderr)
        return EXIT_INELIGIBLE, None

    if package is None:
        print("内容未变，已有同样的发布包：{}".format(state.updated_at))
        return EXIT_OK, None

    print("标题：{}".format(package.title))
    print("字数：{} 字符（平台计 {} 字；切片上限 {} 字符）".format(
        len(result.article.body),
        package.platform_chars,
        capability.limits.body_chars,
    ))
    print("图片：{} 张".format(len(result.article.images)))
    print("发布包：{}".format(package.package_dir))
    if snapshot is None:
        print("账本未动（--packages-only）：快照与状态文件都没写")
    else:
        print("状态快照：{}".format(snapshot))
    for note in result.article.notes:
        print("  ! {}".format(note))
    # 出包本身成功了，但状态文件坏过：这次运行不算干净。
    return (EXIT_ERROR if broken else EXIT_OK), package


def cmd_convert(args) -> int:
    """Slice one post (or the whole corpus) and write the package."""
    if args.all_posts:
        return cmd_convert_all(args)
    if not args.slug:
        print(
            "convert 要么给一个 slug（convert <slug>），要么给 --all",
            file=sys.stderr,
        )
        return EXIT_USAGE
    code, _package = _convert(args)
    return code


def cmd_convert_all(args) -> int:
    """Slice the whole corpus and write every publish package.

    一篇一篇敲 ``convert <slug>`` 在五百多篇的语料上不现实：每篇都要人
    盯着屏幕上那五行输出。这里跑一遍整个语料，每篇一行，最后一行是账。

    **不合格的那几篇不算失败**：语料里本来就有切不出内容的稿子（正文只剩
    一段代码那种），它们会被点名，但不会拖垮整批。真的失败（写盘出错、
    状态文件坏过）才让退出码变成 3 —— 一次运行「成功」却漏了几篇，是这个
    项目最贵的那种错。
    """
    capability = _capability(args.capability)
    try:
        posts = discover(args.posts_dir)
    except FileNotFoundError as error:
        # 目录不存在：错误消息里已经带了「先产出内容单元再同步进站点」的指引。
        print("扫描失败：{}".format(error), file=sys.stderr)
        return EXIT_USAGE
    except ValueError as error:
        # 母稿坏掉（front matter 没闭合）：消息里带着出错的文件路径。
        print("扫描失败：{}".format(error), file=sys.stderr)
        return EXIT_ERROR

    store = StateStore(args.state_file)
    store.all()
    broken = _report_quarantine(store)

    packaged = 0
    skipped = 0
    ineligible = 0
    failed = 0
    for post in posts:
        result = slice_post(post, capability.limits, args.source_url)
        if result.article is None:
            ineligible += 1
            print("  ✗ {} —— {}".format(post.title, result.reason))
            continue
        try:
            package, _snapshot, _state = _package_and_record(
                args, capability, result.article, store
            )
        except (ValueError, OSError) as error:
            failed += 1
            print("  ! {} —— {}".format(result.article.title, error), file=sys.stderr)
            continue
        if package is None:
            skipped += 1
            print("  · {}（内容未变，跳过）".format(result.article.title))
            continue
        packaged += 1
        print("  ✓ {}".format(package.title))

    print("\n出包 {} 篇；跳过 {}（内容未变）；不合格 {}；失败 {}".format(
        packaged, skipped, ineligible, failed
    ))
    if failed:
        return EXIT_ERROR
    if broken:
        # 状态文件坏过：出包照做了，但这份账不可信。
        return EXIT_ERROR
    if packaged == 0 and skipped == 0:
        # 一篇都没成：不能「成功地什么都没做」。
        return EXIT_INELIGIBLE
    return EXIT_OK


def cmd_publish(args) -> int:
    """Package one post and notify about it.

    The API permission is not available yet, so this is the manual path.
    The distinction matters: the notification must say "待上传", not "已发布".
    """
    code, package = _convert(args)
    if package is None:
        # 没有出包：原因已经说过了，退出码也已经带上了。
        return code
    if args.notify and not args.notify_key:
        print(
            "指定了通知通道 {} 但没有通知凭据（--notify-key），没有发通知".format(
                args.notify
            ),
            file=sys.stderr,
        )
    elif args.notify:
        subject, body = build_message(
            "packaged",
            package.title,
            detail="发布包：{}".format(package.package_dir),
        )
        try:
            send(args.notify, args.notify_key, subject, body)
        except Exception as error:                  # noqa: BLE001 -- 通知失败不影响发布结果
            print("通知失败（不影响发布结果）：{}".format(error), file=sys.stderr)
    return code


def cmd_mark(args) -> int:
    """Record what a human did in the editor.

    Two tiers, and both need a receipt:

    - ``drafted``   -- a draft exists on the platform; a human still has to
      publish it.  The receipt is the platform-side draft id.
    - ``published`` -- it is out.  The receipt is the public URL.

    **没有凭据就不许说那句话。** 「已存草稿」一旦说错，下一轮就会把它当成
    没发过再发一遍——发重了比发慢了糟糕得多。

    2026-11-15 实测：草稿档**真的**存在了（``save=0`` 分支从 11-13 的一律
    7050 变成「保存成功」，见 docs/02-试点记录.md §R4）。在那之前这个档位
    不存在，``mark`` 只认 ``published``。
    """
    if args.state == "drafted":
        if not args.draft_id:
            print(
                "drafted 档必须给 --draft-id（平台侧的草稿 id）",
                file=sys.stderr,
            )
            return EXIT_USAGE
    elif not args.url:
        print("published 档必须给 --url（公开链接）", file=sys.stderr)
        return EXIT_USAGE

    post = _resolve_post(args.posts_dir, args.slug)
    if post is None:
        print("找不到文章: {}".format(args.slug), file=sys.stderr)
        return EXIT_USAGE

    path = Path(args.outbox_dir) / snapshot_name(post.slug, "toutiao")
    if not path.is_file():
        print(
            "找不到状态快照：{}（先跑一次 convert）".format(path),
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("状态快照读不了：{}".format(error), file=sys.stderr)
        return EXIT_ERROR

    payload["status"] = args.state
    payload["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if args.state == "published":
        payload["published_url"] = args.url
        payload["reason"] = None
    else:
        # 草稿不是已发布：公开链接必须还是空的。
        payload["published_url"] = None
        payload["draft_id"] = args.draft_id
        payload["reason"] = DRAFTED_REASON
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    store = StateStore(args.state_file)
    state = store.get(post.slug)
    state.status = args.state
    if args.state == "published":
        state.published_url = args.url
    else:
        # 平台侧的 id 记在 object_id：它是「平台上有这篇东西」的凭据。
        state.object_id = args.draft_id
    store.save(post.slug, state)

    print("标题：{}".format(payload.get("title", "")))
    print("状态：{}".format(args.state))
    if args.state == "published":
        print("公开链接：{}".format(args.url))
    else:
        print("草稿 id：{}".format(args.draft_id))
        print("草稿在平台后台的「草稿箱」里，等人工发表")
    print("状态快照：{}".format(path))
    return EXIT_OK


def cmd_status(args) -> int:
    """Show the recorded state of every article."""
    store = StateStore(args.state_file)
    articles = store.all()
    if _report_quarantine(store):
        # 状态文件坏掉时的空状态是不可信的：说清楚，别让它读成「没发过」。
        print("状态文件损坏，本次按空状态处理，没有可显示的记录（详情见 stderr）")
        return EXIT_ERROR
    if not articles:
        print("还没有发过任何文章")
        return EXIT_OK
    for content_id in sorted(articles):
        entry = articles[content_id]
        status = entry.get("status") or "-"
        print("  {}  {}  {}".format(
            content_id,
            _STATUS_TEXT.get(status, status),
            entry.get("published_url") or entry.get("package_dir") or "",
        ))
    return EXIT_OK


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    """Attach the options every command shares.

    ``default=argparse.SUPPRESS`` is what makes the option work on
    either side of the command name: an option that was not given stays
    out of the namespace, so the subcommand's default cannot overwrite
    the value that was given before the command name.
    """
    parser.add_argument("--posts-dir", type=Path, default=argparse.SUPPRESS,
                        help="站点文章目录（默认：platforms/blog/site/source/_posts）")
    parser.add_argument("--out-dir", type=Path, default=argparse.SUPPRESS,
                        help="发布包目录（默认：platforms/toutiao/out）")
    parser.add_argument("--outbox-dir", type=Path, default=argparse.SUPPRESS,
                        help="状态快照目录（默认：platforms/toutiao/outbox）")
    parser.add_argument("--capability", type=Path, default=argparse.SUPPRESS,
                        help="平台能力声明（默认：platforms/toutiao/capability.toml）")
    parser.add_argument("--state-file", type=Path, default=argparse.SUPPRESS,
                        help="幂等状态文件（默认：platforms/toutiao/out/state.json）")
    parser.add_argument("--source-url", default=argparse.SUPPRESS,
                        help="正文末尾署名的站点地址")
    parser.add_argument("--notify", default=argparse.SUPPRESS,
                        help="通知通道：serverchan / wechat_work / webhook")
    parser.add_argument("--notify-key", default=argparse.SUPPRESS,
                        help="通知凭据")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, with the shared options on both sides."""
    parser = argparse.ArgumentParser(
        prog="toutiao", description="博客到头条号的切片与发布"
    )
    _add_common_options(parser)

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="盘点：哪些文章能发到头条号",
                   parents=[_common_parser()]).set_defaults(func=cmd_scan)

    convert = sub.add_parser("convert", help="切片并产出发布包（不调接口）",
                             parents=[_common_parser()])
    convert.add_argument("slug", nargs="?",
                         help="文章在站点文章目录下的相对路径（去掉 .md）")
    convert.add_argument("--all", dest="all_posts", action="store_true",
                         help="把整个语料一次性出包")
    convert.add_argument("--packages-only", dest="packages_only", action="store_true",
                         help="只出包：不写快照、不碰状态文件"
                              "（给已在平台上的草稿补东西时用这一档）")
    convert.add_argument("--fetch-remote", dest="fetch_remote", action="store_true",
                         help="把正文里的外链图也下载下来打进包里"
                              "（默认不下载：出包不依赖网络，下不到的还是人工处理）")
    convert.set_defaults(func=cmd_convert)

    publish = sub.add_parser("publish", help="产出发布包（API 权限开通后才会真正上传）",
                             parents=[_common_parser()])
    publish.add_argument("slug")
    publish.set_defaults(func=cmd_publish)

    mark = sub.add_parser("mark", help="记录人工发表的结果",
                           parents=[_common_parser()])
    mark.add_argument("state", choices=["drafted", "published"],
                      help="drafted=草稿已在平台上（要 --draft-id）；published=已发表（要 --url）")
    mark.add_argument("slug")
    mark.add_argument("--url", default=None, help="公开链接，published 档必填")
    mark.add_argument("--draft-id", dest="draft_id", default=None,
                      help="平台侧的草稿 id，drafted 档必填")
    mark.set_defaults(func=cmd_mark)

    sub.add_parser("status", help="查看状态",
                   parents=[_common_parser()]).set_defaults(func=cmd_status)
    return parser


def _common_parser() -> argparse.ArgumentParser:
    """A parser holding the shared options, for a subcommand to inherit."""
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common)
    return common


def _fill_defaults(namespace: argparse.Namespace) -> None:
    """Put the default value in for every shared option that was not given."""
    given_outbox_dir = hasattr(namespace, "outbox_dir")
    for name, value in _DEFAULTS.items():
        if not hasattr(namespace, name):
            setattr(namespace, name, value)
    if not given_outbox_dir:
        # The command line option wins over the environment variable, which
        # wins over the repository default.
        namespace.outbox_dir = _default_outbox_dir()


def main(argv=None) -> int:
    """Run one command and return its exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        # argparse 已经把用法和错误打印出来了。``--help`` 退出码是 0，
        # 其余都是用法错误 —— 本命令约定用法错误是 1。
        return EXIT_OK if error.code == 0 else EXIT_USAGE
    _fill_defaults(args)
    try:
        return args.func(args)
    except _ConfigError as error:
        print(str(error), file=sys.stderr)
        return EXIT_USAGE
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return EXIT_USAGE
    except Exception as error:                      # noqa: BLE001 -- 错误不吞
        print("失败：{}".format(error), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
