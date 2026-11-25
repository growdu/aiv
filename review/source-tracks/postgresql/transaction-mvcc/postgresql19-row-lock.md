---
status: 已合入
src: source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md
---

# 审校：行锁——一次 UPDATE 加锁、等待与唤醒

- 原文：docs/source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md
- 范围：全文
- 审校状态：已合入
- 目标读者：会用 PostgreSQL，但没读过它的源码；想知道「UPDATE 卡住时，源码里发生了什么、怎么自己查出来」的后端工程师
- 一句话定位：把 PostgreSQL 19 的行锁拆成**元组头里的真值、`LOCKTAG_TUPLE` 号牌、`LOCKTAG_TRANSACTION` 阻塞点**三样，按调用链串起来，顺带讲清等待队列怎么排、死锁怎么被检出来
- 核心判断：所谓「行锁」不是一个数据结构，是**三个层次的机制叠在一起**——谁锁住了这一行记在元组头里，排队用的是一把用完就放的 heavyweight 号牌，真正让人卡住的是对方事务的事务锁；`pg_locks` 里能看到的只有最后那一样
- 对照源码：`/work/cwork/postgresql_2`，分支 `REL_19_STABLE`，分支头 `20d6f4a`（2026-11-24）

## 优先修改

1. 位置：`## 等待队列` 一节，唤醒那一段
   - 问题（类别）：事实
   - 建议：改成「唤醒走 `src/backend/storage/lmgr/proc.c:1813` 的 `ProcLockWakeup()`，调用点有两处：`lock.c:1820`（锁被释放之后）与 `deadlock.c:272`（软死锁重排队列之后）」
   - 原因：初稿写成「唤醒走 `lock.c:1820` 的 `ProcLockWakeup()`，它在 `proc.c:1813`」——**定义与调用点写反了**。`ProcLockWakeup()` 定义在 `proc.c:1813`；`lock.c:1820` 是 `LockRelease()` 里的调用点，`deadlock.c:272` 是软死锁重排队列之后的另一个调用点。读者按初稿去 `lock.c:1820` 找函数定义会扑空。

2. 位置：`## 等待队列` 一节，入队那一段
   - 问题（类别）：事实
   - 建议：整段重写——默认**加到队尾**；例外是「我已经持有这把锁上与某个等待者请求冲突的锁」，这时才插到那个等待者前面；插进去之后还有个特例，请求与插点之前的请求都不冲突就当场授予
   - 原因：初稿写「这个函数允许**插队**：第 1288 行有一句 `insert_before = proc`，按 PGPROC 号的大小决定插到谁前面——号小的插到号大的前面」。**这是凭 `insert_before = proc` 一行猜的**，源码里根本没有按 PGPROC 号排序的逻辑。实际规则在 `proc.c:1226` 起的注释里写着，插入点由「谁与我持有的锁冲突」决定，与进程号无关；`proc.c:1288` 那行只是把插队位置记下来。

3. 位置：`## 等待队列` 一节的标题与小结
   - 问题（类别）：事实
   - 建议：标题从「等待队列：不是先进先出」改成「等待队列：冲突的按到达顺序」；结尾改成「互相冲突的请求按到达顺序授予；不冲突的后来者可以先走」
   - 原因：`src/backend/storage/lmgr/README:384` 的原话是「Rule (b) ensures that conflicting requests are granted in order of arrival」——**冲突的请求本来就是按到达顺序授予的**，初稿那句「不是先进先出」会让人以为同一把锁上的请求可以乱序拿到。真正会「插到前面」的是不冲突的后来者，以及持有冲突锁时提前插队的那一个。附上 README 的原文，也就说清了机制。

4. 位置：`## 真值` 一节，UPDATE 与 `SELECT FOR UPDATE` 的对照
   - 问题（类别）：事实
   - 建议：明确分两条路——`heap_lock_tuple()`（`heapam.c:4762`，`SELECT ... FOR UPDATE` 走这条）在 `heapam.c:5374` 写 infomask、`heapam.c:5378` 写 `t_xmax`，锁位齐全且带 `HEAP_XMAX_LOCK_ONLY`；UPDATE 走 `heapam.c:4242`，**更新者的 xid 不带 `HEAP_XMAX_LOCK_ONLY` 位**——它是更新者，不是「只锁不改」的锁持有者
   - 原因：初稿把两条路混成一条，写成「写这些位的是 `compute_new_xmax_infomask()`」，读者会以为 UPDATE 也会把 `HEAP_XMAX_EXCL_LOCK` 写到旧元组上。实际 `compute_new_xmax_infomask()` 分两支：`is_update` 为真时（`heapam.c:5561` 起）只写 xmax 与 `HEAP_KEYS_UPDATED`，**不设** `HEAP_XMAX_EXCL_LOCK`；`is_update` 为假时（`heapam.c:5569` 起）才设 `HEAP_XMAX_LOCK_ONLY` 并在 switch 里按模式填锁位。

