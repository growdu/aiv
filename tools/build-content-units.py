#!/usr/bin/env python3
"""docs/ → content/units/：把已过审的母稿编译成**平台无关的内容单元**。

这一层是内容流的上游编译步骤，也是所有平台共用的那一半：
公众号、头条号、抖音、B 站、站点，读的都是 `content/units/` 里的内容单元，
不是 `docs/` 里的母稿。

**契约**

- 输入：`docs/` 下的目录文档（只有已过审的才在 `docs/` 里）。
- 输出：`content/units/` 下**同构**的一份（`docs/source-tracks/a/b.md`
  → `content/units/source-tracks/a/b.md`）。
- 图片也进内容单元仓库：`docs/` 下的图片按 **docs 相对路径**拷进
  `content/units/images/`（`docs/a/b.png` → `content/units/images/a/b.png`）。
  于是正文里的一张图落在 ``图片根/单元目录/正文里的相对路径``——
  站点与两个 adapter 共用这一条规则。
  ⚠️ `images/` 是**保留名**：`docs/images/` 这一层不编译成内容单元
  （那一层是图片仓库的位置），发现里面有稿子会**往 stderr 说一声**。
- 内容单元 = 一篇 markdown + 一份 front matter。front matter 由母稿的
  front matter、目录链上的 `_index.md`、以及 git 历史推导出来。

**规矩（重要）**

1. **正文一个字都不许改**。这一层只做 front matter 的推导与**拷贝**。
   链接重写、图片重写、围栏语言归一化统统是渲染层的事（见站点侧 remark 插件）。
   旧站点的 `rewrite_images` / `rewrite_links` 是无视围栏的全局正则，
   会改到代码块里的内容——那套做法不许带过来。
2. **不许在这里发明分类**。分类只存在于目录里：一级目录 = 分类，
   二级目录 = 系列，一篇文档 = 一期（见 `review/specs/2026-11-18-目录即接口与分类增设.md`）。
3. **不许静默失败**。母稿缺 front matter 里的必需字段、目录链断了，
   都是错误，不是「留空继续」。

用法：

    python3 tools/build-content-units.py            # 编译
    python3 tools/build-content-units.py --check    # 只检查（幂等性 + 完整性）
    python3 tools/build-content-units.py --only <id>  # 只编一篇（只读，出一段 JSON）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from paths import CONTENT_UNITS as _CONTENT_UNITS, DOCS as _DOCS, IMAGE_EXTENSIONS  # noqa: E402

#: 母稿目录——**模块级全局**（根套件 `tests/test_content_units.py`
#: 的夹具用 `monkeypatch.setattr(module, "DOCS", ...)` 换掉它，
#: 所以读取必须发生在**导入时**，不许改成「在函数里现读环境变量」）。
#:
#: 测试可以指到别处去（跟 ``VIDEO_CONFIG`` 一个路子）：给了 ``AIV_DOCS``
#: 就用它，**没给就用仓库默认的**（默认行为一个字都不许变）。
DOCS = Path(os.environ["AIV_DOCS"]) if os.environ.get("AIV_DOCS") else _DOCS

#: 内容单元仓库——同上，``AIV_CONTENT_UNITS`` 覆盖它。
CONTENT_UNITS = (
    Path(os.environ["AIV_CONTENT_UNITS"])
    if os.environ.get("AIV_CONTENT_UNITS")
    else _CONTENT_UNITS
)

#: 母稿 front matter 里属于「期号」的字段——**母稿里唯一往下搬的一组**。
#: 不在表里的字段不往下传：避免母稿随手写个字段就污染所有平台。
#:
#: **必须与契约层 publish/publishkit/contract.py 的 EPISODE_SCALAR_FIELDS +
#: EPISODE_LIST_FIELDS 一致**——tests/test_content_units.py 钉住这条。
#:
#: 期号字段以前**不在**透传表里，于是被静默丢掉：页面照常渲染，
#: 期号区块是空的。母稿与内容单元之间的「期号」这一条通道是断的。
EPISODE_FIELDS = ("episode", "episode_no", "series", "episode_hook",
                  "episode_subtitle", "episode_duration_s", "episode_license",
                  "episode_sources", "episode_repro")

#: 编译器**自己推导**、不照抄母稿的字段。母稿写了这些字段也不直接算数：
#: title 可从 H1 来、description 可从正文第一段来、date 可从 git 历史来、
#: tags 要并上目录链上的。
BASE_FIELDS = ("title", "date", "author", "description", "tags", "top", "draft")

#: 目录链上的分类名取自各级 `_index.md` 的 `cascade.categories`。
CASCADE_KEY = "cascade"

#: 图片仓库占住的名字——``docs/`` 下这一层**不编译**成内容单元。
#:
#: 编译器把 ``docs/`` 的树镜像进 ``content/units/``，图片仓库就在
#: ``content/units/images/``。用户要是建一个叫 ``images`` 的分类目录，
#: **不跳过它**的话，那一层的内容单元会在同一轮编译里被 ``copy_images()``
#: 连锅端——**源文件还在，产物没了**。
#:
#: 正是为了不发生这件事，这一层才成了**保留名**：编译时跳过 + 清残留时跳过，
#: **两处都跳**。（跟 ``video/`` **不一样**——那个名字不是保留名，
#: 见 :data:`RESERVED_UNIT_DIRS`。）
IMAGES_DIR = "images"

#: **清残留时跳过**的顶层名字。
#:
#: - ``images``：**保留名**——它是**图片仓库**占着这个名字
#:   （``content/units/images/``）。编译时跳过 + 清残留时跳过，**两处都跳**。
#: - ``video``：**不是保留名**——它只是**另一个生产者**
#:   （``tools/build-video-pages.py``）的产物占着那个名字，
#:   所以**只有清残留时跳过**；**编译时照编**
#:   （``docs/video/x.md`` 今天照样编译成 ``content/units/video/x.md``）。
#:
#: 用户在 ``docs/`` 下建同名分类，内容单元会跟产物撞在同一层。
RESERVED_UNIT_DIRS = {"video", IMAGES_DIR}

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class CompileError(Exception):
    """母稿编译不过。带文件与行号，指向具体那一份稿子。"""


@dataclass
class Unit:
    """一个内容单元：正文 + front matter。"""

    path: Path  # 相对 content/units/ 的路径
    title: str
    date: str
    author: str
    description: str
    kind: str  # document | category
    categories: list[str] = field(default_factory=list)
    # 分类**名**（`categories`）对应的分类内容单元 **id**，与 `categories` 同序同长。
    # 平台层要的是分类页的**地址**，地址由 id 推导（如 `source-tracks/_index`），
    # 展示名推不出来——所以这层映射由编译器算出来写进去。
    category_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    extra: dict = field(default_factory=dict)


def split_front_matter(text: str) -> tuple[dict, str]:
    """拆出 front matter 与正文。正文原样返回，一个字都不动。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 4 :]
    body = body.lstrip("\n")
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise CompileError(f"front matter 不是合法 YAML：{exc}") from exc
    if not isinstance(fm, dict):
        raise CompileError("front matter 不是键值映射")
    return fm, body


