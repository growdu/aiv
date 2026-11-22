# video — 品牌系列视频的生产线

把写好的技术文章，变成一条能持续产出、还能被复现的成片流水线。

技术图示一律由代码绘制（cairo + ffmpeg），不交给模型生成；
形象是 3D 静帧 + 位移/缩放/淡入，文字用真实字体在 cairo 阶段渲染。
**入库的是事实**（规范、契约、台账、代码），**产物不入库**（成片、片段、时间轴、发布包留本机）。
**素材归使用者**：立绘、曲库、品牌片是「用这套流水线的人」自己的东西——
版权是他们的，口味也是他们的，所以它们不进仓库，只在
[`config.toml`](config.toml) 里声明位置。
**素材缺失不是错误**：没配就是没配，流水线降级（不画形象 / 不铺 BGM / 不带品牌片），
照样出片；**配了但文件不在**才是错，`make doctor` 会单独报出来。
见[上机指南.md](上机指南.md)。

## 用户怎么用（通过 AI）

用户**不直接敲命令**，而是用一句话告诉 AI，AI 照本 README 与 [`episodes/README.md`](episodes/README.md) 去驱动：

| 用户说 | AI 做的事 |
| --- | --- |
| 「给 AIV 加一期讲 X 的短视频」 | 在 `episodes/AIV/<合集>/<文档>/<档位>/` 建四层目录（建目录即登记），放 `口播稿.md` + `contract.json`，合成旁白 |
| 「这期出片 / 出个竖版给抖音」 | `cd pipeline && make EP=<期路径> align`，再 `make EP=... all`（抖音 `vertical`、无品牌 `nobrand`） |
| 「这期发 B站/视频号/抖音」 | 对应平台 adapter `manual` 档出包，**上传与点发表留给人** |

入口总览见 [`../AGENTS.md`](../AGENTS.md) §五。**忘了 `EP=` 会退出 2**，不会拿空路径跑。

## 目录

| 目录 | 内容 |
| --- | --- |
| `pipeline/` | 出片流水线：`pyv/` 渲染引擎 + `tests/` + `Makefile` |
| `episodes/` | 期的坐标：四层 `系列/合集/文档/档位`，**一期 = 一个档位目录**，口播稿、契约、发布元数据、旁白、审校记录都在里面 |
| `review/` | 视频审校的规则（文本层 `VT-*`、成片层 `VV-*`），一期的审校记录与抽帧清单在期目录里 |
| `character/` | 3D 角色形象：生成、加眼镜、铭牌盖章（`scripts/`） |
| `brand/` | 品牌片头/片尾：渲染与配乐（`scripts/`） |
| `voice/` | 旁白音色与合成（`scripts/`） |
| `music/` | 背景音乐曲库：授权台账（入库，是授权事实）+ 曲库文件（用户自带，不入库） |

## 配置入口

素材的位置不写死在代码里，也不写死在 Makefile 里，而是写在
[`config.toml`](config.toml) 里——那是**框架与使用者之间那道缝**：

```toml
[brand]
name = "<站名>"       # 落版与片尾字幕上的名字
token = "<品牌词>"    # 品牌词：画面里出现它就算有品牌标识
tagline = "<标语>"    # 片头副标题
site = "<站点地址>"   # 片尾落版

[assets.mascot]
image = ""             # 立绘（透明底 PNG）；空 = 不画形象
plain = ""             # 无标牌立绘（可选）

[assets.avatar]
image = ""             # 落版头像（可选）

[assets.music]
dir = "music/tracks"       # 曲库目录
bed = ""                   # 正文铺底那首；空 = 不铺 BGM
library = "music/library.json"

[assets.brand]
clips = "brand/clips"     # 品牌片
audio = "brand/audio"     # 品牌成品音轨
windows = "brand/brand_windows.json"
```

上面 `<站名>` / `<品牌词>` / `<标语>` / `<站点地址>` 是**占位**，
取值分别见 `[brand].name` / `[brand].token` / `[brand].tagline` / `[brand].site`；
角色产物文件名前缀见 `[character].slug`，角色外观描述见 `[character].look`。

三条规矩：

- **相对路径按配置文件所在目录解析**；绝对路径照用。
- **环境变量 `VIDEO_CONFIG`** 指到别的配置文件——同一个仓库里跑两套片子时用。
- **素材缺失不是错误**。没配就是没配，流水线降级出片；配了但文件不在才是错。

