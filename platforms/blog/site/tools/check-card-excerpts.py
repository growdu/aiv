#!/usr/bin/env python3
"""首页卡片摘要的**渲染产物**检查。

构建完之后跑一遍，断言首页那 18 张卡片的摘要**不是残骸**。

**为什么要有这一步**（和 ``check-home-tabs.py`` 同一个道理）：

模板里写了 ``post.summary || post.description || 正文前 80 个字``——这是
**代码**。代码对了不等于页面对了：568 篇文章里只有 1 篇写了
``<!-- more -->``，``post.summary`` 基本上是空的，于是摘要落到了
「正文的前 80 个字」那一档——线上 18 张卡片里 3 张以「TL;DR」开头，另有
几张是表格残骸、「[TOC]」、视频口播稿抬头。

读者看到这种开头，只会觉得这个博客没写完。

所以要在**渲染产物**（``platforms/blog/site/public/index.html``）上断言：

1. 摘要不以「TL;DR」「[TOC]」开头；
2. 摘要不以履历前缀开头（「初稿，」「修订：」——那是「这次改了什么」，
   不是「这篇文章是什么」）；
3. 摘要不是空的。

用法::

    python3 platforms/blog/site/tools/check-card-excerpts.py [--public platforms/blog/site/public]

退出码 0 = 全部通过；1 = 有问题（问题逐条打印在 stdout）。
"""

import argparse
import re
import sys
from pathlib import Path

# 站点的构建链搬进了 platforms/blog/site/，本脚本深了四层：
# parents[0]=tools, [1]=site, [2]=blog, [3]=platforms, [4]=仓库根。
# 路径常量统一从根 tools/paths.py 取——**路径只有一处能改**。
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from paths import SITE_PUBLIC  # noqa: E402

PUBLIC_DIR = SITE_PUBLIC

#: 卡片摘要在渲染产物里的容器。
EXCERPT_CLASS = "post-card__excerpt"

#: 这些开头是「正文的一部分漏出来了」，不是摘要。
RESIDUE_PREFIXES = ("TL;DR", "[TOC]")

#: 履历前缀：说的是「这次改了什么」，不是「这篇文章是什么」。
#: 关键词后面必须跟着分隔符（或到此为止）才算前缀——
#: 「补充完善解决方案」里的「补充」是正文，不是前缀。
HISTORY_PREFIX_RE = re.compile(
    r"^\s*(初稿|修订|校验|校对|更新|整理|补充)\s*(?:[：:，,。；;！!？?+]\s*|$)"
)


def _strip_tags(html: str) -> str:
    """去掉 HTML 标签，留下纯文本。"""
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).strip()


def extract_excerpts(html: str):
    """页面里所有卡片摘要的纯文本。"""
    blocks = re.findall(
        r'<div class="{}">(.*?)</div>'.format(re.escape(EXCERPT_CLASS)),
        html,
        re.S,
    )
    return [_strip_tags(block) for block in blocks]


def check(public_dir):
    """在渲染产物上跑全部检查，返回问题列表（空列表 = 全过）。"""
    problems = []
    index = Path(public_dir) / "index.html"
    if not index.is_file():
        return ["找不到渲染产物：{}".format(index)]

    html = index.read_text(encoding="utf-8")
    excerpts = extract_excerpts(html)
    if not excerpts:
        return ["{} 里没有卡片摘要（.{}）——首页的文章区没渲染出来？".format(
            index, EXCERPT_CLASS
        )]

    for i, excerpt in enumerate(excerpts, 1):
        if not excerpt:
            problems.append("第 {} 张卡片的摘要是空的".format(i))
            continue
        for prefix in RESIDUE_PREFIXES:
            if excerpt.startswith(prefix):
                problems.append(
                    "第 {} 张卡片的摘要以「{}」开头——那是正文漏出来了，不是摘要：{}".format(
                        i, prefix, excerpt[:40]
                    )
                )
                break
        else:
            if HISTORY_PREFIX_RE.match(excerpt):
                problems.append(
                    "第 {} 张卡片的摘要是履历句（说的是「这次改了什么」）：{}".format(
                        i, excerpt[:40]
                    )
                )

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public",
        default=str(PUBLIC_DIR),
        help="渲染产物目录（默认 platforms/blog/site/public）",
    )
    args = parser.parse_args(argv)

    problems = check(args.public)
    if problems:
        print("卡片摘要检查未通过：")
        for problem in problems:
            print("  - {}".format(problem))
        return 1
    print("卡片摘要检查通过：{} 张卡片的摘要都是完整的句子".format(
        len(extract_excerpts((Path(args.public) / "index.html").read_text(encoding="utf-8")))
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
