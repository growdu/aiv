#!/usr/bin/env python3
"""首页文章区 tab 的**渲染产物**检查。

构建完之后跑一遍，断言首页上那三个 tab 真的对应三个面板。

**为什么要有这一步**（和期号区块的检查同一个道理）：

模板里写了 tab、主题 JS 里调了 ``.tabs()``——这些都是**代码**。
代码对了不等于页面对了：面板 id 与标签 href 对不上、面板漏了
``home-tab-panel`` 类名、三个面板被 ``id`` 写重了，页面照样渲染，
只是那个 tab 点了不切换——回到今天这个「假控件」的状态。

所以要在**渲染产物**（``public/index.html``）上断言：

1. 三个 tab 标签的 href 与三个面板的 id 一一对应；
2. 三个面板都带 ``home-tab-panel`` 类名；
3. 默认激活的是「最新发布」；
4. 面板的 id 不重复（重了的话标签只能指到第一个）。

用法：

    python3 tools/check-home-tabs.py [--public public]

退出码 0 = 全部通过；1 = 有问题（问题逐条打印在 stdout）。
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = REPO_ROOT / "public"

#: 首页文章区的三个面板 id。顺序 = 期望的显示顺序。
TAB_IDS = ["home-tab-latest", "home-tab-featured", "home-tab-hot"]

#: 面板共用的类名。CSS 兜底（默认只显示一个面板）靠它生效。
PANEL_CLASS = "home-tab-panel"


def check(public_dir):
    """在渲染产物上跑全部检查，返回问题列表（空列表 = 全过）。"""
    problems = []
    index = Path(public_dir) / "index.html"
    if not index.is_file():
        return ["找不到渲染产物：{}".format(index)]

    html = index.read_text(encoding="utf-8")

    # 1. 三个 tab 标签
    hrefs = re.findall(r'<li class="tab[^"]*"><a[^>]*href="#(home-tab-[^"]+)"', html)
    if hrefs != TAB_IDS:
        problems.append(
            "tab 标签的 href 应当正好是 {}，实际：{}".format(TAB_IDS, hrefs)
        )

    # 2. 三个面板，id 唯一
    panel_ids = re.findall(r'<div id="(home-tab-[^"]+)"', html)
    if panel_ids != TAB_IDS:
        problems.append(
            "面板 id 应当正好是 {}（且顺序一致），实际：{}".format(TAB_IDS, panel_ids)
        )
    duplicates = {pid for pid in panel_ids if panel_ids.count(pid) > 1}
    if duplicates:
        problems.append("面板 id 重复：{}".format(sorted(duplicates)))

    # 3. 每个面板都带 PANEL_CLASS
    for panel_id in TAB_IDS:
        match = re.search(r'<div id="{}"[^>]*>'.format(re.escape(panel_id)), html)
        if match is None:
            problems.append("找不到面板 {}".format(panel_id))
            continue
        if PANEL_CLASS not in match.group(0):
            problems.append(
                "面板 {} 缺少 {} 类名，CSS 兜底对它不生效".format(panel_id, PANEL_CLASS)
            )

    # 4. 默认激活「最新发布」
    active_tabs = re.findall(
        r'<li class="tab[^"]*"><a class="active" href="#(home-tab-[^"]+)"', html
    )
    if active_tabs != ["home-tab-latest"]:
        problems.append(
            "默认激活的应当只有「最新发布」，实际：{}".format(active_tabs)
        )

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public",
        default=str(PUBLIC_DIR),
        help="渲染产物目录（默认 public）",
    )
    args = parser.parse_args(argv)

    problems = check(args.public)
    if problems:
        print("首页 tab 检查未通过：")
        for problem in problems:
            print("  - {}".format(problem))
        return 1
    print("首页 tab 检查通过：{} 个 tab 与 {} 个面板一一对应".format(
        len(TAB_IDS), len(TAB_IDS)
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
