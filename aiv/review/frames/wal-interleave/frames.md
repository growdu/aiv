# 抽帧清单

每一帧对着三件事看：**画面上有没有该有的字**、**字对不对**、**这一帧讲不讲得清**。

**段中点**是画面画得最完整的时刻，**段尾**是结论淡入完之后的样子（只看段中点会把动画中间态当成漏字）。

| 帧 | 类型 | 时间码 | 视觉段 | 应有文案 | 口播 | 文件 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 段中点 | 4.417s | s01 | WAL 里的顺序 / 不等于事务的顺序 / 操作级记录 · 按事务号归并 · 提交才发出 | 关注数据库内核的独立开发者 | `01_s01_mid.png` |
| 2 | 段尾 | 5.542s | s01 | WAL 里的顺序 / 不等于事务的顺序 / 操作级记录 · 按事务号归并 · 提交才发出 | 关注数据库内核的独立开发者 | `02_s01_late.png` |
| 3 | 段中点 | 10.542s | s02 | WAL 是操作级记录，几个事务交错了 / WAL 位置（LSN） / T1 / T2 / T3 / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 颜色 = 事务 / 同一个事务的记录，被别的事务隔开了 | WAL 一条只写一个动作 | `03_s02_mid.png` |
| 4 | 段尾 | 13.708s | s02 | WAL 是操作级记录，几个事务交错了 / WAL 位置（LSN） / T1 / T2 / T3 / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 颜色 = 事务 / 同一个事务的记录，被别的事务隔开了 | 6 条记录三个事务交错 | `04_s02_late.png` |
| 5 | 段中点 | 20.250s | s03 | 按事务号，攒进各自的槽 / ReorderBuffer / 一个事务一个槽 / T1 / T2 / T3 / 10 / 11 / 12 / xid / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 事务号是唯一的归并依据 | 靠 WAL 里的事务号 | `05_s03_mid.png` |
| 6 | 段尾 | 23.917s | s03 | 按事务号，攒进各自的槽 / ReorderBuffer / 一个事务一个槽 / T1 / T2 / T3 / 10 / 11 / 12 / xid / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 事务号是唯一的归并依据 | ReorderBuffer 一个事务一个槽 | `06_s03_late.png` |
| 7 | 段中点 | 27.458s | s04 | 槽里攒的太多，会落到磁盘上 / 内存 / 磁盘 / spill / INSERT / INSERT / UPDATE / UPDATE / DELETE / INSERT / 落盘了，事务的完整性一样不受影响 | 攒多了 spill 到磁盘 | `07_s04_mid.png` |
| 8 | 段尾 | 28.833s | s04 | 槽里攒的太多，会落到磁盘上 / 内存 / 磁盘 / spill / INSERT / INSERT / UPDATE / UPDATE / DELETE / INSERT / 落盘了，事务的完整性一样不受影响 | — | `08_s04_late.png` |
| 9 | 段中点 | 31.500s | s05 | 提交记录出现，才整组发出去 / ReorderBuffer / 整组发出 / 订阅端 / T1 / INSERT / UPDATE / COMMIT / T2 / INSERT / UPDATE / T3 / DELETE / T1 / COMMIT / 发出去的是提交顺序，不是物理顺序 | 提交记录出现才整组发出 | `09_s05_mid.png` |
| 10 | 段尾 | 32.917s | s05 | 提交记录出现，才整组发出去 / ReorderBuffer / 整组发出 / 订阅端 / T1 / INSERT / UPDATE / COMMIT / T2 / INSERT / UPDATE / T3 / DELETE / T1 / COMMIT / 发出去的是提交顺序，不是物理顺序 | 提交记录出现才整组发出 | `10_s05_late.png` |
| 11 | 段中点 | 35.458s | s06 | 一个事务一整组 / CSN 是 openGauss 额外加的 / 独立开发者 · growdu | CSN 是 openGauss 额外加的 | `11_s06_mid.png` |
| 12 | 段尾 | 36.792s | s06 | 一个事务一整组 / CSN 是 openGauss 额外加的 / 独立开发者 · growdu | CSN 是 openGauss 额外加的 | `12_s06_late.png` |
| 13 | 关键帧 | 0.000s | brand_intro | — | — | `13_key_0.000.png` |
| 14 | 关键帧 | 2.958s | s01 | WAL 里的顺序 / 不等于事务的顺序 / 操作级记录 · 按事务号归并 · 提交才发出 | — | `14_key_2.958.png` |
| 15 | 关键帧 | 6.042s | s02 | WAL 是操作级记录，几个事务交错了 / WAL 位置（LSN） / T1 / T2 / T3 / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 颜色 = 事务 / 同一个事务的记录，被别的事务隔开了 | — | `15_key_6.042.png` |
| 16 | 关键帧 | 15.042s | s03 | 按事务号，攒进各自的槽 / ReorderBuffer / 一个事务一个槽 / T1 / T2 / T3 / 10 / 11 / 12 / xid / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 事务号是唯一的归并依据 | — | `16_key_15.042.png` |
| 17 | 关键帧 | 25.042s | s03 | 按事务号，攒进各自的槽 / ReorderBuffer / 一个事务一个槽 / T1 / T2 / T3 / 10 / 11 / 12 / xid / 100 / T1 / INSERT / 110 / T2 / INSERT / 120 / T1 / UPDATE / 130 / T3 / DELETE / 140 / T2 / UPDATE / 150 / T1 / COMMIT / 事务号是唯一的归并依据 | — | `17_key_25.042.png` |
| 18 | 关键帧 | 29.417s | s05 | 提交记录出现，才整组发出去 / ReorderBuffer / 整组发出 / 订阅端 / T1 / INSERT / UPDATE / COMMIT / T2 / INSERT / UPDATE / T3 / DELETE / T1 / COMMIT / 发出去的是提交顺序，不是物理顺序 | — | `18_key_29.417.png` |
| 19 | 关键帧 | 33.542s | s06 | 一个事务一整组 / CSN 是 openGauss 额外加的 / 独立开发者 · growdu | — | `19_key_33.542.png` |
| 20 | 关键帧 | 37.458s | brand_outro | — | — | `20_key_37.458.png` |
