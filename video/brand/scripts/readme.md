---
title: "品牌片脚本：渲染与配乐"
date: 2026-11-11
description: "需要 FFmpeg（7.x 或兼容版本）、Python 3（cairo / numpy / Pillow / scipy）。"
---
需要 FFmpeg（7.x 或兼容版本）、Python 3（cairo / numpy / Pillow / scipy）。

当前的生产入口只有两个，按顺序执行：

```bash
python3 scripts/make_audio_brand.py   # 从配乐原曲里挑 3 秒窗口，混出成品音轨
python3 scripts/render_brand.py       # 渲染片头 + 片尾到 clips/
```

`render_brand.py` 支持 `--intro` / `--outro` 单独渲染；渲染完会核对帧数，
帧数不对直接报错。

## 素材在哪：问配置

品牌片是**使用者的素材**，仓库里不携带。位置写在 `video/config.toml`：

```toml
[assets.brand]
clips = "brand/clips"                  # 渲染出来的片放这里
audio = "brand/audio"                  # 成品音轨放这里
windows = "brand/brand_windows.json"   # 配乐窗口决定
```

相对路径按**配置文件所在目录**（`video/`）解析。
**没配不是错误**（流水线降级，不带品牌片出片），
**配了但文件不在才是错**（`make doctor` 报出来）。

## 源素材的生成入口（消耗生成额度）

源素材（`assets/`）同样是使用者的东西，仓库里不携带，素材没了要重新生成。
依赖 `mcode-tools` CLI（先加载 `mcode-tools-master` skill），
每一步都会消耗生成额度，重复执行前先确认是否真的需要重做：

```bash
python3 ../character/scripts/make_white.py   # 白底主形象（从透明底**合成**，不耗额度）
python3 scripts/generate_poses.py             # 点赞 / 挥手姿态（眼镜修补 + 抠底 + 盖章）
python3 scripts/generate_backgrounds.py       # 两张 AI 背景（生成完过语义验收）
```

三个脚本的分工与踩过的坑见 [`../readme.md`](../readme.md)。

## 旧版 8 秒片（已废弃，保留作兜底素材的再生成入口）

```bash
python3 scripts/fix_plates.py   # 修复底板中被 16:9 裁断的文字（可重复执行）
bash scripts/make_audio.sh       # macOS `say` 童声旁白 + 配乐（音色与现行规范不一致）
bash scripts/render.sh           # Ken Burns 渲染并封装 video/ 下的片头/片尾
```

这三个脚本服务的是旧的 8 秒品牌片（`growdu_intro_8s_1080p.mp4` 等）。
`pipeline/pyv/brand.py` 只在定稿的 3 秒片缺失时才会回退到它们。
新片一律用上面的 `make_audio_brand.py` + `render_brand.py`。

`make_audio.sh` 可用环境变量调整音色：`VOICE`（默认 `Sandy (中文（中国大陆）)` 童声）、
`PITCH`（升调半音数，默认 1.5）。注意这个音色**不符合**
[`../../形象与音色规范.md`](../../形象与音色规范.md) 第二节的定稿。