5. 位置：`## 真值` 一节，`compute_new_xmax_infomask()` 的行号
   - 问题（类别）：事实
   - 建议：函数在 `heapam.c:5536`，switch 在 `heapam.c:5570` 起（初稿写 5569）
   - 原因：5569 那行是 `new_infomask |= HEAP_XMAX_LOCK_ONLY;`，在 switch **之外**；switch 关键字在 5570。

6. 位置：`## 阻塞点` 一节，事务锁的冲突来源
   - 问题（类别）：事实
   - 建议：补一段——事务启动时 `XactLockTableInsert()`（`lmgr.c:622`，第 628 行）给自己记一把 `ExclusiveLock` 的事务锁，等的人要的是 `ShareLock`，共享与独占冲突
   - 原因：初稿只说等的人拿 `ShareLock`，没说对方手里那把是什么模式，读者无从判断「为什么冲突」。`lmgr.c:623` 是函数体的第一行，函数名在 622 行。

7. 位置：`## 号牌` 一节，`LockTupleTuplock()` 与 `tupleLockExtraInfo[]`
   - 问题（类别）：事实
   - 建议：说清 `LockTupleTuplock()` 是 `heapam.c:170` 的**宏**，作用是把行锁模式翻译成 heavyweight 锁模式；翻译用的表就是同文件 `heapam.c:129` 起的 `tupleLockExtraInfo[]`
   - 原因：初稿说 `tupleLockExtraInfo[]`「在需要 heavyweight 锁时才用得上」，与事实相反——每一行锁都要经过这个宏翻译，宏体就是 `LockTuple((rel), (tup), tupleLockExtraInfo[mode].hwlock)`。

8. 位置：`## 这段代码很新` 一节，两条提交的版本对应
   - 问题（类别）：事实
   - 建议：改成「PostgreSQL 16 才有这套结构，再早的版本里等的是 `SHM_QUEUE`」与「PostgreSQL 18 才有这个函数」
   - 原因：初稿写「PG19 里的 `JoinWaitQueue` 是 2024 年 11 月才有的函数」，读者会以为是 19 的新东西。`git merge-base --is-ancestor` 实测：两个提交都已在 `REL_18_0` 里（`5764f611e10b` 更是早在 `REL_16_0` 里），所以 18 与 19 都有 `JoinWaitQueue`，只有 17 及更早没有。

9. 位置：`## 这段代码很新` 一节末，补 `README` 落后于代码的一例
   - 问题（类别）：事实
   - 建议：补一段——`src/backend/storage/lmgr/README:362` 至今写的是「Lock acquisition (routines LockAcquire and ProcSleep) follows these rules」，第 377 行还在说「在 `ProcSleep` 里做这个检查很便宜」，而 `ProcSleep` 里已经没有这个检查了
   - 原因：这条对读者最有用——**连仓库自己的文档都还没跟上**，读老博客的代码片段前先确认版本的建议才立得住。`grep -n "JoinWaitQueue" src/backend/storage/lmgr/README` 无结果。

10. 位置：`## 怎么看` 一节，普通行锁那一段
    - 问题（类别）：措辞
    - 建议：「**普通行锁在 `pg_locks` 里是看不到的。**」改成「**「这一行被锁住了」这件事，在 `pg_locks` 里看不到。**」，并补一句 `locktype = 'tuple'` 的行是号牌本身
    - 原因：初稿那句话自相矛盾——`pg_locks` 里**有** `locktype = 'tuple'` 的行，只是它们是号牌，不是「这一行被锁住了」的证据。改后与下一段（`granted = false` 那一行才是阻塞点）不再打架。

11. 位置：`## 一个 UPDATE 从上往下走` 一节，`ExecUpdateLockMode()` 那一段
    - 问题（类别）：事实
    - 建议：写清判断条件是 `bms_overlap(keyCols, updatedCols)`，并把两个 return 的行号对上——键列被改给 `LockTupleExclusive`（`execMain.c:2582`），没改给 `LockTupleNoKeyExclusive`（`execMain.c:2584`）
    - 原因：初稿把两个模式列在前、两个行号列在后，读不出哪个对哪个；而且只说了结论，没说判断依据是哪一句。

