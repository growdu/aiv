# 出片流水线（按期可切）
#
#   make test      跑全部测试
#   make doctor    环境自检：这台机器缺什么、怎么补（先跑这个）
#   make validate  校验 storyboard 契约（时间码、字幕宽度、禁止词、字体）
#   make align     重新按旁白对齐生成 storyboard
#   make brand     套上品牌片头/片尾（brand/clips/*.mp4）
#   make render    渲染各场景片段（预览用，与成片同样烧字幕）
#   make compose   拼接 + 混音 + 出片
#   make persona   按《人格规范》检查口播稿
#   make topics    按《选题库》的规则检查选题
#   make bgm       按《背景音乐规范》检查曲库台账
#   make mix-verify 成片级混音验收（规范 §5.7）
#   make all       validate → brand → render → compose
#   make nobrand   无品牌导流版（抖音这一档用）：nobrand → render → compose
#                  胸口铭牌也是品牌标识：make EP=<期路径> nobrand NOBADGE=1
#                  换成无标牌形象（默认保留铭牌，等实投结果再定）
#   make vertical  竖版 9:16（抖音那一档）：align --canvas vertical → nobrand
#                  → render → compose
#
# align 是手工步骤，需要在 all 之前单独跑。
# 片段是增量渲染的：build/ 里未过期的片段会被直接复用。
#
# 换一期：make EP=<期路径> ...，例如
#   make EP=postgresql/getting-started/postgresql基操/short align
#
# 期路径 = 系列/合集/文档/档位，四层，相对 video/episodes/。
# **没有登记表**：建目录、放文件，就是新一期。
#
# 素材的位置不在这里写死——问配置要（video/config.toml）：
#   BGM        正文铺底那首曲子
#   NOBADGE    无标牌形象
# 没配就是不配，流水线会降级，不报错。

ROOT := ..
# Python 解释器：Linux 上常常只有 python3，没有 python。
# 想指定别的解释器就 `make PY=/path/to/python3 ...`。
PY ?= $(shell command -v python3 >/dev/null 2>&1 && echo python3 || echo python)

# 读配置里的一个值：python3 -m pyv.cli config <key>
CONFIG := $(PY) -m pyv.cli config

EP ?=
EPISODE_DIR := $(if $(strip $(EP)),$(ROOT)/episodes/$(EP))
# 期路径压平成一个文件名片段（斜杠 → 连字符）。**只有片段目录用它**——
# 片段是中间产物，落在 build/ 下面，用一个扁平名就够。
# **成片不用它**：成片按期分目录（out/<系列>/<合集>/<文档>/<档位>.mp4），
# 一眼看出它属于哪一期。
EP_ID := $(subst /,-,$(EP))
SCRIPT := $(EPISODE_DIR)/口播稿.md
CONTRACT := $(EPISODE_DIR)/contract.json
NARRATION := $(EPISODE_DIR)/narration.mp3
STORYBOARD := $(EPISODE_DIR)/storyboard.json

# 正文铺底（config.toml 的 [assets.music].bed）。没配就没有 BGM。
BGM := $(shell $(CONFIG) bgm)
BGM_ARG := $(if $(strip $(BGM)),--bgm $(BGM))

# 片段目录按期分开：各期的段 id 会重名（s01…），共用一个目录会互相覆盖。
BUILD := $(ROOT)/build/$(EP_ID)
# 成片按期分目录：期路径原样（斜杠就是目录分隔符）。
OUT := $(ROOT)/out/$(EP).mp4

# 无品牌导流版：抖音这一档用。去掉品牌片头/片尾，落版标签也不带品牌名——
# 抖音禁「过度营销信息」与站外引流，片头整屏字标与片尾的 growdu.cn 胶囊
# 正好撞上（规格 §6.6.4）。
#
# **片段目录与成片都另起一份**：不跟带品牌的版本共用，否则增量渲染会把
# 带品牌片的片段当成可复用的（成片的 sha256 变了才发现，已经晚了）。
NOBRAND_STORYBOARD := $(EPISODE_DIR)/storyboard__nobrand.json
NOBRAND_BUILD := $(ROOT)/build/$(EP_ID)__nobrand
NOBRAND_OUT := $(ROOT)/out/$(EP)__nobrand.mp4

# 无标牌形象（抖音这一档备用）：胸口那枚铭牌也是品牌标识，
# 被判「过度营销信息」时用它重出片。**默认不换**——铭牌占比极小，
# 先按保留投一条看审核结果（规格 §十四 第 16 条）。
#
#   make EP=<期路径> nobrand NOBADGE=1
NOBADGE_CHAR := $(shell $(CONFIG) mascot_plain)
CHARACTER_FLAG := $(if $(NOBADGE),$(if $(NOBADGE_CHAR),--character $(NOBADGE_CHAR)))

# 竖版画布（抖音这一档）：9:16。**不套品牌片**——品牌片素材是横版的，
# 贴到竖版画布上会被拉变形（`pyv.cli brand` 会直接拒绝）。
# 竖版这一档同时也是无品牌版：片头片尾本来就不该有。
VERTICAL_ALIGNED := $(EPISODE_DIR)/storyboard__vertical_aligned.json
VERTICAL_STORYBOARD := $(EPISODE_DIR)/storyboard__vertical.json
VERTICAL_BUILD := $(ROOT)/build/$(EP_ID)__vertical
VERTICAL_OUT := $(ROOT)/out/$(EP)__vertical.mp4

