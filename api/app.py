"""创作平台的 HTTP 门面。

**这一层不含业务规则。** 它只做三件事：读文件、调 CLI、起后台作业。
作业调的命令与手敲命令行逐字等价——流水线是唯一的真相（规格反目标 A3）。

**身份不在这里。** 站名、品牌名、平台名全在使用者一侧（site.json /
config.toml / capability.toml），这一层只读。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import documents, drafts, jobs

app = FastAPI(title="创作平台 API", version="1.0.0")

# 本地单用户工具：只允许 vite dev server 那个来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drafts.router)
app.include_router(documents.router)
app.include_router(jobs.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "creation-platform-api"}
