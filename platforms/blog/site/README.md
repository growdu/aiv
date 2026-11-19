# 站点框架

一个**通用的**静态站点实现：目录树 + 学习流 + 视频 + 时间轴。

框架层只放**规则**，不放任何站点的身份。名字、简介、首页、导航、页脚、
主题、内容、学习流的赛道——全是使用者定义的。想把它变成自己的站，
改下面列的几处，不用动框架代码。

---

## 一、你能改的五处

| 改哪儿 | 改什么 | 怎么改 |
| --- | --- | --- |
| `data/site.json` | 站名、简介、首页首屏、导航、页脚 | 手改这个文件 |
| `data/learning-path.json` | 学习流的规则表（赛道 × 阶段）；`enabled: false` 整个关掉 | 手改这个文件 |
| `data/activity.json` | 活动账本（一天一条，只增不改） | `npm run activity -- --append`，或手写 |
| `content/about.md` | 关于页正文 | 手写这个 markdown |
| `src/styles/global.css` | 配色、字号、版心 | 改 CSS 变量 |

内容不在这儿——内容在仓库的 `docs/`，那是**来源与接口**。

---

## 二、构建链

```
docs/  ──tools/build-content-units.py（仓库根）──▶  content/units/
              │                                      │
              │                          site/tools/sync-content.py
              │                                      ▼
              │                            site/src/content/units/
              ▼
site/data/learning-path.json ──tools/build-learning-path.py──▶ learning-path.compiled.json
site/data/activity.json       ──tools/build-activity.py──────▶ activity.compiled.json
                                                              │
                                        Astro（site/src/）────┴──▶ site/dist/
```

三个 `*.compiled.json` 是**产物**，不入库（见 `.gitignore`）。
构建时现编，所以规则表改完不用手动重编。

```bash
cd platforms/blog/site
npm run build      # 编译 + 同步 + 构建
npm test           # 站点自己的守卫
npm run compile    # 只重编学习流
npm run activity   # 只重编活动数据
npm run sync       # 只同步内容单元
```

---

## 三、模块

| 模块 | 地址 | 开着还是关着 |
| --- | --- | --- |
| 目录树文档页 | `/docs/<路径>/` | 总是有（内容单元走这儿） |
| 学习流 | `/learning/` | `data/learning-path.json` 里 `enabled` |
| 视频 | `/videos/` | 总是有（有没有内容看 `docs/`） |
| 全库 | `/all/` | 总是有 |
| 时间轴 | `/timeline/` | 总是有（数字来自活动账本） |
| 关于 | `/about/` | 总是有（正文来自 `content/about.md`） |

**关掉学习流**（`data/learning-path.json` 里写 `"enabled": false`）：
一个学习流页面都不生成，导航项与首页按钮自动消失，站点退成普通的文档站。

导航项与首页按钮可以带 `"feature": "learning_path"`——那个模块关着时，
这一项自动不出现。往 `site.json` 的 `nav` 里加一项就多一个入口；
删一项就少一个。

---

## 四、边界

- **站点只读 `docs/`**。草稿箱、仓库的旧历史都不在它的视野里。
- 内容单元是**上游的产物**：改内容在 `docs/` 里改，然后跑仓库根的
  `tools/build-content-units.py`。站点这边只管渲染。
- 站点不挖仓库的旧历史——往后的数据是**攒**出来的（活动账本）。

---

## 五、守卫

`site/tests/` 是这个模块自己的验收：

```bash
cd platforms/blog/site && python3 -m pytest tests/ -q
```

其中 `test_site_config.py` 守着「通用」这件事本身：**框架源码里不许出现站名**
（站名从 `site.json` 读，再回头去源码里搜）。改了配置忘改代码，它会红。
