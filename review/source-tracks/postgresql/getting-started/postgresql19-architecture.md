---
status: 已合入
src: source-tracks/postgresql/getting-started/postgresql19-architecture.md
---

# 审校：PostgreSQL 19 的模块、进程与扩展

- 原文：docs/source-tracks/postgresql/getting-started/postgresql19-architecture.md
- 范围：全文
- 审校状态：已合入
- 目标读者：会用 PostgreSQL，但没读过它的源码；想知道「19 的内核分成几块、运行时有哪些进程、扩展挂在哪」的后端工程师
- 一句话定位：把 PostgreSQL 19 拆成三块坐标——内核模块划分、运行时进程模型、三层扩展点——每块都给出源码入口或可跑命令
- 核心判断：PostgreSQL 是**目录驱动的多进程系统**；它的骨架不是「一个大进程加线程」，而是「一个 postmaster + 十七种子进程 + 共享内存」，扩展也就挂在这套骨架的三个口子（系统目录、可加载模块、后台工作进程）上
- 对照源码：`/work/cwork/postgresql_2`，分支 `REL_19_STABLE`（发布说明落款 2026-11-19）

## 优先修改

1. 位置：`## 小结与延伸` 首句「内核按职责切成 26 个目录」
   - 问题（类别）：事实
   - 建议：26 改成 **28**
   - 原因：`ls -d src/backend/*/ | wc -l` = 28。正文「内核的七块」那节写的是 28（116 万行也对得上），只有小结这一处是 26——表对、句子错，是最容易被通读蒙过去的一类。开头那句「一句话答案」里同一组数字原本写的是「二十几块目录」，一并改成「二十八个目录」。

2. 位置：`## 进程种类：各自干什么`，并行工作进程那段引用的 `src/backend/access/transam/parallel.c:583`
   - 问题（类别）：事实
   - 建议：行号改成 **630**
   - 原因：`RegisterDynamicBackgroundWorker(&worker, ...)` 的调用点在 630 行；583 行落在这个文件的 `LaunchParallelWorkers()` 函数头上。行号指错，读者按图索骥会落到函数声明处。

3. 位置：`### contrib 里有什么` 首段
   - 问题（类别）：事实
   - 建议：「61 个目录，其中 55 个带 `.control` 文件，也就是 55 个可以直接装的官方扩展」改成「61 个目录，其中 49 个带 `.control` 文件——一共 55 个 `.control` 文件（`spi/` 一个目录里就放了 4 个），也就是 55 个可以直接 `CREATE EXTENSION` 装的官方扩展」；配图里那个框的标题从「contrib/ 61 个模块」改成「contrib/ 61 个目录」
   - 原因：`find contrib -name '*.control' | wc -l` = 55，但 `find contrib -name '*.control' | sed 's|contrib/||;s|/.*||' | sort -u | wc -l` = **49**——`spi/` 目录下有 4 个（autoinc / insert_username / moddatetime / refint），`bool_plperl`、`hstore_plperl`、`jsonb_plperl` 各有 2 个（普通版与 plperlu 版）。装得上的是 55 个扩展，分布在 49 个目录里，两个数不能混着说。

4. 位置：`## 进程种类：各自干什么`，十七行进程表之后
   - 问题（类别）：结构
   - 建议：补一段点明十八条 `PG_PROCTYPE` 里有一条不是进程——`B_INVALID` 是枚举的第 0 项（`src/include/miscadmin.h:341`），表示「这个进程还没认领类型」，所以真正跑得起来的类型是十七种
   - 原因：前一句写「列了 18 条 `PG_PROCTYPE` 宏」，紧接着的表只有 17 行，读者会以为漏了一种。原稿只有一句「这十七种之外还有两类借来的进程」，解释的是并行进程与逻辑复制进程，没解释 18 与 17 的差。

5. 位置：`## 怎么验证`，第二条 SQL
   - 问题（类别）：事实
   - 建议：`WHERE name IN (...)` 里 `'max_wal_senders'` 出现两次，删掉重复的那条，并把 `'max_wal_senders'` 换成 `'io_max_workers'`；上面那句「按进程类型列出内核登记的全部类型，以及每个类型有几个槽位」改成「进程数目上限由这几个参数决定」
   - 原因：查出来的是 GUC 的值，不是「进程类型」也不是「槽位」——注释与查询对不上；重复项说明这条查询没跑过就写下来了。

