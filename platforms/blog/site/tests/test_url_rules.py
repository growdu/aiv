"""共享 URL 规则的守卫：**形状只有一份**。

**生产方不许写死**：站点工具（`tools/`）与根工具层里都不许出现文档前缀、
视频前缀的字面量——它们都得从规则文件里取。
（校验方（`tests/`）要断言具体地址，所以它自己会写着那个字面量。）
"""
import json
import re
import subprocess
from pathlib import Path

from url_shape import rules

REPO_ROOT = Path(__file__).resolve().parents[4]
RULES = REPO_ROOT / "rules" / "urls.json"
SITE = REPO_ROOT / "platforms/blog/site"

#: 这条守卫自己写着那些字面量（要拿来搜别人），所以它不搜自己。
GUARD_FILE = Path(__file__).resolve()


def _site_sources() -> list[Path]:
    """站点里该受管的文件：生产方（tools/，含带点前缀的 mjs）。"""
    out: list[Path] = []
    for path in sorted((SITE / "tools").rglob("*")):
        out.append(path)
    return out


def _scan_site(pattern: str, suffix_ok: set[str]) -> list[str]:
    """在站点里扫写死了某个前缀的地方（测试文件只看 .py）。"""
    offenders = []
    for path in _site_sources():
        if path.resolve() == GUARD_FILE:
            continue  # 这条守卫自己写着那个字面量
        if path.suffix not in suffix_ok:
            continue
        if "content" in path.relative_to(SITE).parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(pattern, text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    return offenders


def test_the_rules_file_is_tracked_by_git():
    out = subprocess.run(["git", "ls-files", "--error-unmatch", "rules/urls.json"],
                         cwd=REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "rules/urls.json 必须入库——它是一份真相，不是构建产物"


def test_the_rules_file_carries_every_key_the_readers_need():
    data = json.loads(RULES.read_text(encoding="utf-8"))
    for key in ("doc_prefix", "video_prefix", "video_id_prefix", "category_suffix"):
        assert data[key], f"规则里少了 {key}"


def test_the_site_source_does_not_hardcode_the_doc_prefix():
    """站点不许自己写死 '/docs/'——**生产方与校验方都不许**，都得从规则里取。"""
    offenders = _scan_site(r"""['"`]/docs/""", {".mjs", ".css", ".py"})
    assert not offenders, f"这些地方写死了 '/docs/'：{offenders}"


def test_the_python_url_producers_do_not_hardcode_the_doc_prefix():
    offenders = []
    for rel in ("publish/publishkit/urls.py", "tools/url_rules.py",
                "platforms/blog/cli.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if re.search(r"""['"]/docs/""", text):
            offenders.append(rel)
    assert not offenders, f"这些地方写死了 '/docs/'：{offenders}"


def test_the_site_source_does_not_hardcode_the_video_prefix():
    """视频前缀也一样：站点不许自己写死，得从规则里取。

    （这是上面那条守卫的另一半——brief 里只点了文档前缀，
    视频前缀是同一条缝的另一半。）
    """
    offenders = _scan_site(r"""['"`]/videos/""", {".mjs", ".css", ".py"})
    assert not offenders, f"这些地方写死了 '/videos/'：{offenders}"


def test_the_site_json_content_hrefs_match_the_shared_rules():
    """`site.json` 里指向文档/视频的 href，必须等于规则算出来的地址。

    **规则管的是「id → 地址」的形状，管不到路由**——站点的真实路由来自
    `source/_posts/` 的 permalink（由 `tools/build-posts.py` 写），
    导航里的内容空间入口必须指向规则算出来的前缀。

    导航**可以**暂时没有内容空间入口（hexo 版的首页只挂学习流/归档/关于）；
    这时候这条守卫是空的，要明说，不能装作验过了。
    """
    data = json.loads((SITE / "data" / "site.json").read_text(encoding="utf-8"))
    shape = rules()
    prefixes = {"videos": "video_prefix", "docs": "doc_prefix"}

    checked = 0
    for item in data.get("nav") or []:
        href = item.get("href") or ""
        prefix_key = next(
            (k for k, v in prefixes.items() if href.startswith(shape[v])), None
        )
        if prefix_key is None:
            continue  # 不是内容空间的导航项（学习流、时间轴……是站点自己的路由）
        checked += 1
        assert href == shape[prefix_key], (
            f"site.json 里的导航项指向 {href!r}，"
            f"规则算出来的是 {shape[prefix_key]!r}——改前缀要连带改导航"
        )
    if checked == 0:
        print("⚠️ site.json 里没有内容空间的导航项——这条守卫现在是空的")
