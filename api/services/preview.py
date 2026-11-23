"""站点 dev server 的按需起停与预览地址。

**预览就是站点的真页面**（规格 D3）：文档流不做第二套渲染——
看到的与线上跑的是同一份 hexo 输出。

**地址形状从 `rules/urls.json` 读**，不抄一份——那是全仓库唯一的 URL 规则
（`doc_prefix` / `trailing_slash` / `category_suffix` 都在那儿）。
"""
from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from .paths import REPO_ROOT, SITE_DIR

#: 全仓库唯一的 URL 形状规则。
RULES_PATH = REPO_ROOT / "rules" / "urls.json"

#: 站点 dev server 的默认地址与端口。
HOST = "127.0.0.1"
PORT = 4000

#: dev server 的日志落点。**在仓库之外**——平台的唯一写点是 `drafts/`，
#: 站点目录是别的模块的地盘（规格 §十一：平台只是观察窗）。
DEV_SERVER_LOG = Path(tempfile.gettempdir()) / "creation-platform-site-dev-server.log"


def load_rules(path: Path = RULES_PATH) -> dict:
    """读 URL 规则文件。读不到就用最小的一份（别让预览整个挂掉）。"""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"doc_prefix": "/docs/", "trailing_slash": True,
                "category_suffix": "_index"}


def site_preview_url(doc_id: str, *, host: str = HOST, port: int = PORT) -> str:
    """一篇文档在 dev server 上的地址。

    `http://127.0.0.1:4000/docs/<id>/`——末尾的斜杠来自规则表的
    `trailing_slash`。分类页的 `/_index` 后缀按规则表剥掉。
    """
    rules = load_rules()
    tail = doc_id.strip("/")
    suffix = rules.get("category_suffix") or ""
    if suffix and tail.endswith(f"/{suffix}"):
        tail = tail[: -(len(suffix) + 1)]
    prefix = rules.get("doc_prefix") or "/docs/"
    path = prefix + tail + ("/" if rules.get("trailing_slash") else "")
    return f"http://{host}:{port}{path}"


def site_server_running(port: int = PORT, host: str = HOST) -> bool:
    """dev server 在不在？探一下端口。"""
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def ensure_site_server(*, port: int = PORT, host: str = HOST,
                       wait_s: float = 20.0) -> tuple[bool, str]:
    """保证 dev server 在跑。

    返回 `(起来了吗, 给人的提示)`。

    已经在跑 → 直接用。没装 `hexo-server` → 说清楚怎么装；
    装了但起不来 → 说清楚怎么手敲。**不假装成功**。
    """
    if site_server_running(port=port, host=host):
        return True, "站点 dev server 已在跑"

    if not (SITE_DIR / "node_modules" / "hexo-server").exists():
        return False, "站点还没装 hexo-server：cd platforms/blog/site && npm install"

    # 日志**不落在仓库里**——平台的唯一写点是 `drafts/`。
    log_path = DEV_SERVER_LOG
    try:
        log = open(log_path, "ab")
    except OSError as exc:
        return False, f"开不了日志文件 {log_path}：{exc}"
    try:
        subprocess.Popen(
            ["npm", "run", "server"],
            cwd=str(SITE_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,          # 脱离本进程：门面关了它也还在
            shell=False,
        )
    except OSError as exc:
        return False, f"起不来：{exc}（cd platforms/blog/site && npm run server）"
    finally:
        log.close()

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if site_server_running(port=port, host=host):
            return True, f"已启动站点 dev server（日志：{log_path}）"
        time.sleep(0.5)

    return False, (f"等了 {int(wait_s)} 秒还没起来："
                   f"cd platforms/blog/site && npm run server（日志：{log_path}）")