6. 位置：`## 怎么验证`，第三条 SQL
   - 问题（类别）：事实
   - 建议：`NOT IN` 列表里去掉 `'logical replication launcher'`，补上 `'startup'`、`'io worker'`、`'slot sync worker'`、`'syslogger'`；上面那句说明改成「剩下的行就是后台工作进程自己登记的类型名」
   - 原因：排除列表按 `proctypelist.h` 里第三列的 description 写才对。核对结果：`client backend`、`background writer`、`checkpointer`、`walwriter`、`archiver`、`autovacuum launcher`、`autovacuum worker`、`walreceiver`、`walsummarizer` 都是 description 原文；但 `logical replication launcher` 不是——它是 `src/backend/replication/logical/launcher.c:1034` 里注册的 `bgw_type`，按上一节讲的规则，`B_BG_WORKER` 显示的是 `bgw_type`，它本来就该出现在结果里。反过来 `startup`、`io worker`、`slot sync worker`、`syslogger` 是 description，会混进结果，把「剩下的就是自定义类型名」这句话搅浑。

7. 位置：`## 怎么验证`，`ps` 那条命令与它的输出样例
   - 问题（类别）：事实
   - 建议：`-o pid,ppid,stat,comm` 改成 `-o pid,ppid,stat,args`，样例里 postmaster 那一行改成完整的可执行文件路径
   - 原因：`comm` 是可执行文件名，18 个进程全叫 `postgres`；样例里那些「postgres: checkpointer」是 `args`（完整命令行）的形态。用 `comm` 配那样例输出，读者照着跑会看到一屏 `postgres`，以为命令不对。

8. 位置：`## 源码树：先知道哪扇门通往哪间屋子`，`src/interfaces/` 那一段
   - 问题（类别）：事实
   - 建议：补一句 19 还多了一个可选的 `libpq-oauth` 模块，实现 OAuth 的设备授权流程（RFC 8628）
   - 原因：`src/interfaces/` 下是 `libpq`、`ecpg`、`libpq-oauth` 三个目录。`libpq-oauth` 是 19 的新东西，且它自己那份 README 明说「从 v19 起这个模块 ABI 是公开的」——对一篇讲模块划分的稿子，这是 19 唯一一个「接口层新增目录」的例子。

9. 位置：`## 进程种类：各自干什么`，逻辑复制工作进程那段
   - 问题（类别）：事实
   - 建议：行号从「`launcher.c:518`」改成「`launcher.c:518` 往下——518、526、536、545 四处」
   - 原因：四个 `bgw_type` 分别落在 518、526、536、545 行，只给 518 会让读者以为只找到一种。

10. 位置：`## 小结与延伸`，预告下一篇的那一段
    - 问题（类别）：事实
    - 建议：原文「锁有三级（表级、行级、页级），但加锁的入口只有一个」改成「表级锁走 heavyweight lock 那一套……但**行级锁是两段**——谁锁住了这一行，记在元组头里；而一个 UPDATE 真正在等的那把锁，是对方事务的 `transactionid` 锁，不是行锁本身。」
    - 原因：这是全篇最该被读者记住的一句，写错了代价最大。三处都要说清：**行锁的「真值」在元组头**——`t_xmax` 加 `HEAP_XMAX_EXCL_LOCK` / `HEAP_XMAX_KEYSHR_LOCK` / `HEAP_XMAX_LOCK_ONLY` 标志位（`src/include/access/htup_details.h:218-224`）；**排队号牌是另一把锁**——`LOCKTAG_TUPLE`，`LockTuple()`（`src/backend/storage/lmgr/lmgr.c:562`）拿的，用完就放（`README.tuplock:191`）；**真正阻塞的是对方事务的锁**——`XactLockTableWait()`（`src/backend/storage/lmgr/lmgr.c:663`）去拿 `LOCKTAG_TRANSACTION` 的 `ShareLock`，`dontWait=false`，会一路走到 `ProcSleep`。原句把行锁当成一把锁、又把加锁入口说成只有一个，读者照着它去找 `LockAcquire` 会扑空；页级的 heavyweight lock 倒是有——`LOCKTAG_PAGE`（`src/include/storage/locktag.h:40`）配 `LockPage()`——但全树只有 GIN 拿它锁元页（`src/backend/access/gin/ginfast.c:815`）。

