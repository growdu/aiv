# 抽帧清单

每一帧对着三件事看：**画面上有没有该有的字**、**字对不对**、**这一帧讲不讲得清**。

**段中点**是画面画得最完整的时刻，**段尾**是结论淡入完之后的样子（只看段中点会把动画中间态当成漏字）。

| 帧 | 类型 | 时间码 | 视觉段 | 应有文案 | 口播 | 文件 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 段中点 | 4.490s | s01 | 两个事务改同一行 / 谁先谁后 / MVCC 管读和写 · 行锁管写和写 · 四种模式一张矩阵 | 关注数据库内核的独立开发者 | `01_s01_mid.png` |
| 2 | 段尾 | 5.651s | s01 | 两个事务改同一行 / 谁先谁后 / MVCC 管读和写 · 行锁管写和写 · 四种模式一张矩阵 | 关注数据库内核的独立开发者 | `02_s01_late.png` |
| 3 | 段中点 | 9.524s | s02 | 两个事务改同一行 / users / id = 1 / T1 / T2 / name = 'X' / name = 'Y' / 两边都看不见对方，后写的覆盖先写的 / 读互不打扰，写却会互相覆盖 | 凭什么不能都改 | `03_s02_mid.png` |
| 4 | 段尾 | 11.888s | s02 | 两个事务改同一行 / users / id = 1 / T1 / T2 / name = 'X' / name = 'Y' / 两边都看不见对方，后写的覆盖先写的 / 读互不打扰，写却会互相覆盖 | 凭什么不能都改 | `04_s02_late.png` |
| 5 | 段中点 | 16.453s | s03 | MVCC 之上，加了一层行锁 / MVCC / 读和写 / 行锁 / 写和写 / KEY SHARE / FOR KEY SHARE / SHARE / FOR SHARE / NO KEY UPDATE / FOR NO KEY UPDATE / EXCLUSIVE / FOR UPDATE / 最弱 / 最强 / 四种模式，从最弱排到最强 | 4 种锁模式 | `05_s03_mid.png` |
| 6 | 段尾 | 18.939s | s03 | MVCC 之上，加了一层行锁 / MVCC / 读和写 / 行锁 / 写和写 / KEY SHARE / FOR KEY SHARE / SHARE / FOR SHARE / NO KEY UPDATE / FOR NO KEY UPDATE / EXCLUSIVE / FOR UPDATE / 最弱 / 最强 / 四种模式，从最弱排到最强 | 4 种锁模式 | `06_s03_late.png` |
| 7 | 段中点 | 23.224s | s04 | 冲不冲突，看一张矩阵 / 已经持有 / 我要申请 / KEY / SHARE / SHARE / NO KEY / UPDATE / EXCLUSIVE / 兼容 / 冲突 / 颜色 = 冲不冲突 / 最弱那一行，除了最强者谁都挡不住 | — | `07_s04_mid.png` |
| 8 | 段尾 | 25.477s | s04 | 冲不冲突，看一张矩阵 / 已经持有 / 我要申请 / KEY / SHARE / SHARE / NO KEY / UPDATE / EXCLUSIVE / 兼容 / 冲突 / 颜色 = 冲不冲突 / 最弱那一行，除了最强者谁都挡不住 | 4×4 兼容性矩阵 | `08_s04_late.png` |
| 9 | 段中点 | 30.645s | s05 | 锁不另起结构，就存在元组头里 / 元组头 / t_xmin / t_xmax / t_infomask / HEAP_XMAX_KEYSHR_LOCK / 0x0010 / HEAP_XMAX_EXCL_LOCK / 0x0040 / HEAP_XMAX_LOCK_ONLY / 0x0080 / HEAP_XMAX_IS_MULTI / 0x1000 / 只是锁住了，行没删 / 行真的被改了 / MultiXact / 多个事务锁同一行 / xmax 只装得下一个事务，装不下就换它 | — | `09_s05_mid.png` |
| 10 | 段尾 | 33.586s | s05 | 锁不另起结构，就存在元组头里 / 元组头 / t_xmin / t_xmax / t_infomask / HEAP_XMAX_KEYSHR_LOCK / 0x0010 / HEAP_XMAX_EXCL_LOCK / 0x0040 / HEAP_XMAX_LOCK_ONLY / 0x0080 / HEAP_XMAX_IS_MULTI / 0x1000 / 只是锁住了，行没删 / 行真的被改了 / MultiXact / 多个事务锁同一行 / xmax 只装得下一个事务，装不下就换它 | 装不下就交给 MultiXact | `10_s05_late.png` |
| 11 | 段中点 | 36.426s | s06 | 写与写之间 / 上游 PostgreSQL 的公开机制 / 独立开发者 · growdu | 上游的公开机制 | `11_s06_mid.png` |
| 12 | 段尾 | 37.531s | s06 | 写与写之间 / 上游 PostgreSQL 的公开机制 / 独立开发者 · growdu | 上游的公开机制 | `12_s06_late.png` |
| 13 | 关键帧 | 0.000s | brand_intro | — | — | `13_key_0.000.png` |
| 14 | 关键帧 | 2.917s | s01 | 两个事务改同一行 / 谁先谁后 / MVCC 管读和写 · 行锁管写和写 · 四种模式一张矩阵 | — | `14_key_2.917.png` |
| 15 | 关键帧 | 6.167s | s02 | 两个事务改同一行 / users / id = 1 / T1 / T2 / name = 'X' / name = 'Y' / 两边都看不见对方，后写的覆盖先写的 / 读互不打扰，写却会互相覆盖 | 订阅端怎么判断能不能一起做 | `15_key_6.167.png` |
| 16 | 关键帧 | 12.917s | s03 | MVCC 之上，加了一层行锁 / MVCC / 读和写 / 行锁 / 写和写 / KEY SHARE / FOR KEY SHARE / SHARE / FOR SHARE / NO KEY UPDATE / FOR NO KEY UPDATE / EXCLUSIVE / FOR UPDATE / 最弱 / 最强 / 四种模式，从最弱排到最强 | MVCC 只管读和写 | `16_key_12.917.png` |
| 17 | 关键帧 | 20.000s | s03 | MVCC 之上，加了一层行锁 / MVCC / 读和写 / 行锁 / 写和写 / KEY SHARE / FOR KEY SHARE / SHARE / FOR SHARE / NO KEY UPDATE / FOR NO KEY UPDATE / EXCLUSIVE / FOR UPDATE / 最弱 / 最强 / 四种模式，从最弱排到最强 | — | `17_key_20.000.png` |
| 18 | 关键帧 | 26.458s | s05 | 锁不另起结构，就存在元组头里 / 元组头 / t_xmin / t_xmax / t_infomask / HEAP_XMAX_KEYSHR_LOCK / 0x0010 / HEAP_XMAX_EXCL_LOCK / 0x0040 / HEAP_XMAX_LOCK_ONLY / 0x0080 / HEAP_XMAX_IS_MULTI / 0x1000 / 只是锁住了，行没删 / 行真的被改了 / MultiXact / 多个事务锁同一行 / xmax 只装得下一个事务，装不下就换它 | 锁藏在元组头里 | `18_key_26.458.png` |
| 19 | 关键帧 | 34.875s | s06 | 写与写之间 / 上游 PostgreSQL 的公开机制 / 独立开发者 · growdu | 上游的公开机制 | `19_key_34.875.png` |
| 20 | 关键帧 | 38.125s | brand_outro | — | — | `20_key_38.125.png` |
