# 目录架构调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把视频生产线改名成 `video/`、把五个第三方平台收进 `platforms/<plat>/` 按平台划分、把按平台归属的数据（能力声明与发布快照）下沉到平台目录，并新增 `drafts/` 草稿箱入口。

**Architecture:** 四层目录搬家加一层接线。`aiv/` 整树改名成 `video/`（内部不动）；`weixin/` `toutiao/` `douyin/` `bilibili/` `channels/` 收进 `platforms/`，内层包压平，**目录名 = 平台 id = Python 包名**；`publish/capabilities/*.toml` 变成 `platforms/<plat>/capability.toml`，`publish/outbox/*.json` 变成 `platforms/<plat>/outbox/*.json`；契约层 `publish/` 只留平台无关的部分，它仍**不 import 任何平台**。

**Tech Stack:** Python 3.12（标准库 + pytest）、Hexo 站点、GitHub Actions。

**Spec:** `review/specs/2026-11-17-directory-architecture-design.md`（**设计稿是准绳**；本计划只把它拆成可执行的动作。实施中发现与设计稿冲突，改设计稿并在此处记录，不擅自改方向）

## Global Constraints

这几条对每个 task 都成立，实施时不得放宽：

- **快照文件名 `<content_id>__<platform>.json` 一个字都不改**——它是幂等键，改名等于让已发过的内容被当成没发过。
- **`docs/life/aiv/` 目录名、`life/aiv/…` 形式的 content id、指向 `life/aiv/` 专题页的站点链接（8 处 `aiv/index.html`，分布在 4 个文件里）一个都不改**——URL 稳定性是硬约束（`publish/spec/00-架构设计.md` §7.4）。
- **567 个快照的正文不改**——`package_dir` 字段里的旧路径搬迁后会失效，但站点构建不读它，不重写历史发布记录。
- **目录名 = 平台 id = Python 包名**：`wechat` `toutiao` `douyin` `bilibili` `channels`。五个能力声明文件统一叫 `capability.toml`。
- **目录改名，标识符里的 AIV 保留**——`AIV_ROOT` 这类常量不改名（AIV 是品牌，还在用）；只有它指向的**目录路径**变。
- **不改任何平台适配层的业务逻辑**——只改路径、import 与调用点。
- **历史计划与试点记录不改**——`publish/plans/`、`review/plans/`、`video/review/plans/`、`video/pipeline/plans/` 里的路径引用是**当时的快照**，改了失真。唯一例外见 Task 6 Step 6。
- **提交信息不带 `Co-Authored-By`**（用户全局 CLAUDE.md 的要求）。
- **每个 task 结束时测试必须全绿**，红了不许往下走。

## Review Focus

设计稿没写、但最可能咬人的五类输入与失败模式。每个都有对应的测试，写在下面各自的 task 里：

1. **读侧漏改 → 重复发布。** outbox 分平台之后，任何还在扫单一目录的读者都会把 567 条已发布记录看成「一篇都没发过」，调度器于是重发。→ Task 4 的守卫：真实仓库的 outbox 索引必须含 567 条；Task 0/Task 7 前后对比 `publishkit schedule status` 的「已发过（567）」。
2. **adapter 子进程找不到包。** 压平之后内层包没了，`python3 -m toutiao.cli` 靠 cwd 在 `sys.path` 里找包；cwd 不跟着改，调度器一调 adapter 就失败。→ Task 2 的守卫：子进程 cwd 必须是 `<repo>/platforms`，且五个平台各自 `python3 -c "import <plat>.cli"` 要成功。
3. **能力声明按 id 找不到目录。** 目录名与 toml 里的 `id` 不一致时，按 id 查目录就查不到。→ Task 3 的守卫：每个平台的目录名必须等于其 toml 里的 `id`。
4. **URL 命名空间被误改 → 老链接全断。** 批量替换 `aiv/` 时误伤 `docs/life/aiv/` 目录、`life/aiv/…` content id，或 `docs/life/_index.md` 里指向 `life/aiv/` 专题页的 `./aiv/index.html` 链接（**全仓 8 处，4 个文件**）。→ Task 1 的守卫 + Task 1 Step 4 的**占位符保护法**。
5. **静默失败。** `tools/build-publish-index.py` 与 `tools/build-video-pages.py` 的测试把 outbox 路径 monkeypatch 成临时目录，路径写错时**测试照样全绿**，只有真跑构建才炸。→ Task 4 的守卫：直接对**真实仓库**调一次 `read_outbox()`，断言条数。

---

### Task 0: 记录基线

**Files:**
- Create: `/tmp/baseline/` 下的几个输出文件（不进仓库）

**Interfaces:**
- Consumes: 无。
- Produces: 一份「迁移前」的对照数字，Task 4 Step 9 与 Task 7 拿它比对。

- [ ] **Step 1: 记下快照数与各平台分布**

```bash
mkdir -p /tmp/baseline
ls publish/outbox/ | wc -l > /tmp/baseline/outbox-count.txt
ls publish/outbox/ | sed 's/.*__//; s/\.json$//' | sort | uniq -c > /tmp/baseline/outbox-per-platform.txt
```

Expected: `567`；分布是 `6 bilibili / 6 channels / 6 douyin / 549 toutiao`。

- [ ] **Step 2: 记下调度器读到的发布历史**

```bash
PYTHONPATH=publish python3 -m publishkit.cli schedule status > /tmp/baseline/status.txt
PYTHONPATH=publish python3 -m publishkit.cli schedule candidates > /tmp/baseline/candidates.txt
```

Expected: `status.txt` 第二行是「已发过（567）：」；`candidates.txt` 是 2 篇候选、各自「已发到过：toutiao」。**这两个输出是 Task 4 读侧改动的对照物**。

- [ ] **Step 3: 记下站点索引的条数**

```bash
python3 tools/build-publish-index.py
python3 -c "
import json; d=json.load(open('source/_data/publish_index.json'))
print(len(d['articles']), len(d['videos']))" > /tmp/baseline/publish-index.txt
```

Expected: `549 0`。

- [ ] **Step 4: 记下视频页数量**

```bash
python3 tools/build-video-pages.py
ls source/_posts/ 2>/dev/null | grep -c 'episode\|视频' || true
```

（`build-video-pages.py` 的产物路径按脚本实际输出确认，把条数写进 `/tmp/baseline/video-pages.txt`。）

---

### Task 1: 视频线改名 `aiv/` → `video/`

**Files:**
- Move: `aiv/` → `video/`（整树，555 个文件；`git mv` 保历史）
- Modify: 129 个含 `aiv/` 的文件里的路径引用（替换规则见 Step 4）
- Modify: `video/pipeline/pyv/character.py`（注释）
- Modify: `video/pipeline/tests/test_character.py`（两条断言 + 一个测试名）
- Modify: `.github/workflows/aiv-pipeline.yml` → `.github/workflows/video-pipeline.yml`
- Modify: `.github/workflows/site-guard.yml`（注释）
- Modify: `pyrightconfig.json`（extraPaths）
- Modify: `requirements/aiv.txt` → `requirements/video-pipeline.txt`、`requirements/video.txt` → `requirements/video-platforms.txt`
- Modify: `requirements/README.md`、`tools/build-video-pages.py`、`tools/sync-hexo.py`
- Test: `tests/test_podcast_spec.py`（新增两条守卫）

**Interfaces:**
- Consumes: Task 0 的基线。
- Produces: 仓库根有 `video/` 目录；`video/pipeline/pyv`、`video/contracts`、`video/review`、`video/scripts`、`video/publish` 路径对全仓生效；`docs/life/aiv/` 这条 URL 命名空间原样不动。

- [ ] **Step 1: 写下两条守卫（此时应绿）**

在 `tests/test_podcast_spec.py` 末尾加（`REPO_ROOT` 该文件里已有；若没有用 `Path(__file__).resolve().parents[1]`）：

```python
def test_the_life_aiv_url_namespace_is_untouched():
    """`docs/life/aiv/` 是 URL 命名空间，搬家不许碰它。"""
    namespace = REPO_ROOT / "docs" / "life" / "aiv"
    assert namespace.is_dir(), "docs/life/aiv/ 不见了——URL 命名空间被搬家弄坏了"
    files = [p for p in namespace.rglob("*") if p.is_file()]
    assert len(files) == 9, f"docs/life/aiv/ 的文件数变了：{len(files)}（应为 9）"


def test_the_links_into_the_life_aiv_topic_page_still_point_at_aiv():
    """专题页还在 life/aiv/ 下，指向它的站点链接一个都不能改成 video/。"""
    links = {
        "docs/life/_index.md": "./aiv/index.html",
        "docs/life/blog-to-wechat/index.md": "../aiv/index.html",
        "docs/life/shehui/media-account/index.md": "../../aiv/index.html",
        "docs/database/_index.md": "../life/aiv/index.html",
    }
    for path, link in links.items():
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert link in text, f"{path} 里的 {link} 链接不见了"

    # 全仓点数：docs/ 里指向 life/aiv 专题页的链接一共 8 处（分处 4 个文件）
    count = 0
    for path in sorted((REPO_ROOT / "docs").rglob("*.md")):
        count += path.read_text(encoding="utf-8").count("aiv/index.html")
    assert count == 8, f"docs/ 里指向 life/aiv 专题页的链接变成 {count} 处（应为 8）"

    # README 里讲解相对链接机制的那两处例子也是 URL 命名空间（搬前叫 aiv/README.md）
    for name in ("video", "aiv"):
        readme = REPO_ROOT / name / "README.md"
        if readme.is_file():
            text = readme.read_text(encoding="utf-8")
            assert "../aiv/背景音乐规范.md" in text, f"{name}/README.md 里的链接例子不见了"
            assert "../aiv/index.html" in text, f"{name}/README.md 里的链接例子不见了"
            break
    else:
        raise AssertionError("既没有 video/README.md 也没有 aiv/README.md")
```

