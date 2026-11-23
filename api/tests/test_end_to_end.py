"""第一版端到端验收：**接口面走一遍，文件落点看得见**。

这个文件对应设计规格 §10.4 的六条验收场景（见
`review/specs/2026-11-23-创作平台前端设计.md`）：

1. 建一篇空白文档草稿 → 列出来 → 读 → 写回 → 文件确实变了；
2. 建一个视频草稿单元 → 写口播稿 → 契约校验过；
3. 文档流的审校面板出信号（夹具文档**故意写出一处 AI 味**）；
4. 「过审」把草稿复制进母稿层，且**草稿仍在**；
5. 界面提示还差哪三步手工；
6. 出包状态表能读出快照。

**不跑 `make`**——渲染流水线要 ffmpeg、cairo、字体，跑一次几分钟，
还依赖本机素材。**出片作业的「命令正确性」由 `test_commands.py` 的命令表
钉住**；这里只验**接口面**与**文件落点**。
唯一碰到的作业是「出片」那一条，它在**第二步就停**（没有旁白 → 退出码 2），
`make` 根本跑不到——这恰好证明了「先过审、再查旁白、后出片」的次序。

**审校信号用的是真的 `tools/review-check.py`**——夹具文档放进临时树，
真跑一遍规则引擎，出来的信号过一遍路由的归一。规则本身不重写。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from api.routes import drafts as drafts_route
from api.routes import episodes as episodes_route
from api.routes import review as review_route
from api.services import identity

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_TOOL = REPO_ROOT / "tools" / "review-check.py"

#: 夹具文档：故意写了一处 AI 味（连接词开头 + 空泛评价 + 泛化收尾）。
AI_FLAVORED = FIXTURES / "ai-flavored.md"

#: 出包快照的夹具树——一个平台目录 + 一个快照文件。
OUTBOX_FIXTURE = FIXTURES / "outbox"

#: 等一个作业结束的上限（秒）。作业在后台线程里跑。
JOB_TIMEOUT = 30.0


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """一棵**临时的仓库**，所有的缝都指过去。

    真 `drafts/`、`docs/`、`video/episodes/` 一律不碰——
    这些用例要能在别的会话改内容时照样跑。
    """
    root = tmp_path / "repo"
    (root / "drafts").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "video" / "episodes").mkdir(parents=True)
    (root / "review").mkdir(parents=True)

    monkeypatch.setattr(drafts_route, "DRAFTS_DIR", root / "drafts")
    monkeypatch.setattr(drafts_route, "REPO_ROOT", root)
    monkeypatch.setattr(review_route, "DOCS_DIR", root / "docs")
    monkeypatch.setattr(review_route, "EPISODES_DIR", root / "video" / "episodes")
    monkeypatch.setattr(review_route, "REPO_ROOT", root)
    monkeypatch.setattr(episodes_route, "DRAFTS_DIR", root / "drafts")
    monkeypatch.setattr(episodes_route, "EPISODES_DIR", root / "video" / "episodes")
    monkeypatch.setattr(episodes_route, "REPO_ROOT", root)
    return root


def _wait_for_job(client, job_id: str) -> dict:
    """等一个作业跑完，拿它的最终状态。"""
    deadline = time.monotonic() + JOB_TIMEOUT
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"作业 {job_id} 没在 {JOB_TIMEOUT} 秒内结束")


# ── 1. 文档草稿：建 → 列 → 读 → 写回 ─────────────────────────────


def test_a_document_draft_goes_from_created_to_saved(client, tree):
    """建一篇空白文档草稿 → 列出来 → 读 → 写回 → **文件确实变了**。"""
    created = client.post("/api/drafts", json={"kind": "document",
                                                "draft_id": "分类/二级/篇",
                                                "title": "篇"})
    assert created.status_code == 200
    unit = created.json()
    assert unit["kind"] == "document"
    assert unit["draft_id"] == "分类/二级/篇"
    assert unit["promotable"] is True

    listed = client.get("/api/drafts").json()["units"]
    assert [u["draft_id"] for u in listed] == ["分类/二级/篇"]

    read = client.get("/api/drafts/分类/二级/篇").json()
    assert "篇.md" in read["contents"]
    assert read["contents"]["篇.md"].startswith("---")

    saved = client.put("/api/drafts/分类/二级/篇",
                       json={"files": {"篇.md": "---\ntitle: 篇\n---\n\n正文。\n"}})
    assert saved.status_code == 200

    on_disk = (tree / "drafts" / "分类" / "二级" / "篇.md").read_text(encoding="utf-8")
    assert on_disk.endswith("正文。\n")


# ── 2. 视频草稿单元：口播稿与契约 ───────────────────────────────


def test_an_episode_draft_carries_a_script_and_a_valid_contract(client, tree):
    """视频草稿单元 → 写口播稿 → **契约能 json.loads**。

    两个 `episode` 字段是**两回事**（规格 §七.4）：
    `口播稿.md` 的 front matter 记**三层文档路径**，
    `contract.json` 的 `episode` 记**四层期路径**。
    """
    created = client.post("/api/drafts", json={
        "kind": "episode",
        "draft_id": "_video/系列/合集/文档/short",
        "title": "标题",
    })
    assert created.status_code == 200
    assert created.json()["kind"] == "episode"

    saved = client.put("/api/drafts/_video/系列/合集/文档/short", json={"files": {
        "口播稿.md": "---\ntitle: 标题\nepisode: 系列/合集/文档\ntier: short\n---\n\n正文。\n",
    }})
    assert saved.status_code == 200

    tier = tree / "drafts" / "_video" / "系列" / "合集" / "文档" / "short"
    contract = json.loads((tier / "contract.json").read_text(encoding="utf-8"))
    assert contract["episode"] == "系列/合集/文档/short"   # 四层期路径

    script = (tier / "口播稿.md").read_text(encoding="utf-8")
    assert "episode: 系列/合集/文档\n" in script            # 三层文档路径


# ── 3. 审校面板出信号 ──────────────────────────────────────────


def _capture_with_fixture_tree(command, **kwargs):
    """把审校命令指向夹具树——**规则引擎是真的**，只是换了棵树。

    路由的命令是 `python3 tools/review-check.py docs/<id>.md --json
    --docs-root=docs/`（cwd 仓库根）。这里把它改成对临时树跑同一条命令。
    """
    rel = Path(command.argv[2])
    docs_root = rel.parts[0]
    doc = Path(kwargs["docs_root"]) / Path(*rel.parts[1:])
    argv = ["python3", str(REVIEW_TOOL), str(doc), "--json",
            f"--docs-root={kwargs['docs_root']}"]
    result = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True,
                            text=True, check=False)
    return result.returncode, result.stdout


def test_the_review_panel_shows_the_signals_of_an_ai_flavored_document(client,
                                                                       tree,
                                                                       monkeypatch):
    """夹具文档**故意有 AI 味** → 审校面板出信号。

    跑的是真的 `tools/review-check.py`——所以「AI 味」的定义还是仓库里
    那一套，不是这里另写的一套。
    """
    docs_root = tree / "docs"
    target = docs_root / "分类" / "二级" / "篇.md"
    target.parent.mkdir(parents=True)
    target.write_text(AI_FLAVORED.read_text(encoding="utf-8"), encoding="utf-8")

    def capture(command, **kwargs):
        return _capture_with_fixture_tree(command, docs_root=str(docs_root))

    monkeypatch.setattr(review_route, "capture", capture)

    body = client.get("/api/review/documents/分类/二级/篇").json()
    rules = {signal["rule"] for signal in body["signals"]}
    assert "AIF-01" in rules          # 连接词开头
    assert "AIF-02" in rules          # 空泛评价无证据
    assert body["counts"]["warn"] >= 3
    assert body["counts"]["error"] == 0     # 信号不是门禁
    assert body["signals"][0]["target"].startswith("第 ")


def test_the_gate_follows_the_review_record_not_the_signals(client, tree,
                                                            monkeypatch):
    """**信号不是门禁**——闸门只看审校记录的状态。

    文档里满是 AI 味（信号一堆），审校记录写着「已合入」→
    闸门放行。**信号不影响能不能过**（规格 §六.2）。
    """
    docs_root = tree / "docs"
    target = docs_root / "分类" / "二级" / "篇.md"
    target.parent.mkdir(parents=True)
    target.write_text(AI_FLAVORED.read_text(encoding="utf-8"), encoding="utf-8")
    record = tree / "review" / "分类" / "二级" / "篇.md"
    record.parent.mkdir(parents=True)
    record.write_text("---\nstatus: 已合入\n---\n\n记录。\n", encoding="utf-8")

    def capture(command, **kwargs):
        return _capture_with_fixture_tree(command, docs_root=str(docs_root))

    monkeypatch.setattr(review_route, "capture", capture)

    body = client.get("/api/review/documents/分类/二级/篇").json()
    assert body["signals"], "这份文档是有 AI 味的，信号不该是空的"
    assert body["gate"]["status"] == "已合入"
    assert body["gate"]["blocking"] is False


# ── 4. 过审 = 只复制，草稿仍在 ─────────────────────────────────


def test_promote_copies_into_the_mother_layer_and_keeps_the_draft(client, tree):
    """「过审」把草稿**复制**进母稿层，且**草稿仍在原地**。"""
    client.post("/api/drafts", json={"kind": "document",
                                     "draft_id": "分类/二级/篇",
                                     "title": "篇"})
    client.put("/api/drafts/分类/二级/篇",
               json={"files": {"篇.md": "---\ntitle: 篇\n---\n\n正文。\n"}})

    response = client.post("/api/drafts/分类/二级/篇/promote")
    assert response.status_code == 200
    body = response.json()
    assert body["targets"] == ["docs/分类/二级/篇.md"]

    mother = tree / "docs" / "分类" / "二级" / "篇.md"
    assert mother.read_text(encoding="utf-8").endswith("正文。\n")

    # **草稿仍在**——过审是复制，不是移动。
    assert (tree / "drafts" / "分类" / "二级" / "篇.md").is_file()


def test_promoting_an_episode_copies_only_the_three_facts(client, tree):
    """一期的过审**只复制入库事实**——旁白、时间轴不跟过去。"""
    client.post("/api/drafts", json={"kind": "episode",
                                     "draft_id": "_video/系列/合集/文档/short",
                                     "title": "标题"})
    tier = tree / "drafts" / "_video" / "系列" / "合集" / "文档" / "short"
    (tier / "narration.mp3").write_bytes(b"fake")

    response = client.post("/api/drafts/_video/系列/合集/文档/short/promote")
    assert response.status_code == 200
    targets = response.json()["targets"]
    assert targets == [
        "video/episodes/系列/合集/文档/short/口播稿.md",
        "video/episodes/系列/合集/文档/short/contract.json",
        "video/episodes/系列/合集/文档/short/publish.json",
    ]
    mother = tree / "video" / "episodes" / "系列" / "合集" / "文档" / "short"
    assert not (mother / "narration.mp3").exists()


# ── 5. 还差哪三步手工 ──────────────────────────────────────────


def test_promote_says_which_three_manual_steps_are_left(client, tree):
    """过审之后**还有三步要人做**——门面报出来，不假装做了。"""
    client.post("/api/drafts", json={"kind": "document",
                                     "draft_id": "分类/二级/篇",
                                     "title": "篇"})

    body = client.post("/api/drafts/分类/二级/篇/promote").json()
    steps = body["manual_steps"]
    assert len(steps) == 3
    joined = "\n".join(steps)
    assert "审校记录" in joined
    assert "INDEX" in joined
    assert "提交" in joined


# ── 6. 出包状态表 ──────────────────────────────────────────────


def test_the_publish_status_table_reads_the_snapshots(client, monkeypatch):
    """出包状态表能读出快照——**只投影公共子集**。"""
    monkeypatch.setattr(identity, "PLATFORMS_DIR", OUTBOX_FIXTURE)

    body = client.get("/api/publish/outbox").json()
    snapshots = body["snapshots"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["platform"] == "platform-a"
    assert snapshot["status"] == "packaged"
    assert snapshot["title"]
    assert set(snapshot) == set(identity.OUTBOX_COMMON)


# ── 出片作业：先过审，再查旁白（`make` 跑不到） ─────────────────


def test_the_build_job_promotes_first_and_stops_before_make(client, tree):
    """出片作业的**次序**：先过审 → 查旁白 → 才轮到 `make`。

    这里没有旁白，所以作业停在第二步、退出码 2——
    **`make` 一次都没跑**（渲染要 ffmpeg 与本机素材，测试里跑不动）。

    断言的是两件事：
    - 第一步**真的过审了**（日志里说复制了什么）；
    - 作业**没跑到 `make`**（退出码 2 = 前置条件没满足）。
    """
    client.post("/api/drafts", json={"kind": "episode",
                                     "draft_id": "_video/系列/合集/文档/short",
                                     "title": "标题"})

    started = client.post("/api/episodes/系列/合集/文档/short/build")
    assert started.status_code == 200
    job = _wait_for_job(client, started.json()["job_id"])

    log = "\n".join(job["log"])
    assert "过审复制了" in log
    assert "还没有旁白" in log
    assert "make" not in log
    assert job["exit_code"] == 2
    assert job["exit_label"] == "precondition"

    # 过审那一步**真的落了地**。
    mother = tree / "video" / "episodes" / "系列" / "合集" / "文档" / "short"
    assert (mother / "contract.json").is_file()