12. 位置：全篇五张 mermaid 图
    - 问题（类别）：结构
    - 建议：核对每张图的框数与框名，逐张走一遍渲染
    - 原因：图是这篇文章的主要载体（作者要求「多画图」），框名与正文用语对不上会让读者在图和文字之间来回找。五张分别是：一次 UPDATE 的调用链（9 框）、三样东西的关系（5 框）、唤醒时挑人的规则（6 框）、死锁环里的硬边与软边（3 框）、`pg_locks` 的数据来源（4 框），都在 `MERMAID_MAX_NODES = 15` 之内。

## 事实待核

- [x] 表锁在**解析期**拿，行锁在**执行期**加——依据：`src/backend/parser/parse_clause.c:205` 的 `parserOpenTable(pstate, relation, RowExclusiveLock)`，它在同文件 178 行的 `setTargetTable()` 里；`parserOpenTable()` 的定义在 `src/backend/parser/parse_relation.c:1459`。行锁那一侧：`src/backend/executor/nodeModifyTable.c:2345` 调 `table_tuple_update()`，进 `src/backend/access/heap/heapam.c:3284` 的 `heap_update()`。
- [x] 行锁模式由 `ExecUpdateLockMode()` 决定，判断是 `bms_overlap(keyCols, updatedCols)`——依据：`src/backend/executor/execMain.c:2567`（函数定义行），第 2581 行 `if (bms_overlap(keyCols, updatedCols))`，第 2582 行 `return LockTupleExclusive;`，第 2584 行 `return LockTupleNoKeyExclusive;`。
- [x] UPDATE 路径上的三件事：先拿号牌、再等对方事务、最后复查——依据：`heapam.c:3687` 的 `heap_acquire_tuplock(relation, &(oldtup.t_self), *lockmode, LockWaitBlock, &have_tuple_lock)`（函数定义在 `heapam.c:5487`）、`heapam.c:3689` 的 `XactLockTableWait(xwait, relation, &oldtup.t_self, XLTW_Update)`、`heapam.c:3699` 的 `xmax_infomask_changed(...)` 判断加 `goto l2`。等待期间页的内容锁放开：`heapam.c:3686` 解锁、`heapam.c:3692` 重锁。
- [x] 号牌是 `LockTuple()`（`src/backend/storage/lmgr/lmgr.c:562`）拿的，用完就放——依据：`src/backend/access/heap/README.tuplock:191` 的原话「LOCKTAG_TUPLE acquirers release it after each row」；`LockTuple()` 内部调 `src/backend/storage/lmgr/lock.c:838` 的 `LockAcquire()`。
- [x] `LockTupleTuplock()` 是宏，翻译表是 `tupleLockExtraInfo[]`——依据：`src/backend/access/heap/heapam.c:170` 的 `#define LockTupleTuplock(rel, tup, mode) LockTuple((rel), (tup), tupleLockExtraInfo[mode].hwlock)`；表在同文件 129 行起，四项映射为 `KeyShare→AccessShareLock`、`Share→RowShareLock`、`NoKeyExclusive→ExclusiveLock`、`Exclusive→AccessExclusiveLock`。
- [x] 真正阻塞的是对方事务的事务锁——依据：`src/backend/storage/lmgr/lmgr.c:663` 的 `XactLockTableWait()`，第 695 行 `SET_LOCKTAG_TRANSACTION(tag, xid)`，第 697 行 `LockAcquire(&tag, ShareLock, false, false)`；`LockAcquire()` 的参数是 `(locktag, lockmode, sessionLock, dontWait)`，见 `lock.c:838` 与 `lock.c:819` 的参数说明。冲突对方是 `lmgr.c:622` 的 `XactLockTableInsert()`，第 628 行 `LockAcquire(&tag, ExclusiveLock, false, false)`。
- [x] 元组头里的锁位定义在 `src/include/access/htup_details.h:218` 起——依据：`HEAP_XMAX_KEYSHR_LOCK`（0x0010）、`HEAP_XMAX_EXCL_LOCK`（0x0040）、`HEAP_XMAX_LOCK_ONLY`（0x0080）、`HEAP_XMAX_SHR_LOCK`。
- [x] `SELECT FOR UPDATE` 与 UPDATE 写元组头的位置不同——依据：`heap_lock_tuple()`（`heapam.c:4762`）在 `heapam.c:5374` 写 `t_infomask`、`heapam.c:5378` 写 `t_xmax`，`compute_new_xmax_infomask()` 以 `is_update = false` 调用（`heapam.c:5349`），走 `heapam.c:5569` 起那支（设 `HEAP_XMAX_LOCK_ONLY`，switch 在 5570）；UPDATE 走 `heapam.c:4242` 的 `HeapTupleHeaderSetXmax(oldtup.t_data, xmax_old_tuple)`，`compute_new_xmax_infomask()` 以 `is_update = true` 调用（`heapam.c:3784`），走 `heapam.c:5561` 起那支，**不设** `HEAP_XMAX_EXCL_LOCK`。
- [x] 等待队列挂在锁上，入队在 `JoinWaitQueue()`——依据：`src/include/storage/lock.h:148` 的 `dclist_head waitProcs`、`src/include/storage/proc.h:311` 的 `PGPROC.waitLink`；`src/backend/storage/lmgr/proc.c:1176` 的 `JoinWaitQueue(LOCALLOCK *locallock, LockMethod lockMethodTable, bool dontWait)`；默认入队规则与例外写在 `proc.c:1226` 起的注释；插队位置在 `proc.c:1288` 记为 `insert_before = proc`。
- [x] 唤醒规则是「冲突的按到达顺序，不冲突的可以先走」——依据：`src/backend/storage/lmgr/proc.c:1813` 的 `ProcLockWakeup()`（用 `aheadRequests` 掩码累积前面等待者的请求模式），规则原文在 `src/backend/storage/lmgr/README:384`；调用点 `lock.c:1820` 与 `deadlock.c:272`。
- [x] 死锁检测只在超时路径上做——依据：`src/backend/storage/lmgr/proc.c:1951` 的 `CheckDeadLockAlert()`（信号处理器，设 `got_deadlock_timeout` 后 `SetLatch()`），`proc.c:1495` 判定该标志，`proc.c:1860` 的 `CheckDeadLock()`，`src/backend/storage/lmgr/deadlock.c:220` 的 `DeadLockCheck()`。`ProcLockWakeup()` 里没有死锁检测调用（`grep -n "ProcLockWakeup" src/backend/storage/lmgr/*.c` 只有定义与两处调用）。
- [x] 硬边与软边的判据——依据：`src/backend/storage/lmgr/deadlock.c:580` 扫 `PROCLOCK` 的 `holdMask`（硬边：对方已持有冲突锁）；`deadlock.c:632` 起扫等待队列（软边：对方排在前面）；`deadlock.c:378` 的 `TestConfiguration()` 按环里软边数区分硬软死锁（`deadlock.c:407` 判 `nSoftEdges == 0`）。
- [x] 硬死锁报错、软死锁重排队列——依据：`deadlock.c:1133` 的 `ereport(ERROR, ... errmsg("deadlock detected"))`，报错前 `proc.c:1917` 的 `RemoveFromWaitQueue()`；软死锁走 `deadlock.c:249` 起的队列重排（`dclist_init` 后按新顺序 `dclist_push_tail`），再 `deadlock.c:272` 的 `ProcLockWakeup()`。
- [x] `pg_locks` 是 `pg_lock_status()` 的壳，粒度是「一个进程的一把锁」——依据：`src/backend/catalog/system_views.sql:439` 的 `CREATE VIEW pg_locks AS`；实现 `src/backend/utils/adt/lockfuncs.c:93`；扫 `PROCLOCK` 表的是 `src/backend/storage/lmgr/lock.c:3809` 的 `GetLockStatusData()`。
- [x] `pg_blocking_pids()` 读的是 `GetBlockerStatusData()`——依据：`src/backend/utils/adt/lockfuncs.c:467` 的 `pg_blocking_pids()`；`src/backend/storage/lmgr/lock.c:4012` 的 `GetBlockerStatusData(int blocked_pid)`。
- [x] 页级 heavyweight lock 存在但几乎不用——依据：`src/include/storage/locktag.h:40` 的 `LOCKTAG_PAGE`；全树 `LockPage(` 的调用只有 `src/backend/access/gin/ginfast.c:815`（GIN 锁元页）。heap 表的普通页用 buffer 内容锁（`heapam.c:3400` 的 `LockBuffer(buffer, BUFFER_LOCK_EXCLUSIVE)`），不进 `pg_locks`、不参与死锁检测。
- [x] 两个提交对应的 PostgreSQL 版本——依据：`git merge-base --is-ancestor 5764f611e10b REL_16_0` 与 `... REL_18_0` 均为真（`dclist` 那套自 16 起）；`git merge-base --is-ancestor 3c0fd64fec8 REL_17_0` 为假、对 `REL_18_0` 为真（`JoinWaitQueue()` 自 18 起）。提交信息分别是 `5764f611e10 2023-01-18 Andres Freund Use dlist/dclist instead of PROC_QUEUE / SHM_QUEUE for heavyweight locks` 与 `3c0fd64fec8 2024-11-04 Heikki Linnakangas Split ProcSleep function into JoinWaitQueue and ProcSleep`。

