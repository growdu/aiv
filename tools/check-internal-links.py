#!/usr/bin/env python3
"""查站内链接断没断。

仓库里原来有两个查链接的工具，都不管用：

- `tools/check-built-links.py` 只看 gaokao 一段（`:60 gaokao_pages()` 只收
  `/life/gaokao` 的页面，`:57 LINK_RE` 只匹配 gaokao 链接），**也不查图片**；
- `tools/check-mermaid.py` 只管图渲染。

全站有 1000 多条站内链接，迁移目录一搬就可能断几百条 —— 没有这把尺子，
迁移就是闭着眼睛走。这个工具补上这块。

查两件事：

1. **母稿侧**：`docs/**/*.md` 里每条相对链接，按 `sync-hexo.py` 的
   `_resolve_link_target()` 同一套规则解析，解析不到就报出来（附「往上一级
   目录再试一次」的兄弟兜底 —— 那是作者写 `./x/` 想指同级 bundle 时的常见笔误，
   编译期会自愈，所以自愈过的**不算断**）。
2. **产物侧**：`public/**/*.html` 里所有站内 `href`，看它指向的页面在
   `public/` 里到底存不存在（死链）。

用法：

```bash
python3 tools/check-internal-links.py                 # 查两边
python3 tools/check-internal-links.py --docs-only
python3 tools/check-internal-links.py --json /tmp/links.json
```

退出码：有断链 → 1；没有 → 0。
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
PUBLIC = os.path.join(REPO, "public")

# 普通 markdown 链接（不含图片，图片是 ![]()）
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# 产物侧的站内 href
HREF_RE = re.compile(r'href="([^"]+)"')
# 素材侧的站内 src
SRC_RE = re.compile(r'src="([^"]+)"')

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico")

EXTERNAL_SCHEMES = (
    "http://", "https://", "data:", "mailto:", "tel:", "ftp://",
    "javascript:", "about:", "//", "#",
)


def is_external(target: str) -> bool:
    return target.startswith(EXTERNAL_SCHEMES)


def decode(target: str) -> str:
    """URL 解码 —— 站上的链接里中文是 %XX 编码的，磁盘上的文件名不是。"""
    return unquote(target)


def _bundle_index(abs_dir: str):
    """目录型 bundle 里那个「首页」文件。"""
    for ext in ("index.md", "index.html", "index.htm", "_index.md"):
        p = os.path.join(abs_dir, ext)
        if os.path.isfile(p):
            return p
    return None


def resolves(abs_target: str) -> bool:
    """这个绝对路径能不能落到一个真实文件上。

    规则与 `sync-hexo.py:_resolve_link_target()` 对齐 —— 那边能解析出
    permalink，这边就判定「不是断链」。
    """
    basename = os.path.basename(abs_target)
    if basename in ("index.md", "index.html", "index.htm"):
        bundle_dir = os.path.dirname(abs_target)
        if os.path.isdir(bundle_dir):
            return _bundle_index(bundle_dir) is not None
    if os.path.isdir(abs_target):
        return _bundle_index(abs_target) is not None
    if os.path.isfile(abs_target):
        return True
    for ext in (".md", ".html", ".htm"):
        if os.path.isfile(abs_target + ext):
            return True
    return False


def _candidate_targets(post_dir: str, raw: str):
    """一条相对链接可能落到哪几个绝对路径上（按优先级）。

    与 `rewrite_links()` 的 `repl()` 同序：先按原样解析，再试「往上一级
    目录找同级 bundle」的自愈兜底。
    """
    out = []
    candidate = os.path.normpath(os.path.join(post_dir, raw))
    if not candidate.startswith("..") and not os.path.isabs(candidate):
        out.append(candidate)
    cleaned = raw.lstrip("./")
    if post_dir:
        parent_dir = os.path.dirname(post_dir)
        if parent_dir and not parent_dir.startswith(".."):
            sibling = os.path.normpath(os.path.join(parent_dir, cleaned))
            if not sibling.startswith(".."):
                out.append(sibling)
    return out


def check_docs():
    """母稿侧：相对链接解析不到目标就是断链。"""
    broken = []
    total = 0
    external = 0
    for root, dirs, files in os.walk(DOCS):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, DOCS)
            text = open(path, encoding="utf-8", errors="replace").read()
            body = re.sub(r"^---\n[\s\S]*?\n---\n", "", text)
            post_dir = os.path.dirname(rel)
            for m in LINK_RE.finditer(body):
                raw = m.group(2)
                if is_external(raw):
                    external += 1
                    continue
                total += 1
                if raw.startswith("/"):
                    # 根绝对路径：编译期只会加挂载点，不校验存在性
                    continue
                target = decode(raw.split("#", 1)[0].split("?", 1)[0])
                if not target:
                    continue
                if not resolves(os.path.join(DOCS, target)):
                    # 试一次编译期的自愈兜底
                    if any(resolves(os.path.join(DOCS, c))
                           for c in _candidate_targets(post_dir, target)):
                        continue
                    broken.append({
                        "source": rel,
                        "target": raw,
                        "line": body[: m.start()].count("\n") + 1,
                    })
    return {"total": total, "external": external, "broken": broken}


def _public_pages():
    """产物里存在哪些页面（URL 形式，无扩展名、带尾斜杠）。"""
    pages = set()
    if not os.path.isdir(PUBLIC):
        return pages
    for root, dirs, files in os.walk(PUBLIC):
        for name in files:
            if name == "index.html":
                rel = os.path.relpath(os.path.join(root, name), PUBLIC)
                url = "/" + rel[:-len("index.html")].replace(os.sep, "/")
                pages.add(url)
                pages.add(decode(url))
    return pages


def check_public():
    """产物侧：href 指向的页面在 public/ 里存不存在。"""
    pages = _public_pages()
    if not pages:
        return {"total": 0, "broken": []}
    broken = []
    total = 0
    for root, dirs, files in os.walk(PUBLIC):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, PUBLIC).replace(os.sep, "/")
            text = open(path, encoding="utf-8", errors="replace").read()
            for m in HREF_RE.finditer(text):
                href = m.group(1)
                if is_external(href) or href.startswith("#"):
                    continue
                # 内联 JS 里的字符串拼接不是链接（' + esc(p.url) + '）
                if not re.match(r"^/[\w\-./%~]*$", href) and not re.match(
                        r"^[\w\-./%~]+\.html?$", href):
                    continue
                total += 1
                url = decode(href.split("#")[0].split("?")[0])
                if not url.startswith("/"):
                    base = "/" + os.path.dirname(rel) + "/"
                    url = os.path.normpath(base + url)
                    if not url.startswith("/"):
                        url = "/" + url
                if url.endswith("/index.html"):
                    url = url[: -len("index.html")]
                if url == "/index.html":
                    url = "/"
                if url in pages or (url.rstrip("/") + "/") in pages:
                    continue
                # 静态资源（.css/.js/.png/…）不查
                if os.path.splitext(url)[1].lower() in (
                        ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                        ".webp", ".ico", ".json", ".xml", ".txt", ".mp3", ".mp4",
                        ".woff", ".woff2", ".ttf"):
                    continue
                broken.append({
                    "source": rel,
                    "target": href,
                    "url": url,
                })
    return {"total": total, "broken": broken}


def main():
    ap = argparse.ArgumentParser(description="查站内链接断没断")
    ap.add_argument("--docs-only", action="store_true", help="只查母稿侧")
    ap.add_argument("--public-only", action="store_true", help="只查产物侧")
    ap.add_argument("--json", help="把结果写成 JSON")
    ap.add_argument("--max", type=int, default=40, help="每侧最多列出多少条")
    args = ap.parse_args()

    result = {}
    if not args.public_only:
        docs = check_docs()
        result["docs"] = docs
        print(f"母稿侧：站内相对链接 {docs['total']} 条（外链 {docs['external']} 条不计），"
              f"断链 {len(docs['broken'])} 条")
        for item in docs["broken"][: args.max]:
            print(f"  {item['source']}:{item['line']}  ->  {item['target']}")
        if len(docs["broken"]) > args.max:
            print(f"  …… 还有 {len(docs['broken']) - args.max} 条")

    if not args.docs_only:
        pub = check_public()
        result["public"] = pub
        print(f"产物侧：站内 href {pub['total']} 条，断链 {len(pub['broken'])} 条")
        for item in pub["broken"][: args.max]:
            print(f"  {item['source']}  ->  {item['target']}  ({item['url']})")
        if len(pub["broken"]) > args.max:
            print(f"  …… 还有 {len(pub['broken']) - args.max} 条")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"结果写到 {args.json}")

    broken_total = sum(len(v.get("broken", [])) for v in result.values())
    return 1 if broken_total else 0


if __name__ == "__main__":
    sys.exit(main())
