"""共享 URL 规则的守卫：**形状只有一份**。

**生产方与校验方都不许写死**：站点源码（`src/`）与站点测试（`tests/`）里
都不许出现文档前缀、视频前缀的字面量——它们都得从规则文件里取。
（校验方自己写一份期望地址，改规则就得改四处——那不叫「一份」。）
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
    """站点里该受管的文件：生产方（src/）与校验方（tests/）。"""
    out: list[Path] = []
    for sub in ("src", "tests"):
        out.extend(sorted((SITE / sub).rglob("*")))
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
    offenders = _scan_site(r"""['"`]/docs/""", {".astro", ".ts", ".mjs", ".css", ".py"})
    assert not offenders, f"这些地方写死了 '/docs/'：{offenders}"


def test_the_python_url_producers_do_not_hardcode_the_doc_prefix():
    offenders = []
    for rel in ("publish/publishkit/urls.py", "tools/url_rules.py",
                "platforms/blog/cli.py", "platforms/blog/site/tools/build-activity.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if re.search(r"""['"]/docs/""", text):
            offenders.append(rel)
    assert not offenders, f"这些地方写死了 '/docs/'：{offenders}"


def test_the_site_source_does_not_hardcode_the_video_prefix():
    """视频前缀也一样：站点不许自己写死，得从规则里取。

    （这是上面那条守卫的另一半——brief 里只点了文档前缀，
    视频前缀是同一条缝的另一半。）
    """
    offenders = _scan_site(r"""['"`]/videos/""", {".astro", ".ts", ".mjs", ".css", ".py"})
    assert not offenders, f"这些地方写死了 '/videos/'：{offenders}"


def test_the_site_json_content_hrefs_match_the_shared_rules():
    """`site.json` 里指向文档/视频的 href，必须等于规则算出来的地址。

    **规则管的是「id → 地址」的形状，管不到路由**——站点的真实路由来自
    Astro 的文件路由（`src/pages/docs/`、`src/pages/videos/`）与
    `site.json` 的导航。所以改了前缀要**连带**改这两处：
    改了规则却忘了改导航，链接会指向一个没有路由的地址，
    而报错出现在链接检查上，很难一眼看出是规则改了。

    这条守卫盯的就是「改了前缀却忘了改导航」。
    """
    data = json.loads((SITE / "data" / "site.json").read_text(encoding="utf-8"))
    shape = rules()
    prefixes = {"videos": "video_prefix", "docs": "doc_prefix"}

    checked = 0
    for item in data.get("nav") or []:
        key = item.get("key")
        prefix_key = prefixes.get(key)
        if prefix_key is None:
            continue  # 不是内容空间的导航项（学习流、时间轴……是站点自己的路由）
        checked += 1
        assert item.get("href") == shape[prefix_key], (
            f"site.json 里的 {key} 入口指向 {item.get('href')!r}，"
            f"规则算出来的是 {shape[prefix_key]!r}——改前缀要连带改导航"
        )
    assert checked > 0, "site.json 里一个内容空间的导航项都没有，这条守卫是空的"
