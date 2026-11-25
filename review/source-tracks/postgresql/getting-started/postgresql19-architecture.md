---
status: 已合入
src: source-tracks/postgresql/getting-started/postgresql19-architecture.md
---

# 审校：PostgreSQL 19 整体架构

- 原文：docs/source-tracks/postgresql/getting-started/postgresql19-architecture.md
- 范围：全文
- 审校状态：已合入
- 目标读者：读过 PostgreSQL 用法、想知道「19 里面到底有哪些部件、它们怎么说话」的后端工程师
- 一句话定位：把 PostgreSQL 19 从「一条 SQL 进去、一张表出来」的黑盒，拆成「进程、共享内存、存储、MVCC 与 WAL」四层坐标
- 核心判断：PostgreSQL 的骨架是**多进程 + 共享内存**，不是多线程；理解这一点，后面的锁、WAL、复制才有挂靠的地方
- 对照源码：`/work/cwork/postgresql_2`，分支 `REL_19_STABLE`

## 优先修改

1. 位置：`## 共享内存是怎么被登记的` → `### 内置子系统有 44 个`（含小节末尾一句与 `## 小结` 末尾一句）
   - 问题（类别）：事实
   - 建议：三处「44 个子系统」全部改成 **43**
   - 原因：`src/include/storage/subsystemlist.h` 里 `PG_SHMEM_SUBSYSTEM(...)` 宏调用实际是 43 条（`grep -cE "^PG_SHMEM_SUBSYSTEM\("` = 43，最后一条是第 89 行的 `AioShmemCallbacks`）。原文自己那张表列的是对的，只有散文里的计数多算了一个——这种「表对、句子错」最容易蒙过通读。

2. 位置：`### postmaster 自己是个状态机` 首段
   - 问题（类别）：事实
   - 建议：「一共 14 个状态」改成 **13**
   - 原因：`src/backend/postmaster/postmaster.c` 第 336 行往下的 `PMState` 枚举只有 13 个值（`PM_INIT` … `PM_NO_CHILDREN`）。原文紧跟着的那张状态表列的也正好是 13 行，同样是散文与表打架。

3. 位置：整篇（`## MVCC 与 WAL：两份元数据` 之后、`## 小结` 之前）
   - 问题（类别）：结构
   - 建议：补一节 `## 怎么验证`，按本文的顺序把骨架、共享内存、五站、页与缓冲池、MVCC 与 WAL 各给一组能跑的查询
   - 原因：检查器的「技术深度五要素」里，**可复现证据**这一项整篇命中 0 次——7 个代码块里 6 个是 mermaid 图，剩下 1 个是 C 宏，没有一条能照着跑的命令或 SQL。五要素只要命中两三项就够，但这一篇讲的是「怎么读源码」，读者最需要的恰恰是「怎么在跑起来的实例上把这一层看见」。补完这一节，可复现证据从 0 变成 9。

4. 位置：`### 页与缓冲池：8 KB 是真的` 标题与正文
   - 问题（类别）：可读性
   - 建议：正文补一句「`block_size` 的值就是 8192——8 KB 一页」，让标题里的「8 KB」在正文里落地
   - 原因：标题里的术语正文里没出现（HEAD-06 信号）。补这一句的同时把 8 KB 的来源指到 `block_size` 这个参数上，比原来只说「8 KB」更有据。

5. 位置：`## 共享内存是怎么被登记的` 之前
   - 问题（类别）：表达
   - 建议：标题前补一个空行
   - 原因：这一处二级标题紧贴在上一段的正文后面，中间没有空行。Markdown 渲染得出来，但同一篇里其他二级标题都有空行——排版不统一，读源码式文档时格外明显。这一篇共发现 1 处。

## 事实待核

