# 站点框架

一个**通用的**静态站点实现：文章页 + 学习流 + 归档。

实现是 **Hexo 7 + matery 主题**（2026-11-20 从 blog-bak 那套搬过来的翻版），
框架层只放**规则**，不放任何站点的身份。名字、简介、导航、页脚、起始日期、
学习流的赛道——全是使用者定义的。想把它变成自己的站，改下面列的几处，
不用动框架代码。

---

## 一、你能改的五处

| 改哪儿 | 改什么 | 怎么改 |
| --- | --- | --- |
| `data/site.json` | 站名、简介、导航、页脚、起始日期、站点地址 | 手改这个文件 |
| `data/learning-path.json` | 学习流的规则表（赛道 × 阶段）；`enabled: false` 整个关掉 | 手改这个文件 |
| `content/about.md` | 关于页正文 | 手写这个 markdown |
| `themes/matery/source/css/tech.css` | 首页与学习流页的版面 | 改 CSS |
| `themes/matery/_config.yml`（覆盖层 `_config.matery.yml`） | 主题行为的开关：代码复制、目录悬浮、mermaid 选项…… | 手改配置 |

内容不在这儿——内容在仓库的 `docs/`，那是**来源与接口**。

---

## 二、构建链

```
docs/  ──tools/build-content-units.py（仓库根）──▶  content/units/
              │                                          │
              │                        site/tools/build-posts.py
              │                                          ▼
              │                                 site/source/_posts/**（文章）
              │                                 site/source/docs/**（目录页）
              │                        site/tools/rewrite-links.mjs
              │                                          │（正文里的相对链接 → 站上地址）
              │                                          ▼
site/data/learning-path.json ──tools/build-learning-path.py──▶ source/_data/learning.json
site/data/site.json ──tools/apply-site-config.py──▶ _config.yml + source/_data/site.json
                                                              │
                                          hexo generate ────┴──▶ site/dist/
```

生成物（`dist/`、`_config.yml`、`source/_posts/`、`source/_data/`、
`source/learning/`、`source/images/`、`source/lib/`、`source/about/`、
`source/robots.txt`、`source/manifest.json`、`data/learning-path.compiled.json`）
**都不入库**（见仓库根的 `.gitignore`），构建时现编。

```bash
cd platforms/blog/site
npm run build      # 编译 + 注入身份 + 生成（= npm run sync && npm run clean && hexo generate）
npm run sync       # 只做前面那几样（不生成站点）
npm run clean      # 清掉上一次的产物
npm run server     # 本地起一个 hexo 服务器
```

> `npm run build` 需要 `content/units/` 在（那是上游内容单元层的产物）。
> 没有它，构建会**报错并告诉你先跑什么**——不会编出一份「0 篇内容」的站点
> 还显示成功。

---

## 三、页面

| 地址 | 是什么 | 来源 |
| --- | --- | --- |
| `/` | 首页：统计条 + 学习路径面板，正好一屏 | `site.data.learning` + 文章 |
| `/docs/<id>/` | 文章页 | 内容单元（`kind: document`） |
| `/docs/<目录>/` | 目录导航页 | 内容单元（`kind: category`，母稿是 `_index.md`） |
| `/learning/` `/learning/<赛道>/` | 学习路径总览与赛道页 | 规则表 + 内容单元 |
| `/archives/` | 归档页（按年按月） | hexo-generator-archive |
| `/all/` | 旧地址 → `/archives/` 的跳转页 | 主题自带 |
| `/about/` | 关于页 | `content/about.md` |
| `/404.html` | 404 页 | `source/404.md` |
| `/sitemap.xml` `/atom.xml` `/search.json` | 站点地图 / 订阅 / 检索索引 | hexo 生成器 |

**站上没有视频页**（作者拍板）：视频单元的地址在地址表里，但站内不生成那些页面。

**关掉学习流**（`data/learning-path.json` 里写 `"enabled": false`）：
一个学习流页面都不生成，导航项与首页面板自动消失，站点退成普通的文档站。

导航项可以带 `"feature": "learning_path"`——那个模块关着时，这一项自动不出现。

---

## 四、内容怎么变成页面