- [ ] **Step 2: 跑测试确认它们现在会绿**

Run: `python3 -m pytest tests/test_podcast_spec.py -q -k "life_aiv"`
Expected: PASS（2 passed）。

- [ ] **Step 3: 换目录**

```bash
git mv aiv video
```

- [ ] **Step 4: 替换路径引用（占位符保护法）**

**先看哪些形式必须保留：**

| 形式 | 例子 | 处置 |
| --- | --- | --- |
| `life/aiv/…` | `docs/life/aiv/`、`life/aiv/voice/README`、`/growdu.cn/2026/11/12/life/aiv/` | **不动**（URL 命名空间与 content id） |
| 指向 `life/aiv/` 专题页的站内相对链接（**8 处**） | `[AIV 视频生产线](../aiv/index.html)`、`../aiv/背景音乐规范.md` | **不动**（站点链接，指向 `life/aiv/`） |
| 其余 `aiv/…` | `aiv/pipeline/pyv/`、`aiv/字幕-行锁.md`、`aiv/contracts/`、`../../aiv/index.md`（在 `publish/spec/` 里指的是**仓库目录**） | **改成 `video/…`** |

> 站内相对链接与仓库路径的区别**不能靠词形判断**——`publish/spec/00-架构设计.md` 里的
> `../../aiv/` 指的是仓库根的 `aiv/` 目录（该换），`docs/life/` 里的 `../aiv/` 指的是
> 站点上的 `life/aiv/` 专题页（不该换）。所以下面按**文件**逐个列出要保护的字面量，
> 先占位保护、替换完再还原。

用这个脚本跑一遍（放在仓库根执行）：

```bash
python3 - <<'PY'
import pathlib, re

ROOT = pathlib.Path(".")
# 这些文件里的路径引用是「当时的快照」，不改
EXCLUDE = (
    "publish/plans/",
    "review/plans/",
    "review/specs/2026-11-17-directory-architecture-design.md",
    "review/plans/2026-11-17-directory-architecture-plan.md",
    "video/review/plans/",
    "video/pipeline/plans/",
    "docs/blog/重构方案.md",          # 已发布的旧文章
)
# 这些字面量是「站内相对链接」，指向 life/aiv/ 专题页——替换前先占位，替换完还原。
# aiv/README.md 与 video/README.md 是同一个文件（搬前/搬后），两个名字都列上。
PROTECTED = {
    "docs/life/_index.md": ("./aiv/index.html",),
    "docs/life/blog-to-wechat/index.md": ("../aiv/index.html",),
    "docs/life/shehui/media-account/index.md": ("../../aiv/index.html",),
    "docs/database/_index.md": ("../life/aiv/index.html",),
    "aiv/README.md": ("../aiv/背景音乐规范.md", "../aiv/index.html"),
    "video/README.md": ("../aiv/背景音乐规范.md", "../aiv/index.html"),
}
MARK = "\x00SL{}\x00"

changed = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or "/.git/" in f"/{path}":
        continue
    rel = path.as_posix()
    if rel.startswith(EXCLUDE):
        continue
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    text = original
    saved = []
    for i, literal in enumerate(PROTECTED.get(rel, ())):
        if literal in text:
            text = text.replace(literal, MARK.format(i))
            saved.append((i, literal))
    new = re.sub(r"(?<!life/)aiv/", "video/", text)
    for i, literal in saved:
        new = new.replace(MARK.format(i), literal)
    if new != original:
        path.write_text(new, encoding="utf-8")
        changed.append(rel)
print(f"改了 {len(changed)} 个文件")
PY
```

> **`aiv/` 前面是 `life/` 的绝不换**——那是 URL 命名空间与 content id。
> **那 8 处站内相对链接绝不换**——它们指向 `life/aiv/` 专题页，脚本里逐个占位保护。

- [ ] **Step 5: 替换独立出现的 `aiv` 词（不带斜杠的路径）**

```bash
git grep -n -P '(?<!life/)\baiv\b' -- '*.py' '*.yml' '*.yaml' '*.toml' '*.json' '*.txt' | grep -v 'plans/'
```

逐条判断。可预期的两类：

| 位置 | 现状 | 改成 |
| --- | --- | --- |
| `video/pipeline/pyv/character.py:29` | `# aiv 与 weixin 同级，直接挂在仓库根下` | `# video/ 与 platforms/ 同级，都挂在仓库根下` |
| `video/pipeline/tests/test_character.py:18` | `"""aiv 是仓库根级模块，与 weixin 同级。` | `"""video 是仓库根级模块，与 platforms 同级。` |

- [ ] **Step 6: 改 `test_character.py` 的两条断言**

`video/pipeline/tests/test_character.py`：

```python
def test_repo_paths_are_resolved_correctly():
    assert character.AIV_ROOT.name == "video"
    assert character.REPO_ROOT == character.AIV_ROOT.parents[0]
    assert character.STATIC_IMAGE.is_relative_to(character.AIV_ROOT)
```

```python
def test_video_sits_next_to_platforms_at_repo_root():
    """video 是仓库根级模块，与 platforms 同级。

    目录层级被文档、脚本和 Makefile 里的相对路径引用着，挪一层就得全量改一遍。
    这里钉住它的位置，免得以后再被悄悄挪走。
    """
    repo_root = character.REPO_ROOT
    assert (repo_root / "video").is_dir()
    assert character.AIV_ROOT == repo_root / "video"
    # 旧位置只剩发布用的文档副本，工程内容（pipeline/ 等）必须已经搬走
    legacy = repo_root / "docs" / "life" / "aiv"
    assert legacy.is_dir()
    assert not (legacy / "pipeline").exists(), "工程目录还留在旧位置"
```

（`platforms/` 要等到 Task 2 才存在，所以那条 `assert (repo_root / "platforms").is_dir()`
在 Task 2 Step 3 补上——本 task 先不写，否则这里必红。）

- [ ] **Step 7: 改 CI 与配置**

| 文件 | 改什么 |
| --- | --- |
| `.github/workflows/aiv-pipeline.yml` → `video-pipeline.yml` | `git mv` 改名；`paths:` 的 `"aiv/**"` → `"video/**"`（两处）；`working-directory: aiv/pipeline` → `video/pipeline`（两处）；`aiv/pipeline/requirements.txt` → `video/pipeline/requirements.txt`；**`name: AIV pipeline` 保留**（品牌） |
| `.github/workflows/site-guard.yml:13` | 注释里的 `aiv-pipeline.yml` → `video-pipeline.yml` |
| `pyrightconfig.json` | extraPaths 里 `"aiv/pipeline"` → `"video/pipeline"` |
| `requirements/aiv.txt` → `requirements/video-pipeline.txt` | `git mv` 改名；首行注释 `aiv/pipeline/pyv` → `video/pipeline/pyv` |
| `requirements/video.txt` → `requirements/video-platforms.txt` | `git mv` 改名（它指「视频号/B 站」，与新目录 `video/`「视频生产线」撞名）；注释里的 `channels/channels`、`bilibili/bilibili` 留到 Task 2 改 |
| `requirements/README.md` | 表格：`aiv.txt` → `video-pipeline.txt`、`video.txt` → `video-platforms.txt`、`weixin.txt` → `wechat.txt`（Task 2 改）；「用哪份」表里的模块路径 |
| `tools/build-video-pages.py` | `AIV_ROOT = REPO_ROOT / "aiv"` → `REPO_ROOT / "video"` |
| `tools/sync-hexo.py` | 注释里的 `aiv/voice/README.md` |

- [ ] **Step 8: 把 `docs/life/aiv/` 的副本重新同步一遍**

`video/*.md`（人格规范、形象与音色规范、背景音乐规范）是 `docs/life/aiv/` 的源，
Step 4 改了源文件，副本要跟上：

```bash
python3 video/scripts/sync_publish_docs.py
```

Expected: 打印若干行「已同步 → docs/life/aiv/…」；`git status` 里 `docs/life/aiv/` 下有改动。

- [ ] **Step 9: 跑测试**

```bash
cd video/pipeline && python3 -m pytest tests/ -q && cd -
python3 -m pytest tests/ -q
python3 -m pytest publish/tests -q
```

Expected: 全绿。`video/pipeline` 期望 1267 passed / 14 skipped；仓库根期望 507 passed / 8 skipped（比迁移前多 2 条新守卫）。

- [ ] **Step 10: 确认 URL 命名空间与站点链接没被误伤**

```bash
git grep -n 'docs/life/video/' -- . ; echo "退出码 $?（1 = 没有命中，好）"
find docs/life/aiv -type f | wc -l   # 必须是 9
git grep -n 'life/aiv' -- data/learning-path.json   # 三条正则必须原样
python3 -m pytest tests/test_podcast_spec.py -q -k "life_aiv"
```

Expected: 三条 `learning-path.json` 正则一字未改；两条守卫 PASS。

- [ ] **Step 11: 提交**

