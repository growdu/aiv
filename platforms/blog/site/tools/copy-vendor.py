#!/usr/bin/env python3
"""Copy vendor assets from node_modules to the site's ``source/lib/``.

Handles:
1. CDN-localized files (from the root ``tools/cdn-manifest.json``)
2. Prism/Mermaid/Gitalk assets (fixed)
3. Font Awesome webfonts (referenced by css/all.min.css)

Run AFTER sync-hexo.py (which creates the site's ``source/``).
"""
import os, json, shutil, sys
from pathlib import Path

# 站点的构建链搬进了 platforms/blog/site/，本脚本深了四层：
# parents[0]=tools, [1]=site, [2]=blog, [3]=platforms, [4]=仓库根。
# 路径常量统一从根 tools/paths.py 取——**路径只有一处能改**。
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from paths import ROOT_TOOLS, SITE, SITE_SOURCE  # noqa: E402

#: 站点的私有源目录下的 vendor 库
LIB = str(SITE_SOURCE / "lib")
#: 根 tools/ 下的 CDN 清单（localize-cdn.py 生成）
MANIFEST = str(ROOT_TOOLS / "cdn-manifest.json")
#: node_modules 跟着站点搬了家（package.json 在 platforms/blog/site/）。
#: CI 里 npm install 装在这儿；本地开发时它是软链回仓库根的 node_modules。
#: 两种情况都从这个绝对路径找。
NODE_MODULES = str(SITE / "node_modules")


def _vendor_src(path):
    """清单里的 'node_modules/...' → 站点 node_modules 下的实际路径。"""
    if path.startswith("node_modules/"):
        return os.path.join(NODE_MODULES, path[len("node_modules/"):])
    return path


def _vendor_dst(path):
    """清单里的 'source/lib/...' → 站点 source/lib 下的实际路径。"""
    if path.startswith("source/"):
        return os.path.join(str(SITE_SOURCE), path[len("source/"):])
    return path

# Fixed vendor assets
FIXED = [
    ('node_modules/prismjs/themes/prism-tomorrow.min.css', f'{LIB}/prism/prism-tomorrow.min.css'),
    ('node_modules/prismjs/components/prism-core.min.js', f'{LIB}/prism/prism-core.min.js'),
    ('node_modules/prismjs/plugins/autoloader/prism-autoloader.min.js', f'{LIB}/prism/prism-autoloader.min.js'),
    ('node_modules/mermaid/dist/mermaid.min.js', f'{LIB}/mermaid/mermaid.min.js'),
    ('node_modules/gitalk/dist/gitalk.css', f'{LIB}/gitalk/gitalk.css'),
    ('node_modules/gitalk/dist/gitalk.min.js', f'{LIB}/gitalk/gitalk.min.js'),
]

# Directories to copy (fontawesome webfonts referenced by all.min.css)
FIXED_DIRS = [
    ('node_modules/prismjs/components', f'{LIB}/prism/components'),

    ('node_modules/@fortawesome/fontawesome-free/webfonts', f'{LIB}/fontawesome-free/webfonts'),
]

copies = list(FIXED)

if os.path.isfile(MANIFEST):
    with open(MANIFEST, encoding='utf-8') as f:
        copies.extend(json.load(f))
    print(f'Loaded CDN manifest')

ok = skip = 0
for src, dst in copies:
    src = _vendor_src(src)
    dst = _vendor_dst(dst)
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        ok += 1
    else:
        print(f'WARNING: {src} not found')
        skip += 1

for src_dir, dst_dir in FIXED_DIRS:
    src_dir = _vendor_src(src_dir)
    dst_dir = _vendor_dst(dst_dir)
    if os.path.isdir(src_dir):
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        ok += len(os.listdir(dst_dir))
    else:
        print(f'WARNING: {src_dir} not found')

print(f'Copied {ok} files, {skip} missing')
