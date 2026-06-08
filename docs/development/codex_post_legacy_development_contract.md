# Codex Post-Legacy Development Contract

本文档是给 Codex 的硬规则。任何 Post-Legacy 之后的开发都必须先执行本合同，再进入代码修改。

## 每次开发前必须读取

- `docs/architecture/post_legacy_next_development_rules.md`
- `docs/architecture/post_legacy_product_baseline_inventory.md`
- `docs/route_ownership/production_route_ownership_manifest.yaml`
- 相关模块 inventory

## 每次开发必须先做 existing module search

- 成员选择先搜 customer/member/identity/ops。
- 群发先搜 cloud_orchestrator/automation/user_ops。
- 支付先搜 commerce/public_product/payment adapters。
- 媒体先搜 media_library。
- 标签先搜 customer_tags。

如果已有模块，必须复用，不允许另起一套。如果确实需要新模块，必须在 PR 说明为什么不能复用，并登记 route owner、lifecycle、smoke、no-real-external 默认行为。

## 禁止项

- 不允许恢复 `production_compat`。
- 不允许新增 `forward_to_legacy_flask`。
- 不允许新建 legacy facade。
- 不允许默认真实外部调用。
- 不允许页面/API 分离成壳。
- 不允许按钮先上、API 后补。
- 不允许 API 先上、页面未接且不写 API-only。
- 不允许不写 smoke。
- 不允许不登记 route owner。
- 不允许跳过 strict guard。
- 不允许新建 parallel checkout；也就是禁止 duplicate checkout。
- 不允许新建 parallel media upload；也就是禁止 duplicate media upload。
- 不允许新建 parallel customer selector；也就是禁止 duplicate customer selector。
- 不允许新建 parallel tag catalog；也就是禁止 duplicate tag catalog。
- 不允许新建 parallel broadcast sender；也就是禁止 duplicate broadcast sender。
- 不允许在新 runtime path 直接调用 `WeComClient.from_app`。
- 不允许写入 `real_external_call_executed=True`。
- 不允许任何 `real_enabled default` 或 default real_enabled 行为。

## Codex 执行顺序

1. 读取架构规则、baseline inventory、production manifest、相关模块 inventory。
2. 执行 existing module search，确认复用路径。
3. 修改代码前列出 frontend/API/backend matrix。
4. 改代码时保持 Next-owned，不接 legacy Flask forward，不接 compatibility facade。
5. 同步 route registry、production manifest、smoke、no-real-external tests。
6. 运行 strict guard、route resolution、代表性 smoke。
7. PR 描述必须写明可复用模块、未复用原因、删除或暂留的 legacy 模块、最终验收结论。

## 验收底线

`python scripts/check_no_new_legacy.py --strict` 和 `python tools/check_production_route_resolution.py` 必须通过。route resolution 中 `production_compat_route_count`、`production_compat_catch_all_count`、`wildcard_legacy_forward_count`、`undocumented_routes_count`、`unknown_owner_routes_count`、`deleted_but_still_registered_count`、`legacy_fallback_routes_count` 必须全部为 0。
