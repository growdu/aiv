# platforms/blog —— 站点平台 adapter（hexo + matery）

> **这是什么**：把内容单元渲染成**个人站点**的平台 adapter。2026-11-18 顶层设计加进来的
> 第六个平台——**站点也是第三方平台**：内容发到自己的地盘，但同样走「适配 → 生成 → 出包 → 发布」。
> 与其它五个平台平级、互不引用（见 [`docs/01-站点即第三方平台.md`](docs/01-站点即第三方平台.md)）。

---

## 一、结构

```
platforms/blog/
├── cli.py          # 平台层命令行入口
└── site/           # hexo + matery 工程（站点私产，构建链住这里）
    ├── tools/      # 构建脚本（与根 tools/ 同职责、但深了四层）
    └── tests/      # 站点私产测试
```

## 二、构建链

```
build-learning-path.py && build-posts.py && apply-site-config.py
  && copy-vendor.py && rewrite-links.mjs && clean && hexo generate
```

- `content/units/` → `source/_posts/` + `source/docs/`（hexo）。
- **身份缝**：站名/简介/导航在 `site/data/site.json`（不在框架源码里）。
  框架源码里不许出现站名（`tests/test_instance_identity.py` 守着）。

## 三、AI 如何使用本目录

- **改站点先跑**：`cd platforms/blog/site && python3 -m pytest tests/ -q`。
- 构建命令：`cd platforms/blog/site && npm run build`。
- 改配色/主题 → 读 `site/themes/matery/`（**禁碰**：第三方主题，不是本仓库代码）。
- 改身份值 → 改 `site/data/site.json`，**不要**在框架源码里写死站名。
- 站点是六个平台里**唯一没有 publish 子命令**的特例。