def git_date(rel_path: Path) -> str:
    """取这篇稿子**最早一次提交**的时间。

    站点上的日期用的是「这篇内容什么时候开始写的」，不是最后一次改的时间。
    `git log` 倒着取第一行。`%ai` 带时区偏移，这里**只留墙钟时间**——
    旧站点踩过一个坑：带 `+0800` 的时间被 hexo 当 UTC 又折算一次，
    日期会莫名往前跳一天（见 `review/specs/ops/架构.md`）。
    """
    proc = subprocess.run(
        ["git", "log", "--format=%ai", "--follow", "--", str(rel_path)],
        cwd=DOCS.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return ""
    return lines[-1][:19]


def first_h1(body: str) -> str:
    m = H1_RE.search(body)
    return m.group(1).strip() if m else ""


def first_paragraph(body: str) -> str:
    """正文里第一段不是标题、不是表格、不是引用的文字。"""
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith(("#", ">", "|", "```", "---", "* ", "- ")):
            continue
        return re.sub(r"\s+", " ", block).strip()
    return ""


def ancestors(rel: Path) -> list[Path]:
    """从顶层到紧邻父级的 `_index.md` 列表。

    `docs/source-tracks/postgresql/getting-started/x.md`
    → `[source-tracks/_index.md, source-tracks/postgresql/_index.md,
       source-tracks/postgresql/getting-started/_index.md]`
    """
    out: list[Path] = []
    parts = rel.parts[:-1]
    for i in range(len(parts)):
        out.append(Path(*parts[: i + 1]) / "_index.md")
    return out


def read_index_chain(rel: Path) -> tuple[list[str], list[str], list[str]]:
    """走一遍目录链，收集分类链与标签链。

    分类链来自各级 `_index.md` 的 `cascade.categories`（一级目录 = 分类，
    二级 = 系列……）；标签链来自各级 `_index.md` 的 `tags`。

    同时收**分类内容单元 id**：某个分类名是**哪一级** `_index.md` 报出来的，
    就配那一级的 id（`docs/a/_index.md` → `a/_index`）。
    名字与 id **一起去重**——上级报过的名字不再重复报，id 也不跟着多一条，
    否则两个列表会错位（名字 2 个、id 3 个）。
    """
    categories: list[str] = []
    category_ids: list[str] = []
    tags: list[str] = []
    for idx in ancestors(rel):
        idx_path = DOCS / idx
        if not idx_path.exists():
            raise CompileError(
                f"目录链断了：{rel} 的上级 {idx} 没有 _index.md"
            )
        fm, _ = split_front_matter(idx_path.read_text(encoding="utf-8"))
        cascade = fm.get(CASCADE_KEY) or {}
        # 祖先自己的内容单元 id：路径去掉 `.md`（`a/_index.md` → `a/_index`）。
        idx_id = idx.as_posix().removesuffix(".md")
        for name in cascade.get("categories") or []:
            if name not in categories:
                categories.append(name)
                category_ids.append(idx_id)
        for tag in fm.get("tags") or []:
            if tag not in tags:
                tags.append(tag)
    return categories, category_ids, tags


def build_unit(path: Path) -> Unit:
    rel = path.relative_to(DOCS)
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)

    is_index = path.name == "_index.md"
    title = (fm.get("title") or "").strip()
    if not title:
        title = first_h1(body)
    if not title:
        raise CompileError(f"{rel} 没有标题（front matter 里没有 title，正文也没有 H1）")

    description = (fm.get("description") or "").strip()
    if not description:
        description = first_paragraph(body)
    if not description:
        raise CompileError(f"{rel} 没有描述（front matter 里没有 description，正文里也找不到第一段）")

    categories, category_ids, tags = read_index_chain(rel)
    for tag in fm.get("tags") or []:
        if tag not in tags:
            tags.append(tag)

    date = fm.get("date")
    if isinstance(date, str) and date.strip():
        date = date.strip()
    else:
        date = git_date(path)
    if not date:
        raise CompileError(f"{rel} 找不到日期（front matter 里没有 date，git 里也查不到历史）")

    # 母稿里多出来的字段按白名单搬进 `extra`。白名单**只有期号字段**——
    # 母稿随手写的别的字段不往下传。
    #
    # 空的值**不搬**：`episode_sources: []` 落盘后，契约层的扁平解析器把
    # `[]` 读成**字符串** `'[]'`（空值读成 `'null'`），然后报
    # 「episode_sources 必须是列表」。空的就当「没有这个字段」，
    # 让契约层看到**缺省**，而不是看到坏形状。
    extra: dict = {}
    for key in EPISODE_FIELDS:
        if key not in fm:
            continue
        if key in BASE_FIELDS:
            # ⚠️ **防御性不变量**，不是过滤器：今天
            # ``EPISODE_FIELDS ∩ BASE_FIELDS = ∅``，这一句**永不触发**。
            # 它守的是「编译器自己推导的那几个字段，母稿写了也不算数」这条规则——
            # 万一将来有人往两个元组里加了同一个名字，它会挡住。
            # （不许删：删了将来就没人守这条了。）
            continue
        value = fm[key]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        extra[key] = value

    return Unit(
        path=rel,
        title=title,
        date=str(date),
        author=str(fm.get("author") or "growdu"),
        description=description,
        kind="category" if is_index else "document",
        categories=categories,
        category_ids=category_ids,
        tags=tags,
        body=body,
        extra=extra,
    )