```bash
git add -A
git commit -m "refactor(video): 视频生产线改名 aiv/ → video/，路径引用全量跟上"
```

---

### Task 2: 五个平台收进 `platforms/` 并压平

**Files:**
- Move: `weixin/` → `platforms/wechat/`（内层 `weixin/wechat/*.py` 压到 `platforms/wechat/`）
- Move: `toutiao/` → `platforms/toutiao/`、`douyin/` → `platforms/douyin/`、`bilibili/` → `platforms/bilibili/`、`channels/` → `platforms/channels/`（同理）
- Modify: `publish/publishkit/cli.py::invoke_adapter`（cwd）
- Modify: `publish/capabilities/*.toml` 的 `[adapter]` 段（5 个文件）
- Modify: `platforms/<plat>/tests/conftest.py`（5 个：sys.path 与 `parents[2]` → `parents[3]`）
- Modify: 深度变了的其余文件（Step 3 的表：`platforms/{bilibili,channels,douyin}/cli.py`、`platforms/wechat/{cli,assets}.py`、`platforms/<plat>/tests/*.py` 里另外 5 个、`platforms/wechat/tools/*.py` 里 3 个、`platforms/wechat/tests/test_portability.py`）
- Modify: `platforms/channels/tests/test_package.py`（钉死路径字符串的那条断言）
- Modify: `platforms/wechat/deploy/launchd.plist.template` + `platforms/wechat/tests/test_launchd.py`
- Modify: `browser/browser/cli.py`（三个默认路径）
- Modify: `ruff.toml`、`pyrightconfig.json`
- Modify: `.github/workflows/contracts.yml`（三个 pytest 路径 + requirements 路径）
- Modify: `requirements/weixin.txt` → `requirements/wechat.txt`、`requirements/README.md`
- Test: `platforms/<plat>/tests/`、`browser/tests/`、`publish/tests/`

**Interfaces:**
- Consumes: Task 1 的 `video/`。
- Produces: `platforms/<plat>/` 是 Python 包 `<plat>`（`platforms/` 在 `sys.path` 上）；`publishkit.invoke_adapter` 的子进程 cwd 是 `<repo>/platforms`；五个能力声明的 `[adapter] package` = 平台 id。

- [ ] **Step 1: 写下「包名 = 平台 id」的守卫（此时应红）**

在 `publish/tests/test_real_declarations.py` 末尾加：

```python
def test_every_platform_is_importable_under_its_own_name():
    """平台目录名 = Python 包名 = 平台 id。

    压平之后 `platforms/<plat>/` 本身就是那个包，`python3 -m <plat>.cli`
    靠 cwd 在 sys.path 里找到它——目录名和包名必须是同一个词。
    """
    platforms = REPO_ROOT / "platforms"
    assert platforms.is_dir(), "platforms/ 不存在"
    for plat in ("wechat", "toutiao", "douyin", "bilibili", "channels"):
        package = platforms / plat
        assert package.is_dir(), f"platforms/{plat}/ 不存在"
        assert (package / "__init__.py").is_file(), f"platforms/{plat}/ 缺 __init__.py"
        result = subprocess.run(
            [sys.executable, "-c", f"import {plat}.cli"],
            cwd=str(platforms), capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"import {plat}.cli 失败：{result.stderr.strip()}")
```

该文件需要 `import subprocess` 与 `import sys`（没有就加）。

Run: `python3 -m pytest publish/tests/test_real_declarations.py::test_every_platform_is_importable_under_its_own_name -v`
Expected: FAIL（`platforms/` 不存在）。

- [ ] **Step 2: 搬目录并压平**

```bash
mkdir -p platforms
for plat in wechat toutiao douyin bilibili channels; do
  case $plat in
    wechat) old=weixin ;;
    *) old=$plat ;;
  esac
  git mv "$old" "platforms/$plat"
  inner="platforms/$plat/$plat"
  if [ -d "$inner" ]; then
    git mv "$inner"/*.py "platforms/$plat/"
    rmdir "$inner" 2>/dev/null || true
  fi
done
```

微信的内层包名本来就是 `wechat`（`weixin/wechat/`），压平后 `platforms/wechat/` 里是
`__init__.py cli.py capability.py …`——**包名仍是 `wechat`，测试里的 `from wechat import …`
不用改**。这正是设计稿 D7 选 `wechat` 而不是 `weixin` 的原因。

- [ ] **Step 3: 改 sys.path 与目录深度**

**搬家改了两处深度，两处方向相反：**

| 变化 | 哪些文件 | 后果 |
| --- | --- | --- |
| **内层包压平**（`weixin/wechat/x.py` → `platforms/wechat/x.py`） | 五个平台的内层包 | 层级数不变（`<plat>/<plat>/x.py` → `platforms/<plat>/x.py`），但 `parents[1]` 从「包目录」变成了「`platforms/`」 |
| **`tests/` `tools/` 下沉一层**（`weixin/tests/x.py` → `platforms/wechat/tests/x.py`） | 五个平台的 `tests/` 与 `tools/` | `parents[2]` 从「仓库根」变成了「`platforms/`」 |

**要改的（逐个文件核对，不要批量 sed）：**

| 文件（搬完后的路径） | 现状 | 改成 |
| --- | --- | --- |
| `platforms/{bilibili,channels,douyin}/cli.py` | `DEFAULT_OUT = Path(__file__).resolve().parents[1] / "out"` | `parents[0] / "out"` |
| `platforms/wechat/assets.py` | `SVG_CACHE_DIR = Path(__file__).resolve().parents[1] / "out" / "svg"` | `parents[0] / "out" / "svg"` |
| `platforms/wechat/cli.py` | `DEFAULT_OUT_DIR` `DEFAULT_SECRETS_FILE` `DEFAULT_COLLECTIONS_FILE` `DEFAULT_STAMP_FILE` `DEFAULT_COVER` 全是 `parents[1]` | 全部 `parents[0]` |
| `platforms/{wechat,toutiao,douyin,bilibili,channels}/tests/conftest.py` | `REPO_ROOT = Path(__file__).resolve().parents[2]` | `parents[3]` |
| `platforms/bilibili/tests/test_package.py` | `Path(__file__).resolve().parents[2] / "publish" / "capabilities" / "bilibili.toml"` | `parents[3]` |
| `platforms/toutiao/tests/test_measured_limits.py`、`test_render.py` | `parents[2]` | `parents[3]` |
| `platforms/wechat/tests/test_audit.py` | `parents[2]` | `parents[3]` |
| `platforms/douyin/tests/test_end_to_end.py` | `AIV_ROOT = Path(__file__).resolve().parents[2] / "aiv"` | `parents[3] / "video"`（Task 1 已把 `aiv` 换成 `video`） |
| `platforms/wechat/tools/measure-brand.py`、`measure-length.py`、`prune-empty-drafts.py` | `ROOT = Path(__file__).resolve().parents[2]` | `parents[3]` |
| `platforms/wechat/tests/test_portability.py` | `PACKAGE = Path(__file__).resolve().parents[1] / "wechat"` | `parents[1]`（内层包没了） |

**不要改的（深度没变）：**

- 五个平台内层包里所有 `parents[2]`——`weixin/wechat/x.py` 与 `platforms/wechat/x.py` 层级数一样，仓库根还在 `parents[2]`。
- `platforms/<plat>/tests/test_cli.py` 的 `parents[1]`（仍是平台目录）。
- `platforms/wechat/tests/test_launchd.py` 的 `parents[1] / "deploy" / ...`。
- `platforms/wechat/tools/check-drafts.py` 的 `parents[1]`。

**conftest 的 sys.path 也要改**（五个都一样）：

```python
REPO_ROOT = Path(__file__).resolve().parents[3]      # 原来 parents[2]（仓库根）→ 现在 parents[3]
if str(REPO_ROOT / "platforms") not in sys.path:      # 原来 REPO_ROOT / "<plat>"
    sys.path.insert(0, str(REPO_ROOT / "platforms"))
```

`douyin` `bilibili` `channels` 三个 conftest 里还有 `REPO_ROOT / "video" / "pipeline"`
（Task 1 已改好），保留。

**同时把 Task 1 Step 6 留的半条断言补上**：`video/pipeline/tests/test_character.py` 里
`assert (repo_root / "platforms").is_dir()` 现在可以加回去了。

- [ ] **Step 3b: 改那些钉死了路径的断言**

**① `platforms/channels/tests/test_package.py` 里写死了仓库相对路径的那条：**

```python
    target = package.REPO_ROOT / "channels" / "out" / "ep01"
    assert package.repo_relative(target) == "channels/out/ep01"
```

`repo_relative` 算的是**相对仓库根的真路径**，目录一挪它就变：

```python
    target = package.REPO_ROOT / "platforms" / "channels" / "out" / "ep01"
    assert package.repo_relative(target) == "platforms/channels/out/ep01"
```

同文件里 `package_dir="channels/out/ep01"` 那个入参（写进快照的测试数据）也一并改成
`"platforms/channels/out/ep01"`——它是**测试数据**不是历史快照，改了才对。
`platforms/bilibili/tests/test_package.py` 里 `package_dir="bilibili/out/ep02"` 同理。

**② `publish/tests/test_real_declarations.py` 里那两条找 adapter 目录的：**

压平前 adapter 的包目录是 `REPO_ROOT / <plat>`（`weixin/wechat/`、`toutiao/toutiao/`…），
压平后是 `REPO_ROOT / "platforms" / <plat>`。所以：

