"""发布执行器的命令行入口。

    python3 -m browser.cli doctor          这台机器能不能跑浏览器投稿
    python3 -m browser.cli probe           打开视频号助手，扫码，dump 页面结构
    python3 -m browser.cli prepare <EP>    上传 + 填表 + 截图，**不发表**
    python3 -m browser.cli submit <EP>     上传 + 填表 + 截图 + **确认后发表**
    python3 -m browser.cli bilibili-draft <EP>   传片 + 填表 + **存草稿**

**prepare 与 submit 为什么分开。** 「发表」是不可逆的外部可见动作：
发出去就收不回来。所以填表和发表分成两步，`prepare` 跑完留下截图与
一份「填了什么」的清单，人能自己看一眼；`submit` 会**重新走一遍填表**
（浏览器一关表单就没了），在点「发表」之前把截图路径打出来并等确认。

**bilibili-draft 只到「存草稿」。** B站 的「立即投稿」会把视频公开给
所有人看；「存草稿」只存在自己的创作中心里，随时能改能删。
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

from browser import doctor, probe
from browser.driver import ActionError, PageDriver
from browser.flows import bilibili as bilibili_flow
from browser.flows import channels as channels_flow
from browser.flows import toutiao as toutiao_flow
from browser.plan import PlanError, load_bilibili_plan, load_plan
from browser.plan import find_toutiao_plan
from browser.session import BrowserSession, SessionConfig, default_profile_dir

ToutiaoUploader = toutiao_flow.ToutiaoUploader
ToutiaoError = toutiao_flow.ToutiaoError
BROWSER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BROWSER_ROOT.parent
DEFAULT_PACKAGES = REPO_ROOT / "platforms" / "channels" / "out"
DEFAULT_BILIBILI_PACKAGES = REPO_ROOT / "platforms" / "bilibili" / "out"
DEFAULT_TOUTIAO_PACKAGES = REPO_ROOT / "platforms" / "toutiao" / "out"
DEFAULT_OUTBOX = REPO_ROOT / "platforms" / "toutiao" / "outbox"
DEFAULT_OUT = BROWSER_ROOT / "out"
DEFAULT_SELECTORS = BROWSER_ROOT / "selectors" / "channels.json"
DEFAULT_BILIBILI_SELECTORS = BROWSER_ROOT / "selectors" / "bilibili.json"

# 回填快照用的命令模板。**用 subprocess 调外部命令，不 import channels**——
# 这样浏览器执行器可以给任意平台用，平台不会��进代码里。
DEFAULT_MARK_TEMPLATE = "{python} -m channels.cli mark published {episode} --url {url}"


def _package_dir(episode: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_PACKAGES / episode


def _open_session(args: argparse.Namespace) -> BrowserSession:
    profile = Path(args.profile).expanduser().resolve() if args.profile else default_profile_dir()
    config = SessionConfig.build(profile_dir=profile, headless=args.headless,
                                 slow_mo=args.slow_mo)
    return BrowserSession(config)


def _load_plan(episode: str, override: str | None):
    target = _package_dir(episode, override)
    plan = load_plan(target)
    problems = channels_flow.check_limits(plan)
    if problems:
        for problem in problems:
            print(f"ERROR  {problem}", file=sys.stderr)
        raise PlanError(f"文案没过视频号的字数限制，不填进页面：{target}")
    return plan


# -- 子命令 -----------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    findings = doctor.run_doctor(Path(args.profile) if args.profile else None)
    print(doctor.render(findings))
    failed = [f for f in findings if f.level == "fail"]
    print()
    if failed:
        print(f"FAIL {len(failed)} 项没通过——先补齐再跑投稿")
        return 1
    print("OK 这台机器可以跑浏览器投稿")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """打开视频号助手，等人扫码，然后把页面结构 dump 出来。

    **这一步不需要任何选择器**——所以它能用来「先探页面，再填选择器」。

    两种等待方式：

    - 默认：在终端里等回车（人在终端前，适合本地手动操作）。
    - `--watch`：每 `--interval` 秒探一次，最多 `--timeout` 秒，
      每次都把最新结构覆盖写到 out 目录里——**不用守着终端**，
      别人（比如另一个会话）随时能读最新的一份。
    """
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    with _open_session(args) as session:
        flow = channels_flow.ChannelsFlow(
            PageDriver(session.page, shot_dir=out_dir),
            _config_or_default(args),
        )
        flow.open_entry()
        print("== 视频号助手已打开 ==", flush=True)

        if args.watch:
            print(f"请在弹出的浏览器窗口里用微信扫码登录。")
            print(f"每 {args.interval} 秒探一次，最多等 {args.watch_timeout} 秒。", flush=True)
            deadline = time.monotonic() + args.watch_timeout
            dump = probe.dump_structure(session.page)
            while True:
                probe.save(dump, out_dir / "structure.json")
                (out_dir / "structure.txt").write_text(
                    probe.render_text(dump), encoding="utf-8")
                print(probe.summarize(dump), flush=True)
                if probe.looks_logged_in(dump):
                    break
                if time.monotonic() >= deadline:
                    print("超时了——页面看起来还停在登录页。", file=sys.stderr)
                    break
                time.sleep(args.interval)
                dump = probe.dump_structure(session.page)
        else:
            print("请在弹出的浏览器窗口里用微信扫码登录。")
            print("登录完成后回到这个终端，按回车继续（Ctrl-C 取消）。")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                print("\n取消。", file=sys.stderr)
                return 1
            dump = probe.dump_structure(session.page)
            probe.save(dump, out_dir / "structure.json")
            (out_dir / "structure.txt").write_text(
                probe.render_text(dump), encoding="utf-8")

        shot = out_dir / "structure.png"
        try:
            session.page.screenshot(path=str(shot), full_page=True)
        except Exception:
            shot = None

    print()
    print(probe.render_text(dump))
    print()
    print(f"原始数据：{out_dir / 'structure.json'}")
    print(f"可读版本：{out_dir / 'structure.txt'}")
    if shot:
        print(f"截图：{shot}")
    print(f"照着上面的 suggested 填：{DEFAULT_SELECTORS}")
    return 0


def _config_or_default(args: argparse.Namespace) -> channels_flow.ChannelsConfig:
    path = Path(args.selectors) if getattr(args, "selectors", None) else None
    return channels_flow.ChannelsConfig.load(path)


def _prepare(session, plan, args) -> dict:
    cover = Path(args.cover).expanduser().resolve() if getattr(args, "cover", None) else None
    if cover is not None and not cover.is_file():
        raise PlanError(f"指定的封面不存在：{cover}")
    flow = channels_flow.ChannelsFlow(
        PageDriver(session.page, timeout_ms=args.timeout,
                   shot_dir=Path(args.shot_dir) if args.shot_dir else None),
        _config_or_default(args),
    )
    return flow.prepare(plan, cover=cover)


def cmd_prepare(args: argparse.Namespace) -> int:
    episode = args.episode
    plan = _load_plan(episode, args.package)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / episode
    out_dir.mkdir(parents=True, exist_ok=True)

    with _open_session(args) as session:
        filled = _prepare(session, plan, args)
        shot = out_dir / "prepare.png"
        session.page.screenshot(path=str(shot), full_page=True)

    summary = {
        "episode": episode,
        "package_dir": str(plan.package_dir),
        "filled": filled,
        "screenshot": str(shot),
        "note": "还没发表。要发就跑 python3 -m browser.cli submit " + episode,
    }
    (out_dir / "prepare.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("== 填好的内容 ==")
    for key, value in filled.items():
        print(f"  {key}: {value}")
    print()
    print(f"截图：{shot}")
    print(f"清单：{out_dir / 'prepare.json'}")
    print("**还没发表。** 确认没问题后跑："
          f"python3 -m browser.cli submit {episode}")
    return 0


def _row_text(plan) -> str:
    """内容列表那一行里会出现的文字。

    **列表行显示的是简介，不是短标题**（实测 2026-11-13）——
    拿短标题去常常找不到行，所以给简介里那一段；简介空了就退回短标题。
    """
    if plan.description:
        return plan.description[:20]
    return plan.title[:20]


def cmd_submit(args: argparse.Namespace) -> int:
    episode = args.episode
    plan = _load_plan(episode, args.package)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / episode
    out_dir.mkdir(parents=True, exist_ok=True)

    with _open_session(args) as session:
        # 取公开链接要读剪贴板——权限得先授上（只给这一个站点）
        session.grant_clipboard("https://channels.weixin.qq.com")
        filled = _prepare(session, plan, args)
        shot = out_dir / "submit.png"
        session.page.screenshot(path=str(shot), full_page=True)

        print("== 填好的内容 ==")
        for key, value in filled.items():
            print(f"  {key}: {value}")
        print()
        print(f"截图：{shot}")

        if not args.yes:
            print()
            print("== 这一步会真的发表出去，收不回来 ==")
            try:
                answer = input("确认发表？输入 yes 继续：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n取消。", file=sys.stderr)
                return 1
            if answer.lower() != "yes":
                print("取消。")
                return 1

        flow = channels_flow.ChannelsFlow(
            PageDriver(session.page, timeout_ms=args.timeout,
                       shot_dir=Path(args.shot_dir) if args.shot_dir else None),
            _config_or_default(args),
        )
        try:
            url = flow.submit()
            if not url:
                # 平台不在成功页给链接——去内容列表那一行的分享菜单里取
                # （「复制视频链接」把链接写进剪贴板，再读回来）。
                # **取链接失败不影响「已经发出去了」这个事实**——
                # 那时候该做的是回填快照，不是重发。
                try:
                    url = flow.collect_published_url(_row_text(plan))
                except (channels_flow.FlowError, ActionError) as error:
                    print(f"WARN 取链接失败（{error}）——"
                          "稿子已经发出去了，手动回填链接即可，别重发。",
                          file=sys.stderr)
        finally:
            # 点完「发表」再拍一张。**出事的时候，现场证据全看这张图**——
            # 2026-11-13 那次截图拍在点击之前，结果「点了没反应」一点痕迹都没留。
            shot_after = out_dir / "submit-after.png"
            try:
                session.page.screenshot(path=str(shot_after), full_page=True)
            except Exception:
                shot_after = None

    print()
    if shot_after:
        print(f"点完发表的截图：{shot_after}")
    if not url:
        print("WARN 没能自动取到发布链接。")
        print(f"     请手动复制链接，然后跑：")
        print(f"     cd platforms && {sys.executable} -m channels.cli mark published "
              f"{episode} --url \"<链接>\"")
        return 2

    print(f"OK 已发表：{url}")
    _mark_published(episode, url, args)
    return 0


def _mark_published(episode: str, url: str, args: argparse.Namespace) -> None:
    """回填发布状态。

    走外部命令而不是 import——浏览器执行器不认平台。
    """
    template = args.mark_cmd or DEFAULT_MARK_TEMPLATE
    command = template.format(python=sys.executable, episode=episode, url=url)
    cwd = Path(args.mark_cwd).resolve() if args.mark_cwd else REPO_ROOT / "platforms"
    print(f"回填状态：{command}（cwd={cwd}）")
    result = subprocess.run(shlex.split(command), cwd=str(cwd))
    if result.returncode != 0:
        print(f"ERROR 回填失败（退出码 {result.returncode}）——"
              f"状态快照还是 packaged，别当成已发布。", file=sys.stderr)
        raise SystemExit(result.returncode)


# -- B站（存草稿） ----------------------------------------------------------

def _open_cdp_session(args: argparse.Namespace) -> BrowserSession:
    """挂到已经在跑的浏览器上；没给 ``--cdp`` 就自己起一个。

    **为什么优先挂上去。** 这些平台的登录态是扫码来的，很脆：
    每跑一条命令就重启一次浏览器，登录态可能当场作废。
    所以浏览器用 ``--remote-debugging-port`` 起一次，
    命令用 ``--cdp`` 挂上去（挂上去的会话 ``close()`` 不会关浏览器）。
    """
    cdp = getattr(args, "cdp", None)
    if cdp:
        return BrowserSession.attach(cdp)
    profile = Path(args.profile).expanduser().resolve() if args.profile else default_profile_dir()
    config = SessionConfig.build(profile_dir=profile, headless=args.headless,
                                 slow_mo=args.slow_mo)
    return BrowserSession(config)


def _open_bilibili_session(args: argparse.Namespace) -> BrowserSession:
    """B站 的会话。默认**挂到已经在跑的浏览器**上。

    **为什么不自己起一个。** B站 的登录态是扫码来的，脆；
    每跑一条命令就重启一次浏览器，登录态可能当场作废。
    所以浏览器用 `--remote-debugging-port` 起一次，
    这条命令用 `--cdp` 挂上去（挂上去的会话 `close()` 不会关浏览器）。
    """
    return _open_cdp_session(args)


def cmd_bilibili_draft(args: argparse.Namespace) -> int:
    """传片 + 填表 + **存草稿**（不点「立即投稿」）。"""
    episode = args.episode
    package = (Path(args.package).expanduser().resolve() if args.package
               else DEFAULT_BILIBILI_PACKAGES / episode)
    plan = load_bilibili_plan(package)

    problems = bilibili_flow.check_limits(plan)
    if problems:
        for problem in problems:
            print(f"ERROR  {problem}", file=sys.stderr)
        raise PlanError(f"文案没过 B站 的字数限制，不填进页面：{package}")

    out_dir = Path(args.out) if args.out else DEFAULT_OUT / "bilibili" / episode
    out_dir.mkdir(parents=True, exist_ok=True)
    selectors = (Path(args.selectors) if getattr(args, "selectors", None)
                 else DEFAULT_BILIBILI_SELECTORS)

    with _open_bilibili_session(args) as session:
        flow = bilibili_flow.BilibiliFlow(
            PageDriver(session.page, timeout_ms=args.timeout,
                       shot_dir=Path(args.shot_dir) if args.shot_dir else None),
            bilibili_flow.BilibiliConfig.load(selectors),
        )
        if not flow.is_logged_in():
            print("ERROR 这个浏览器还没登录 B站——先扫码登录，再跑这条命令。",
                  file=sys.stderr)
            return 3
        filled = flow.draft(plan)
        shot = out_dir / "draft.png"
        try:
            session.page.screenshot(path=str(shot), full_page=True)
        except Exception:  # noqa: BLE001
            shot = None

    summary = {
        "episode": episode,
        "package_dir": str(package),
        "filled": filled,
        "screenshot": str(shot) if shot else None,
        "note": "已存草稿，**没有投稿**。投稿要在创作中心里手动点「立即投稿」。",
    }
    (out_dir / "draft.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("== 填好的内容 ==")
    for key, value in filled.items():
        print(f"  {key}: {value}")
    print()
    if shot:
        print(f"截图：{shot}")
    print(f"清单：{out_dir / 'draft.json'}")
    print("**已存草稿，没有投稿。** 要公开就在创作中心里点「立即投稿」。")
    return 0


# -- 头条号（给草稿补图） ----------------------------------------------------

def _toutiao_draft_id(outbox_dir: Path, content_id: str) -> str:
    """从状态快照里读出平台侧的草稿 id。

    快照（``platforms/toutiao/outbox/<slug>__toutiao.json``）是**公开的契约文件**：
    里面记着这篇在平台上是什么状态、平台侧 id 是多少。执行器读它就行，
    不 import 那个 adapter（adapter 也不该知道执行器的事）。
    """
    root = Path(outbox_dir)
    if not root.is_dir():
        raise PlanError(f"状态快照目录不存在：{root}")
    for path in sorted(root.glob("*__toutiao.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("content_id") != content_id:
            continue
        draft_id = payload.get("draft_id")
        if not draft_id:
            raise PlanError(
                f"{content_id} 的快照里没有 draft_id——它可能还没在平台上建过草稿。"
                "**没有草稿 id 就不能补图**：存草稿的请求里带上 pgc_id 才是更新那一条，"
                "不带就是新建一条新的。"
            )
        return str(draft_id)
    raise PlanError(f"状态快照里没有 {content_id}：{root}")


def cmd_toutiao_images(args: argparse.Namespace) -> int:
    """给**已经在平台上的草稿**补图。

    只更新，不新建：请求里带平台侧的草稿 id。没有 id 就不做。
    """
    packages_dir = (Path(args.packages_dir).expanduser().resolve()
                    if args.packages_dir else DEFAULT_TOUTIAO_PACKAGES)
    outbox_dir = (Path(args.outbox_dir).expanduser().resolve()
                  if args.outbox_dir else DEFAULT_OUTBOX)

    content_ids = list(args.content_ids or [])
    if args.all_posts:
        content_ids = []
        for path in sorted(outbox_dir.glob("*__toutiao.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") == "drafted" and payload.get("content_id"):
                content_ids.append(payload["content_id"])
        content_ids.sort()

    if not content_ids:
        print("没有要处理的文章。", file=sys.stderr)
        return 1

    out_dir = Path(args.out).expanduser().resolve() if args.out else DEFAULT_OUT / "toutiao"
    out_dir.mkdir(parents=True, exist_ok=True)

    done: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []

    with _open_cdp_session(args) as session:
        uploader = ToutiaoUploader(session.page)
        for content_id in content_ids:
            try:
                plan = find_toutiao_plan(packages_dir, content_id)
            except PlanError as error:
                failed.append({"content_id": content_id, "error": str(error)})
                continue
            paths = plan.image_paths()
            if not paths and plan.cover is None and not args.force:
                skipped.append({"content_id": content_id, "reason": "这篇没有图，也裁不出封面"})
                continue
            try:
                draft_id = _toutiao_draft_id(outbox_dir, content_id)
                result = uploader.fill_draft(plan, draft_id, images=paths,
                                            cover=not args.no_cover)
            except (ToutiaoError, PlanError) as error:
                failed.append({"content_id": content_id, "error": str(error)})
                continue
            done.append({"content_id": content_id, "draft_id": draft_id, **result})

    summary = {"done": done, "failed": failed, "skipped": skipped}
    (out_dir / "toutiao-images.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in done:
        print(f"✓ {item['content_id']}：图 {item['uploaded']} 张"
              + (f"，缺图 {item['missing']}" if item["missing"] else "")
              + ("，封面已设" if item.get("cover") else ""))
    for item in skipped:
        print(f"· {item['content_id']}：{item['reason']}")
    for item in failed:
        print(f"✗ {item['content_id']}：{item['error']}", file=sys.stderr)
    print(f"\n补图 {len(done)} 篇；跳过 {len(skipped)}；失败 {len(failed)}")
    print(f"清单：{out_dir / 'toutiao-images.json'}")
    return 1 if failed else 0


# -- 入口 -------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="browser",
                                     description="用 Playwright 驱动真实 Chromium 做平台投稿")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--profile", default=None,
                       help="浏览器 profile 目录（登录态放这里）")
        p.add_argument("--headless", action="store_true",
                       help="无头模式——扫码登录时用不了")
        p.add_argument("--slow-mo", type=int, default=0,
                       help="每个动作放慢多少毫秒，调试时用")
        p.add_argument("--selectors", default=None,
                       help=f"选择器表路径，默认 {DEFAULT_SELECTORS}")
        p.add_argument("--timeout", type=int, default=20000,
                       help="单步等元素多久（毫秒）")
        p.add_argument("--shot-dir", default=None, help="失败截图放哪")

    p_doctor = sub.add_parser("doctor", help="环境自检")
    p_doctor.add_argument("--profile", default=None)
    p_doctor.set_defaults(func=cmd_doctor)

    p_probe = sub.add_parser("probe", help="打开视频号助手，扫码，dump 页面结构")
    add_common(p_probe)
    p_probe.add_argument("--out", default=None, help="探测结果存哪")
    p_probe.add_argument("--watch", action="store_true",
                          help="持续轮询页面并覆盖写结果（不用守着终端按回车）")
    p_probe.add_argument("--interval", type=int, default=3, help="轮询间隔（秒）")
    p_probe.add_argument("--watch-timeout", type=int, default=600,
                          help="持续轮询最多等多久（秒）")
    p_probe.set_defaults(func=cmd_probe)

    p_prepare = sub.add_parser("prepare", help="上传 + 填表 + 截图，不发表")
    add_common(p_prepare)
    p_prepare.add_argument("episode")
    p_prepare.add_argument("--package", default=None, help="发布包目录")
    p_prepare.add_argument("--out", default=None, help="产物目录")
    p_prepare.add_argument("--cover", default=None,
                          help="要上传的封面图；不给就用平台自动生成的封面")
    p_prepare.set_defaults(func=cmd_prepare)

    p_submit = sub.add_parser("submit", help="上传 + 填表 + 截图 + 发表")
    add_common(p_submit)
    p_submit.add_argument("episode")
    p_submit.add_argument("--package", default=None, help="发布包目录")
    p_submit.add_argument("--out", default=None, help="产物目录")
    p_submit.add_argument("--cover", default=None,
                          help="要上传的封面图；不给就用平台自动生成的封面")
    p_submit.add_argument("--yes", action="store_true",
                          help="跳过发表前的确认（无人值守时用）")
    p_submit.add_argument("--mark-cmd", default=None,
                          help="回填状态的命令模板")
    p_submit.add_argument("--mark-cwd", default=None,
                          help="跑回填命令时的工作目录")
    p_submit.set_defaults(func=cmd_submit)

    p_bili = sub.add_parser("bilibili-draft",
                             help="传片 + 填表 + 存草稿（B站，**不投稿**）")
    add_common(p_bili)
    p_bili.add_argument("episode")
    p_bili.add_argument("--package", default=None,
                        help="B站 发布包目录，默认 platforms/bilibili/out/<期号>")
    p_bili.add_argument("--out", default=None, help="产物目录")
    p_bili.add_argument("--cdp", default=None,
                        help="挂到已经在跑的浏览器上，"
                             "例如 http://127.0.0.1:9335（不给就自己起一个）")
    p_bili.set_defaults(func=cmd_bilibili_draft)

    p_tt = sub.add_parser("toutiao-images",
                           help="给**已经在平台上的草稿**补图（头条号，只更新不新建）")
    add_common(p_tt)
    p_tt.add_argument("content_ids", nargs="*",
                       help="文章在站点里的 id（就是 source/_posts 下的相对路径，去掉 .md）")
    p_tt.add_argument("--all", dest="all_posts", action="store_true",
                       help="把账本里所有 drafted 的文章都过一遍")
    p_tt.add_argument("--packages-dir", default=None,
                       help="头条号发布包目录，默认 platforms/toutiao/out")
    p_tt.add_argument("--outbox-dir", default=None,
                       help="状态快照目录，默认 platforms/toutiao/outbox")
    p_tt.add_argument("--out", default=None, help="产物目录，默认 browser/out/toutiao")
    p_tt.add_argument("--cdp", default=None,
                       help="挂到已经在跑的浏览器上，"
                            "例如 http://127.0.0.1:9333（不给就自己起一个）")
    p_tt.add_argument("--no-cover", action="store_true", help="不传封面")
    p_tt.add_argument("--force", action="store_true",
                       help="连没有图的也重存一遍（默认跳过：没有图就没有要补的东西）")
    p_tt.set_defaults(func=cmd_toutiao_images)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (PlanError, channels_flow.FlowError, bilibili_flow.FlowError,
            ToutiaoError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    except ActionError as error:
        print(f"ERROR 页面操作失败：\n{error}", file=sys.stderr)
        return 1
    except Exception as error:  # pragma: no cover - 兜底
        print(f"ERROR {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
