---
status: 已合入
src: distributed/foundations/cap-consistency-tradeoffs.md
---

# 审校：CAP 讲的不是「三选二」

- 原文：docs/distributed/foundations/cap-consistency-tradeoffs.md
- 范围：全文
- 审校状态：已合入
- 目标读者：写过分布式存储、正在给「一致性 vs 可用性」拍板的后端工程师
- 一句话定位：把 CAP 从「三选二」的三角图，拉回「分区发生的那一刻你必须放弃哪一个」
- 核心判断：CAP 不是让你三样里挑两样常驻；分区发生时必须二选一，没有分区时你两者都要、付的是延迟的账

## 优先修改

1. 位置：`## 分区不是「宕机」` 末尾讲 available 的那一段
   - 问题（类别）：事实
   - 建议：按 Gilbert & Lynch 的原文改写——CAP 的可用性是「每个发往非故障节点的请求最终都要有一个响应」，**错误响应也算响应**；把「CAP 的字面定义」与「工程上说的用不了（拒绝服务 / 挂住不回）」分成两句话说。
   - 原因：原稿写的是「它返回错误，在 CAP 的定义里就已经是不 available 了」，这与原文相反。原文（SIGACT News 2002 §2.2）要的是 "must result in a response"，并补了一句 "any algorithm used by the service must eventually terminate"——只回 503 也算响应成功。评审时这句最容易被抬杠。

2. 位置：`## 怎么验证` 的实验二与实验三
   - 问题（类别）：结构
   - 建议：实验三从「注入延迟，而不是只注入断连」改成「丢一部分包（半开的连接）」，用 `tc qdisc add dev eth0 root netem loss 10%`；并在三组实验之后补上清理命令（`tc qdisc del` + 两条 `iptables -D`）。
   - 原因：原来的实验三是实验二的重复陈述（两段都在讲「注入延迟」），占了篇幅却没多给一步可复现的动作。改成丢包之后，三组实验刚好覆盖断连 / 延迟 / 丢包三种不同的客户端表现；补清理命令是因为读者照做会把自己的网卡留在注入状态。

3. 位置：`## 一致性级别怎么落到接口上` 的「按操作选级别」
   - 问题（类别）：表达
   - 建议：「**钱、库存、库存扣减**」→「**钱、库存扣减**」
   - 原因：同一行里「库存」出现两次。

4. 位置：`## 本文解决什么` 与 `## 一份可以带走的清单`
   - 问题（类别）：结构
   - 建议：两处的「延迟注入」同步成「延迟与丢包注入」
   - 原因：实验三改成丢包之后，原措辞与正文对不上；开头承诺的和结尾交付的要一致。

5. 位置：`## 「三选二」误读导致的三个具体后果` → 后果一里的 RTT 数字
   - 问题（类别）：事实
   - 建议：「同城机房 RTT 大概 0.5 毫秒」→「同城机房 RTT 通常在一毫秒以内」
   - 原因：0.5 毫秒是某个具体环境的数字，写成一般结论会误导；跨洲「30 毫秒起」是行业里普遍成立的下界，保留。

## 事实待核

- [x] Gilbert & Lynch 2002 的可用性定义（"every request received by a non-failing node in the system must result in a response"，以及脚注 4：Brewer 原本只要求「几乎所有请求」有响应）——依据：论文原文 PDF（cs.princeton.edu 课程镜像，第 2.2 节）。
- [x] 「错误响应也算响应」这个口径——依据同上：原文把 available 定义成 "must result in a response"，未附加「响应必须是成功」的限定。
- [x] Abadi et al. 2012 的 PACELC 表述：P 分区时在 A 与 C 之间选，E（else，正常运行时）在 L（latency）与 C 之间选——依据：论文原文 PDF（cs.umd.edu/~abadi/papers/abadi-pacelc.pdf，「PACELC」一节）。
- [x] 「CAP 只在分区**发生**时才逼你二选一，平时不分区时 CAP 并不禁止你降低一致性；平时那笔账是 PACELC 里的 E-L 账」——依据同上（论文明确说 "it is not merely the partition tolerance that necessitates a tradeoff … rather, the combination of partition tolerance and the existence of a network partition itself"）。
- [x] 「PACELC 里 E 是延迟，不是可用性」——依据同上（"else (E) … how does the system trade off latency (L) and consistency (C)"）。

## 可补的技术证据或产物

- 实验或观测：三组实验（etcd 3 成员 + iptables / `tc netem delay` / `tc netem loss`）的**实测输出**——写延迟的 p99 曲线、少数派侧写失败的实际报错。原文已经写明「这一节给的是可复现的步骤，不是我们的实测结论」，补上输出就更有说服力。
- 机制 / 源码入口：Raft 论文（Ongaro & Ousterhout, 2014）与 etcd 官方文档的入口没给；读者想顺着 quorum 往下挖时，现在只能自己找。
- 结尾清单或下一篇链接：`## 延伸阅读` 只有两篇论文，没有链回本系列。分类页是 `/docs/distributed/foundations/`，下一篇（一致性协议 / Raft 与 DCF）还没写——先链分类页也行。

## 已确认的改动

- 上面五条都已改进正文（`drafts/distributed/foundations/cap-consistency-tradeoffs.md`，与 `docs/` 那份逐字节一致）。
- 两张分类页（`docs/distributed/_index.md`、`docs/distributed/foundations/_index.md`）与这篇文章**一起过审**：它们是目录导航，不套技术深度五要素，但要列的文章必须都已过审——它们列的正是这一篇。
- 机械检查：`python3 tools/review-check.py docs/distributed/foundations/cap-consistency-tradeoffs.md --json` → **0 信号**，深度五要素全过。
- 整条链路过了一遍：编译出 3 个内容单元（1 篇文章 + 2 张目录页）→ 契约检查 0 违规 → 站点构建出文章页与两级目录页。
- 站点侧顺带修了两个真缺陷：
  1. `themes/matery/layout/docs-index.ejs` 里 `(site.posts || []).concat(...)`——`site.posts` 在 Hexo 里是 Query（warehouse 的查询对象），没有 `concat`；渲染抛 TypeError 被 Hexo 吞掉，目录页生成成 **0 字节的空文件**（`docs/` 里没有内容时没有目录页，所以这个洞一直没被看见）。同一个模板还有第二个坑：页面自己的 `permalink` 以 `index.html` 结尾、文章的以 `/` 结尾，形状对不上，目录页一个子级都列不出来。两处都已修，并补了守卫 `platforms/blog/site/tests/test_rendered_pages_are_not_silent.py`（空页面 / 非完整 HTML / 目录页列得出子级）。
  2. `.gitignore` 漏挡 `platforms/blog/site/source/docs/`——那是 `build-posts.py` 编出来的目录页（跟 `source/_posts/` 一样是产物）。第一个目录页出现时才暴露。