11. 位置：`## 内核的七块`（标题、首段「是七块」）与 `## 小结与延伸` 的「归成七块」
    - 问题（类别）：事实
    - 建议：全部改成「**六块**」，并把分组图拆成两张
    - 原因：分组表只有**六行**，逐目录对数也对得上——请求进来 4 个（parser / rewrite / optimizer / nodes）、把计划做出来 3 个、数据落在哪 4 个（access / storage / catalog / partitioning）、谁来跑 3 个、通用设施 3 个（utils / lib / port）、剩下 11 个，合计 28；六行的行数相加也正好是 1 161 472。原稿写「七块」，是**句子跟表对不上**——与第 1 条那处「26 个目录」同一类错误，通读时最容易蒙过去。原配图只画了五块、且第四块的标题（「把话变成计划」）跟表里的行名（「请求进来」）还不一样，两处一起改：图拆成两张（14 个框 + 14 个框，都在 15 框的上限内），框名改成跟表一致。
12. 位置：全篇措辞（「顶层只分三摊」「中间是五站」等）
    - 问题（类别）：措辞
    - 建议：自造的分类单位改成现成的说法
    - 原因：作者点名「三摊」不是计算机里的术语。读者在句子里遇到一个没有公认定义的词，只能从上下文反推作者想数什么——这是 [`review/specs/2026-11-24-术语纪律与反造词.md`](../specs/2026-11-24-术语纪律与反造词.md) 说的第一类造词。已改的八处：「三摊」→「三类」「五站」→「五个环节」（四处连用）→「防呆门」→「防呆检查」「版本门」→「版本检查」「落地过程」→「装进系统目录」「底子」→「跨平台那层代码」「试金石」→「最直接的办法」「哪扇门通往哪一间屋子」→「哪个目录归哪一块」。判据本身不放松：`rules/terminology.json` 的 `banned` 收了「三摊」——子串匹配只能收整词，「拿一个字当分类单位」这个**类别**仍然靠人判。
13. 位置：`## 源码树` 首段与 `## 怎么验证`
    - 问题（类别）：事实
    - 建议：把源码树钉到提交号 `20d6f4a`（2026-11-24 的分支头），并说明行数只在干净 checkout 上成立
    - 原因：`REL_19_STABLE` 是**活的分支**——文章写的是「源码取自 `REL_19_STABLE` 分支」，读者下周 checkout 到的行号就对不上了。另一个坑：构建过的树里多出 37 个生成文件（`gram.c`、`copyfuncs.funcs.c`、`nodetags.h` 等），加起来约 145 000 行，同一条 `find … | wc -l` 在两种树上给出 1 161 472 与 1 306 452 两个数。所以「怎么验证」那节补了两条命令，并写清这个数得在干净树上量。

## 事实待核