def one_line(value: str) -> str:
    """把多行标量压成**一行**：连续的空白（含换行）折成一个空格，首尾去掉。

    契约层的 front matter 解析器是**扁平**的：只读每个键的**首行**。
    编译器一旦产出多行标量（母稿写 ``description: |`` 时就是），契约层
    只读到第一行 → 描述被截成半句（跟 safe_dump 的 ``width`` 无关）。

    ⚠️ 只折 **ASCII 空白**（空格 / 制表符 / 回车 / 换行）。Python 的 ``\\s``
    对 str 模式匹配的是 **Unicode 空白**，会把中文稿里的全角空格（U+3000）
    和 NBSP（U+00A0）换成半角空格——那是**字面失真**，中文稿里全角空格常用来
    做缩进与对齐。折行的目的是「压成一行」，不是「改空白字符」。
    首尾的 ``.strip()`` 保持不变（首尾空白本来就该剥）。
    """
    return re.sub(r"[ \t\r\n]+", " ", value).strip()


def flatten(value):
    """把 front matter 的值压成单行形态。

    字符串压成一行；列表里的**字符串元素**同样压；数字、布尔等非字符串
    原样（它们本来就是单行的）。
    """
    if isinstance(value, str):
        return one_line(value)
    if isinstance(value, list):
        return [one_line(v) if isinstance(v, str) else v for v in value]
    return value


