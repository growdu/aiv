# 运行环境依赖清单

仓库里原来没有任何依赖声明：每个模块各自 import，靠「谁在跑就装什么」的口头约定。这份清单把依赖钉死，换机器不用再问人。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements/<你需要的那个>.txt
```

**按模块装，不要一次装全**：video 需要 cairo 的系统头文件，CI 容器里装起来比 pip 一条命令麻烦得多；只跑契约层与测试的话不需要它。

## 系统依赖（pip 装不了的）

| 依赖 | 用途 | Debian/Ubuntu |
| --- | --- | --- |
| ffmpeg / ffprobe | 出片、切片、成片预检 | `apt-get install ffmpeg` |
| 中文字体 | 公众号封面、字幕渲染 | `apt-get install fonts-noto-cjk` |
| cairo 库与头文件 | pycairo 的编译依赖 | `apt-get install libcairo2-dev` |

## 用哪份

| 文件 | 覆盖的模块 |
| --- | --- |
| `dev.txt` | 所有测试用的公共依赖（pytest） |
| `publish.txt` | 发布契约层与调度层（`publish/publishkit`） |
| `toutiao.txt` | 头条号 adapter（`toutiao/toutiao`） |
| `weixin.txt` | 公众号 adapter（`weixin/wechat`） |
| `video-platforms.txt` | 视频号 / B 站 adapter（`channels`、`bilibili`） |
| `video-pipeline.txt` | AIV 视频生产线（出片引擎、形象、音色） |

依赖是「下限」而不是「锁死」：上游发大版本通常不破坏这里的用法，真出事了再在这里钉死具体版本。