- [x] `src/backend/` 下是 **28** 个子目录、`.c` 与 `.h` 合计 **1 161 472** 行——依据：`ls -d src/backend/*/ | wc -l` = 28；在 `20d6f4a` 的干净 checkout 上 `find src/backend \( -name '*.c' -o -name '*.h' \) -type f -print0 | xargs -0 cat | wc -l` = 1161472。分组表六行相加也是 1 161 472：163 828 + 206 996 + 289 998 + 67 881 + 305 688 + 127 081。**这个数只在干净树上成立**：构建过的树里另有 37 个生成文件（`gram.c`、`copyfuncs.funcs.c`、`nodetags.h` 等，约 145 000 行），同一条命令会给出 1 306 452。
- [x] 分组是**六块**不是七块——依据：分组表六行，逐目录对数 4 + 3 + 4 + 3 + 3 + 11 = 28；六行行数相加 = 1 161 472。原稿写「七块」，与表对不上。
- [x] 三大目录的代码量：`utils/` = 297 115、`access/` = 165 968、`commands/` = 114 136——依据：逐目录 `find … | xargs wc -l`。三者合计 577 219，占 1 161 472 的 **49.70%**。
- [x] `access/` 下七个访问方法 = `heap`、`nbtree`、`hash`、`gist`、`spgist`、`brin`、`gin`——依据：`ls -d src/backend/access/*/`。另有 `table/`、`index/`、`transam/`。原稿把 B-tree 目录写成 `btree/`，已改。
- [x] `src/bin/` 顶层是 **21** 个可执行程序目录，`src/bin/scripts/` 里另有 **8** 个客户端小工具（`createdb`、`createuser`、`dropdb`、`dropuser`、`clusterdb`、`reindexdb`、`vacuumdb`、`pg_isready`）——依据：`ls -d src/bin/*/ | wc -l` = 22，逐个目录读 `Makefile` 的 `PROGAMS`。原文只写「共 21 个」，`scripts/` 里那 8 个程序被漏掉了。
- [x] `src/interfaces/` 下是 `libpq`、`ecpg`、`libpq-oauth` 三个目录；`libpq-oauth` 是 19 新增的可选模块，实现 OAuth 设备授权流程——依据：`src/interfaces/libpq-oauth/README`。
- [x] 进程类型是 **18** 条 `PG_PROCTYPE` 宏，其中 `B_INVALID` 是第 0 项哨兵，实际类型 **17** 种——依据：`src/include/postmaster/proctypelist.h`（`grep -c "^PG_PROCTYPE"` = 18，逐条读出 `B_INVALID = 0`）；`src/include/miscadmin.h:340` 的 `typedef enum BackendType`。
- [x] `backend_type` 的取值就是 `proctypelist.h` 第三列的 description——依据：18 条宏逐条读过，取值如 `client backend`、`background writer`、`walwriter`、`archiver`、`startup`、`io worker`、`slot sync worker`、`syslogger`、`walreceiver`、`walsummarizer`、`checkpointer`、`autovacuum launcher`、`autovacuum worker`、`dead-end client backend`、`standalone backend`。
- [x] `B_BG_WORKER` 在 `pg_stat_activity` 里显示的是注册的 `bgw_type`，不是枚举名——依据：`src/backend/utils/adt/pgstatfuncs.c:602-609`，`if (beentry->st_backendType == B_BG_WORKER)` 分支里取 `GetBackgroundWorkerTypeByPid()`。
- [x] 并行工作进程在 19 改走动态注册，`bgw_type` = `"parallel worker"`——依据：`src/backend/access/transam/parallel.c:607` 的 `snprintf(worker.bgw_type, …, "parallel worker")`，第 630 行调 `RegisterDynamicBackgroundWorker()`。
- [x] 逻辑复制工作进程的四种 `bgw_type` = `logical replication apply worker`、`logical replication parallel worker`、`logical replication sequencesync worker`、`logical replication tablesync worker`——依据：`src/backend/replication/logical/launcher.c:518 / 526 / 536 / 545`；另有 `logical replication launcher`（1034 行，逻辑复制启动器本身）。
- [x] `postmaster` 的状态机是 **13** 个状态——依据：`src/backend/postmaster/postmaster.c:336` 起的 `typedef enum`（`PM_INIT` … `PM_NO_CHILDREN`），第 353 行 `} PMState;`。
- [x] 客户端后端的槽位是 `2 × (MaxConnections + max_wal_senders)`——依据：`src/backend/postmaster/pmchild.c:111`。
- [x] `NUM_SPECIAL_WORKER_PROCS` = **2**——依据：`src/include/storage/proc.h:520`。
- [x] `MAX_BACKENDS` = `2^18 - 1` = **262 143**——依据：`src/include/storage/procnumber.h:38-39`（`MAX_BACKENDS_BITS 18`）。
- [x] `InitializeMaxBackends()` 在 `src/backend/utils/init/postinit.c:566`——依据：该行是函数定义行。
- [x] 内置共享内存子系统是 **43** 个——依据：`src/include/storage/subsystemlist.h`，`grep -c "^PG_SHMEM_SUBSYSTEM"` = 43。
- [x] `PG_MODULE_MAGIC` 宏在 `src/include/fmgr.h:530`——依据：第 530 行是 `#define PG_MODULE_MAGIC`（511 行是 `PG_MODULE_MAGIC_DATA`，548 行是 `PG_MODULE_MAGIC_EXT`）。
- [x] `CREATE EXTENSION` 的入口是 `CreateExtension()`，在 `src/backend/commands/extension.c:2279`——依据：第 2279 行是 `CreateExtension(ParseState *pstate, CreateExtensionStmt *stmt)`。
- [x] `REPACK CONCURRENTLY` 的解码 worker 入口是 `RepackWorkerMain`，在 `src/backend/commands/repack_worker.c:59`——依据：第 59 行是函数定义行。
- [x] `pg_extension` 是系统目录——依据：`src/include/catalog/pg_extension.h:31` 的 `CATALOG(pg_extension, 3079, ExtensionRelationId)`。
- [x] 19 的新增项：`contrib/pg_plan_advice`（控制优化器的关键决策、稳定计划）与 `contrib/pg_stash_advice`（`comment = 'store and automatically apply plan advice'`）——依据：两个目录都在树里，后者的 `.control` 自述用途。
- [x] `io_workers` 这个变量在 19 里没有了，换成 `io_min_workers`、`io_max_workers`、`io_worker_idle_timeout`、`io_worker_launch_interval` 四个——依据：`src/backend/utils/misc/guc_parameters.dat` 里 `grep -n "io_workers"` 无结果；`grep -n "name => 'io_"` 出这四个（另有 `io_method`、`io_combine_limit`、`io_max_combine_limit`、`io_max_concurrency`）。`io_max_workers` 的取值范围是 1–32（`postgresql.conf.sample:227`），所以进程表里 I/O 进程那行写「≤ 32」。
- [x] `REPACK` 与 `WAIT` 进了内核——依据：`doc/src/sgml/release-19.sgml` 里 `Introduce the REPACK command`（第 1201 行）与 `Implement WAIT FOR command`（第 1879 行）。
- [x] `wal_level = replica` 时逻辑复制可以不再重启就打开——依据：release-19.sgml 第 48-50 行的 Highlights 原句。
- [x] 19 的发布日期是 2026-11-19——依据：`doc/src/sgml/release-19.sgml` 第 9 行 `<para>2026-11-19</para>`。
- [x] `contrib/` 下是 61 个目录、55 个 `.control` 文件、分布在 49 个目录里——依据：`ls -d contrib/*/ | wc -l` = 61；`find contrib -name '*.control' | wc -l` = 55；按顶层目录去重后 = 49。
- [x] **行级锁是三样东西，不是三档粒度**——依据：① 真值在元组头：`src/include/access/htup_details.h:218-224` 的 `HEAP_XMAX_KEYSHR_LOCK`（0x0010）、`HEAP_XMAX_EXCL_LOCK`（0x0040）、`HEAP_XMAX_LOCK_ONLY`（0x0080）、`HEAP_XMAX_SHR_LOCK`；写这些位的是 `compute_new_xmax_infomask()`（`src/backend/access/heap/heapam.c:5541`）。② 排队号牌是 `LOCKTAG_TUPLE` 锁：`LockTuple()`（`src/backend/storage/lmgr/lmgr.c:562`）拿的，`README.tuplock:191` 明写「acquirers release it after each row」。③ 真正阻塞的是 `LOCKTAG_TRANSACTION` 锁：`XactLockTableWait()`（`src/backend/storage/lmgr/lmgr.c:663`）拿 `ShareLock`，`dontWait=false`。
- [x] 页级的 heavyweight lock 存在但几乎不用——依据：`src/include/storage/locktag.h:40` 的 `LOCKTAG_PAGE` 与 `SET_LOCKTAG_PAGE`（`src/backend/storage/lmgr/lmgr.c:511-546`）；全树用 `LockPage()` 的只有 GIN 锁元页（`src/backend/access/gin/ginfast.c:815`）与 `ConditionalLockPage()`（827 行）。heap 表的普通页靠 `LockBuffer(buffer, BUFFER_LOCK_EXCLUSIVE)`（`src/backend/access/heap/heapam.c:3401`），那是 buffer content lock，不进 `pg_locks`、不参与死锁检测。

