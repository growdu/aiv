# 部署触发器：谁在什么时间跑什么

这一层只有一件东西自己会跑：**触发器**。它没有调用方，装错了不会在安装时报错——
它会在下一个触发点（周五 09:00）安静地什么都不做。那种失败往往几个月后才发现，
所以模板的关键参数由 `publish/tests/test_trigger_templates.py` 钉住。

## 四个触发器

| 触发器 | 装在哪 | 模板 | 跑什么 | 什么时候 |
| --- | --- | --- | --- | --- |
| `com.example.publish.schedule` | 本机 Mac（launchd） | `launchd.plist.template` | `publishkit.cli schedule weekly` | 每周五 09:00 |
| `com.example.weixin.auto-draft` | 本机 Mac（launchd） | `../../platforms/wechat/deploy/launchd.plist.template` | `wechat.cli auto-draft --new-only` | 每两小时一次（01/03/…/23 点整） |
| `com.example.weixin.refresh-drafts` | 本机 Mac（launchd） | `../../platforms/wechat/deploy/launchd-refresh.plist.template` | `wechat.cli batch --limit 100` | 每 6 小时一次（00/06/12/18 点半） |
| 服务器例行发布 | 发布服务器（cron） | `crontab.template` | `publishkit.cli schedule weekly` | 每周五 09:00 |

> **标签里的 `example` 是占位**：launchd 的 Label 是**反 DNS 串**，
> `com.example.*` 只是形状示例——安装前把 `example` 换成你自己的域。
> `platforms/wechat/deploy/` 下那两份模板带的是同一个前缀，要一起改。

另有一份 `github-action.yml.template` 是**对照物**：规格 §5.2 明确说 CI schedule 不可行
（托管 runner 的出口 IP 是动态的，公众号接口会回 40164 全挡）。它留在仓库里，是为了让
「为什么不放 CI」这件事有实物可指，而不是只存在于规格里。

**为什么本机用 launchd、服务器用 cron**：本机是 Mac，会合盖休眠，launchd 的
`StartCalendarInterval` 在错过的点醒来后会补跑，cron 不会——那样会「周一才补发周五该发的稿」。
服务器是常开的 CentOS，cron 就够。

**为什么不用 GitHub Actions 发稿**：公众号接口要求调用方出口 IP 在后台白名单里。
发布动作必须留在固定 IP 的机器上。

## 占位符

三份 launchd 模板认三个占位符，cron 模板认三个（少了 `__HOME__`，多了 `__LOG__`）：

| 占位符 | 换成 | 怎么取 |
| --- | --- | --- |
| `__REPO__` | 仓库根目录 | 本机与服务器各自的仓库根目录（本机是 checkout 所在目录，服务器是部署目录） |
| `__PYTHON__` | 跑测试用的那个 python3 | `python3 -c "import sys; print(sys.executable)"` |
| `__HOME__` | 用户主目录 | `$HOME` |
| `__LOG__` | 日志文件路径 | cron 不会自己写日志，必须自己重定向 |

凭据本身不进任何一份触发器配置——`PUBLISH_SECRETS` 指向的 `secrets.json` 由
`platforms/wechat/.gitignore` 挡着。

## 装之前先读这一段：2026-11-17 目录重构后必须重装一次

重构把顶层目录改成了 `platforms/<平台>/`（原来微信叫 `weixin/`），
视频线从 `aiv/` 改成 `video/`。**仓库里改模板不会自动更新机器上已经装好的触发器**——
装在 `~/Library/LaunchAgents/` 里的 plist 是机器上的文件，不是仓库的一部分。
不改的后果不是报错，是那条路径指向不存在的目录，触发时静默失败。

已经装过旧版触发器的机器，要做四件事：

1. **被 gitignore 的本地文件搬家**。git 不会帮你搬这些，忘了搬就是功能悄悄少一块。
   五个平台目录原来都在顶层，现在都在 `platforms/` 下面，凭据要一个个跟过去：

   | 旧目录 | 新目录 | 要搬的本地文件 |
   | --- | --- | --- |
   | `weixin/` | `platforms/wechat/` | `secrets.json`、`collections.json`、`.env`、`*.secret`、`out/` |
   | `toutiao/` | `platforms/toutiao/` | `secrets.json`、`.env`、`*.secret`、`out/` |
   | `douyin/` | `platforms/douyin/` | `secrets.json`、`out/` |
   | `bilibili/` | `platforms/bilibili/` | `secrets.json`、`out/` |
   | `channels/` | `platforms/channels/` | `secrets.json`、`out/` |

   `secrets.json` 丢了就得重新配凭据；`collections.json` 是合集配置，代码会读它
   （仓库里那份是 `collections.example.json`）；`out/` 里是本机工作状态，
   丢了能靠 `platforms/<平台>/outbox/` 里的入库快照重建，但搬过去能保住连续性。
   `__pycache__/`、`*.pyc` 不用搬。

   微信那两份是代码按默认路径读的：`weixin/secrets.json` → `platforms/wechat/secrets.json`，
   `weixin/collections.json` → `platforms/wechat/collections.json`——搬对了才不用改任何配置。

2. **卸载三个旧 LaunchAgent**，用新模板重新渲染后 `launchctl load -w`。
   变化的是：`PUBLISH_SECRETS` 指向新路径；两个微信任务的 `WorkingDirectory`
   与 `PYTHONPATH` 从 `__REPO__/weixin` 改成 `__REPO__/platforms`
   （`wechat` 包现在直接挂在 `platforms/` 下面）。
3. **服务器 crontab 改 `PUBLISH_SECRETS`**，同样从 `__REPO__/weixin/secrets.json`
   改成 `__REPO__/platforms/wechat/secrets.json`，并把服务器上的 `secrets.json` 一起搬。
4. **核对**（见下）。

改完核对：

```bash
launchctl list | grep example          # 三个任务都在
grep -A1 PYTHONPATH ~/Library/LaunchAgents/com.example.*.plist   # 都指向 .../platforms
crontab -l | grep publishkit          # PUBLISH_SECRETS 指向 .../platforms/wechat/secrets.json
```

`com.example.weixin.refresh-drafts` 是一次性的存量刷新，跑完（篇数由使用者的存量决定）就可以 unload 掉。