```python
def test_every_declaration_points_at_an_adapter_that_exists():
    for capability in CAPABILITIES:
        package = capability.adapter_package
        assert package, f"{capability.id} 的能力声明没有 [adapter].package"

        directory = REPO_ROOT / "platforms" / package
        assert directory.is_dir(), (
            f"{capability.id} 指向的 adapter 目录不存在：{directory}"
        )


def test_every_adapter_command_names_a_module_that_exists():
    """命令是 ``python3 -m <模块>``，模块要真的在那个目录里。"""
    for capability in CAPABILITIES:
        command = capability.adapter_command
        assert command, f"{capability.id} 的能力声明没有 [adapter].command"

        module = command[-1].split(".")[0]
        directory = REPO_ROOT / "platforms" / capability.adapter_package
        candidates = [
            directory / "__init__.py",        # 压平后包目录就是 platforms/<plat>/
            directory / (module + ".py"),
        ]
        assert any(path.is_file() for path in candidates), (
            f"{capability.id} 的命令 {' '.join(command)} 指向的模块不在 {directory} 里"
        )
```

> **注意区别**：测试里的**期望值**要跟着改（它算的是真路径），
> 而 `publish/outbox/` 里 567 个快照的 `package_dir` 是**历史记录，一个字都不改**
> （全局约束）。

- [ ] **Step 3c: 加一条深度守卫**

在 `publish/tests/test_real_declarations.py` 里（Step 1 那条守卫旁边）加：

```python
def test_the_platform_dirs_keep_the_repo_root_at_the_right_depth():
    """搬家改了两处深度：内层包压平（−1 层）、tests/tools 下沉（+1 层）。

    「仓库根在哪一层」是这些目录里所有相对路径的地基——钉住它，
    免得以后再被悄悄挪走一层，而症状要等到出包时才炸。
    """
    repo_root = REPO_ROOT.resolve()
    for plat in ("wechat", "toutiao", "douyin", "bilibili", "channels"):
        package = (REPO_ROOT / "platforms" / plat).resolve()
        assert package.parents[1] == repo_root, f"platforms/{plat}/ 的仓库根深度变了"
        for sub in ("tests", "tools"):
            directory = package / sub
            if directory.is_dir():
                assert directory.parents[2] == repo_root, (
                    f"platforms/{plat}/{sub}/ 的仓库根深度变了")
```

- [ ] **Step 4: 能力声明的 `[adapter]` 段**

`publish/capabilities/<plat>.toml` 末尾的 `[adapter]` 段改成：

```toml
[adapter]
package = "<plat>"
command = ["python3", "-m", "<plat>.cli"]
```

五个平台：`wechat`（原 `package = "weixin"` / `command = ["python3","-m","wechat.cli"]`，
上面那段解释 cwd 的注释也要改写）、`toutiao`、`douyin`、`bilibili`、`channels`。

- [ ] **Step 5: 契约层调 adapter 的 cwd**

`publish/publishkit/cli.py::invoke_adapter`：

```python
    working_dir = config.repo_root / "platforms"
    if not (working_dir / package).is_dir():
        raise ScheduleConfigError(
            "adapter 的包目录不存在：{}（能力声明 {} 写的 package 是 {!r}）".format(
                working_dir / package, capability.id, package
            )
        )
```

同时把该函数 docstring 里「cwd 必须是 `<仓库>/<adapter 包名>`」改成
「cwd 必须是 `<仓库>/platforms`——`python3 -m <包名>.cli` 靠 cwd 在 `sys.path` 里找到它」。

- [ ] **Step 6: 写死 cwd 的守卫测试**

在 `publish/tests/test_schedule.py` 加：

```python
def test_the_adapter_runs_inside_the_platforms_directory(monkeypatch):
    """压平后包在 platforms/<plat>/ 下，子进程的 cwd 必须是 platforms/。"""
    captured = {}

    def fake_run(argv, cwd=None, env=None, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    # 用仓库里真实的 toutiao 能力声明与真实的 resolve_config()，只换掉 subprocess.run
    config = resolve_config(repo_root=REPO_ROOT)
    capability = load_capability("toutiao",
                                  capabilities_dir=REPO_ROOT / "publish" / "capabilities")
    cli.invoke_adapter(config, capability, "some-content-id", 300)
    assert captured["cwd"] == str(REPO_ROOT / "platforms")
    assert captured["argv"][:3] == ["python3", "-m", "toutiao.cli"]
```

> `invoke_adapter` 的真实签名是 `invoke_adapter(config, capability, content_id: str, timeout: float)`——
> `content_id` 是**单独一个字符串参数**，不是列表；`publish` 这个词是函数自己拼进 argv 的
> （`argv = command + ["publish", content_id]`）。

`REPO_ROOT`、`cli`、`resolve_config`、`load_capability`、`subprocess` 的 import 按该文件现有写法补
（Task 3 会把 `capabilities_dir` 改名成 `platforms_dir`，那时一并改这个测试）。

- [ ] **Step 7: 公众号的 launchd 模板与它的守卫**

`platforms/wechat/deploy/launchd.plist.template`：

- `WorkingDirectory`：`__REPO__/weixin` → `__REPO__/platforms`
- `PYTHONPATH`：`__REPO__/weixin` → `__REPO__/platforms`
- `ProgramArguments` 里的 `-m wechat.cli` **不变**（包名仍是 wechat）

`platforms/wechat/tests/test_launchd.py`：

```python
def test_the_job_runs_inside_the_platforms_directory():
    config = _load()
    assert config["WorkingDirectory"].endswith("/platforms")
    assert config["EnvironmentVariables"]["PYTHONPATH"].endswith("/platforms")
```

（原函数名是 `test_the_job_runs_inside_the_weixin_package`。）

- [ ] **Step 8: browser 的默认路径**

`browser/browser/cli.py`：

```python
DEFAULT_PACKAGES = REPO_ROOT / "platforms" / "channels" / "out"
DEFAULT_BILIBILI_PACKAGES = REPO_ROOT / "platforms" / "bilibili" / "out"
DEFAULT_TOUTIAO_PACKAGES = REPO_ROOT / "platforms" / "toutiao" / "out"
```

`DEFAULT_OUTBOX` 留到 Task 4（那时才知道 outbox 放哪）。

- [ ] **Step 9: 替换五个平台目录的路径引用**

**五个目录都搬了家**——`weixin/` `toutiao/` `douyin/` `bilibili/` `channels/` 全部收进
`platforms/`，所以要改的不只是 `weixin/`。用与 Task 1 Step 4 同一形状的脚本，规则换成：

| 形式 | 处置 |
| --- | --- |
| `weixin/wechat/…` | → `platforms/wechat/…`（内层包压平了） |
| 其余 `weixin/…`（`weixin/docs/`、`weixin/tests/`、`weixin/tools/`、`weixin/secrets.json`…） | → `platforms/wechat/…` |
| `toutiao/toutiao/…` `douyin/douyin/…` `bilibili/bilibili/…` `channels/channels/…` | → `platforms/<plat>/…`（内层包压平了） |
| 其余 `toutiao/…` `douyin/…` `bilibili/…` `channels/…` | → `platforms/<plat>/…` |
| `weixin.qq.com` / `weixin.jpg` / `weixin_39033058` | **不动**（官方域名、图片、外部链接） |

**两条排除，比 Task 1 多一条：**

1. 历史计划 + `docs/blog/重构方案.md` + 本设计稿与本计划稿——与 Task 1 相同。
2. **`publish/outbox/` 整个目录——567 个快照的正文一个字都不改**（全局约束）。
   快照里的 `"package_dir": "toutiao/out/…"` 是**当时的发布记录**，目录搬走了它就过时，
   但历史不改写。

```bash
python3 - <<'PY'
import pathlib, re

ROOT = pathlib.Path(".")
EXCLUDE = (
    "publish/plans/",
    "review/plans/",
    "review/specs/2026-11-17-directory-architecture-design.md",
    "review/plans/2026-11-17-directory-architecture-plan.md",
    "video/review/plans/",
    "video/pipeline/plans/",
    "docs/blog/重构方案.md",
    "publish/outbox/",               # 567 个快照的正文不改（全局约束）
)

# 目录名 = 平台 id；微信的老目录名是 weixin，包名却是 wechat
PLATFORMS = (
    ("weixin", "wechat"),
    ("toutiao", "toutiao"),
    ("douyin", "douyin"),
    ("bilibili", "bilibili"),
    ("channels", "channels"),
)

changed = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or "/.git/" in f"/{path}":
        continue
    rel = path.as_posix()
    if rel.startswith(EXCLUDE):
        continue
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    new = original
    for old, plat in PLATFORMS:
        # 一遍吃掉两种形式：<old>/<plat>/ 与 <old>/。
        # **必须单遍**——分成两条正则的话，第一遍产出的 platforms/<plat>/
        # 会被第二遍再套一层，变成 platforms/platforms/<plat>/。
        new = re.sub(rf"(?<!platforms/){re.escape(old)}/(?:{re.escape(plat)}/)?",
                     f"platforms/{plat}/", new)
    if new != original:
        path.write_text(new, encoding="utf-8")
        changed.append(rel)
print(f"改了 {len(changed)} 个文件")
PY
```

> **`publish/outbox/` 被排除**——脚本跑完必须核对：
> `git diff --stat -- publish/outbox/` 必须是空的，567 个快照一个字节都没动。

**剩下的独立 `weixin` 词**逐条判断：

