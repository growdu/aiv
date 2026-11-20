#!/usr/bin/env python3
"""身份注入：`data/site.json` → 站点配置与模板要读的身份数据。

**输入**

- `platforms/blog/site/data/site.json` —— **全仓库唯一的身份源**。
  站名、简介、导航、页脚都在这儿。

**输出**

- `platforms/blog/site/_config.yml` —— hexo 的站点配置（由 `_config.template.yml`
  填身份填出来）。**不入库**：它是生成物。
- `platforms/blog/site/source/_data/site.json` —— 模板读的身份
  （hexo 把 `source/_data/*.json` 挂成 `site.data.*`）。
- `platforms/blog/site/source/about/index.md` —— 关于页。
  正文取 `content/about.md`（没有就按身份字段生成一段）。
- `platforms/blog/site/source/robots.txt` —— 搜索引擎的入口，sitemap 的地址
  得跟着站点地址走，所以它也是生成物。
- `platforms/blog/site/source/manifest.json` —— PWA 清单（站名、简介是身份）。

**规矩**

1. **框架里不许写死身份**。模板读 `site.data.site.*`，一个字都不写死。
2. **导航项可以带 `feature`**：那个功能关着的时候，这一项自动不出现
   （学习流关着 → 导航里没有「学习流」）。
3. **地址不是身份，是部署的事**：`SITE_URL` 环境变量优先，其次 `site.json`
   里的 `url`，都没有就用本地地址。

用法::

    python3 platforms/blog/site/tools/apply-site-config.py
    python3 platforms/blog/site/tools/apply-site-config.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SITE = Path(__file__).resolve().parents[1]
SITE_JSON = SITE / "data" / "site.json"
CONFIG_TEMPLATE = SITE / "_config.template.yml"
CONFIG_OUT = SITE / "_config.yml"
DATA_DIR = SITE / "source" / "_data"
ABOUT_DIR = SITE / "source" / "about"
ABOUT_BODY = SITE / "content" / "about.md"
ROBOTS = SITE / "source" / "robots.txt"
MANIFEST = SITE / "source" / "manifest.json"

#: 身份文件里必须有的字段。少一个就是身份没写全——报错，不猜。
REQUIRED_KEYS = ("name", "tagline", "description", "start_date", "nav", "footer")

#: 没有 `SITE_URL`、也没有 `site.json` 的 `url` 时，用这个。
DEFAULT_URL = "http://localhost:4000"
DEFAULT_LANGUAGE = "zh-CN"


def load_site_json() -> dict:
    """读身份文件，校验必填字段。"""
    if not SITE_JSON.exists():
        print(f"身份文件不存在：{SITE_JSON}", file=sys.stderr)
        raise SystemExit(2)
    try:
        data = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"身份文件不是合法 JSON：{exc}", file=sys.stderr)
        raise SystemExit(2)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        print(f"身份文件缺字段：{'、'.join(missing)}", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(data["nav"], list):
        print("身份文件的 nav 必须是数组", file=sys.stderr)
        raise SystemExit(2)
    return data


def learning_enabled() -> bool:
    """学习流这个模块开着吗。规则表没有、或 `enabled: false` → 关着。"""
    rules_path = SITE / "data" / "learning-path.json"
    if not rules_path.exists():
        return False
    try:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return rules.get("enabled") is not False


def feature_enabled(feature: str | None) -> bool:
    """一个功能开着吗。没写 `feature` 的一律当作常开。"""
    if not feature:
        return True
    if feature == "learning_path":
        return learning_enabled()
    # 认不出来的功能名：当作关着（别给访客看一个点进去什么都没有的入口）。
    return False


def build_nav(site: dict) -> list[dict]:
    """导航项：把关着的功能那一项去掉。"""
    out = []
    for item in site.get("nav") or []:
        if not isinstance(item, dict):
            continue
        if not feature_enabled(item.get("feature")):
            continue
        entry = {
            "key": str(item.get("key") or item.get("label") or ""),
            "href": str(item.get("href") or "/"),
            "label": str(item.get("label") or item.get("key") or ""),
        }
        if item.get("icon"):
            entry["icon"] = str(item["icon"])
        out.append(entry)
    return out


def _yaml_scalar(value: str) -> str:
    """把身份字段变成能安全放进 YAML 的标量。

    模板里占位符都带引号，所以这里只要处理两种情况：
    换行（YAML 标量不能跨行）与双引号（要转义）。
    """
    text = " ".join(str(value).splitlines())
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_config(site: dict) -> str:
    """把身份填进配置模板。"""
    if not CONFIG_TEMPLATE.exists():
        print(f"配置模板不存在：{CONFIG_TEMPLATE}", file=sys.stderr)
        raise SystemExit(2)
    text = CONFIG_TEMPLATE.read_text(encoding="utf-8")
    url = os.environ.get("SITE_URL") or site.get("url") or DEFAULT_URL
    values = {
        "name": _yaml_scalar(site["name"]),
        "tagline": _yaml_scalar(site["tagline"]),
        "description": _yaml_scalar(site["description"]),
        "start_date": _yaml_scalar(site["start_date"]),
        "url": _yaml_scalar(url),
        "language": _yaml_scalar(site.get("language") or DEFAULT_LANGUAGE),
        "timezone": _yaml_scalar(site.get("timezone") or ""),
    }
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = [
        line
        for line in text.splitlines()
        if "{{" in line and "}}" in line and not line.lstrip().startswith("#")
    ]
    if leftover:
        print(
            "配置模板里有没填的占位符：\n  " + "\n  ".join(leftover),
            file=sys.stderr,
        )
        raise SystemExit(2)
    return text


def render_about(site: dict) -> str:
    """关于页的正文。

    有 `content/about.md` 就用它（使用者自己写的），没有就按身份字段生成一段。
    """
    body = ""
    if ABOUT_BODY.exists():
        body = ABOUT_BODY.read_text(encoding="utf-8").strip()
    else:
        lines = [
            f"# {site['name']}",
            "",
            str(site["tagline"]),
            "",
            str(site["description"]),
            "",
        ]
        note = (site.get("footer") or {}).get("note")
        if note:
            lines += [str(note), ""]
        body = "\n".join(lines)

    head = [
        "---",
        f"title: {json.dumps('关于', ensure_ascii=False)}",
        "layout: about",
        "---",
        "",
    ]
    return "\n".join(head) + body.rstrip() + "\n"


def render_robots(url: str) -> str:
    """robots.txt。sitemap 的地址要跟着站点地址走，所以是生成物。"""
    return f"User-agent: *\nAllow: /\n\nSitemap: {url.rstrip('/')}/sitemap.xml\n"


def render_manifest(site: dict) -> str:
    """PWA 清单。站名与简介是身份的一部分。"""
    manifest = {
        "name": site["name"],
        "short_name": site["name"],
        "description": site["description"],
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#009688",
        "lang": site.get("language") or DEFAULT_LANGUAGE,
        "icons": [
            {
                "src": "/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
            }
        ],
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def write_outputs(site: dict) -> dict[str, str]:
    """把所有产物写进磁盘。返回 {路径: 内容}（--check 时用来比对）。"""
    outputs: dict[str, str] = {}

    outputs[str(CONFIG_OUT)] = render_config(site)

    identity = {
        "name": site["name"],
        "tagline": site["tagline"],
        "description": site["description"],
        "start_date": site["start_date"],
        "nav": build_nav(site),
        "footer": site.get("footer") or {},
    }
    outputs[str(DATA_DIR / "site.json")] = (
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n"
    )

    outputs[str(ABOUT_DIR / "index.md")] = render_about(site)

    url = os.environ.get("SITE_URL") or site.get("url") or DEFAULT_URL
    outputs[str(ROBOTS)] = render_robots(url)
    outputs[str(MANIFEST)] = render_manifest(site)

    return outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="把身份注入站点配置与模板数据")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args()

    site = load_site_json()
    try:
        outputs = write_outputs(site)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"身份注入失败：{exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = []
        for raw_path, text in outputs.items():
            path = Path(raw_path)
            if not path.exists():
                problems.append(f"{path}：不存在（该跑一次 apply-site-config.py）")
            elif path.read_text(encoding="utf-8") != text:
                problems.append(f"{path}：与身份文件不同步")
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            print(f"\n{len(problems)} 处不一致", file=sys.stderr)
            return 1
        print(f"站点配置与身份文件一致（{len(outputs)} 个产物）")
        return 0

    for raw_path, text in outputs.items():
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")

    print(f"身份：{site['name']}（导航 {len(build_nav(site))} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
