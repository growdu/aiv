# source-tracks（工作副本）

`docs/source-tracks/` 的**一份副本**——四条源码主线（PostgreSQL / Linux /
DPDK 与 VPP / Ceph）的文章，**后续的视频生成要按它来**。

它同时是**改动起点**：按总规则，往后的新增与修改都在 `drafts/` 里做，
过完 `review/` 才进 `docs/` 和 `video/`。所以这一份是 `source-tracks`
的**工作副本**——

| | 已过审的版本 | 工作副本（这份） |
| --- | --- | --- |
| 位置 | `docs/source-tracks/` | `drafts/source-tracks/` |
| 谁改 | review 通过后由工作副本覆盖 | **改动在这里做** |
| 干什么 | 站点发布 | 视频生成读素材；改动稿 |

两边现在**内容一致**（`diff -rq` 只差这份自己的 `README.md`）。
改哪篇就在这份里改哪篇。

## 为什么要副本

视频线是**另一个模块**：它不认 `docs/`，它认 `video/` 和它自己的素材目录。
让两个模块读写同一个目录，就是让它们能同时写同一个文件——
那正是顶层设计要拆掉的耦合（见
`review/specs/2026-11-18-顶层设计与目录调整.md`）。

所以分工是：**读**的部分复制一份，**写**的部分各写各的。

## 流程

```
drafts/source-tracks/<主线>/<系列>/<文章>.md   ← 改这份（工作副本）
                            │
                            ▼
                      review/                  ← 审
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
docs/source-tracks/…                  video/字幕-<期号>.md
（站点发布，已过审）                    （视频母稿）
```

## 两个方向的同步

**① review 通过之后，把工作副本推回 `docs/`**（常规方向）：

```bash
rsync -a --delete --exclude '/README.md' \
  drafts/source-tracks/ docs/source-tracks/
```

**② `docs/` 那边有别的改动（存量维护）时，把 `docs/` 拉回工作副本**：

```bash
rsync -a --delete --exclude '/README.md' \
  docs/source-tracks/ drafts/source-tracks/
```

两条命令的排除项相同，是为了让两个目录**保持同构**：
`README.md` 只在这份里。

**链接不用改。** 文章里那些 `../../getting-started/…` 是站内相对链接，
在副本里同样解析得到；指向 `/categories/…` 的是站点地址，指向的是站上，
跟这份副本在不在同一个目录无关。