| 位置 | 现状 | 改成 |
| --- | --- | --- |
| `requirements/weixin.txt` | 文件名 | `git mv requirements/weixin.txt requirements/wechat.txt`（本 task 一并改） |
| `.github/workflows/contracts.yml:56` | `-r requirements/weixin.txt` | `-r requirements/wechat.txt` |
| `publish/spec/00-架构设计.md:731` | `REPO_ROOT/'weixin'` | `REPO_ROOT/'platforms'` |
| `video/pipeline/pyv/character.py` | 注释「与 `weixin/` 同级」 | 「与 `platforms/` 同级」（Task 1 Step 5 已改） |

- [ ] **Step 10: 改 CI 的 pytest 路径**

`.github/workflows/contracts.yml`：

```yaml
      - name: Toutiao adapter tests
        run: python3 -m pytest platforms/toutiao/tests -q

      - name: Weixin adapter tests
        run: python3 -m pytest platforms/wechat/tests -q
```

文件里的注释「视频线（aiv）不在这里」→ 「视频线（video）不在这里」。

- [ ] **Step 11: lint 与类型配置**

| 文件 | 改什么 |
| --- | --- |
| `ruff.toml` | `"weixin/tools/*.py"` → `"platforms/wechat/tools/*.py"` |
| `pyrightconfig.json` | extraPaths：删掉 `weixin` `toutiao` `channels` `bilibili` 四条，加 `"platforms"` 一条（`publish` `browser` `video/pipeline` 保留） |

- [ ] **Step 12: 跑测试**

```bash
for plat in wechat toutiao douyin bilibili channels; do
  python3 -m pytest "platforms/$plat/tests" -q
done
python3 -m pytest browser/tests -q
python3 -m pytest publish/tests -q
python3 -m pytest tests/ -q
cd video/pipeline && python3 -m pytest tests/ -q && cd -
```

Expected: 全绿，含 Task 2 Step 1 那条守卫（现在 PASS）。

- [ ] **Step 13: 真跑一次 adapter 调用（五个平台各一次）**

```bash
cd platforms
for plat in wechat toutiao douyin bilibili channels; do
  python3 -c "import $plat.cli" && echo "$plat ok"
done
cd -
```

Expected: 五个 `ok`。这是「压平后 `-m` 还找得到包」的真实验证。

- [ ] **Step 14: 提交**

```bash
git add -A
git commit -m "refactor(platforms): 五个平台收进 platforms/ 并压平，目录名即平台 id"
```

---

### Task 3: 能力声明下沉到 `platforms/<plat>/capability.toml`

**Files:**
- Move: `publish/capabilities/wechat.toml` → `platforms/wechat/capability.toml`（其余四个同理）
- Modify: `publish/publishkit/capability.py`（`default_capabilities_dir` / `load_capability` / `list_capabilities` / `available_platforms`）
- Modify: `publish/publishkit/cli.py`（`--capabilities-dir` → `--platforms-dir`）
- Modify: `publish/publishkit/schedule.py`（`ScheduleConfig.capabilities_dir` → `platforms_dir`；`discover_repo_root` 的锚点）
- Modify: `video/pipeline/pyv/epmeta.py`（`CAPABILITIES_DIR`、`load_limits`）
- Modify: `video/pipeline/pyv/preflight.py`（`_load_media`、`check_video`）
- Modify: `platforms/toutiao/capability.py::default_capability_path`
- Modify: `platforms/bilibili/package.py::_bilibili_limits_loader`
- Modify: `platforms/douyin/contract.py`（docstring 里的路径）
- Modify: `platforms/bilibili/tests/test_package.py`（真实 toml 的路径）
- Modify: `publish/tests/test_schedule.py`（Task 2 Step 6 那个测试的 `capabilities_dir=` 关键字）
- Test: `publish/tests/`、`video/pipeline/tests/`、`platforms/*/tests/`

**Interfaces:**
- Consumes: Task 2 的 `platforms/<plat>/`。
- Produces: `publishkit.default_platforms_dir() -> Path`（`<repo>/platforms`）；
  `load_capability(platform_id, *, platforms_dir=None) -> Capability`；
  `list_capabilities(*, platforms_dir=None) -> list[Capability]`；
  `available_platforms(*, platforms_dir=None) -> list[str]`；
  `epmeta.load_limits(platform, platforms_dir=None) -> dict`；
  `preflight.check_video(info, platform, platforms_dir=None) -> list[Finding]`。

- [ ] **Step 1: 先钉住「目录名 == 文件里的 id」这条不变量**

在 `publish/tests/test_real_declarations.py` 加：

```python
def test_every_platform_directory_is_named_after_its_id():
    """平台目录名 = 能力声明里的 id = Python 包名。"""
    platforms = REPO_ROOT / "platforms"
    for directory in sorted(p for p in platforms.iterdir() if p.is_dir()):
        declaration = directory / "capability.toml"
        assert declaration.is_file(), f"{directory.name}/ 缺 capability.toml"
        data = tomllib.loads(declaration.read_text(encoding="utf-8"))
        assert data["id"] == directory.name, (
            f"{directory.name}/ 的能力声明里 id 是 {data['id']!r}，两者必须一致")
```

该文件若还没 `import tomllib` 就加上。

- [ ] **Step 2: 改契约层的能力模型**

`publish/publishkit/capability.py`：

```python
def default_platforms_dir() -> Path:
    """平台目录（``<仓库>/platforms/``）——每个平台一个子目录。"""
    return Path(__file__).resolve().parents[2] / "platforms"


def load_capability(platform_id: str, *, platforms_dir=None) -> Capability:
    ...
    directory = Path(platforms_dir) if platforms_dir is not None else default_platforms_dir()
    path = directory / platform_id / "capability.toml"
    ...


def list_capabilities(*, platforms_dir=None) -> list:
    ...
    directory = Path(platforms_dir) if platforms_dir is not None else default_platforms_dir()
    if not directory.is_dir():
        return []
    capabilities = [
        load_capability_file(path)
        for path in sorted(directory.glob("*/capability.toml"))
    ]
    return sorted(capabilities, key=lambda cap: cap.id)
```

`available_platforms()` 跟着把关键字参数改成 `platforms_dir`。
`default_capabilities_dir` **删掉**（不留旧名——留着就会有人继续用旧路径）。
模块头 docstring 里的「读 `publish/capabilities/<platform>.toml`」也要改。

**`__all__` 里那一项也要换**——`capability.py:87` 写着 `"default_capabilities_dir"`，
改成 `"default_platforms_dir"`（留着旧名，`from publishkit import *` 照样能拿到旧函数）。

- [ ] **Step 3: 改配置与命令行**

`publish/publishkit/schedule.py`：

- `ScheduleConfig` 的 `capabilities_dir: Path` 字段改成 `platforms_dir: Path`。
- `resolve_config(..., platforms_dir=None, ...)`；默认值 `root / "platforms"`。
- `discover_repo_root()` 的锚点从「含 `publish/capabilities` 的那一层」改成
  「含 `publish/publishkit` 的那一层」——能力声明散了，原锚点失效了。
- **`schedule.py:466` 那条报错信息里的路径拼法也要改**：
  `config.capabilities_dir / "{}.toml".format(platform_filter)` 指的是
  「一个目录下的一个 toml 文件」，现在文件在平台目录里，得改成
  `config.platforms_dir / platform_filter / "capability.toml"`。

`publish/publishkit/cli.py`：

- `--capabilities-dir` 改名 `--platforms-dir`，help 改成「平台目录（默认：`<仓库>/platforms`）」。
- `resolve_config(..., platforms_dir=getattr(args, "platforms_dir", None), ...)`。
- 内部所有 `capabilities_dir=` 关键字改 `platforms_dir=`（含 Task 2 Step 6 那个测试）。

- [ ] **Step 4: 搬能力声明文件**

```bash
for plat in wechat toutiao douyin bilibili channels; do
  git mv "publish/capabilities/$plat.toml" "platforms/$plat/capability.toml"
done
rmdir publish/capabilities
```

- [ ] **Step 5: 改能力声明里的路径注释**

五个 toml 的注释里写着旧路径（`platforms/wechat/docs/03-试点记录.md`、
`platforms/wechat/posts.py`、`platforms/toutiao/docs/02-试点记录.md` 等）——
Task 2 Step 9 的脚本已经改过一遍；这里只需人工确认没有漏的，
特别是 `wechat.toml` 顶部那段提到 `weixin/docs/03-试点记录.md`、
`weixin/wechat/posts.py`、`weixin/README.md`、`weixin/docs/06-超长文章拆分.md` 的注释。

- [ ] **Step 6: 改视频线的读侧**

`video/pipeline/pyv/epmeta.py`：

```python
PLATFORMS_DIR = REPO_ROOT / "platforms"


def load_limits(platform: str, platforms_dir: Path | None = None) -> dict:
    """读平台能力声明的 [limits] 段。"""
    base = Path(platforms_dir) if platforms_dir else PLATFORMS_DIR
    path = base / platform / "capability.toml"
    if not path.is_file():
        raise MetaError(f"能力声明不存在：{path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data.get("limits", {}) or {}
```

`video/pipeline/pyv/preflight.py` 的 `_load_media` 同样改（`base / platform / "capability.toml"`），
`check_video(info, platform, capabilities_dir=None)` 的参数改名 `platforms_dir`。
**`preflight.py:20` 的 import 也要跟着改**：
`from pyv.epmeta import CAPABILITIES_DIR, Finding, MetaError` → `PLATFORMS_DIR`。