脚本怎么问配置要值：

```bash
cd video/pipeline
python3 -m pyv.cli config <key>
```

支持的 key：`path`、`brand_name`、`brand_token`、`brand_tagline`、`brand_site`、
`mascot`、`mascot_plain`、`avatar`、`music_dir`、`bgm`、`music_library`、
`brand_clips`、`brand_audio`、`brand_windows`。
**没配就打印空行**——脚本据此「不传这个参数」。

**内置字体不在配置里**：它是规则级的东西（两台机器用同一份字体文件，
跨机版式才一致），跟着仓库走。

**品牌文案也在配置里**：片头/片尾的品牌片副标题、成片旁白、片头药丸那句话、
片尾落版的标题与标签，全都在 `[brand]` 的 `intro_tagline`、`outro_subtitle`、
`outro_narration`、`intro_line`、`outro_line`、`share_suffix`、`share_emphasis`、
`outro_title`、`outro_labels` 里——脚本只读这些值，不再把文案写死在自己身上。
`intro_line` / `outro_line` 里的 `{brand}` / `{site}` 占位由 `build()` 一次性替换成
上面配的名字与站点地址；`share_emphasis` 是那句后缀拆成两段画时的**金字**，
断点由它给出（不在空格上），所以别把它整句抄进 `share_suffix`。
留空 = 用脚本里的通用写法。守这条的是 `pipeline/tests/test_config.py`：
把配置换成别的站名/标语，画面文案跟着变；没配，脚本里就不该出现站名。

## 规范

| 文档 | 内容 |
| --- | --- |
| [人格规范.md](人格规范.md) | 角色是谁、怎么想、怎么讲；9 条可机检规则 |
| [形象与音色规范.md](形象与音色规范.md) | 角色设定、铭牌文字的确定性、旁白音色定稿 |
| [背景音乐规范.md](背景音乐规范.md) | 选曲白名单、风格标准、技术规格、混音与 ducking 规则 |
| [选题库.md](选题库.md) | 每期的题目、口播骨架、画面契约草案与数字出处（选题的唯一事实来源） |
| [上机指南.md](上机指南.md) | 换机器怎么装依赖、字体差异、常见故障 |
| [review/README.md](review/README.md) | 视频审校规范：两层规则、抽帧方法、一期一条记录 |

模块自己的说明在 [character/readme.md](character/readme.md)、
[brand/readme.md](brand/readme.md)、[voice/readme.md](voice/readme.md)、
[music/readme.md](music/readme.md)。

## 选题库

[选题库.md](选题库.md) 是**选题这件事的唯一事实来源**：每一期一条，
含题目、主钩子、关联文档、适配理由、口播骨架、画面契约草案与数字出处。

它同样可机检（`pipeline/pyv/topics.py`，8 条规则）：

```bash
cd video/pipeline
make topics       # python -m pyv.cli topics check
```

守的是四件事：**结构完整**（必备字段与三段小节都在）、
**关联文档真实存在**（被删了就该红）、**口径不跑偏**（标题与钩子不命中
《人格规范》的禁词表，且整期落在能力域内）、**数字有出处**（实测类数字
必须带作者本人归因）。句数与字数按系列硬指标（10 句、230~280 字）卡住。

选题库里的口播骨架是**草案**，出片前要按实际旁白重新定标语速。

### 进度

这条线刚清空重来：规则齐了，还没有期。建一期就是建一个档位目录，
见 [episodes/README.md](episodes/README.md)。

## 本期内容进契约，版式常量留代码

一条视频的**画面文案与数字**（标题、副标题、标签、核数、顺序号、性能倍数……）
全部写在 `episodes/<期路径>/contract.json` 的视觉分镜契约里，不写在场景代码里。

| | 放哪 | 谁定 |
| --- | --- | --- |
| 文案、数字、标签、枚举 | `episodes/<期路径>/contract.json` | 每一期 |
| 位置、尺寸、配色、动效 | `pipeline/pyv/scenes/*.py` | 模板 |

这么分是为了让「换一期」不再等于「改一遍代码」：新一期只写契约，
场景渲染器一行都不用动。两条硬规矩：

