#!/usr/bin/env python3
"""抓 GoatCounter 的真实阅读量（PV），写成快照 ``data/view-counts.json``。

**为什么要有这个工具**：侧栏那个🔥数字曾经是假的——``patch-theme.py``
里写的是 ``Math.max(5, Math.floor(字数 / 50))``，十万字的文章显示
「🔥 2000」。要显示真的阅读量，就得在**构建期**拿到 PV。

页面运行时那两套统计（GoatCounter 的 ``count.js``、不蒜子的
``busuanzi``）都是脚本填的，模板拿不到——所以要有一份构建期的快照。

**为什么是 GoatCounter 而不是不蒜子**：

- GoatCounter 的 API 是**只读**的：查一次不会给那个路径 +1。
  不蒜子只有一个按 Referer 判路径的端点，每请求一次给那个路径 +1
  （返回值里含自己那一次）——用它做统计会把统计本身改坏。
- 不蒜子实测有 30–50% 的请求返回 502。

**用法**::

    GOATCOUNTER_API_KEY=xxx python3 tools/fetch-view-counts.py

key 在 GoatCounter 账号设置里（Username → API），CI 侧放 secret
``GOATCOUNTER_API_KEY``。抓完把 ``data/view-counts.json`` 提交上去，
站点下次构建就会用上。

**没有 key 也能用**：快照是空的，模板会退回按 ``top`` 排序，
tab 改名成「编辑精选」——不会显示任何假的数字。

**快照的形状**::

    {
      "source": "goatcounter",
      "generated_at": "2026-11-16T08:00:00Z",
      "start": "...", "end": "...",
      "counts": {"2026/08/18/db/postgresql/xxx": 42}
    }

键是**归一化过的路径**（没有前导 ``/``、没有 ``index.html``），
跟模板里 ``post.path`` 的归一化口径一致（见 ``normalize_path``）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "view-counts.json"
CONFIG_PATH = REPO_ROOT / "_config.matery.yml"

#: 统计区间的起点。取一个很早的日期——我们要的是**累计**阅读量。
DEFAULT_START = "2020-01-01T00:00:00Z"

#: GoatCounter 一次最多给 100 条路径，超了要翻页。
PAGE_LIMIT = 100

#: 最多翻多少页。服务端一直说「还有」也不能无限翻——600 篇文章按 100 条一页
#: 是 6 页，翻到 20 页还没完就该出问题了。
MAX_PAGES = 20

#: GoatCounter 的 API 根。写成常量而不是散在代码里，是为了测试能把它指向
#: 本地的一台假服务器（真接口没有 key 跑不了，但请求长什么样可以钉死）。
API_BASE = "https://{code}.goatcounter.com/api/v0"


def _now_iso() -> str:
    """当前 UTC 时间（秒精度，RFC3339）。"""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def percent_decode(text: str) -> str:
    """把百分号编码还原成原文；解不了就**原样返回**。

    GoatCounter 记的是浏览器请求的那个 URL，也就是**百分号编码**的
    （arp242/goatcounter#834）。hexo 的 ``post.path`` 却是原始 Unicode。
    两边不统一的话，614 篇文章里有 358 篇（路径带中文）永远匹配不上——
    而且是安静地不匹配：「近期热门」只排那 42% 的 ASCII 路径文章，
    看上去一切正常。
    """
    if "%" not in text:
        return text
    try:
        return urllib.parse.unquote(text, errors="strict")
    except UnicodeDecodeError:
        # 落单的 % 或坏掉的转义：原样留着，别变成乱码。
        return text


def normalize_path(path) -> str:
    """把各种写法的路径归一到同一个键。

    hexo 的 ``post.path`` 是 ``2026/08/18/db/aaa/index.html``，
    GoatCounter 记的是 ``/2026/08/18/db/aaa/``——两边都得归一成
    ``2026/08/18/db/aaa``，模板才匹配得上。

    还要把**百分号编码**还原：GoatCounter 返回的是编码过的路径，
    hexo 的是原始 Unicode——不解码的话中文路径的文章一条都匹配不上。

    归一口径必须和模板里的那段 JS **一模一样**，否则永远匹配不上。
    """
    s = str(path or "").strip()
    if s.startswith("/"):
        s = s[1:]
    if s.endswith("/index.html"):
        s = s[: -len("/index.html")]
    elif s == "index.html":
        s = ""
    s = s.rstrip("/")
    return percent_decode(s)


def parse_counts(payload) -> dict:
    """GoatCounter 的响应 → ``{路径: PV}``。

    ``/api/v0/stats/hits`` 返回 ``{"hits": [{"path": ..., "count": ...}]}``。
    直接给一个数组的旧形状也认。

    首页（``/``）不是文章，不进快照。
    """
    hits = payload.get("hits") if isinstance(payload, dict) else payload
    counts = {}
    if not isinstance(hits, list):
        return counts
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        key = normalize_path(hit.get("path"))
        if not key:
            continue
        count = hit.get("count")
        if not isinstance(count, int):
            continue
        counts[key] = counts.get(key, 0) + count
    return counts


def site_code(config_path=CONFIG_PATH) -> str:
    """从 ``_config.matery.yml`` 里读 ``goatcounter.code``。

    站点 code 只有一处真相——主题配置里那一行。这里不引 pyyaml
    （CI 的 job 里只装了 pytest），正则读那一段就够。
    """
    try:
        text = Path(config_path).read_text(encoding="utf-8")
    except OSError:
        return ""
    block = re.search(r"^goatcounter:[ \t]*\n((?:[ \t]+.*\n)*)", text, re.M)
    if not block:
        return ""
    code = re.search(r"^[ \t]+code:[ \t]*['\"]?([A-Za-z0-9_-]+)", block.group(1), re.M)
    return code.group(1) if code else ""


def fetch_page(api_key, code, start, end, offset=0, limit=PAGE_LIMIT) -> dict:
    """调一次 GoatCounter 的统计接口。"""
    query = urllib.parse.urlencode(
        {
            "start": start,
            "end": end,
            "limit": limit,
            "offset": offset,
            "path_by_name": "true",
        }
    )
    url = API_BASE.format(code=code) + "/stats/hits?" + query
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def fetch_counts(api_key, code, start=DEFAULT_START, end=None, max_pages=MAX_PAGES) -> dict:
    """把 GoatCounter 上所有路径的 PV 抓回来。

    接口一次最多给 100 条，后面靠 ``offset`` 翻页——**不是** ``exclude_paths``。
    exclude_paths 的办法是把已经拿到的路径全塞回下一次请求：600 条路径之后
    URL 有八万多字符，多数服务器和代理在 8–32KB 就掐了，刷新会硬失败。
    offset 的 URL 长度是恒定的。
    """
    end = end or _now_iso()
    counts = {}
    seen = set()
    offset = 0
    for _ in range(max_pages):
        payload = fetch_page(api_key, code, start, end, offset=offset)
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not hits:
            break
        raw_paths = [
            str(hit["path"]) for hit in hits
            if isinstance(hit, dict) and hit.get("path")
        ]
        # 同一页被返回两次 = 翻页参数没被服务端认（offset 被忽略了）。
        # 悄悄把阅读量翻倍比直接失败更糟——数字看着合理，其实全错。
        repeated = seen.intersection(raw_paths)
        if repeated:
            raise RuntimeError(
                "第 %d 页出现了上一页已有的路径（%s）——offset 没被服务端认，"
                "再抓下去会把阅读量翻倍。已中止。"
                % (offset // PAGE_LIMIT + 1, ", ".join(sorted(repeated)[:3]))
            )
        seen.update(raw_paths)
        for key, count in parse_counts(payload).items():
            counts[key] = counts.get(key, 0) + count
        if not payload.get("more"):
            break
        offset += len(raw_paths)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="抓 GoatCounter 的真实阅读量")
    parser.add_argument(
        "--code",
        default=None,
        help="GoatCounter 的站点 code（默认读 _config.matery.yml 的 goatcounter.code）",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="统计区间起点（RFC3339，默认累计）",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="统计区间终点（RFC3339，默认现在）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="快照写到哪（默认 data/view-counts.json）",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("GOATCOUNTER_API_KEY", "").strip()
    if not api_key:
        print(
            "缺少 GOATCOUNTER_API_KEY —— 没有 key 抓不到真实阅读量。\n"
            "key 在 GoatCounter 账号设置里（Username → API）。"
        )
        return 2

    code = args.code or site_code()
    if not code:
        print(
            "读不到 goatcounter.code —— 用 --code 指定，"
            "或检查 _config.matery.yml 里的 goatcounter: code:"
        )
        return 2

    end = args.end or _now_iso()
    counts = fetch_counts(api_key, code, args.start, end)

    out = Path(args.out)
    old_counts = {}
    if out.is_file():
        try:
            old_counts = (json.loads(out.read_text(encoding="utf-8")) or {}).get("counts") or {}
        except (OSError, ValueError):
            old_counts = {}

    # 坏数据不能覆盖好数据。
    #
    # 空快照 = 侧栏一个🔥都不显示、首页那个 tab 改名成「编辑精选」——
    # 整个功能被**悄悄**关掉，而 CI 是绿的。API 的形状变了、key 过期了、
    # 站点改名了，都会让抓取结果变成空的或者少一大半。
    if old_counts:
        if not counts:
            print(
                "抓到的路径数是 0，而 %s 里已经有 %d 条 —— 拒绝覆盖。\n"
                "（API 形状变了、key 不对、站点改名，都会这样。先查清楚再刷新。）"
                % (out, len(old_counts))
            )
            return 3
        if len(counts) < len(old_counts) * 0.5:
            print(
                "只抓到 %d 条路径，上一份有 %d 条（少了一半以上）—— 拒绝覆盖。\n"
                "（多半是 API 的形状变了。先查清楚再刷新。）"
                % (len(counts), len(old_counts))
            )
            return 3

    payload = {
        "_comment": (
            "真实阅读量快照。tools/fetch-view-counts.py 从 GoatCounter 抓的，"
            "sync-hexo.py 复制到 source/_data/，hexo 挂到 site.data 上。"
            "counts 为空 = 还没抓过——页面会退回按 top 排序，"
            "不会显示任何假的数字。"
        ),
        "source": "goatcounter",
        "generated_at": _now_iso(),
        "start": args.start,
        "end": end,
        "counts": dict(sorted(counts.items())),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote {} ({} paths)".format(out, len(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
