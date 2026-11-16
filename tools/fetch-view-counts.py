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


def _now_iso() -> str:
    """当前 UTC 时间（秒精度，RFC3339）。"""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_path(path) -> str:
    """把各种写法的路径归一到同一个键。

    hexo 的 ``post.path`` 是 ``2026/08/18/db/aaa/index.html``，
    GoatCounter 记的是 ``/2026/08/18/db/aaa/``——两边都得归一成
    ``2026/08/18/db/aaa``，模板才匹配得上。

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
    return s


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


def fetch_page(api_key, code, start, end, exclude=None, limit=PAGE_LIMIT) -> dict:
    """调一次 GoatCounter 的统计接口。"""
    query = urllib.parse.urlencode(
        {"start": start, "end": end, "limit": limit, "path_by_name": "true"}
    )
    if exclude:
        # exclude_paths 是**路径名**（path_by_name=true 时按名字排除），
        # 重复同一个参数名。
        query += "&" + urllib.parse.urlencode(
            {"exclude_paths": list(exclude)}, doseq=True
        )
    url = "https://{}.goatcounter.com/api/v0/stats/hits?{}".format(code, query)
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


def fetch_counts(api_key, code, start=DEFAULT_START, end=None) -> dict:
    """把 GoatCounter 上所有路径的 PV 抓回来。

    接口一次最多给 100 条，后面靠 ``exclude_paths`` 翻页。
    """
    end = end or _now_iso()
    counts = {}
    exclude = []
    while True:
        payload = fetch_page(api_key, code, start, end, exclude)
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not hits:
            break
        for key, count in parse_counts(payload).items():
            counts[key] = counts.get(key, 0) + count
        if not payload.get("more"):
            break
        # 翻页：把已经拿到的路径排除掉。
        exclude.extend(
            str(hit["path"]) for hit in hits
            if isinstance(hit, dict) and hit.get("path")
        )
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
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote {} ({} paths)".format(out, len(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
