# 实施计划：视频审核模块

> 上游规格：[../specs/2026-11-16-video-review-design.md](../specs/2026-11-16-video-review-design.md)
> 规范：[../README.md](../README.md)
>
> **纪律**（与本仓库其它计划一致）：
> - 每个 commit 完成立即提交，配套单元测试；
> - 每条新增守卫都要**注入缺陷验证它会红**；
> - 阈值写成字面量，一致性由另一条测试钉住；
> - 不静默成功、不静默截断：跳过要说出来。

---

## Task 1：规范、进度表与初始记录

- [x] `aiv/review/README.md`：审核规范（唯一权威）——原则、两层规则表、流程、记录模板、边界
- [x] `aiv/review/INDEX.md`：进度表，一行一期
- [x] `aiv/review/episodes/<EP>.md` × 6：初始记录，状态「待审」

**验收**：文件入库；`INDEX.md` 六行与 `episodes/` 六个文件一一对应；
`aiv/pipeline/tests/test_review.py` 里一条测试盯住这个对应关系。

## Task 2：文本层

- [x] `aiv/pipeline/pyv/review.py`：
  - `Signal` / `Report` 数据结构
  - `Materials` 与 `load_materials(episode)`：口播稿 + 字幕表 + 契约 + 母稿 + 出处表
  - `VT-01` 连接词开头占比 > 15%
  - `VT-02` 空泛评价且句中无数字
  - `VT-03` 结尾泛化收尾语
  - `VT-04` 近似重复句
  - `VT-05` 数字在母稿与出处表里找不到
  - `VT-06` 字幕丢了口播里的数字
  - `VT-07` 源字幕表里的禁止词与超宽行（阈值调 `pyv/timeline.py`）
- [x] 并入 `persona.py` 的 9 条结论（不重写）
- [x] `pyv/cli.py` 加 `review text` 子命令
- [x] `Makefile` 加 `review-text` 目标
- [x] 测试：七条规则各有注入缺陷验证

**验收**：`make review-text EP=<期号>` 出报告；七条规则各自能被注入触发。

## Task 3：成片层与抽帧

- [x] `pyv/review.py`：
  - `Media` 与 `load_media(episode)`：成片 + 时间轴 + 旁白 + BGM
  - `VV-01` 抽帧近乎纯色
  - `VV-02` 底部字幕带没有暗色像素
  - `VV-03` 正文区间旁白静音 > 1.0 s（阈值量出来的，见 README §3.2）
  - `VV-04` 成片时长与时间轴对不上
  - `VV-05` 关键帧间隔（调 `preflight.keyframe_gaps`）
  - `VV-06` 混音电平（调 `bgm.measure_mix` + `check_mix`）
  - `VV-07` 平台门槛（调 `preflight.check_video`）
  - `extract_frames()` + 抽帧清单（Markdown）：
    每段抽 2 帧（段中点 + 段尾 85%）加关键帧，
    「应有文案」递归摊平契约 `params`
- [x] `pyv/cli.py` 加 `review video` 与 `review frames` 子命令
- [x] `Makefile` 加 `review-video` / `review-frames` 目标
- [x] 测试：七条规则各有注入缺陷验证；产物缺失时显式「跳过」

**验收**：`make review-video EP=<期号>` 出报告；缺 ffprobe / 缺成片时报「跳过」而不是假装绿。

## Task 4：跨模块一致性

- [x] `test_text_rule_vocabulary_matches_the_document_checker`：
      `pyv/review.py` 的词表与 `tools/review-check.py` 逐字相同
- [x] `test_text_rule_thresholds_match_the_document_checker`：阈值数值相同
- [x] `test_review_records_match_the_index`：六期记录与进度表一一对应

**验收**：改文档侧词表 → 这条测试红。

## Task 5：六期实跑与结论落记录

- [x] 六期文本层实跑，信号进记录
- [ ] 六期抽帧，Agent 逐帧看，结论进记录（画面有没有漏字、文案对不对、讲不讲得清）
      - [x] ep06（row-lock）：成片已产出，20 帧全部看过，结论进 `episodes/row-lock.md`
      - [ ] ep01~ep05：本机没有成片产物，出片后补
- [x] 有信号的地方列改稿/改代码建议，状态推到「建议中」
- [x] `INDEX.md` 六行状态更新

**验收**：进度表能看出每一期走到哪一步；「已合入」的期有成片层复审通过。
