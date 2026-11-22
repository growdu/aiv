# tools/ —— 编译器与共享构建脚本（根工具层）

> **这是什么**：内容流的「编译器 + 共享读取器」。把母稿编译成平台无关的内容单元，
> 并提供仓库里**唯一一份**路径常量与 URL 规则读取器。各平台 adapter 都不 import 这里——
> 它们只通过 `content/units/`（构建产物）取内容。

---

## 一、脚本清单

| 脚本 | 干什么 |
|------|--------|
| `build-content-units.py` | `docs/` → `content/units/`：只拷 front matter + 正文，正文一字不改 |
| `build-video-pages.py` | `video/episodes/` → `content/units/video/<期号>.md`：口播稿变内容单元 |
| `check-content-contract.py` | 内容契约闸门：把所有内容单元过一遍契约，违规即构建失败 |
| `review-check.py` | 审校信号检查器：把 `review/README.md` 里的机械指标（AI 味、证据密度、结构）变成带编号的信号，只标不下结论 |
| `url_rules.py` | 共享 URL 规则的**读取器**（规则只有一份：`rules/urls.json`） |
| `paths.py` | 仓库里所有构建脚本的**路径常量——唯一一处** |
| `nginx_soft404.py` / `fix-soft-404.sh` | 运维辅助（软 404 排查），非流水线 |

## 二、层间关系（必守）

- **不 import 任何平台层**，也不被 `publish/publishkit/` import（两层之间靠**文件**说话，
  不是 import）。这条接缝由 `tests/test_episode.py`、`publish/tests/` 守着。
- `paths.py` 的深度写死在各脚本里，所以它在 import 时断言一次层级数——层级变了就炸。

## 三、AI 如何使用本目录

- **改这里先跑**：`cd .. && python3 -m pytest tests/ -q`（身份守卫、编译器、退出码、内容契约）。
- 想加/改编译逻辑 → 读对应脚本开头的 docstring，它写得很细（契约、图片保留名、期目录口径）。
- 想校一篇稿的审校信号 → `python3 tools/review-check.py <文章路径>`。
- 想校验内容契约 → `python3 tools/check-content-contract.py`（CI 里也跑这一道）。
- **URL 形状永远从 `url_rules.py` 取，不要在别处写死前缀。**
