# episodes —— 一期一个目录

**一期 = `video/episodes/<slug>/` 一个目录。** 目录就是接口：
一期在磁盘上是什么，路径说了算；流水线里没有期号登记表，
加一期不用改代码。

| 文件 | 是什么 | 入库 |
| --- | --- | --- |
| `口播稿.md` | 这一期的母稿：口播句子 + 字幕表 | ✅ |
| `contract.json` | 视觉分镜契约：哪几句配哪张图、图上写什么 | ✅ |
| `publish.json` | 发布元数据：各平台的标题、简介、话题与分区 | ✅ |
| `narration.mp3` | 旁白音频（出片必需） | ✅ |
| `storyboard.json` | 时间轴（由 `align` 从旁白算出来） | ❌ 产物 |
| `review.md` | 这一期的审校记录 | ✅ |
| `frames.md` | 抽帧清单 | ✅ |
| `frames/` | 抽出来的帧 | ❌ 产物 |

## slug 与期号不是一回事

- **slug 是身份**：英文 kebab-case，进路径、进 JSON 字段、进命令行参数。
  改标题不改 slug，所以文件链接不会因为改标题而失效。
- **期号（`ep01`…）是播放顺序**：编辑事实，不是身份。
  它落在两个地方，两边对得上才算数：
  - 口播稿的 front matter：`episode_number: ep01`
  - 《选题库》里那一期的 `id`：`ep01`

口播稿的 front matter 里**两个名字都在**：`episode` 记 slug（跟期目录名
一致），`episode_number` 记期号。流水线用期号去《选题库》找母稿与数字出处
（`pyv/review.py` 的 `VT-05`）。取不到就记一条 note 跳过，不静默放过。

## 新建一期

```bash
mkdir -p video/episodes/<slug>
```

然后往里放 `口播稿.md`（带 front matter 的 `episode:` 与 `episode_number:`）、
`contract.json`，再合成旁白：

```bash
python3 video/voice/scripts/synthesize_narration.py \
    --script video/episodes/<slug>/口播稿.md \
    --out video/episodes/<slug>/narration.mp3
```

出片：

```bash
cd video/pipeline
make EP=<slug> align     # 按旁白对齐出时间轴
make EP=<slug> all       # validate → brand → render → compose
```

**忘了 `EP=` 就跑 `make` 会当场报错**，不会拿空路径去跑，
也不会静悄悄地拿上一期的稿子出片。

## 这份文件是说明文件，不是内容

`README.md` 是说明，不是一期，所以它不进 `episodes/` 的期列表
（`pyv.episodes.known_eps()` 只认子目录）。
这一层与文档侧同一条纪律：说明文件不进 `docs/`。