- **参数缺失当场报错**。契约少给一个参数，渲染前就抛 `MissingParam`，
  绝不悄悄退回硬编码的旧文案——那会让契约与画面的不一致变得无声无息。
- **文案不许回流到代码**。`pipeline/tests/test_contract.py` 会解析场景源码，
  只要契约里的文案还以字符串字面量的形式出现在场景里，测试就红。

契约里还规定「哪几句旁白配哪张图」，句子必须**恰好被覆盖一次**：
漏了、重了都会在 `align` 之前就报错。

## 跑一遍

```bash
cd video/pipeline
python3 scripts/install_font.py   # 装内置字体（两台机器用同一份，跨机版式一致）
make doctor      # 环境自检：这台机器缺什么、怎么补（换机器先跑这个）
make test        # 全量测试
make topics      # 按《选题库》的规则检查选题
make bgm         # 按《背景音乐规范》检查曲库台账
make pronunciation  # 多音字读音验收（要联网合成探针）
```

下面几条要指定期路径（`EP=` 收的是期路径，见 §换一期）：

```bash
make EP=<期路径> persona     # 按《人格规范》检查这一期的口播稿
make EP=<期路径> mix-verify  # 成片级混音验收（规范 §5.7）
make EP=<期路径> probe       # ffprobe 看成片的时长、编码与像素格式
```

出片链路（`align → validate → brand → render → compose`）需要旁白音频
（`episodes/<期路径>/narration.mp3`）与视觉分镜契约
（`episodes/<期路径>/contract.json`）——契约决定**画面上写什么**，
旁白决定**什么时候出现**。
时间轴 `episodes/<期路径>/storyboard.json` 由 `align` 从旁白算出来，是产物，不入库。

### 出片之后：验收、体检与审校

出片不是终点。成片要过两道体检，再进审校：

| 环节 | 命令 | 查什么 |
| --- | --- | --- |
| 成片验收 | `make EP=<期路径> mix-verify` | 稳态 duck 深度、旁白/BGM 电平差、真峰值（规范 §5.7） |
| 发布体检 | `python3 -m pyv.cli publish check --episode <期路径>` | 发布元数据 + 成片技术门槛（每个平台各判一遍） |
| 文本层审校 | `make review-text EP=<期路径>` | `VT-*`：口播腔调、数字出处、口播与字幕是否一致 |
| 成片层审校 | `make review-video EP=<期路径>` | `VV-*`：漏画、字幕没烧上、旁白静音、时长与时间轴对不上 |
| 抽帧看画面 | `make review-frames EP=<期路径>` | 每段两帧 + 关键帧，出一份「这一帧该有什么文案」的对照清单 |

审校的两层、阈值与边界见 [review/README.md](review/README.md)。

### 抖音那一档：无品牌导流版与竖版

抖音禁「过度营销信息」与站外引流，所以另出两档：

```bash
make EP=<期路径> nobrand            # 去品牌片头/片尾
make EP=<期路径> nobrand NOBADGE=1  # 再去掉胸口铭牌（铭牌也是品牌标识）
make EP=<期路径> vertical           # 9:16 竖版
```

三件事要记住：

- **片段目录与成片都另起一份**
  （`build/<期路径压平>__nobrand/`、`out/<期路径>__nobrand.mp4`），
  不跟带品牌的版本共用——共用会让增量渲染把带品牌片的片段当成可复用的。
- **竖版本来就不套品牌片**：品牌片素材是横版的，贴到竖版画布上会被拉变形，
  `pyv.cli brand` 会直接拒绝。
- **铭牌默认保留**：铭牌占比极小，先按保留投一条看审核结果再定。

### 换一台机器

macOS 与 Linux 都能跑。一台干净的 Linux 机器上：

```bash
sudo bash video/pipeline/scripts/bootstrap_linux.sh   # 装依赖
cd video/pipeline && make doctor                       # 自检
```

唯一的差异是**字体**：macOS 用 `PingFang SC`，Linux 用开源的 `Noto Sans CJK SC`
（PingFang 是 Apple 授权字体，不能随仓库分发），所以同一段文字的**像素不同**，
文案与版式规则一致。详见[上机指南.md](上机指南.md)。

### 版式在两台机器上长得一样