- [x] 内置共享内存子系统是 **43** 个，不是 44——依据：`src/include/storage/subsystemlist.h`，`grep -cE "^PG_SHMEM_SUBSYSTEM\("` = 43；第 89 行是最后一条 `PG_SHMEM_SUBSYSTEM(AioShmemCallbacks)`。
- [x] `PMState` 是 **13** 个状态，不是 14——依据：`src/backend/postmaster/postmaster.c` 第 336 行往下的枚举，逐个列出是 `PM_INIT`、`PM_STARTUP`、`PM_RECOVERY`、`PM_HOT_STANDBY`、`PM_RUN`、`PM_STOP_BACKENDS`、`PM_WAIT_BACKENDS`、`PM_WAIT_XLOG_SHUTDOWN`、`PM_WAIT_XLOG_ARCHIVAL`、`PM_WAIT_IO_WORKERS`、`PM_WAIT_CHECKPOINTER`、`PM_WAIT_DEAD_END`、`PM_NO_CHILDREN`。
- [x] 进程类型表是 **18** 条 `PG_PROCTYPE(...)`，每条五个字段——依据：`src/include/postmaster/proctypelist.h`（`grep -c "^PG_PROCTYPE"` = 18）与宏定义 `PG_PROCTYPE(bktype, bkcategory, description, main_func, shmem_attach)`（`src/backend/postmaster/launch_backend.c` 第 180 行）。
- [x] `backend_type` 的取值就是进程类型表的 description 字段——依据：`src/backend/utils/init/miscinit.c` 第 264 行的 `GetBackendTypeDesc()`；`proctypelist.h` 里 `PG_PROCTYPE(B_BACKEND, "backend", gettext_noop("client backend"), ...)`。
- [x] 资源管理器是 **22** 条——依据：`src/include/access/rmgrlist.h`，`grep -cE "^PG_RMGR\("` = 22。
- [x] `src/backend/executor/` 下有 **43** 个 `node*.c`——依据：目录清点 = 43。
- [x] 页是 8 KB——依据：`src/backend/utils/misc/guc_parameters.dat` 第 374 行的 `block_size`（`PGC_INTERNAL`，值 8192）；`shared_buffers` 在同一文件第 2721 行。
- [x] WAL 段是 16 MB——依据：`src/include/pg_config_manual.h` 第 20 行的 `DEFAULT_XLOG_SEG_SIZE`；`wal_segment_size` 在 `guc_parameters.dat` 第 3568 行。
- [x] 缓冲区映射分成 128 份——依据：`src/include/storage/buf_internals.h` 的 `NUM_BUFFER_PARTITIONS`（128）。
- [x] `pg_shmem_allocations`、`pg_backend_memory_contexts`、`pg_control_checkpoint()` 的列名与来源——依据：`src/backend/catalog/system_views.sql` 第 691 行与第 709 行的视图定义；`src/include/catalog/pg_proc.dat` 第 8649 行（`pg_get_shmem_allocations`，列 `name, off, size, allocated_size`）、第 8681 行（`pg_get_backend_memory_contexts`，列 `name, ident, type, level, path, total_bytes, total_nblocks, free_bytes, free_chunks, used_bytes`）、第 12327 行（`pg_control_checkpoint`，含 `checkpoint_lsn`、`redo_lsn`、`redo_wal_file`、`timeline_id`、`checkpoint_time`）。
- [x] `EXPLAIN ANALYZE` 的 `Planning Time` 与 `Execution Time` 分属优化器与执行器——依据：`src/backend/commands/explain.c` 第 636 行与第 686 行。**服务端日志本身没有这个拆分**，不要写成「日志行里有 plan/execute 两段」——`check_log_duration()`（`src/backend/tcop/postgres.c` 第 2441 行）只给一个总时长。
- [x] `xmin` / `xmax` 是元组头里的两个事务 id——依据：`src/include/access/htup_details.h` 第 122 行的 `HeapTupleFields`（`t_xmin` 是插入事务，`t_xmax` 是删除或锁定事务）；系统列 `xmin` 的定义在 `src/backend/catalog/heap.c` 第 161 行。
- [x] 全文 **96 处**「`文件` 第 N 行」引用逐条核对过：文件都存在、行号都在文件范围内，且该行上下文中确实有文中所述的标识符——依据：对 `/work/cwork/postgresql_2` 全树做的自动核对 + 逐条人工复核。

## 可补的技术证据或产物

- 跑起来的实例上的**实际输出**：`pg_shmem_allocations` 的十几行、`pg_buffercache` 的十几行、`pg_control_checkpoint()` 的一行。现在文中给的是「该跑什么」，没有「跑出来长什么样」——补上实际输出，这篇的说服力会明显不一样。
- 异步 I/O 的**对比数字**：19 的 `io_method=worker` 与 18 的同步 I/O 在同一台机器上的吞吐与延迟。本文说了「19 在这一层动得最多」，但没有数字；这是这一篇最该补的实验。
- 内存上下文那节的**三层实例**：现在只给了查询，没给一棵真实的 `pg_backend_memory_contexts` 树。截一棵真树的图，比讲「三层结构」更直观。
- 下一篇的入口：文末已经指向 L2「存储引擎：页、文件与内存」，等那一站建好目录页之后，把链接换成站页的相对链接。

## 已确认的改动

- 三处数字改掉了：子系统 44→43（三处）、`PMState` 14→13。改在 `drafts/source-tracks/postgresql/getting-started/postgresql19-architecture.md`，与 `docs/` 那份逐字节一致（`diff -r` 无差异）。
- 补了一节 `## 怎么验证`，六组可跑的查询：进程类型、共享内存登记表、内存上下文三层、`EXPLAIN ANALYZE` 的 plan/execute 分界、页与缓冲池、MVCC 与 WAL 坐标。补完这一节，检查器的「可复现证据」从 0 变成 9，「技术深度五要素」从命中 4 项变成命中 5 项。
- 「页与缓冲池」那一节补了 `block_size` = 8192 的一句，HEAD-06 的信号也一并消掉。
- `## 共享内存是怎么被登记的` 标题前补了空行，全篇二级标题的空行规矩统一了。
- 三张目录页（`docs/source-tracks/_index.md`、`docs/source-tracks/postgresql/_index.md`、`docs/source-tracks/postgresql/getting-started/_index.md`）与这篇文章**一起过审**：它们是目录导航，不套技术深度五要素，但要列的文章必须都已过审——它们列的正是这一篇与同一站的第二篇。
- 机械检查：`python3 tools/review-check.py drafts/source-tracks/postgresql/getting-started/postgresql19-architecture.md --json` → **0 警告 0 提示**，五要素全过。
- 整条链路过了一遍：编译出 8 个内容单元（3 篇文章 + 5 张目录页）→ 内容契约 0 违规 → 站点构建出文章页与三级目录页 → `platforms/blog/site` 的 126 条测试全绿。