**`REPO_ROOT` 在这两个文件里怎么推的，要保持深度不变**——`aiv/` → `video/` 是同深度，
`Path(__file__).resolve().parents[N]` 的层数不用动。

- [ ] **Step 7: 改平台自己那份读法**

`platforms/toutiao/capability.py`：

```python
def default_capability_path() -> Path:
    """The declaration shipped with the repository."""
    return _REPO_ROOT / "platforms" / "toutiao" / "capability.toml"
```

`_REPO_ROOT = Path(__file__).resolve().parents[2]` **不用改**——压平后深度不变
（`platforms/toutiao/capability.py` 的 `parents[2]` 仍是仓库根）。

`platforms/bilibili/package.py::_bilibili_limits_loader`：参数 `capabilities_dir` 改名
`platforms_dir`，默认值走 `epmeta.load_limits`（Step 6 已改好签名）。

- [ ] **Step 8: 改守卫**

`publish/tests/test_real_declarations.py:57` 那条 `assert capability.path.stem == capability.id`
不再成立（文件名统一叫 `capability.toml`）——删掉它，换成 Step 1 已经加的
`test_every_platform_directory_is_named_after_its_id`。

- [ ] **Step 9: 跑测试**

```bash
python3 -m pytest publish/tests -q
cd video/pipeline && python3 -m pytest tests/ -q && cd -
for plat in wechat toutiao douyin bilibili channels; do python3 -m pytest "platforms/$plat/tests" -q; done
python3 -m pytest tests/ -q
```

Expected: 全绿。

- [ ] **Step 10: 提交**

```bash
git add -A
git commit -m "refactor(capability): 能力声明下沉到 platforms/<plat>/capability.toml"
```

---

### Task 4: 发布快照按平台下沉到 `platforms/<plat>/outbox/`

**Files:**
- Move: `publish/outbox/*.json` → `platforms/<plat>/outbox/`（按 `__<plat>` 后缀分流，567 个）
- Modify: `publish/publishkit/schedule.py`（`outbox_dir` → `outbox_root` + `outbox_dir_for()`；`load_outbox_index`；`secrets_file` 默认路径）
- Modify: `publish/publishkit/cli.py`（`--outbox-dir` → `--outbox-root`；写快照；读索引的 5 处；`PUBLISH_OUTBOX_DIR`；help 文本）
- Modify: `publish/publishkit/contract.py`、`publish/publishkit/episode.py`（docstring 里的 outbox 路径）
- Modify: `tools/build-publish-index.py`（`OUTBOX_DIR` → 扫 `platforms/*/outbox/`）
- Modify: `tools/build-video-pages.py`（同上）
- Modify: `browser/browser/cli.py`（`DEFAULT_OUTBOX`）
- Modify: `platforms/wechat/snapshot.py`（`OUTBOX_DIR`）
- Modify: `platforms/toutiao/tests/conftest.py`、`platforms/douyin/tests/conftest.py`（outbox 路径）
- Modify: `publish/tests/test_schedule.py`（`REPO_OUTBOX`）
- Test: `publish/tests/`、`platforms/*/tests/`、`tests/`

**Interfaces:**
- Consumes: Task 3 的 `platforms/<plat>/`。
- Produces: `ScheduleConfig.outbox_root: Path`（默认 `<repo>/platforms`）；
  `ScheduleConfig.outbox_dir_for(platform: str) -> Path`（`<root>/<platform>/outbox`）；
  `publishkit.load_outbox_index(outbox_root) -> OutboxIndex`（**扫 `<root>/*/outbox/*.json`**）。

- [ ] **Step 1: 先写「读侧不能漏」的守卫**

加在 `publish/tests/test_schedule.py`：

```python
def test_the_real_outbox_index_finds_every_snapshot():
    """真实仓库里的 567 条快照必须一条不落地被索引到。

    这是「读侧漏改」的唯一防线：outbox 分平台之后，任何还在扫单一
    目录的读者都会把已发过的内容看成没发过——于是重复发布。
    """
    index = load_outbox_index(REPO_ROOT / "platforms")
    assert len(index.records) == 567, f"索引到 {len(index.records)} 条快照，应为 567"
    assert not index.errors, f"有快照读不出来：{index.errors}"
```

`REPO_ROOT` 与 `load_outbox_index` 按该文件现有 import 补。

Run: `python3 -m pytest publish/tests/test_schedule.py::test_the_real_outbox_index_finds_every_snapshot -v`
Expected: FAIL（`load_outbox_index` 现在只扫一个目录，索引到 0 条）。

- [ ] **Step 2: 搬快照**

```bash
mkdir -p platforms/toutiao/outbox platforms/bilibili/outbox platforms/channels/outbox platforms/douyin/outbox platforms/wechat/outbox
for f in publish/outbox/*.json; do
  plat="${f##*__}"; plat="${plat%.json}"
  git mv "$f" "platforms/$plat/outbox/$(basename "$f")"
done
rmdir publish/outbox
```

文件名**一个字都不改**（`git mv` 保留原名）。`__wechat` 的快照是 0 个——
公众号还没走过发布流水线，`platforms/wechat/outbox/` 会是空目录，
空目录 git 不跟踪，用 `.gitkeep` 占位（`platforms/wechat/outbox/.gitkeep`）。

- [ ] **Step 3: 改契约层的配置与索引**

`publish/publishkit/schedule.py`：

```python
@dataclass(frozen=True)
class ScheduleConfig:
    repo_root: Path
    posts_dir: Path
    outbox_root: Path
    state_dir: Path
    schedule_file: Path
    platforms_dir: Path
    secrets_file: Path

    def outbox_dir_for(self, platform: str) -> Path:
        """某个平台的快照目录：``<outbox_root>/<platform>/outbox``。"""
        return self.outbox_root / platform / "outbox"
```

`resolve_config`：参数 `outbox_dir` 改名 `outbox_root`，默认值 `root / "platforms"`
（**不再跟 state 目录走**——outbox 现在住在平台目录里，而且它是入库的发布记录）。

`load_outbox_index(outbox_root)` 改成扫子目录：

```python
def load_outbox_index(outbox_root) -> OutboxIndex:
    """扫描平台目录下的 outbox 建索引。

    每个平台的快照住在 ``<root>/<platform>/outbox/``；这里把五个目录
    一起扫了——**读侧漏一个目录，就等于把已发过的内容当成没发过**。
    """
    root = Path(outbox_root)
    records = {}
    errors = []
    if not root.is_dir():
        return OutboxIndex(records={}, errors=())
    for directory in sorted(root.glob("*/outbox")):
        for path in sorted(directory.glob("*.json")):
            ...（原来的解析逻辑不变）
```

`schedule.py` 里凭据的默认路径：`root / "weixin" / "secrets.json"` →
`root / "platforms" / "wechat" / "secrets.json"`；
那张环境变量表的 `secrets_file` 一行同步改。

- [ ] **Step 4: 改契约层的命令与写盘**

`publish/publishkit/cli.py`：

| 位置 | 改什么 |
| --- | --- |
| `--outbox-dir` | 改名 `--outbox-root`，help 改成「平台根目录（默认：`<仓库>/platforms`）」 |
| `resolve_config(...)` | `outbox_dir=` → `outbox_root=` |
| `write_snapshot` | `outbox = config.outbox_dir` → `outbox = config.outbox_dir_for(platform)` |
| `environment["PUBLISH_OUTBOX_DIR"]` | `str(config.outbox_dir)` → `str(config.outbox_dir_for(capability.id))`——**每个平台不同** |
| `load_outbox_index(config.outbox_dir)`（5 处） | → `load_outbox_index(config.outbox_root)` |
| 报错文案里的 `config.outbox_dir` | → `config.outbox_dir_for(platform)` |
| `--secrets` 的 help | 「或 `<仓库>/weixin/secrets.json`」→ 「或 `<仓库>/platforms/wechat/secrets.json`」 |

`publish/publishkit/schedule.py` 里 `load_outbox_index(config.outbox_dir)` 的 3 处同上。

`publish/publishkit/contract.py` 与 `publish/publishkit/episode.py` 的 docstring
（`publish/outbox/<EP>__<平台>.json`）→ `platforms/<平台>/outbox/<EP>__<平台>.json`。

- [ ] **Step 5: 改两个站点工具（静默失败的两个）**

`tools/build-publish-index.py`：

```python
PLATFORMS_DIR = REPO_ROOT / "platforms"


def read_outbox():
    """Every publish snapshot, keyed by content_id."""
    records = {}
    if not PLATFORMS_DIR.is_dir():
        return records
    for directory in sorted(PLATFORMS_DIR.glob("*/outbox")):
        for path in sorted(directory.glob("*.json")):
            ...（原来的解析逻辑不变）
```

`tools/build-video-pages.py` 的 `read_outbox()` 同样改；它的 `OUTBOX_DIR` 常量改成
`PLATFORMS_DIR = REPO_ROOT / "platforms"`。

**这两个工具的测试把 outbox 路径 monkeypatch 成临时目录**——所以路径写错时测试照样绿。
必须补一条对**真实仓库**的断言（Review Focus 第 5 条）：

```python
def test_read_outbox_finds_the_real_snapshots():
    records = read_outbox()
    assert sum(len(v) for v in records.values()) == 567
```