「像素不同」这件事后来收窄了。做法是让两台机器用**同一个字体文件**，
再把字体之外的变量按住：

| 做法 | 在哪 | 为什么 |
| --- | --- | --- |
| 内置字体子集入库 | `pipeline/assets/fonts/` | 两台机器装同一份 `AIV Sans CJK SC`（Regular + Bold），不是各装各的系统字体 |
| 关掉 hinting | `pyv/fingerprint.py` 的前置条件 | Linux 的 FreeType 默认开 autohinter，轮廓点吸附像素网格——实测一行字的步进能差 **68px**，字号跟着差 3.2px |
| 粗体用真 Bold 字形 | `assets/fonts/AIVSansCJKSC-Bold.otf` | 只装常规字重时 cairo 会**合成**粗体，CoreText 合成一套、FreeType 合成另一套，轮廓包围盒差 3.14px |
| 布局指纹守卫 | `pyv/fingerprint.py` + `tests/test_layout_fingerprint.py` | 记落笔坐标、字号、步进宽度、轮廓包围盒——这四类是**字体的性质**，跨机可比 |
| 逐像素基准 | `scripts/capture_scene_baseline.py` + `tests/test_contract.py` | 覆盖全部视觉段，守的是「文案搬进契约不该动到画面」 |

**逐像素基准跨机不可比**：cairo 在 macOS 走 CoreText、在 Linux 走 FreeType，
栅格化不同，像素必然不同。所以跨机靠**指纹**（实测最大差：坐标 0.000、字号 0.027、
步进 0.812、包围盒 0.711），逐像素基准只在同平台内比；Linux CI 上那条守卫会
**跳过并说明原因**，不是红，也不是假装绿。

## 换一期

**坐标就是接口。** 期根 `video/episodes/`，往下四层：

```
video/episodes/<系列>/<合集>/<文档>/<档位>/
                 一级   二级   三级   四级
```

一级是系列（`<系列>`），二级是合集（`<合集>`），
三级是文档（一篇母稿，`<文档>`），四级是档位（`short` / `mid` / `full`）。

**一期 = 一个档位目录**，所以一篇文档出三期（short/mid/full），
每期有自己的口播稿、契约与旁白；共享的是那一篇文档的骨架
（`skeleton.yaml`，放在文档目录里，三档共用）。

期路径就是这四段：

```bash
cd video/pipeline
make EP=<系列>/<合集>/<文档>/<档位> align   # 按这一期的旁白对齐出时间轴
make EP=<系列>/<合集>/<文档>/<档位> all     # validate → brand → render → compose
```

`EP` 收的是**期路径**（四段，相对 `video/episodes/`），它决定这一期读哪个目录：
那一层里的口播稿、契约、旁白，就是这一期的输入。
**忘了 `EP=` 会当场报错退出 2**，不会拿空路径去跑；
路径写错了也一样（目录不存在时报错）。
也不会静悄悄地拿上一期的稿子出片。

**没有登记表**：建目录、放文件，就是新的一期。

期目录里放这一期的全部输入与产物：`口播稿.md`（口播稿 + 字幕表）、
`contract.json`（视觉分镜契约）、`publish.json`（发布元数据）、
`narration.mp3`（旁白）、`storyboard.json`（时间轴）、
`review.md`（这一期的审校记录）、`frames.md`（抽帧清单）、
`frames/`（抽出来的帧）。哪些入库、哪些是产物，看下面这张表。

期路径会**压平**成一个文件名片段（斜杠换连字符），**片段目录**（`build/`）里用的就是它：

```
<系列>/<合集>/<文档>/<档位>
→ <系列>-<合集>-<文档>-<档位>
```

**成片不用压平名**：成片按期分目录（`out/<系列>/<合集>/<文档>/<档位>.mp4`），
一眼看出它属于哪一期。

片段目录也按期分开（`build/<期路径压平>/`）：各期的段 id 会重名（`s01`…），
共用一个目录会互相覆盖。