def render(unit: Unit) -> str:
    """把内容单元写成 markdown + front matter。正文原样。"""
    fm: dict = {
        "title": unit.title,
        "date": unit.date,
        "author": unit.author,
        "description": unit.description,
        "kind": unit.kind,
        "categories": unit.categories,
        "category_ids": unit.category_ids,
        "tags": unit.tags,
        "source_path": unit.path.as_posix(),
    }
    for key, value in unit.extra.items():
        fm[key] = value

    # 全部压成单行：契约层只读每个键的首行，多行标量它读不全。
    fm = {key: flatten(value) for key, value in fm.items()}

    # `width=4096`：**不折行**。PyYAML 默认按 80 列折长标量，续行是缩进的
    # 标量——契约层的扁平 front matter 解析器只读首行，于是 `description`
    # 被截成半句（契约层 parse_front_matter 的 docstring 里记着这个坑）。
    head = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False,
        width=4096,
    ).rstrip("\n")
    return f"---\n{head}\n---\n\n{unit.body.lstrip()}\n"


def compile_units() -> list[Unit]:
    units: list[Unit] = []
    for path in sorted(DOCS.rglob("*.md")):
        if path.relative_to(DOCS).parts[0] == IMAGES_DIR:
            continue  # images/ 是图片仓库的位置——保留名，不编译
        units.append(build_unit(path))
    _warn_images_dir()
    return units