## 可补的技术证据或产物

- 两段 `UPDATE` 的复现步骤是**照着源码写的**，还没有在真机上跑过——两会话卡住的实际现象、`pg_locks` 里那一行的确切 `locktype` 与 `mode`（`ShareLock`）、`pg_blocking_pids()` 返回的 pid，都该有一份真实输出附在文末。现在的写法是「预期会看到什么」，读者得自己跑一遍才知道对不对。
- 死锁那一节可以补一段**真机死锁复现**：两个会话各改两行、顺序相反，第二个会话报 `deadlock detected`；再配 `log_lock_waits = on` 的日志片段，把「等了多久才检测到」这件事量化出来。现在文里只有源码路径，读者对「死锁检测有多慢」没有直觉。
- 「等待队列不是先进先出」这条结论可以用一个并发实验坐实：三个会话改同一行，观察谁先拿到锁——不过这条在改写后已经变成「冲突的按到达顺序」，实验价值下降，优先级低。
- 文末那张「想知道的 → 打开哪个文件」的表可以补一行 `src/backend/access/heap/heapam.c` 里的 `heap_lock_tuple()`，并注明它与 `heap_update()` 是两条不同的路——现在表里只有文件名，读者还得自己分辨。
- **下一篇的入口已经写在文末**（`HeapTupleSatisfiesUpdate()` 怎么判断这一行能不能改），等第三篇过审之后，把那一行换成可点的相对链接。