| 入库 | 不入库（留本机） |
| --- | --- |
| `episodes/<期路径>/口播稿.md` 口播稿与字幕表 | `episodes/<期路径>/storyboard.json` 时间轴 |
| `episodes/<期路径>/contract.json` 视觉分镜契约 | `episodes/<期路径>/narration.mp3` 旁白（TTS 合成，本机素材） |
| `episodes/<期路径>/publish.json` 发布元数据 | `build/<期路径压平>/*.mp4` 片段 |
| `episodes/<期路径>/review.md` 审校记录 | `out/<期路径>.mp4` 成片 |
| `episodes/<期路径>/frames.md` 抽帧清单 | `episodes/<期路径>/frames/*.png` 抽出来的帧 |
| `episodes/<文档路径>/skeleton.yaml` 讲稿骨架（三档共用） | 发布包 |
| `pipeline/pyv/scenes/*.py` 场景代码 | 立绘、曲库、品牌片（用户素材，位置在 `config.toml`） |
| `pipeline/assets/fonts/*.otf` 内置字体子集（**跨机版式一致要用**） | |
| `music/library.json` 曲库授权台账（授权是事实） | |
| `brand/brand_windows.json` 片头片尾的配乐窗口（决策是事实） | |

抽帧的**帧不入库、清单入库**：帧是产物，跟着本机的成片走；清单是
「这一期抽了哪些帧、每帧该有什么文案」的对照表——审核记录里的判断要能对着它复核。

## 审校（review）

`review/` 存放对这条线的**审校规范与进度**，一期的审校记录在期目录里
（`episodes/<期路径>/review.md`），规范在
[review/README.md](review/README.md)。目标不是把片子做得更华丽，
而是让它像一位有经验的工程师在清楚地讲一件事：具体、自然、有判断。

两层分开：

| 层 | 编号 | 审什么 |
| --- | --- | --- |
| 文本层 | `VT-01`~`VT-07` | 要讲什么：口播腔调、泛化收尾、近似重复句、数字出处、口播与字幕是否一致、字幕表格式 |
| 成片层 | `VV-01`~`VV-07` | 做出来是什么样：漏画、字幕没烧上、旁白静音、时长对不上、关键帧间隔、混音电平、平台技术门槛 |

```bash
cd video/pipeline
make review-text   EP=<期路径>   # 文本层
make review-video  EP=<期路径>   # 成片层（需要本机有 out/<期路径>.mp4）
make review-frames EP=<期路径>   # 抽帧 + 清单（帧不入库，清单入库）
```

三条规矩：

- **信号不是门禁**：命中信号不会让命令失败——一期历史问题不该永久卡住流水线。
- **信号为 0 不等于这期没问题**：机械信号干净的一期照样可能需要改；
  信号是「值得看一眼的地方」，不是「问题清单」。
- **改稿会改到画面**：口播改了，契约的句子覆盖关系可能变，`align` 要重算时间轴、
  片段要重渲。只审文本不审成片，等于审了一份没出片的稿子。

一期一条记录在 `episodes/<期路径>/review.md`，进度在 `review/INDEX.md`（只维护一份）。
`review/` 只记录审核过程与结论，**不是对外发布内容**，不进 `docs/`
（与文档侧的根 `review/` 同一条纪律）。

## 这些文档不进站点

`video/` 在仓库根，不在 `docs/` 下面。站点读的是从 `docs/` 编译出来的内容单元，
而 `docs/` 里发的是**母稿**——面向读者的稿子。

**这条线的文档是模块内部说明书**（怎么搭一条视频流水线），不是稿子。
所以它们**不发布**：仓库里没有副本，站点上也没有它们的页面。
（2026-11-19 之前有一套「发布副本」机制：把 `video/` 的文档同步一份到
`docs/life/aiv/`，站点发那一份。那套机制连同它的白名单一起删了——
发布路径写死在视频线的脚本里，等于这条线替站点挑了分类树的位置，
那不是它该管的事。要发稿子，稿子就写在 `docs/` 里。）

`pipeline/` 下的内部设计、实施计划与测试夹具同样留在仓库里，
不进博客——测试夹具尤其不能发，其中一份是故意写坏的样本。

### 这条线的专题页

`视频线总览.md` 讲的是这条线本身：九个环节、唯一契约、入库边界，
以及「片尾接回片头」的配乐闭环。它是**模块内部文档**，不发到站点。

（写稿子时的站内链接规矩——相对链接怎么变成绝对路径、
文件名为什么就是 URL 的一段——属于**站点**，
写在 [`platforms/blog/site/README.md`](../platforms/blog/site/README.md) §四。）
