# tests/ —— 仓库根测试（身份守卫 / 编译器 / 退出码 / 契约）

> **这是什么**：仓库**根**这一层的验收套件。跨模块的「缝」测试住在这里——
> 它们不验证某个模块的实现，只验证模块**之间**的契约没破。

---

## 一、测试清单

| 测试文件 | 守什么 |
|----------|--------|
| `test_instance_identity.py` | **身份缝**：框架源码里不许出现站名（值全在使用者一侧） |
| `test_content_units.py` | 编译器产物：`content/units/` 的目录/front matter 形状 |
| `test_exit_codes.py` | 各层 CLI 的退出码口径一致 |
| `test_url_rules.py` | URL 规则读取器与 `rules/urls.json` 口径逐字相同 |
| `test_review_check.py` | `tools/review-check.py` 的信号输出 |
| `test_review_records.py` | 审校记录（review/ 下的判据与记录一致） |
| `test_config.py` | 身份/配置的读取（使用者一侧的值） |

## 二、AI 如何使用本目录

- **改根 `tools/` 后先跑**：`cd .. && python3 -m pytest tests/ -q`。
- 这是**整仓**的根套件，不是某个模块的——各模块在自己目录里跑自己的套件（见 [`../AGENTS.md`](../AGENTS.md) §4.4）。
- 跨模块只验**接口**（缝），不验实现：谁的实现改了、只要缝没破，这里就不该红。