## 可补的技术证据或产物

- 这一篇给的是坐标，读者真正会问的是「坐标怎么用」：可以把文末那张「想知道的 → 打开哪个文件」的表扩成**一条阅读动线**——比如「想知道一条 SELECT 怎么走到执行器」，从 `src/backend/tcop/postgres.c` 的 `exec_simple_query` 起步，依次落到 `parser/`、`analyze.c`、`optimizer/plan/`、`executor/execMain.c`，每一步给一个函数名。现在这张表是查手册式的，读者得自己接上。
- `pg_stat_activity` 那三段 SQL 缺**实际输出**。文中给的是「该跑什么」，没有「跑出来长什么样」。补一段真机输出（尤其是 `backend_type` 里出现 `parallel worker`、`logical replication apply worker` 这种自定义名），能直接印证本文最容易记错的那一点。
- 三块之内各缺一个「量出来」的数字：模块一块可以给 `utils/` 与 `access/` 的行数占比随版本的变化（把 18 与 19 的数放一起）；进程一块可以给一台真实实例上的进程数与各 `backend_type` 的计数；扩展一块可以给 `pg_available_extensions` 在 contrib 装齐后的行数。
- **下一篇的入口已经写在文末**（「行锁是怎么加上去的」），等第二篇过审之后，把那一行换成可点的相对链接——这一篇的「延伸」目前只是一个预告。

