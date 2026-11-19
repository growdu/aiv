# 全树范围分类：哪些不是面向读者的技术文章

- 日期：2026-11-14（2026-11-19 按清空后的 `docs/` 重做）
- 依据：`tools/review-check.py` 对 `docs/` 全树（20 篇）跑出的信号，加逐篇读原文的判断
- 目的：把审校范围限定在**面向读者的技术文章**上，
  免得把站点目录页、规则模板也按技术深度五要素去审。

## 五个桶

| 桶 | 含义 | 篇数 | 技术深度五要素 |
| --- | --- | --- | --- |
| 1 非内容 | 根本不面向读者：站点目录页、代码仓库说明、内部工作文档、外链指北、只有标题的未成稿 | 10 | 不审 |
| 2 速查/清单/操作类 | 面向读者，但形态是命令表、步骤、清单，没有成篇解释 | 0 | 不适用 |
| 3 非技术内容 | 面向读者，但写的是生活、备考、内部规范 | 9 | 不适用 |
| 4 转载内容 | 标了来源、署名他人的转载稿 | 0 | 不按原创稿审改 |
| 5 技术文章 | 面向读者的技术解释 | 1 | **审** |

**审校工作面 = 1 篇**（桶 5）。桶 2、3 面向读者但不是技术文章，
可选做表达与结构审，不套五要素；桶 1 不审；桶 4 是转载稿，
怎么处理（保留标注 / 删除 / 重写）是站长的决定。

## 判据

机械层（可复跑）：

- 目录页：文件名为 `_index.md`
- 代码仓库说明：路径在 `docs/engineering/engineering-practice/code/` 下
- 只有标题的未成稿：散文字符数为 0、无表格、无代码块、总字符 < 150
  （散文字符数 = 排开标题、代码块、表格、列表后的正文长度，引用块计入）

人工层（逐篇读过原文，一次判断写死）：

- 内部工作文档：开发交付计划、验证步骤、测试进度表、内部规范、个人数据记录
- 外链指北：正文只有 `# reference` 链接列表
- 速查/清单/操作类：有内容但形态是命令表、步骤、清单，没有机制解释
- 非技术内容：`docs/life/` 下的规则模板与个人记录；生活、备考类目录
- 转载内容：正文顶部有 `> 来源:` 标记，署名他人

复跑方式：

```bash
python3 tools/review-check.py docs --json --out /tmp/all_docs.json
```

## 逐支柱分布

| 支柱 | 总数 | 非内容 | 速查操作 | 非技术 | 转载 | 技术文章 | warn | DEP-00 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| life | 16 | 7 | 0 | 9 | 0 | 0 | 0 | 0 |
| source-tracks | 4 | 3 | 0 | 0 | 0 | 1 | 0 | 0 |
| **合计** | **20** | **10** | **0** | **9** | **0** | **1** | **0** | **0** |

## 排除清单

下面四桶逐篇列出。**桶 5 = `docs/` 全集减去这份清单**，不单独列。
契约测试守着两件事：清单里的路径不许悬空；审校记录的原文不许落在清单里。

### 桶 1 非内容（10 篇）

#### 站点目录页（10 篇）
- `docs/life/_index.md`
- `docs/life/aiv/_index.md`
- `docs/life/aiv/brand/_index.md`
- `docs/life/aiv/brand/scripts/_index.md`
- `docs/life/aiv/character/_index.md`
- `docs/life/aiv/music/_index.md`
- `docs/life/aiv/voice/_index.md`
- `docs/source-tracks/_index.md`
- `docs/source-tracks/postgresql/_index.md`
- `docs/source-tracks/postgresql/getting-started/_index.md`

### 桶 2 速查/清单/操作类（0 篇）

当前为空——清空之后 `docs/` 里没有命令表、步骤清单这类文章。

### 桶 3 非技术内容（9 篇）

视频线的规则模板与模块说明：写的是人格、形象、音色、曲库与品牌片，
不是技术解释。

- `docs/life/aiv/背景音乐规范.md`
- `docs/life/aiv/人格规范.md`
- `docs/life/aiv/形象与音色规范.md`
- `docs/life/aiv/brand/README.md`
- `docs/life/aiv/brand/scripts/README.md`
- `docs/life/aiv/character/README.md`
- `docs/life/aiv/index.md`
- `docs/life/aiv/music/README.md`
- `docs/life/aiv/voice/README.md`

### 桶 4 转载内容（0 篇）

当前为空——清空之后没有转载稿。
