---
status: 已合入
src: source-tracks/postgresql/getting-started/postgresql19-concurrency-persistence-extension.md
---

# 审校：PostgreSQL 19 的并发、持久性与扩展

- 原文：docs/source-tracks/postgresql/getting-started/postgresql19-concurrency-persistence-extension.md
- 范围：全文
- 审校状态：已合入
- 目标读者：写过业务、开始读 PostgreSQL 内核，想弄明白「并发到底靠什么挡、持久性靠什么兜」的后端工程师
- 一句话定位：把并发拆成三层互不干扰的锁，把持久性钉在 WAL 的坐标上，把扩展摊成几个具体可用的口子
- 核心判断：三层锁不是三种强度的锁，是**三种管不同东西的锁**；把持久性理解成「一个 LSN 就是一个事务的全部」，比背 WAL 流程图管用
- 对照源码：`/work/cwork/postgresql_2`，分支 `REL_19_STABLE`

## 优先修改

1. 位置：`## 并发控制：三层锁` → `### 第二层：重量级锁` 里「锁标签的类型是一个枚举」那一句
   - 问题（类别）：事实
   - 建议：「一共 13 种」改成 **12**
   - 原因：`src/include/storage/locktag.h` 第 36 行往下的 `LockTagType` 枚举只有 12 个值（`LOCKTAG_RELATION` … `LOCKTAG_APPLY_TRANSACTION`）。原文紧跟着的那张类型表列的也正好是 12 行——跟第一篇一样，是散文里的计数多算了一个，表本身没错。

2. 位置：`## 一份可以带走的清单` 里「postmaster 是个 14 状态的状态机」那一条
   - 问题（类别）：事实
   - 建议：14 改成 **13**
   - 原因：`src/backend/postmaster/postmaster.c` 第 336 行往下的 `PMState` 枚举是 13 个值。第一篇同一处也写错了 14，两篇一起改。

3. 位置：`## 一份可以带走的清单` 里「内置的 44 个子系统列在……」那一条
   - 问题（类别）：事实
   - 建议：44 改成 **43**
   - 原因：`src/include/storage/subsystemlist.h` 里 `PG_SHMEM_SUBSYSTEM(...)` 实际 43 条（`grep -cE "^PG_SHMEM_SUBSYSTEM\("` = 43）。第一篇三处都写成了 44，两篇一起改。

4. 位置：`## 并发控制：三层锁`、`## WAL 的文件布局、checkpoint 与恢复`、`## 复制：物理与逻辑两条路`、`## 扩展点：内核留出来的门` 四个二级标题之前
   - 问题（类别）：表达
   - 建议：每个标题前补一个空行
   - 原因：这四处标题紧贴在上一段的正文后面，中间没有空行。渲染得出来，但同一篇里其他二级标题都有空行——排版不统一。这一篇共发现 4 处。

## 事实待核

