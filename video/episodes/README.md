# episodes —— 一期一个档位目录

**坐标就是接口。** 期根是 `video/episodes/`，往下四层：

```
video/episodes/<系列>/<合集>/<文档>/<档位>/
                 一级   二级   三级   四级
```

| 层 | 是什么 | 例子 |
| --- | --- | --- |
| 一级 | **系列**——一条主线 | `postgresql` |
| 二级 | **合集**——主线下的一块 | `getting-started` |
| 三级 | **文档**——一篇母稿 | `postgresql基操` |
| 四级 | **档位**——这篇文档的三条片子 | `short` / `mid` / `full` |

**一期 = 一个档位目录。** 同一篇文档的三档是三期，各有自己的口播稿、契约与旁白；
它们共享的是那一篇文档的骨架（`skeleton.yaml`，放在文档目录里，三档共用）。

**没有登记表。** 目录就是登记表：建目录、放文件，就是新的一期。
流水线里没有任何一张「期号 → 目录」的映射表要维护——以前有，
现在没有了，因为坐标本身就是那张表。

## 四个名字，别混

| 名字 | 是什么 | 落在哪 |
| --- | --- | --- |
| **期路径** | 身份：期目录相对期根的路径，四段 | 命令行 `EP=`、审校记录、进度表 |
| **文档路径** | `系列/合集/文档`——母稿的身份，三段 | 口播稿 front matter 的 `episode` |
| **档位** | short / mid / full | 口播稿 front matter 的 `tier`，也是目录名 |
| **期号** | 播放顺序 `ep01` | 口播稿 front matter 的 `episode_number` |

期路径的例子：

```
postgresql/getting-started/postgresql基操/short
└──── 一级 ────┘ └─ 二级 ─┘ └── 三级 ──┘ └ 四级 ┘
```

期路径会**压平**成一个文件名片段（斜杠换连字符），`out/` 与 `build/` 里用的就是它：

```
postgresql/getting-started/postgresql基操/short
→ postgresql-getting-started-postgresql基操-short.mp4
```

压平的理由很实际：`out/` 下面会长出一层一层的目录，翻起来费劲，
而期号之外的层级信息（系列/合集/文档/档位）已经全在压平后的名字里了。

期号（`ep01`）是**播放顺序**，编辑事实，不是身份：它落在两个地方，
两边对得上才算数——口播稿的 front matter（`episode_number`）与
《选题库》里那一期的 `id`。流水线用期号去《选题库》找母稿与数字出处
（`pyv/review.py` 的 `VT-05`）；取不到就记一条 note 跳过，不静默放过。

## 一个档位目录里有什么

| 文件 | 是什么 | 入库 |
| --- | --- | --- |
| `口播稿.md` | 这一期的母稿：口播句子 + 字幕表 | ✅ |
| `contract.json` | 视觉分镜契约：哪几句配哪张图、图上写什么 | ✅ |
| `publish.json` | 发布元数据：各平台的标题、简介、话题与分区 | ✅ |
| `review.md` | 这一期的审校记录 | ✅ |
| `frames.md` | 抽帧清单 | ✅ |
| `narration.mp3` | 旁白音频（TTS 合成，要联网重合成） | ❌ 本机素材 |
| `storyboard.json` | 时间轴（由 `align` 从旁白算出来） | ❌ 产物 |
| `frames/` | 抽出来的帧 | ❌ 产物 |

**文档目录**（三层 `系列/合集/文档/`）里另有一样东西：

| 文件 | 是什么 |
| --- | --- |
| `skeleton.yaml` | 讲稿骨架——一篇母稿解析出来的中间物，**三档共用** |

骨架放在文档目录而不是档位目录，是因为它记的是**这篇文档讲什么**，
而那是三档共享的东西：short/mid/full 是同一篇稿子的三种长度，
骨架拆一次就够，不必拆三遍。

**入库的是事实，产物与素材都不入库**：
口播稿、契约、发布元数据、审校记录、抽帧清单入库；
时间轴、抽出来的帧是产物；旁白是 TTS 合成出来的本机素材。
判据见 `pipeline/tests/test_assets_are_tracked.py`。

## 怎么建一期

```bash
# 期根下四层：系列/合集/文档/档位
mkdir -p video/episodes/postgresql/getting-started/postgresql基操/short
```

口播稿的 front matter 记着三个名字，缺一个流水线就认不出这一期：

```yaml
---
title: "PostgreSQL 基操 · 短版"
episode: postgresql/getting-started/postgresql基操   # 文档路径
episode_number: ep01                                  # 期号
tier: short                                           # 档位
---
```

然后放 `contract.json`，再合成旁白：

```bash
python3 video/voice/scripts/synthesize_narration.py \
    --script video/episodes/postgresql/getting-started/postgresql基操/short/口播稿.md \
    --out video/episodes/postgresql/getting-started/postgresql基操/short/narration.mp3
```

出片：

```bash
cd video/pipeline
make EP=postgresql/getting-started/postgresql基操/short align   # 按旁白对齐出时间轴
make EP=postgresql/getting-started/postgresql基操/short all     # validate → brand → render → compose
```

`align` 是手工步骤，要单独跑（在 `all` 之前）。

**忘了 `EP=` 就跑 `make` 会当场报错退出 2**，不会拿空路径去跑，
也不会静悄悄地拿上一期的稿子出片。期路径写错了也一样——目录不存在时直接报错。

## 这份文件是说明文件，不是内容

`README.md` 是说明，不是一期，所以它不进 `episodes/` 的期列表
（`pyv.episodes.known_eps()` 只认深度为 4、末段是档位名的目录）。
这一层与文档侧同一条纪律：说明文件不进 `docs/`。