## 已确认的改动

- 事实错误改了九处，全部改在 `drafts/source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md`，与 `docs/` 那份逐字节一致（`diff` 无差异）：`ProcLockWakeup` 的定义与调用点写反（改为 `proc.c:1813` 定义、`lock.c:1820` 与 `deadlock.c:272` 调用）；等待队列的插入规则重写（从「按 PGPROC 号插队」改成 `proc.c:1226` 注释里的真实规则）；队列标题与结尾按 `README:384` 改成「冲突的按到达顺序」；UPDATE 与 `SELECT FOR UPDATE` 写元组头的位置分开说清；`compute_new_xmax_infomask()` 的 switch 行号 5569→5570；补 `XactLockTableInsert()` 的 `ExclusiveLock` 冲突来源，行号 623→622；`LockTupleTuplock()` 标明是宏、`tupleLockExtraInfo[]` 的用法说准；两个提交对应的版本改成「16 起」「18 起」；`ExecUpdateLockMode()` 两个 return 的行号与模式对上。
- 第九处之后又补了三条：事务锁的冲突来源、`README` 落后于代码的一例、`pg_locks` 里普通行锁那句措辞。
- 两张目录页随这一篇一起过审：`docs/source-tracks/postgresql/transaction-mvcc/_index.md`（新建，L4 站页）与 `docs/source-tracks/postgresql/_index.md`（系列页，L4 那行从「未开目录」改成链接，并补一句 L4 第一篇讲什么）。目录页只能列已过审的内容，所以它跟文章同时落 `docs/`。
- 机械检查：`python3 tools/review-check.py drafts/source-tracks/postgresql/transaction-mvcc/postgresql19-row-lock.md` → **0 警告 0 提示**，技术深度五要素全过（DEP-01=13、DEP-02=69、DEP-03=7、DEP-04=1、DEP-05=7）。两张目录页单独跑，同样 0 信号。
- 五张 mermaid 图全部走公众号出包那条路渲染（`platforms/wechat/mermaid.py` 的 `render_mermaid`），逐张看过，版式正确。
- 视频可行性：母稿散文 **7 730 字**（`video/pipeline/pyv/motherdoc.py` 的 `load_motherdoc()` 实测，去空白口径），按语速 7.19 字/秒算——full 档散文全读约 1 075 秒（≈ 18 分钟）、压缩比 1:1（限 1.5:1）；mid 档 2 157~4 314 字，最差压缩比 3.6:1（限 12:1）；short 档 ≤ 431 字，最差压缩比 17.9:1（限 100:1）——三档都落在 `publish/spec/09-长视频三档.md` 的口径里。