- [x] 锁标签类型是 **12** 种，不是 13——依据：`src/include/storage/locktag.h` 第 36 行往下的 `LockTagType`，逐个列出是 `LOCKTAG_RELATION`、`LOCKTAG_RELATION_EXTEND`、`LOCKTAG_DATABASE_FROZEN_IDS`、`LOCKTAG_PAGE`、`LOCKTAG_TUPLE`、`LOCKTAG_TRANSACTION`、`LOCKTAG_VIRTUALTRANSACTION`、`LOCKTAG_SPECULATIVE_TOKEN`、`LOCKTAG_OBJECT`、`LOCKTAG_USERLOCK`、`LOCKTAG_ADVISORY`、`LOCKTAG_APPLY_TRANSACTION`；文件里还有 `LOCKTAG_LAST_TYPE` 定义为最后一条。
- [x] 锁模式是 **8** 种（1~8）——依据：`src/include/storage/lockdefs.h` 第 36 行的 `AccessShareLock`(1) 到第 45 行的 `AccessExclusiveLock`(8)，第 48 行 `MaxLockMode 8`。
- [x] `PMState` 是 **13** 个状态——依据：`src/backend/postmaster/postmaster.c` 第 336 行往下的枚举（与第一篇同一条事实）。
- [x] 内置共享内存子系统是 **43** 个——依据：`src/include/storage/subsystemlist.h`（与第一篇同一条事实）。
- [x] `PG_LWLOCK(...)` 45 条、`PG_LWLOCKTRANCHE(...)` 42 条、单独命名的锁 58 个槽位——依据：`src/include/storage/lwlocklist.h`（`grep -c "^PG_LWLOCK("` = 45，`grep -c "^PG_LWLOCKTRANCHE("` = 42）；最大锁 id 是 57，`generate-lwlocknames.pl` 据此生成 `NUM_INDIVIDUAL_LWLOCKS` = 58。
- [x] 用户自定义 tranche 上限 256、用户 tranche 的 id 从 100 起——依据：`src/backend/storage/lmgr/lwlock.c` 第 170 行的 `MAX_USER_DEFINED_TRANCHES 256`；`src/include/storage/lwlock.h` 第 164 行的 `LWTRANCHE_INVALID = NUM_INDIVIDUAL_LWLOCKS - 1` 与第 172 行的 `LWTRANCHE_FIRST_USER_DEFINED`——42 个内置 tranche 依次占 58~99，用户 tranche 从 100 起。
- [x] 锁表分区是 **16** 份、谓词锁表分区也是 **16** 份、缓冲池映射分区 **128** 份——依据：`src/include/storage/lwlock.h` 第 83 行的 `NUM_BUFFER_PARTITIONS 128`、第 86~87 行的 `LOG2_NUM_LOCK_PARTITIONS 4` / `NUM_LOCK_PARTITIONS (1 << 4)`、第 90~91 行的谓词锁分区同理。
- [x] `pg_locks` 视图是 **16** 列——依据：`src/backend/utils/adt/lockfuncs.c` 第 66 行的 `NUM_LOCK_STATUS_COLUMNS 16`。
- [x] 谓词锁占 **5** 块共享内存——依据：`src/backend/storage/lmgr/predicate.c` 第 1131、1148、1171、1182、1203 行的五处 `shmem_request_hash`。
- [x] 资源管理器是 **22** 条——依据：`src/include/access/rmgrlist.h`，`grep -cE "^PG_RMGR\("` = 22。
- [x] 进程类型表是 **18** 条——依据：`src/include/postmaster/proctypelist.h`，`grep -c "^PG_PROCTYPE"` = 18。
- [x] 内核参数表有 **439** 条记录，由 `gen_guc_tables.pl` 生成 `guc_tables.inc.c`——依据：`src/backend/utils/misc/guc_parameters.dat`（`grep -cE "^\{ name =>"` = 439）与 `src/backend/utils/Makefile` 第 58 行的生成规则。
- [x] 参数生效分 **七** 档——依据：`src/include/utils/guc.h` 第 71 行往下的 `GucContext` 枚举：`PGC_INTERNAL`、`PGC_POSTMASTER`、`PGC_SIGHUP`、`PGC_SU_BACKEND`、`PGC_BACKEND`、`PGC_SUSET`、`PGC_USERSET`。
- [x] `pg_plan_advice` 是可加载模块、不在扩展列表里；`pg_stash_advice` 才是 SQL 扩展——依据：`contrib/pg_plan_advice/Makefile` 里是 `MODULE_big = pg_plan_advice` 且该目录下**没有** `.control` 文件；`contrib/pg_stash_advice/` 下有 `pg_stash_advice.control` 与 `pg_stash_advice--1.0.sql`。
- [x] `WAIT FOR LSN` 的选项名与取值——依据：`src/backend/parser/gram.y` 第 16636 行往下的 `WaitStmt` 产生式（`WAIT FOR LSN_P Sconst opt_wait_with_clause`）与 `src/backend/commands/wait.c` 第 101 行起的选项解析：`mode` 取 `standby_replay` / `standby_write` / `standby_flush` / `primary_flush`，另有 `timeout`（第 126 行）与 `no_throw`（第 149 行）。
- [x] `pg_stat_progress_repack` 与 `pg_stat_autovacuum_scores` 存在——依据：`src/backend/catalog/system_views.sql` 第 1349 行与第 798 行。
- [x] 全文 **99 处**「`文件` 第 N 行」引用逐条核对过：文件都存在、行号都在文件范围内，且该行上下文中确实有文中所述的标识符——依据：对 `/work/cwork/postgresql_2` 全树做的自动核对 + 逐条人工复核。

## 可补的技术证据或产物

- **实际的死锁现场**：这一篇讲了等待与死锁检测，但没给一段真实的 `pg_locks` 输出（谁在等谁、`waitstart` 多久）。补一段现场，读者对着自己的库就能认。
- **异步 I/O 的对比数字**：19 的 `io_method=worker` 与 18 的同步 I/O 在同一台机器上的吞吐与尾延迟。第一篇也缺这个，两篇都留在这里等一个实测。
- **逻辑复制的完整一轮**：建订阅、同步数据、增量应用、故障恢复的实测输出。现在给的是四个角色的分工，不是走完一圈的样子。
- 扩展那一节的**最小可编译扩展**：正文给了 `.control` 的字段与钩子，但没给一个能直接 `make install` 的骨架工程。读者照着写容易漏掉 `MODULES` / `REGRESS` 这些细节。
- 下一篇的入口：文末的「延伸阅读」还没链到分类页；`/docs/source-tracks/postgresql/getting-started/` 这一站建好之后，把链接换成站页的相对链接。

## 已确认的改动

- 三处数字改掉了：锁标签 13→12、postmaster 状态 14→13、子系统 44→43。改在 `drafts/source-tracks/postgresql/getting-started/postgresql19-concurrency-persistence-extension.md`，与 `docs/` 那份逐字节一致（`diff -r` 无差异）。
- 四个二级标题前补了空行（`## 并发控制：三层锁`、`## WAL 的文件布局、checkpoint 与恢复`、`## 复制：物理与逻辑两条路`、`## 扩展点：内核留出来的门`），排版与全篇其余标题统一。
- 三张目录页（`docs/source-tracks/_index.md`、`docs/source-tracks/postgresql/_index.md`、`docs/source-tracks/postgresql/getting-started/_index.md`）与这篇文章**一起过审**：它们是目录导航，不套技术深度五要素，但要列的文章必须都已过审——它们列的正是这一篇与同一站的第一篇。
- 机械检查：`python3 tools/review-check.py drafts/source-tracks/postgresql/getting-started/postgresql19-concurrency-persistence-extension.md --json` → **0 警告 0 提示**，五要素全过。
- 整条链路过了一遍：编译出 8 个内容单元（3 篇文章 + 5 张目录页）→ 内容契约 0 违规 → 站点构建出文章页与三级目录页 → `platforms/blog/site` 的 126 条测试全绿。
