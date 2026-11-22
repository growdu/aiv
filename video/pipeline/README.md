# video/pipeline —— 出片流水线（pyv 渲染引擎）

> **是什么**：视频母稿层的核心——把口播稿、契约、素材渲染成一条成片流水线。
> 技术图示一律由代码绘制（cairo + ffmpeg），不交给模型生成；文字用真实字体在 cairo 阶段渲染。
> **产物不入库**（成片、片段、时间轴、发布包留本机）。

---

## 一、结构

```
video/pipeline/
├── Makefile         # validate → brand → render → compose（默认 all）
├── requirements.txt
├── pyv/             # 渲染引擎（29 个模块）
│   ├── cli.py       # 命令行入口
│   ├── episodes.py  # 期坐标（四层：系列/合集/文档/档位）
│   ├── epmeta.py    # 元数据/退出码读取
│   ├── contract.py  # 画面契约校验
│   ├── align.py timeline.py compose.py render.py draw.py ...
│   ├── scenes/      # 各场景绘制（s01_intro.py、s02_*、s03_*…）
│   └── ...
├── assets/          # 字体等（fonts/）
├── scripts/         # 辅助脚本（装字体、抓场景基线、字体子集…）
└── tests/           # 流水线私产测试
```

## 二、命令（pyv CLI）

```bash
python3 -m pyv.cli validate   --storyboard <期路径>/contract.json
python3 -m pyv.cli align      --audio <narration.mp3> --script <口播稿.md>
python3 -m pyv.cli render     --storyboard <contract.json> --out <build>
python3 -m pyv.cli compose    --storyboard <contract.json> --build <build> --out <out>
python3 -m pyv.cli persona check --script <口播稿.md>
python3 -m pyv.cli bgm check    --music <music/tracks/motif.wav>
```

期路径 = `系列/合集/文档/档位`，相对 `video/episodes/`。`make` 串起整条（`validate brand render compose`）。

## 三、AI 如何使用本目录

- **改这里先跑**：`cd video/pipeline && python3 -m pytest tests/ -q`（CI 需 cairo/ffmpeg/font 依赖）。
- 成片产物（`out/`、`build/`）**不入库**，改它没用；改的是 `pyv/` 引擎与期目录。
- 期坐标口径与 `publish/publishkit/episode.py` **同一套**——改一处两处对齐。
- 素材位置在 [`video/config.toml`](../config.toml)（缝），**不写死在 Makefile/代码里**。
- 总入口说明见 [`../README.md`](../README.md)（视频层）。
