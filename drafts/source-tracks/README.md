# source-tracks（副本）

`docs/source-tracks/` 的一份**副本**——给**视频线**当素材用。

**真身在 `docs/source-tracks/`。** 这里是副本：改了不算数，
`docs/` 那份才是母稿（母稿唯一）。这一份只**读**，不写。

## 为什么要副本

视频生成要读母稿的正文，但视频线是**另一个模块**：
它不认 `docs/`，它认 `video/` 和它自己的素材目录。
让两个模块读同一个目录，就是让它们能同时写同一个文件——
那正是顶层设计要拆掉的耦合（见
`review/specs/2026-11-18-顶层设计与目录调整.md`）。

所以分工是：**读**的部分复制一份，**写**的部分各写各的。

## 怎么用

一期视频的稿子从某个系列的一篇出发：

```
drafts/source-tracks/<主线>/<系列>/<文章>.md   ← 读这份（素材）
                            │
                            ▼
video/字幕-<期号>.md                             ← 写这份（视频母稿）
                            │
                      video/review/
                            │
                            ▼
                          成片 → 平台
```

## 同步

`docs/source-tracks/` 那边改了，这边要重新同步：

```bash
rsync -a --delete \
  --exclude '/postgresql/.claude/' \
  --exclude '/README.md' \
  docs/source-tracks/ drafts/source-tracks/
```

`--exclude '/README.md'` 是为了不把这页自己删掉；
`postgresql/.claude/` 是工具的本地配置（不是一个插件开关），
不是内容，不跟过来。

## 这份副本里有什么

四条源码主线（PostgreSQL / Linux / DPDK 与 VPP / Ceph 筹备中），
324 篇 Markdown 与 192 张 PNG 等素材，与 `docs/source-tracks/` **逐字节一致**
（`diff -rq` 只差那个 `.claude/` 目录）。

**链接不用改。** 文章里那些 `../../getting-started/…` 是站内相对链接，
在副本里同样解析得到；指向 `/categories/…` 的是站点地址，指向的是站上，
跟这份副本在不在同一个目录无关。