### 站内相对链接怎么变成绝对路径

母稿里的站内链接是相对路径（`./<文档>.md`），站点的 URL 是另一套
（`/docs/<路径>/`）。这层翻译由 `tools/rewrite-links.mjs` 做——
它在 **AST 上**（remark）定位链接节点，再按节点位置**外科式**替换原文的
那一小段，**不用正则扫全文**，所以代码块里的内容一个都不碰。

**URL 形状住在仓库根的共享规则 `rules/urls.json`**——不在站点源码里。
站点（`tools/urls.py`）与发布层（`publish/publishkit/urls.py`）读的是
**同一份 JSON** 的 `doc_prefix`，于是「一篇文章的地址是什么」全仓库只有一份答案。
你**不**在站点里改链接长什么样；要改形状，改 `rules/urls.json`。
编出来的对照表落在 `source/_data/urls.json`，重写器读它。

**目标页不存在时，链接就原样留下**，于是 404。
所以补一个缺失的页面时**不用去改引用它的那些链接**——把页面写出来，
链接会自己恢复。

### 文件名就是 URL 的一段

- **不能叫 `index.md`**——那是目录落地页的位置，一篇叫 `index.md` 的稿子
  会跟同目录的分类页抢同一个 URL，稿子直接消失（站上就少了一页，还不报错）。
- 分类页的文件名固定是 `_index.md`（不是 `index.md`），它的 id 是
  「路径 + `_index`」。

### 一个曾经踩过的坑：正文里的方括号

> ⚠️ 老站点（hexo 时代）的链接重写是**正则**：按「左方括号 + 文字 + 右方括号 +
> 左圆括号 + 地址 + 右圆括号」的形状扫全文，**不认代码块**。正文里任何不成对的
> 左方括号（比如区间写法里的半开区间记号）都会让它一路吃到后面某个链接的
> 右圆括号，把中间整段包成一个链接——markdown 源码看着没变，渲染出来却是
> 上千字的巨型蓝色链接。
>
> **现在不是这么做的**：重写在 AST 上改链接节点，不扫文本。CommonMark 的规定是
> 「链接标签里不能有未转义的方括号」，所以不成对的 `[` 根本成不了标签。
>
> 写稿子时区间记号照常写 `[s, s+D)` 就行。

---

## 五、边界

- **站点只读 `content/units/`**（内容单元与图片都从那儿来）。草稿箱、
  仓库的旧历史都不在它的视野里。
- 内容单元是**上游的产物**：改内容在 `docs/` 里改，然后跑仓库根的
  `tools/build-content-units.py`。站点这边只管渲染。
- 站点不挖仓库的旧历史——往后的数据是**攒**出来的。

---

## 六、守卫

`site/tests/` 是这个模块自己的验收：

```bash
cd platforms/blog/site && npm run build && python3 -m pytest tests/ -q
```

| 文件 | 守什么 |
| --- | --- |
| `test_site_config.py` | **「通用」这件事本身**：站名不出现在框架源码里；身份只有一份；导航指向的页面真的存在 |
| `test_posts.py` | 地址形状（`/docs/<id>/`）、目录页落在哪儿、视频不进站点、front matter 齐不齐 |
| `test_pages.py` | 每个内容单元都有页面；站内没有死链；固定页面一个都不少 |
| `test_learning_path.py` | 每个内容单元恰好归一类；兜底桶是空的；站上那一面不含视频 |
| `test_mermaid_render.py` | ```mermaid 变成 `<div class="mermaid">`；普通代码块不被误伤 |
| `test_home_first_screen.py` | 首页第一屏是统计条；只有一个 h1；没有入场动画 |
| `test_taxonomy_retired.py` | 分类与标签整套退休 |
| `test_content_nav_not_materialize_navbar.py` | 内容模板里不许用 `<nav>`（Materialize 会压成红条） |
| `test_all_page_is_browsable.py` | `/all/` 跳 `/archives/`，带 canonical + noindex + 真链接 |
| `test_perf_optimizations.py` | 资源本地化；prism 与 mermaid 按需加载；jQuery 同步加载 |
| `test_check_markdown.py` | 母稿的围栏体检（`tools/check-markdown.py`） |