放在各自已有的测试文件里（`tools/` 下的测试在哪就放哪；若没有，
放到 `tests/test_publish_visibility.py` 里——它已经在测发布相关的东西）。

- [ ] **Step 6: 改 browser 与平台自己的快照模块**

| 位置 | 改什么 |
| --- | --- |
| `browser/browser/cli.py` | `DEFAULT_OUTBOX = REPO_ROOT / "platforms"`（它是根，调用方按平台扫子目录） |
| `platforms/wechat/snapshot.py` | `OUTBOX_DIR = Path(__file__).resolve().parents[2] / "platforms" / "wechat" / "outbox"` |
| `platforms/toutiao/tests/conftest.py` | `OUTBOX_DIR = REPO_ROOT / "platforms" / "toutiao" / "outbox"` |
| `platforms/douyin/tests/conftest.py` | `repo_outbox = REPO_ROOT / "platforms" / "douyin" / "outbox"` |
| `platforms/wechat/tests/test_snapshot.py` | 断言 outbox 目录名的用例改成 `"wechat"` |

- [ ] **Step 7: 改 publish 测试里的真实仓库路径**

`publish/tests/test_schedule.py`：

```python
REPO_OUTBOX = REPO_ROOT / "platforms"
```

并把该文件里断言 `config.outbox_dir == root / "publish" / "outbox"` 的两处改成
`config.outbox_root == root / "platforms"`。

- [ ] **Step 8: 跑测试**

```bash
python3 -m pytest publish/tests -q
for plat in wechat toutiao douyin bilibili channels; do python3 -m pytest "platforms/$plat/tests" -q; done
python3 -m pytest browser/tests -q
python3 -m pytest tests/ -q
```

Expected: 全绿，且 Task 4 Step 1 那条守卫现在是 PASS（567 条）。

- [ ] **Step 9: 真跑一次站点构建与调度器（测试查不出来的那一步）**

```bash
python3 tools/build-publish-index.py
python3 tools/build-video-pages.py
PYTHONPATH=publish python3 -m publishkit.cli schedule status > /tmp/after-status.txt
PYTHONPATH=publish python3 -m publishkit.cli schedule candidates > /tmp/after-candidates.txt
diff /tmp/baseline/status.txt /tmp/after-status.txt && echo "status 一致"
diff /tmp/baseline/candidates.txt /tmp/after-candidates.txt && echo "candidates 一致"
```

Expected: 两个 diff 都为空——**「已发过（567）」一字不变**。
若不一致，说明读侧漏改，回去查 `load_outbox_index`。

- [ ] **Step 10: 提交**

```bash
git add -A
git commit -m "refactor(outbox): 发布快照按平台下沉到 platforms/<plat>/outbox/"
```

---

### Task 5: 草稿箱 `drafts/`

**Files:**
- Create: `drafts/README.md`
- Modify: `review/README.md`（指向草稿箱的流程说明）
- Test: `tests/test_podcast_spec.py`（加一条守卫）

**Interfaces:**
- Consumes: Task 1–4 的目录结构。
- Produces: `drafts/` 目录 + `drafts/README.md`（流程约定的唯一出处）。

- [ ] **Step 1: 先写守卫**

在 `tests/test_podcast_spec.py` 加：

```python
def test_the_draft_box_exists_and_says_how_it_works():
    """草稿箱是两条流水线的共同入口，它的约定必须写在仓库里。"""
    readme = REPO_ROOT / "drafts" / "README.md"
    assert readme.is_file(), "drafts/README.md 不见了"
    text = readme.read_text(encoding="utf-8")
    for keyword in ("drafts/", "review/", "docs/", "video/", "platforms/"):
        assert keyword in text, f"草稿箱的约定里没提到 {keyword}"
```

Run: `python3 -m pytest tests/test_podcast_spec.py::test_the_draft_box_exists_and_says_how_it_works -v`
Expected: FAIL（`drafts/` 不存在）。

- [ ] **Step 2: 写 `drafts/README.md`**

内容按设计稿 §4.9，并且**必须写清楚「底稿不参与派生」**：

```markdown
# 草稿箱

新写的稿子先落这里，审完也留着。它是两条流水线的共同入口。

## 流程

1. 新写的稿子放 `drafts/`，文件名带日期与主题。
2. 过总审核：文章看 `review/`，视频稿看 `video/review/` 的口径要求。
3. 通过后**复制**一份进 `docs/`（站点文章）或 `video/`（视频母稿）。
4. 底稿留在 `drafts/`，**不再参与任何派生**。
5. 平台版由 `platforms/<plat>/` 各自出包，落在 `platforms/<plat>/outbox/`。

## 底稿不进派生

真相只在 `docs/`。草稿箱留的是同一份内容的历史副本，不是第二个产地——
下游的一切都从 `docs/` 的母稿重建。留底稿是为了看出「当初交上去的是什么、
审校改了什么」，不是为了让稿子有两个地方可以改。
```

- [ ] **Step 3: 在 `review/README.md` 加一句指路**

`review/README.md` 开头加一行：「新的稿子先落 `drafts/`，审完复制进 `docs/`；
本目录存审校记录与复盘。」

- [ ] **Step 4: 跑测试**