.PHONY: all test doctor validate align brand render compose nobrand vertical probe persona bgm mix-verify topics pronunciation review review-text review-video review-frames clean require-EP

all: validate brand render compose

# 下面这些 target 要指定期路径（EP 收的是 期路径）。没给就当场说清楚，
# 别拿空路径去跑。
require-EP:
	@if [ -z "$(strip $(EP))" ]; then \
		echo "缺少 EP=<期路径>：期路径 = 系列/合集/文档/档位"; \
		echo "  ls video/episodes/ 看有哪些期"; \
		exit 2; \
	fi
	@if [ ! -d "$(EPISODE_DIR)" ]; then \
		echo "没有这一期：$(EPISODE_DIR)"; \
		echo "  期路径是四层：系列/合集/文档/档位（档位 short/mid/full）"; \
		exit 2; \
	fi

test:
	$(PY) -m pytest tests/ -q

# 环境自检：缺什么报什么，并给出可执行的修复命令
doctor:
	$(PY) -m pyv.cli doctor

validate: require-EP
	$(PY) -m pyv.cli validate --storyboard $(STORYBOARD)

align: require-EP
	$(PY) -m pyv.cli align --audio $(NARRATION) --script $(SCRIPT) \
		--scenes $(CONTRACT) --out $(STORYBOARD)

brand: require-EP
	$(PY) -m pyv.cli brand --storyboard $(STORYBOARD) --out $(STORYBOARD) \
		--build $(BUILD)

render: require-EP
	$(PY) -m pyv.cli render --storyboard $(STORYBOARD) --out $(BUILD)

compose: require-EP
	$(PY) -m pyv.cli compose --storyboard $(STORYBOARD) --build $(BUILD) \
		--out $(OUT) --narration $(NARRATION) $(BGM_ARG)

# 无品牌导流版（抖音这一档用）
nobrand: require-EP
	$(PY) -m pyv.cli nobrand --storyboard $(STORYBOARD) \
		--out $(NOBRAND_STORYBOARD)
	$(PY) -m pyv.cli render --storyboard $(NOBRAND_STORYBOARD) \
		--out $(NOBRAND_BUILD) $(CHARACTER_FLAG)
	$(PY) -m pyv.cli compose --storyboard $(NOBRAND_STORYBOARD) \
		--build $(NOBRAND_BUILD) --out $(NOBRAND_OUT) \
		--narration $(NARRATION) $(BGM_ARG)

# 竖版（抖音这一档）：9:16
# align 直接产出竖版画布的 storyboard，再走 nobrand（竖版不要品牌片，
# 也不要落版上的品牌名）。
vertical: require-EP
	$(PY) -m pyv.cli align --audio $(NARRATION) --script $(SCRIPT) \
		--scenes $(CONTRACT) --canvas vertical --out $(VERTICAL_ALIGNED)
	$(PY) -m pyv.cli nobrand --storyboard $(VERTICAL_ALIGNED) \
		--out $(VERTICAL_STORYBOARD)
	$(PY) -m pyv.cli render --storyboard $(VERTICAL_STORYBOARD) \
		--out $(VERTICAL_BUILD) $(CHARACTER_FLAG)
	$(PY) -m pyv.cli compose --storyboard $(VERTICAL_STORYBOARD) \
		--build $(VERTICAL_BUILD) --out $(VERTICAL_OUT) \
		--narration $(NARRATION) $(BGM_ARG)

persona: require-EP
	$(PY) -m pyv.cli persona check --script $(SCRIPT)

bgm:
	$(PY) -m pyv.cli bgm library

# 选题库检查：结构、口径、句数字数、数字出处
topics:
	$(PY) -m pyv.cli topics check

# 多音字读音验收：确认「行锁」确实念 xíng、「航锁」确实念 háng
# （要联网合成探针；判据见 voice/scripts/pronunciation.py）
pronunciation:
	$(PY) ../voice/scripts/check_pronunciation.py --calibrate

# 成片级验收：稳态 duck 深度、旁白/BGM 电平差、真峰值、旁白增益（规范 §5.7）
mix-verify: require-EP
	@if [ -z "$(strip $(BGM))" ]; then \
		echo "没配 BGM：config.toml 的 [assets.music].bed 是空的"; \
		exit 2; \
	fi
	$(PY) -m pyv.cli bgm verify --video $(OUT) --narration $(NARRATION) \
		--music $(BGM) --storyboard $(STORYBOARD)

probe: require-EP
	ffprobe -v error -show_entries format=duration \
		-show_entries stream=width,height,codec_type,codec_name,pix_fmt \
		-of default=noprint_wrappers=1 $(OUT)

# ---- 视频审核（见 video/review/README.md）------------------------------------
#
# 两层分开：文本层审「要讲什么」，成片层审「做出来是什么样」。
# **信号不是门禁**：命中信号不会让命令失败——一期历史问题不该
# 永久卡住流水线。记录与状态在 video/review/episodes/<期路径>.md。
review-text: require-EP
	$(PY) -m pyv.cli review text --episode $(EP)

review-video: require-EP
	$(PY) -m pyv.cli review video --episode $(EP)

# 抽帧 + 清单：给人和 Agent 看画面用。帧不入库（video/.gitignore 拦 frames/），
# 入库的是清单与结论。
review-frames: require-EP
	$(PY) -m pyv.cli review frames --episode $(EP)

clean:
	rm -rf $(BUILD) $(OUT)
