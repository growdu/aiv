"""共享 URL 规则的守卫：**形状只有一份**。"""
import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RULES = REPO_ROOT / "rules" / "urls.json"


def test_the_rules_file_is_tracked_by_git():
    out = subprocess.run(["git", "ls-files", "--error-unmatch", "rules/urls.json"],
                         cwd=REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "rules/urls.json 必须入库——它是一份真相，不是构建产物"


def test_the_rules_file_carries_every_key_the_readers_need():
    data = json.loads(RULES.read_text(encoding="utf-8"))
    for key in ("doc_prefix", "video_prefix", "video_id_prefix", "category_suffix"):
        assert data[key], f"规则里少了 {key}"


def test_the_site_source_does_not_hardcode_the_doc_prefix():
    """站点不许自己写死 '/docs/'——它得从规则里取。"""
    offenders = []
    for path in sorted((REPO_ROOT / "platforms/blog/site/src").rglob("*")):
        if path.suffix not in {".astro", ".ts", ".mjs", ".css"}:
            continue
        if "content" in path.relative_to(REPO_ROOT / "platforms/blog/site/src").parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"""['"`]/docs/""", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"这些地方写死了 '/docs/'：{offenders}"


def test_the_python_url_producers_do_not_hardcode_the_doc_prefix():
    offenders = []
    for rel in ("publish/publishkit/urls.py", "tools/rules.py",
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
    offenders = []
    for path in sorted((REPO_ROOT / "platforms/blog/site/src").rglob("*")):
        if path.suffix not in {".astro", ".ts", ".mjs", ".css"}:
            continue
        if "content" in path.relative_to(REPO_ROOT / "platforms/blog/site/src").parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"""['"`]/videos/""", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"这些地方写死了 '/videos/'：{offenders}"
