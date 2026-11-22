# content/ —— 构建产物区（缝之一）

> **这是什么**：所有平台共用的**内容单元（content units）**仓库——编译器从母稿编译出来的产物。
> 这里是**缝**（seam）之一：平台层与母稿层之间只通过它对话，不互相 import。

---

## 一、目录结构

```
content/
└── units/                 # 内容单元根（构建产物）
    ├── images/            # 母稿里的图片（按 docs 相对路径拷贝而来）
    ├── <分类>/.../<slug>.md   # 文档内容单元
    └── video/<期号>.md         # 视频内容单元
```

- 一篇内容单元 = 一篇 markdown + 一份 front matter。**平台无关**——公众号、头条号、
  站点、三个视频平台读的都是这里的同一份内容单元。
- **内容单元 id** = 它相对 `content/units/` 的路径（不带 `.md`）。这是全站、各平台、发布层共用的主键。

## 二、谁往这里写 / 谁从这里读

- **写**：只有 [`../tools/build-content-units.py`](../tools/)（`docs/` → `units/`）和
  [`../tools/build-video-pages.py`](../tools/)（`video/` → `units/video/`）写。
- **读**：各平台 adapter（`../platforms/`）、站点构建链、发布层（`../publish/publishkit/`）、
  URL 规则读取器。

## 三、AI 如何使用本目录（必读）

- ⚠️ **不要手改这里的文件**。它是构建产物：`content/units/` 不入库（gitignore），
  下次编译就覆盖。**改它没用。**
- 要改内容单元的内容 → 改上游母稿（`docs/` 或 `video/episodes/`），再重跑编译器。
- 内容单元为空（编译前）是合法状态，不是错误。
- **身份缝**：内容单元的 front matter 里**不许出现站名**（`tests/test_instance_identity.py` 守着）。
- 地址形状看 [`../rules/urls.json`](../rules/) 与各读取器，**不要在这里写死 URL**。