def _warn_images_dir() -> None:
    """``docs/images/`` 下有稿子就说一声——静悄悄吃掉一个分类最难查。

    那一层不编译成内容单元（``images/`` 是图片仓库的位置），所以用户
    建的分类**不会**变成页面。悄悄吃掉一个分类是最难查的那种问题：
    稿子还在，页面没了，人只会去怀疑编译器。
    """
    layer = DOCS / IMAGES_DIR
    if not layer.is_dir():
        return
    if not any(layer.rglob("*.md")):
        return
    print(
        "警告：docs/images/ 这一层不编译成内容单元——`images/` 是图片仓库的位置"
        "（content/units/images/）。那一层的稿子请挪到别的目录。",
        file=sys.stderr,
    )


def _source_images() -> dict[Path, Path]:
    """``docs/`` 下的图片：相对路径 → 源文件。

    只有后缀在 :data:`IMAGE_EXTENSIONS` 里的才算图片——markdown、json
    这些不是图片，不该被拷进图片仓库。
    """
    out: dict[Path, Path] = {}
    if not DOCS.is_dir():
        return out
    for path in sorted(DOCS.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            out[path.relative_to(DOCS)] = path
    return out


def _copied_images() -> dict[Path, Path]:
    """``content/units/images/`` 下已有的图片：相对路径 → 文件。"""
    root = CONTENT_UNITS / "images"
    out: dict[Path, Path] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root)] = path
    return out


def copy_images() -> None:
    """把 ``docs/`` 下的图片复制进 ``content/units/images/``。

    图片按 **docs 相对路径**落盘——它跟内容单元是同构的：
    ``docs/db/pg/a.png`` → ``content/units/images/db/pg/a.png``。
    于是正文里的一张图落在 ``图片根/单元目录/正文里的相对路径``，
    站点与两个 adapter 用的都是这一条规则。

    **先删后拷**：上一轮的图留在那儿，下一轮就发出去了。
    清理只碰 ``content/units/images/``——内容单元（含视频单元）不在里面。

    ⚠️ 这里用的是**编译器模块的** ``CONTENT_UNITS``（模块级全局），
    **不是** ``paths.CONTENT_UNIT_IMAGES``：后者在 import 时算死成真仓库的
    绝对路径，用它会把图拷进真的仓库（既写脏仓库，又让用例必红）。
    """
    root = CONTENT_UNITS / "images"
    if root.exists():
        shutil.rmtree(root)
    for rel, source in _source_images().items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def image_problems() -> list[str]:
    """图片与 ``docs/`` 不同步的地方——``--check`` 用它。

    缺了、多了、字节不一样，都算不同步：图跟内容单元一样是产物，
    不同步就该报出来，而不是悄悄发出去。
    """
    problems: list[str] = []
    source_images = _source_images()
    copied_images = _copied_images()
    root = CONTENT_UNITS / "images"
    for rel, source in sorted(source_images.items()):
        target = root / rel
        if not target.exists():
            problems.append(f"images/{rel.as_posix()}：图片不存在（该跑一次 build-content-units.py）")
        elif target.read_bytes() != source.read_bytes():
            problems.append(f"images/{rel.as_posix()}：图片与 docs/ 不同步")
    for rel in sorted(copied_images):
        if rel not in source_images:
            problems.append(
                f"images/{rel.as_posix()}：图片还在，但 docs/ 里已经没有了（撤出的存量没清干净）"
            )
    return problems


def locate_source(rel_id: str) -> Path:
    """在 `docs/` 里定位一篇稿子。

    `rel_id` 是相对 `docs/` 的路径，带不带 `.md` 都认。三种形态都找：

    | 形态 | 位置 | 内容单元 id |
    | --- | --- | --- |
    | flat 稿 | `docs/<名>.md` | `<名>` |
    | bundle 稿 | `docs/<名>/index.md` | `<名>/index` |
    | 分类页 | `docs/<名>/_index.md` | `<名>/_index` |
    """
    rel = rel_id.strip().lstrip("/")
    if rel.endswith(".md"):
        rel = rel[:-3]
    for candidate in (DOCS / f"{rel}.md", DOCS / rel / "index.md", DOCS / rel / "_index.md"):
        if candidate.is_file():
            return candidate
    raise CompileError(f"docs/ 里找不到这一篇：{rel_id}")


