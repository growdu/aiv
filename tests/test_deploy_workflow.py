"""Contract tests for the deployment workflow (``.github/workflows/hexo.yml``).

Why this file exists
--------------------
On 2026-11-13 the site froze.  ``growdu.cn`` stopped at a commit from 12:02
and ``growdu.github.io/blog`` at 12:26, and stayed there for the better part
of an hour while dozens of commits were pushed.  Two independent causes were
involved, and **both are silent** -- the workflow file stays valid, the
test suite stays green, the site just quietly stops moving:

1. **A job that never returns.**  ``deploy-server``'s ssh had no
   ``BatchMode``, so a rejected key turned into "waiting for a password
   prompt" instead of an error.  A workflow run only finishes when *every*
   job finishes, and the concurrency group is only released when the run
   finishes -- so one stuck job parks every later push in ``pending`` and
   the whole queue stops draining.  The cure is a timeout on every job, so
   the stuck job dies and the queue resumes.

2. **Cancelling the in-flight run.**  ``cancel-in-progress: true`` looks
   like "latest push wins", but during a burst of pushes it kills every run
   before ``build`` can finish, so nothing is ever published.  GitHub's
   concurrency already collapses the *pending* queue down to the newest
   run, so ``false`` gives "latest push wins" without the starvation.

Neither property is visible when you read the YAML, so both are pinned here.

The workflow is parsed textually rather than with PyYAML: the suite then
keeps running with nothing but pytest installed.  The parsing helpers below
are therefore part of the contract -- every scanning test asserts the
*scope* of its scan (how many jobs / how many ssh calls it found) so that a
parser that quietly stops matching cannot turn these checks into green
no-ops.

Nothing here talks to the network: these are contract tests over a file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github/workflows/hexo.yml"

# A job key sits at two-space indentation under ``jobs:``.
_JOB_KEY = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
# ``timeout-minutes`` sits at four-space indentation, right under the job key.
_TIMEOUT = re.compile(r"^    timeout-minutes:\s*([0-9]+)\s*$", re.M)
_NEEDS = re.compile(r"^    needs:\s*(.*)$", re.M)
REQUIRED_JOBS = {"build", "deploy-server", "build-github-pages", "deploy-github-pages"}


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), f"找不到部署工作流：{WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def _jobs(text: str) -> dict[str, str]:
    """Split the ``jobs:`` section into one text block per job."""
    lines = text.splitlines()
    try:
        start = lines.index("jobs:")
    except ValueError:
        return {}
    blocks: dict[str, str] = {}
    name: str | None = None
    buf: list[str] = []
    for line in lines[start + 1:]:
        match = _JOB_KEY.match(line)
        if match:
            if name is not None:
                blocks[name] = "\n".join(buf)
            name = match.group(1)
            buf = []
            continue
        if name is None:
            continue
        if line.strip() and not line.startswith("  ") and not line.startswith("#"):
            break  # left the jobs: section
        buf.append(line)
    if name is not None:
        blocks[name] = "\n".join(buf)
    return blocks


def _needs_of(block: str) -> list[str]:
    match = _NEEDS.search(block)
    if not match:
        return []
    raw = match.group(1).strip()
    if not raw:
        return []
    if raw.startswith("["):
        return [d.strip().strip("'\"") for d in raw.strip("[]").split(",") if d.strip()]
    return [d.strip() for d in raw.split(",") if d.strip()]


def test_workflow_shape_is_recognised() -> None:
    """Scan-scope self-check: the parser must find the whole job set."""
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS), (
        f"只认出 {len(jobs)} 个 job（期望至少 {len(REQUIRED_JOBS)}），解析多半坏了"
    )
    assert REQUIRED_JOBS <= set(jobs), (
        f"少了这些 job：{sorted(REQUIRED_JOBS - set(jobs))}；"
        "两个发布出口（自建服务器 + GitHub Pages）都要有人在"
    )


def test_every_job_is_bounded_by_a_timeout() -> None:
    """A job without a timeout can hold the concurrency group forever."""
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS)
    missing = sorted(name for name, block in jobs.items() if not _TIMEOUT.search(block))
    assert not missing, (
        f"这些 job 没有 timeout-minutes：{missing}。"
        "job 挂死不退出 → run 不结束 → 并发组不释放 → 后面所有推送全卡在 pending"
    )
    for name, block in jobs.items():
        minutes = int(_TIMEOUT.search(block).group(1))
        assert 1 <= minutes <= 60, f"job {name} 的 timeout-minutes={minutes} 不合理"


def test_concurrency_keeps_the_running_run_and_collapses_the_queue() -> None:
    """``false`` is what makes this converge -- see the module docstring."""
    text = _workflow_text()
    block = re.search(r"^concurrency:\n((?:[ \t]+.*\n)+)", text, re.M)
    assert block, "找不到 concurrency 段"
    body = block.group(1)
    # 设置项固定在两空格缩进上。注释行开头是 '#'，匹配不上——
    # 这样「注释里写了 cancel-in-progress: false」不会被误当成真设置。
    assert re.search(r"^  group:\s*\S+\s*$", body, re.M), "concurrency 段里没有 group"
    assert re.search(r"^  cancel-in-progress:\s*false\s*$", body, re.M), (
        "cancel-in-progress 必须保持 false：GitHub 本来就会把 pending 队列收敛成最新一个，"
        "设成 true 反而会在推送密集时把每次 run 在 build 完之前砍掉，站点永远停在旧版本"
    )


def test_ssh_calls_are_non_interactive() -> None:
    """ssh must never wait for input: waiting == job hangs == queue stalls.

    The options now live in one shared ``SSH_OPTS`` variable, so the check
    is on the *effective* command: the variable must carry both switches,
    and every ssh invocation must go through it.  A bare ``ssh -p ...``
    somewhere would silently lose the switches, so those are rejected too.
    """
    text = _workflow_text()
    code = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    )

    opts = re.search(r'SSH_OPTS="([^"]*)"', code)
    assert opts, "找不到 SSH_OPTS 定义"
    switches = opts.group(1)
    assert "BatchMode=yes" in switches, (
        f"SSH_OPTS 里没有 BatchMode=yes：{switches}"
        "——认证失败会变成「等密码提示」，整个 job 挂死"
    )
    assert "ConnectTimeout=" in switches, f"SSH_OPTS 里没有连接超时：{switches}"

    # 小写 "ssh " 后面必须跟空白：这样不会误匹配 ssh-keyscan。
    calls = [line for line in code.splitlines() if re.search(r"(?:^|[^\w-])ssh\s", line)]
    assert len(calls) >= 4, (
        f"只认出 {len(calls)} 处 ssh 调用（期望至少 4：取上一个 release、"
        "rsync 的 -e、切 symlink、清理旧 release），扫描多半没生效"
    )
    for line in calls:
        assert "${SSH_OPTS}" in line, (
            f"这处 ssh 绕过了 SSH_OPTS，会丢掉非交互选项：{line.strip()}"
        )


def test_known_hosts_is_verified_before_use() -> None:
    """An empty known_hosts turns ssh into a "trust this host?" prompt."""
    text = _workflow_text()
    assert "ssh-keyscan" in text, "Setup SSH 步骤不写 known_hosts"
    assert re.search(r"ssh-keyscan\s+-T\s+\d+", text), "ssh-keyscan 自己也要有超时"
    assert "! -s ~/.ssh/known_hosts" in text, (
        "known_hosts 为空时 ssh 会卡在「是否信任这个主机」的问句上，"
        "必须在连接之前判死，并把最可能的原因写进报错里"
    )


def test_job_graph_has_no_dangling_edges_and_no_cycles() -> None:
    """Integration-level: ``needs`` must point at real jobs, and the graph must be acyclic."""
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS)
    graph = {name: _needs_of(block) for name, block in jobs.items()}
    for name, deps in graph.items():
        for dep in deps:
            assert dep in jobs, f"job {name} 依赖了不存在的 job {dep}"

    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        assert state.get(node, 0) != 1, f"job 依赖成环了：{' -> '.join(path + [node])}"
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph[node]:
            visit(dep, path + [node])
        state[node] = 2

    for name in graph:
        visit(name, [])


def test_workflow_triggers_on_push_to_master() -> None:
    text = _workflow_text()
    assert re.search(r"^on:", text, re.M), "工作流没有 on: 触发器"
    assert re.search(r"^\s*push:", text, re.M), "工作流不由 push 触发"
    assert re.search(r"^\s*-\s*master\s*$", text, re.M), "push 触发器里没有 master 分支"


def _is_tracked(path: str) -> bool:
    """这个文件在 git 里吗（跟踪着）？"""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=REPO, capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def test_the_deploy_only_transfers_what_changed() -> None:
    """部署不能每次都全量重传。

    每次部署都往新的时间戳目录里全量传 167MB / 2400 个文件，站点滞后
    多久就完全取决于跨太平洋链路的快慢——2026-11-13 同一条命令跑出过
    38 秒、也跑出过 20 分钟还没完。``--link-dest`` 让没变的文件走硬链接，
    只有变化的那几个过网络，链路再慢也无所谓。

    这条盯的是「选项还在不在」，所以只认代码、不认注释。
    """
    text = _workflow_text()
    step = re.search(
        r"- name: Deploy via rsync\n(.*?)(?=\n      - name:|\n  [a-zA-Z-]+:)", text, re.S
    )
    assert step, "工作流里找不到 Deploy via rsync 步骤"
    code = "\n".join(
        line for line in step.group(1).splitlines()
        if not line.strip().startswith("#")
    )
    assert "--link-dest" in code, (
        "rsync 没有 --link-dest——每次部署都要全量传一遍，"
        "站点滞后多久全看跨太平洋链路的脸色"
    )


def test_the_npm_cache_is_never_used_without_a_tracked_lockfile() -> None:
    """``cache: npm`` 需要 lockfile **在仓库里**，否则整个 build 挂掉。

    2026-11-13 实测：给 setup-node 加上 ``cache: npm`` 之后，
    setup-node 直接报「Dependencies lock file is not found」——
    本仓库的 ``package-lock.json`` 被 ``.gitignore`` 挡掉了，
    **本地有、仓库里没有**。于是每一个 run 都在 build 的第一步就红了，
    而且报的是「锁文件找不到」，跟「缓存」八竿子打不着，很难第一眼联想到。

    所以这条不是「缓存好不好」的问题，是「用了缓存的前提满足没有」。
    """
    text = _workflow_text()
    # 不管用不用缓存，依赖总得装——否则 build 根本跑不起来。
    assert re.search(r"npm (install|ci)", text), "工作流里没有装依赖的步骤"

    if "cache: npm" not in text:
        return  # 没开 npm 缓存，这条前提不适用

    assert _is_tracked("package-lock.json"), (
        "workflow 用了 cache: npm，但 package-lock.json 不在仓库里"
        "（本仓库把它 gitignore 了）——setup-node 会直接失败，"
        "每个 run 都在 build 第一步就红"
    )


# --- 两套 build 并行 ------------------------------------------------------


def _code_without_comments(text: str) -> str:
    """去掉整行注释，只留可执行的部分。

    注释里经常要提到脚本名、job 名、开关名，统计时必须只认代码，
    否则"注释里提了一句"会被当成"多了一处"。
    """
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def test_the_two_builds_run_in_parallel() -> None:
    """两套 hexo generate 不该前后排。

    2026-11-14 实测：``build`` 599 秒、``build-github-pages`` 564 秒，
    串起来就是 20 分钟一次部署——站点滞后多久全看这两段相加。
    两边产出的东西互不相干（只是 root 前缀不同），没有理由串行。

    当初串行只是为了躲开 Gitalk issue 的竞态，现在改由单一 job 建 issue
    （见下一条），所以这里的串行已经没有任何理由，必须去掉。
    """
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS)
    pages_needs = _needs_of(jobs["build-github-pages"])
    assert "build" not in pages_needs, (
        "build-github-pages 又依赖上 build 了——两套 hexo generate 串行，"
        f"每次部署要多等 {9} 分钟（实测 599s + 564s）"
    )
    assert "build-github-pages" not in _needs_of(jobs["build"]), (
        "build 依赖了 build-github-pages，方向反了"
    )


def test_only_one_place_creates_gitalk_issues() -> None:
    """建 Gitalk issue 的地方只能有一处。

    两处都建会打架：各自列一遍 issue、各自觉得"这篇还没有"、
    各自建一份，2026-11-13 因此攒出 **182 对**重复 issue
    （同一个 gitalk-id 被建了两遍，评论区分裂成两个）。

    修法不是"让它们排队"（那只是把竞态藏起来，还白搭 9 分钟），
    而是**整个工作流里只剩一处**调用 init-gitalk-issues.js。
    """
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS)

    creators = [
        name
        for name, block in jobs.items()
        if "init-gitalk-issues.js" in _code_without_comments(block)
    ]
    assert len(creators) == 1, (
        f"有 {len(creators)} 个 job 在建 Gitalk issue：{creators}。"
        "多于一处就会各自建一份重复 issue（2026-11-13 攒过 182 对）"
    )
    assert creators[0] == "build", (
        f"建 issue 的 job 变成了 {creators[0]}——"
        "主域名 growdu.cn 那套 build 建出来的 issue，正文里链接才指向主域名"
    )
    # Pages 那套只出产物，不碰 issue。
    assert "init-gitalk-issues.js" not in _code_without_comments(
        jobs["build-github-pages"]
    ), "build-github-pages 又开始建 issue 了"


def test_the_deploys_still_wait_for_their_own_build() -> None:
    """并行化不能把"发布前必须先构建出来"这条弄丢。"""
    jobs = _jobs(_workflow_text())
    assert len(jobs) >= len(REQUIRED_JOBS)
    assert "build" in _needs_of(jobs["deploy-server"]), (
        "deploy-server 不等 build 就发布，站点会被 rsync 成一堆半成品"
    )
    assert "build-github-pages" in _needs_of(jobs["deploy-github-pages"]), (
        "deploy-github-pages 不等 build-github-pages 就发布"
    )


def test_the_icon_subset_step_never_blocks_the_deploy() -> None:
    """字体裁剪是锦上添花，不许把发布带崩。

    ``tools/subset-icons.py`` 裁成功省 240 KB，裁失败保持原字体——网站照常
    上线。所以这一步必须 ``continue-on-error``：让"省了点体积"去换"站点
    发不出去"，不划算。

    空白图标的防线在工具内部（码位必须在原字体里、裁完必须在 cmap 里），
    这里的 continue-on-error 说的是另一件事：工具本身跑不起来时也别阻断。
    """
    text = _workflow_text()
    steps = re.findall(
        r"- name: Subset Font Awesome fonts\n(.*?)(?=\n      - name:|\n  [a-zA-Z-]+:)",
        text,
        re.S,
    )
    assert len(steps) == 2, (
        f"两套 build 都应该有字体裁剪步骤（现在找到 {len(steps)} 个）"
    )
    for step in steps:
        assert (
            "continue-on-error: true" in step or "|| echo" in step
        ), (
            "字体裁剪步骤没有 continue-on-error、也没有 || echo 兜底——"
            "裁剪失败会把发布一起带崩"
        )
        assert "tools/subset-icons.py" in step, "裁剪步骤调的不是 tools/subset-icons.py"
        assert "::warning::" in step, (
            "裁剪失败要发一条 ::warning:: 注解，否则日志里只有一句"
            "「exit code 1」，看不出是没装上还是裁不动"
        )