```bash
python3 -m pytest tests/ -q
```

Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(drafts): 建草稿箱，写清两条流水线的共同入口与底稿约定"
```

---

### Task 6: 文档跟上 + 回写 `docs/platform-meta/`

**Files:**
- Modify: `README.md`（§2 架构、§2.3 视频生产线、平台表、目录表）
- Modify: `publish/spec/*.md`（活的规格里的路径引用）
- Modify: `publish/deploy/crontab.template`、`publish/deploy/launchd.plist.template`、`publish/deploy/github-action.yml.template`（凭据路径）
- Modify: `review/README.md`、`review/specs/`（路径引用）
- Modify: `platforms/<plat>/docs/`（各平台自己的活文档）
- Modify: `tests/test_episode_block.py`、`tests/test_podcast_spec.py`
- Modify: `docs/db/_index.md`（讲仓库布局的那一行）
- Modify: `review/plans/2026-11-17-内容分类与结构重构.md`（上游计划里指向公众号转换规则的那 2 行）
- Modify: `docs/platform-meta/platform-overview/one-repo-three-pipelines.md`（旧路径 → 新路径）
- Create: `docs/platform-meta/platform-overview/two-pipelines-one-draft-box.md`（新文章）
- Modify: `docs/platform-meta/platform-overview/_index.md`（文章列表）
- Modify: `docs/platform-meta/multiplatform/_index.md`、`docs/platform-meta/video-line/_index.md`（W4）
- Test: `tests/test_podcast_spec.py`、`tests/test_learning_path.py`

**Interfaces:**
- Consumes: Task 1–5 的最终目录结构。
- Produces: 站点上关于仓库自身的文章与仓库实际结构一致。

- [ ] **Step 1: 先让守卫红起来**

`tests/test_podcast_spec.py` 的 `REPO_TOP_DIRS` 更新成新的顶层目录集合：

```python
REPO_TOP_DIRS = {
    "browser", "drafts", "platforms", "public", "publish", "review",
    "scripts", "source", "tests", "themes", "tools", "video",
}
```

（去掉 `aiv` 与五个旧平台名，加上 `drafts` `platforms` `video`。）
同时把 `PLANNED_PATHS` 里所有 `aiv/…` 改成 `video/…`（Task 1 Step 4 已经改过）。

Run: `python3 -m pytest tests/test_podcast_spec.py -q`
Expected: **FAIL**——规格文档里还写着旧路径，守卫会把它们判成「仓库里不存在的路径」。

- [ ] **Step 2: 改 `publish/spec/*.md` 里的路径引用**

`publish/spec/00-架构设计.md`（§2 架构图、§5 能力模型、§8 平台规格、附录）、
`06-发布计划与调度.md`（凭据路径）、`07-视频发布契约.md`、`08-站点IP骨架.md`、
`09-长视频三档.md` 里的 `aiv/` `weixin/` `toutiao/` 等路径 → 改成新路径。

**注意**：`publish/spec/` 是活的规格，`tests/test_podcast_spec.py`
会逐条核对里面写的仓库路径是否存在，所以改漏一条就红一条。

- [ ] **Step 3: 改根 `README.md`**

§2 的四层架构表、§2.3 的视频生产线、平台适配层那五个目录、目录清单表、
「AIV 视频（cd aiv/pipeline）」的命令示例、`aiv-pipeline.yml` 的表格行——
全部按新结构改。平台适配层那一行写成 `platforms/`（每个平台一个目录）。

- [ ] **Step 4: 改部署模板**

| 模板 | 改什么 |
| --- | --- |
| `publish/deploy/crontab.template` | `PUBLISH_SECRETS=__REPO__/weixin/secrets.json` → `__REPO__/platforms/wechat/secrets.json`。`cd __REPO__/publish` 与 `PYTHONPATH=__REPO__/publish` **不变**（publishkit 还住 `publish/`） |
| `publish/deploy/launchd.plist.template` | 同上一条；`WorkingDirectory` = `__REPO__/publish` 不变 |
| `publish/deploy/github-action.yml.template` | `PUBLISH_SECRETS: ${{ github.workspace }}/weixin/secrets.json` → `.../platforms/wechat/secrets.json` |

`publish/tests/test_trigger_templates.py:84` 的断言
`env["PUBLISH_SECRETS"].endswith("/weixin/secrets.json")` 改成
`endswith("/platforms/wechat/secrets.json")`。

- [ ] **Step 5: 改平台自己的活文档与剩余引用**

| 位置 | 改什么 |
| --- | --- |
| `platforms/<plat>/docs/*.md` | 里面指向 `weixin/` `toutiao/` `aiv/` 的路径 |
| `platforms/wechat/docs/03-试点记录.md` 等 | 同上 |
| `tests/test_episode_block.py` | `row["subtitle"] == "aiv/字幕-行锁.md"`（Task 1 Step 4 已改）；注释里的 `aiv/字幕-*.md` 已改 |
| `docs/db/_index.md:23` | 那行讲「视频与自媒体生产线专题……与 `weixin/` 同级」的路径引用 → 改成 `video/` 与 `platforms/` |
| `review/README.md` | 路径引用 |
| `review/specs/2026-11-13-content-review-design.md` | 若有路径引用则改；**本次的目录架构设计稿不改**（它描述的就是这次迁移） |

- [ ] **Step 6: 上游计划里那一处指向真实文件的路径**

`review/plans/2026-11-17-内容分类与结构重构.md` 第 305、470 行指向
`weixin/docs/01-转换规则.md`——那是**上游正在执行的活计划**，路径改了它就指空，
所以这两行单独改。其余历史计划一律不动（Global Constraints）。

- [ ] **Step 7: 改站点上那篇讲分层的老文章（W1）**

`docs/platform-meta/platform-overview/one-repo-three-pipelines.md`：

| 位置 | 改什么 |
| --- | --- |
| mermaid 图第 55 行 | `D --> C["aiv/contracts/ 视觉分镜契约"]` → `D --> C["video/contracts/ 视觉分镜契约"]` |
| §三分层表第 90 行 | 视频生产层 `aiv/` → `video/` |
| §三分层表第 92 行 | 平台适配层 `weixin/`、`toutiao/`、`douyin/`、`channels/`、`bilibili/` → `platforms/`（每个平台一个目录） |

**只改路径，不动这篇文章的结论**——三条产线、母稿唯一、依赖单向、
平台之间是复制不是共用，这些都不因目录改名而变。

- [ ] **Step 8: 新写一篇《两条流水线，一个草稿箱》（W2）**

`docs/platform-meta/platform-overview/two-pipelines-one-draft-box.md`，front matter 照现有三篇的形状：

```yaml
---
description: "仓库现在有两条流水线：文档流从草稿箱到站点与文本平台，视频流从草稿箱到成片再到视频平台。为什么这么分，草稿箱是什么，两条审核线怎么分工。"
tldr: "草稿箱是两条流水线的共同入口；真相只在 docs/；草稿箱留底稿但不参与派生；平台按平台划分，加平台只动 platforms/。"
difficulty: 2
---
```

正文按现有文章的形状写：开头一张「编写人 / 编写时间 / 适用版本」的表，
然后一节的表 + mermaid 图 + 逐条说明。至少讲清四件事：

1. **两条流水线**：文档流（`drafts/` → 总审核 → `docs/` + 文本平台）、
   视频流（`drafts/` → 总审核 → `video/` → 成片审核 → 视频平台）。
   两条线正交于分发层。
2. **目录分层**：为什么视频独立成 `video/`，为什么五个平台收进 `platforms/`
   并压平（目录名 = 平台 id = 包名），为什么能力声明与发布快照跟着平台走。
3. **两条审核线**：总审核在 `review/` 与 `video/review/`，平台审核在 `platforms/<plat>/` 内。
4. **草稿箱**：它是入口也是底稿，**但不参与派生**——真相只在 `docs/`。

**写法照现有三篇**：讲「为什么这么设计」而不是「怎么改」，不写成提交记录。

- [ ] **Step 9: 把新文章加进系列索引（W3）**

`docs/platform-meta/platform-overview/_index.md` 的「本系列文章」加一行：

```markdown
- [两条流水线，一个草稿箱](./two-pipelines-one-draft-box.md) — 目录架构本身：
  草稿箱是什么、两条流水线怎么分、平台为什么按平台划分
```

- [ ] **Step 10: 改两个尚未成稿系列里的旧路径（W4）**

`docs/platform-meta/multiplatform/_index.md` 与 `docs/platform-meta/video-line/_index.md`
里如果提到「能力声明住在 `publish/capabilities/`」「视觉分镜契约住在 `aiv/contracts/`」，
改成 `platforms/<plat>/capability.toml` 与 `video/contracts/`。

- [ ] **Step 11: 跑站点链路与测试**

```bash
python3 tools/sync-hexo.py
python3 -m pytest tests/ -q
```

Expected: 全绿。`tests/test_learning_path.py` 必须绿——新文章落在
`platform-meta/platform-overview/` 的已有前缀规则上，不需要改
`data/learning-path.json`，但守卫会检查「没有文章靠 fallback 兜底」。

- [ ] **Step 12: 确认文章真能上站**

```bash
ls source/_posts/platform-meta/platform-overview/
```

Expected: 两篇都在（老的 + 新的）。

- [ ] **Step 13: 提交**

```bash
git add -A
git commit -m "docs(platform-meta): 回写目录架构——改旧文章的分层表，新写《两条流水线，一个草稿箱》"
```

---

### Task 7: 全量验收

**Files:**
- 无新文件；只跑检查。

**Interfaces:**
- Consumes: Task 1–6 的全部结果。
- Produces: 一条干净的验收记录。

- [ ] **Step 1: 全量测试**

```bash
cd video/pipeline && python3 -m pytest tests/ -q && cd -
python3 -m pytest tests/ -q
python3 -m pytest publish/tests -q
for plat in wechat toutiao douyin bilibili channels; do python3 -m pytest "platforms/$plat/tests" -q; done
python3 -m pytest browser/tests -q
```

Expected: 全绿，无 skip 异常（skip 的条数应与迁移前一致）。

- [ ] **Step 2: 契约层能列出五个平台**

```bash
PYTHONPATH=publish python3 -m publishkit.cli --help | grep platforms-dir
```

Expected: 出现 `--platforms-dir 路径`（不再是 `--capabilities-dir`）。

- [ ] **Step 3: 兜底 grep（应为空）**

```bash
git grep -n 'publish/outbox\|publish/capabilities' -- . ; echo "退出码 $?（1 = 干净）"
git grep -n '"weixin/"\|weixin/secrets\|/weixin$' -- . ; echo "退出码 $?（1 = 干净）"
git grep -n -P '(?<!life/)aiv/' -- . | grep -v 'plans/\|directory-architecture-' ; echo "退出码 $?（1 = 干净）"
```

第三条的白名单：`plans/` 下的历史计划、本设计稿与本计划稿、以及
`docs/` 里那 8 处指向 `life/aiv/` 专题页的站点链接（它们前面是 `./` 或 `../`，
正则的 `(?<!life/)` 拦不住——所以这里用排除法核对）。

**逐条人工看第三条的输出**，确认剩下的每一处都是「有意保留」。

- [ ] **Step 4: 确认旧目录真的没了**

```bash
ls -d aiv weixin toutiao douyin bilibili channels publish/outbox publish/capabilities 2>&1
```

Expected: 全部报「No such file or directory」。

- [ ] **Step 5: 确认快照一条不少、名字没变**

```bash
find platforms/*/outbox -name '*.json' | wc -l   # 必须是 567
git diff --stat HEAD~5 -- 'publish/outbox' | tail -3
```

Expected: 567；diff 里只有删除行、没有新增行（说明是纯粹的重命名）。

- [ ] **Step 6: 与基线比对**

```bash
diff /tmp/baseline/status.txt /tmp/after-status.txt && echo "发布历史一致"
diff /tmp/baseline/candidates.txt /tmp/after-candidates.txt && echo "候选集一致"
python3 tools/build-publish-index.py
python3 -c "
import json; d=json.load(open('source/_data/publish_index.json'))
print(len(d['articles']), len(d['videos']))"   # 应与 /tmp/baseline/publish-index.txt 相同
```

- [ ] **Step 7: 站点构建真跑一次**

```bash
python3 tools/sync-hexo.py
python3 tools/build-publish-index.py
python3 tools/build-video-pages.py
```

Expected: 无异常，索引里 567 条。

- [ ] **Step 8: 把结果告诉用户**

汇报：全量测试结果、三个兜底 grep 的结果、快照条数与改名情况、
以及**仓库外那件用户要自己做的事**——本机 Mac 上已装的
`~/Library/LaunchAgents/com.growdu.publish.schedule.plist` 仍写着旧的
`PUBLISH_SECRETS` 路径与旧的仓库绝对路径，仓库里改模板不会自动更新它，
需要 unload/load 一次；服务器上的 crontab 同理。

---

## 实施记录

*（执行时在这里记：与设计稿冲突的地方、改了设计稿的哪一条、跳过的步骤及原因。）*

已定的三个判断（执行时不必再想，但要在「实施记录」里确认落地）：

1. **标识符里的 AIV 保留**——`AIV_ROOT` 等 170 处常量不改名，只改它们指向的目录路径。
2. **`requirements/` 的文件名跟着模块走**——`aiv.txt` → `video-pipeline.txt`、
   `video.txt`（视频号/B 站）→ `video-platforms.txt`、`weixin.txt` → `wechat.txt`。
3. **历史计划与试点记录不改路径引用**——它们是当时的快照；唯一例外是
   `review/plans/2026-11-17-内容分类与结构重构.md` 里指向真实文件的那 2 行。