def compile_only(rel_id: str) -> dict:
    """只编译一篇，返回它推导出来的字段。**不动磁盘。**

    给「这一篇能不能进站」这类问题用的——**规则只在这里有一份**，
    平台层（`platforms/blog/cli.py`）问的是这个编译器，不是自己抄一遍规则。
    """
    path = locate_source(rel_id)
    if path.relative_to(DOCS).parts[0] == IMAGES_DIR:
        # ⚠️ 顺序：先 locate_source（找不到就是「找不到这一篇」），再判保留名。
        # 全量编译跳过这一层，--only 也得跳——不然「这一篇能不能进站」会答错。
        raise CompileError(
            "images/ 是保留名（图片仓库的位置），这一层不编译成内容单元：{}".format(rel_id))
    unit = build_unit(path)
    rel = unit.path.as_posix()
    unit_id = rel[:-3] if rel.endswith(".md") else rel
    return {
        "ok": True,
        "unit_id": unit_id,
        "kind": unit.kind,
        "title": unit.title,
        "description": unit.description,
        "date": unit.date,
        "author": unit.author,
        "categories": unit.categories,
        "category_ids": unit.category_ids,
        "tags": unit.tags,
        "source_path": rel,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="把 docs/ 编译成 content/units/")
    ap.add_argument(
        "--check",
        action="store_true",
        help="只检查：编译到内存里，跟磁盘上已有的内容单元比对，不一致就非零退出",
    )
    ap.add_argument(
        "--only",
        metavar="ID",
        help="只编一篇（相对 docs/ 的路径，带不带 .md 都认），只读，出一段 JSON",
    )
    args = ap.parse_args()

    if args.only:
        try:
            result = compile_only(args.only)
        except CompileError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        units = compile_units()
    except CompileError as exc:
        print(f"编译失败：{exc}", file=sys.stderr)
        return 2

    rendered = {u.path: render(u) for u in units}

    if args.check:
        problems = []
        for rel, text in rendered.items():
            target = CONTENT_UNITS / rel
            if not target.exists():
                problems.append(f"{rel}：内容单元不存在（该跑一次 build-content-units.py）")
                continue
            if target.read_text(encoding="utf-8") != text:
                problems.append(f"{rel}：内容单元与 docs/ 不同步")
        for existing in sorted(CONTENT_UNITS.rglob("*.md")):
            rel = existing.relative_to(CONTENT_UNITS)
            if rel.parts and rel.parts[0] in RESERVED_UNIT_DIRS:
                continue  # 清残留时都跳：images/ 是保留名（图片仓库），video/ 是另一个生产者的产物
            if rel not in rendered:
                problems.append(f"{rel}：内容单元还在，但 docs/ 里已经没有了（撤出的存量没清干净）")
        # 图跟内容单元一样是产物——不同步也要报出来
        problems.extend(image_problems())
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print(f"内容单元与 docs/ 一致（{len(rendered)} 篇）")
        return 0

    written = 0
    for rel, text in rendered.items():
        target = CONTENT_UNITS / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            written += 1

    # docs/ 里撤掉但内容单元还在的（除 images/ 与 video/ 这两层），清掉——它们是撤出存量的残留。
    removed = 0
    for existing in sorted(CONTENT_UNITS.rglob("*.md")):
        rel = existing.relative_to(CONTENT_UNITS)
        if rel.parts and rel.parts[0] in RESERVED_UNIT_DIRS:
            continue  # 清残留时都跳：images/ 是保留名（图片仓库），video/ 是另一个生产者的产物
        if rel not in rendered:
            existing.unlink()
            removed += 1
    for d in sorted(CONTENT_UNITS.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    # 图也进内容单元仓库（先删后拷，过期的图不留）
    copy_images()

    print(f"内容单元：{len(rendered)} 篇（写入 {written}，清理残留 {removed}），"
          f"图片 {len(_source_images())} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