## 已确认的改动

- 数字与行号修了九处，全部改在 `drafts/source-tracks/postgresql/getting-started/postgresql19-architecture.md`，与 `docs/` 那份逐字节一致（`diff` 无差异）：目录数 26→28、「二十几块目录」→「二十八个目录」；`parallel.c:583`→`:630`；contrib 的 55→49（两处，含配图框标题）；逻辑复制四种 `bgw_type` 的行号补全；`pg_settings` 那条 SQL 去重并换 `io_max_workers`；第三条 SQL 的排除列表按 description 重列；`ps` 命令 `-o …,args` 与样例输出；`src/interfaces/` 补 `libpq-oauth`。
- 第九处之后又改了第十处（预告第二篇的那段）：「锁有三级……加锁的入口只有一个」改成「表级锁走 heavyweight lock 那一套……但行级锁是两段——谁锁住了这一行，记在元组头里；而一个 UPDATE 真正在等的那把锁，是对方事务的 `transactionid` 锁，不是行锁本身。」这一处是**合入后才发现的**——初稿把行锁当成一把锁、又把加锁入口说成只有一个，读者照着这句去找 `LockAcquire` 会扑空。改这一句时还改过一版更粗的（「行级锁不走 heavyweight lock 那一套」），复核源码后才发现行锁其实是三样东西（元组头里的真值、`LOCKTAG_TUPLE` 号牌、`LOCKTAG_TRANSACTION` 阻塞点），最后按第三版定稿。
- 补了一段说明十八条 `PG_PROCTYPE` 与十七种进程的差（`B_INVALID` 是第 0 项哨兵），补在十七行进程表之后。
- 三张目录页（`docs/source-tracks/postgresql/_index.md`、`docs/source-tracks/postgresql/getting-started/_index.md`，以及随之更新的 `drafts/` 那两份）**与这篇文章一起过审**：目录页只能列已过审的内容，两张页原先指向的是 11-24 撤下的那两篇稿子，现在改指这一篇。`docs/source-tracks/_index.md` 不需要改——它只指向「PostgreSQL」这个二级目录。
- 机械检查：`python3 tools/review-check.py drafts/source-tracks/postgresql/getting-started/postgresql19-architecture.md` → **0 警告 0 提示**，技术深度五要素全过（DEP-01=28、DEP-02=47、DEP-03=7、DEP-04=6、DEP-05=7）。目录页按文件名分流，只查链接、拼写、H1 与图示。
- 13 张 mermaid 图全部走公众号出包那条路渲染（`platforms/wechat/mermaid.py` 的 `render_mermaid`），逐张看过，版式正确。
- **第二轮（作者点名「三摊」之后）**：①按术语纪律把自造词清了一遍，共改九处措辞（详见「优先修改」第 12 条）；②复核数字时发现「七块」与表对不上，改成六块，分组图拆成两张并让框名与表一致；③源码树钉到 `20d6f4a`，「怎么验证」补上目录数与行数两条命令，并写清行数只在干净 checkout 上成立（构建过的树里多 37 个生成文件）。这一轮改动同样先落 `drafts/`，再覆盖 `docs/`，两份逐字节一致；公众号草稿**就地更新**（media_id 不变），头条号重新出包。
- 视频可行性：正文散文 7 431 字（去所有空白），按语速 7.19 字/秒算，full 档约 17 分钟；short 档压缩比约 17:1（限 100:1）、mid 档约 3.4:1（限 12:1）——三档都落在 `publish/spec/09-长视频三档.md` 的口径里。
