# Refactor 历史文档归档

V1 主线（Wave 1-5）已于 **2026-04-22 closeout**（见 `v1/v1-master-closeout.md`）。
V1 → V2 过渡层（7 个 `application/<domain>/_legacy_delegate.py` + 强制走 delegate 的架构闸 contract test）已在 PR #188/#191/#193/#194/#197/#198/#199/#201 全部清理。

application 层现在直接调 `domains.<domain>.service`，不再有中间转发层。

## 归档目录结构

| 子目录 | 内容 | PR/closeout |
|---|---|---|
| `v1/` | V1 主线总关单 + 遗留例外 ledger + 测试基线（4 文件） | 2026-04-22 |
| `wave1/` | Wave 1（read 入口收口、MCP transport、`services.py` shim） | wave1-closeout |
| `wave2/` | Wave 2（identity / class_user / routing_config / user_ops write path 收口，15 文件） | wave2-closeout |
| `wave3/` | Wave 3（questionnaire formal owner + caller cutover，6 文件） | wave3-closeout |
| `wave4/` | Wave 4（automation engine formal owner + caller cutover + 第一轮内部拆分，6 文件） | wave4-closeout |
| `wave5/` | Wave 5（AI Assist formal owner + caller cutover + 第一轮内部拆分，6 文件） | wave5-closeout |

## 这些文档保留为历史决策记录

日常开发**不需要再读**这些文档。如果未来要追溯"为什么 V1 这样做"，来这里看。

**不要删除这些文档**——它们是 git history 之外的高层决策摘要，回答"当时这个 wave 想干什么、关单条件是什么、有哪些遗留例外没清"等问题。

## 仍在 `docs/refactor/` 的活跃文档

V1 之后产生的、仍可能与 V2 / 持续重构相关的文档（如 `application-contract-catalog.md`、`fat-file-inventory.md`、`merge-hotspots.md`、`services-shim-ledger.md`、各 domain 的 `*-closeout.md` / `*-primitive-boundary.md` / `*-remaining-exceptions-ledger.md`、`single-entry-map.md`、JS API 相关 phase 文档）继续留在 `docs/refactor/` 顶层。
