# Legacy Replacement Backlog - Current Progress Snapshot

Status: Current progress snapshot, no runtime change. This document is generated from the production route ownership manifest and must stay synchronized with the route registry and checker.

## Replacement Principles

1. read-only first
2. internal write second
3. external side-effect third
4. timer / automation execution last

## Business Continuity

- Do not interrupt current production daily use.
- Do not restore production_compat or legacy facade fallback.
- Do not enable real external calls.
- Do not let fixture/local_contract data enter production success paths.
- Keep route registry, manifest, and generated backlog synchronized.

## Summary By Capability Owner

- `aicrm_next.admin_auth`: 2 routes; P0=1, P2=1
- `aicrm_next.admin_jobs`: 2 routes; P3=2
- `aicrm_next.admin_shell`: 1 routes; P2=1
- `aicrm_next.ai_assist`: 3 routes; P0=1, P2=1, P3=1
- `aicrm_next.automation_engine`: 40 routes; P0=4, P1=4, P2=27, P3=5
- `aicrm_next.automation_runtime_v2`: 1 routes; P2=1
- `aicrm_next.channel_entry`: 6 routes; P1=3, P2=3
- `aicrm_next.class_user_management`: 1 routes; P2=1
- `aicrm_next.cloud_orchestrator`: 6 routes; P0=1, P2=4, P3=1
- `aicrm_next.commerce`: 16 routes; P2=16
- `aicrm_next.customer_read_model`: 20 routes; P0=7, P2=13
- `aicrm_next.customer_tags`: 15 routes; P2=15
- `aicrm_next.hxc_dashboard`: 10 routes; P0=5, P2=5
- `aicrm_next.identity_contact`: 4 routes; P0=3, P2=1
- `aicrm_next.integration_gateway`: 1 routes; P2=1
- `aicrm_next.media_library`: 7 routes; P2=7
- `aicrm_next.message_archive`: 9 routes; P0=5, P1=1, P2=2, P3=1
- `aicrm_next.ops_enrollment`: 12 routes; P2=12
- `aicrm_next.owner_migration`: 8 routes; P0=2, P1=1, P2=5
- `aicrm_next.platform_foundation`: 2 routes; P0=2
- `aicrm_next.post_legacy_deferred`: 3 routes; P2=3
- `aicrm_next.public_product`: 3 routes; P2=3
- `aicrm_next.questionnaire`: 25 routes; P2=25
- `aicrm_next.sidebar_write`: 8 routes; P2=8

## Summary By Replacement Phase

- `keep_guarded_until_adapter_ready`: 70 routes; blocked_or_guarded=70
- `phase_3_readonly`: 31 routes; readonly=30, shell_or_navigation=1
- `phase_4_internal_write`: 9 routes; internal_write=1, readonly=8
- `phase_5_external_adapter`: 85 routes; adapter_contract=9, external_side_effect=76
- `phase_6_timer_automation`: 10 routes; timer_or_automation_execution=10

## Top 10 Suggested First Replacements

### 1. `/admin/cloud-orchestrator/campaigns`

- owner: `aicrm_next.cloud_orchestrator`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tools/check_production_route_resolution.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 2. `/admin/hxc-dashboard`

- owner: `aicrm_next.hxc_dashboard`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_hxc_dashboard_pages.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 3. `/admin/hxc-send-config`

- owner: `aicrm_next.hxc_dashboard`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_hxc_dashboard_pages.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 4. `/api/admin/automation-conversion/member`

- owner: `aicrm_next.automation_engine`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_automation_member_actions_registry_lifecycle.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 5. `/api/admin/automation-conversion/overview`

- owner: `aicrm_next.automation_engine`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_automation_overview_read_model.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 6. `/api/admin/automation-conversion/pools`

- owner: `aicrm_next.automation_engine`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_automation_overview_read_model.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 7. `/api/admin/customers/profile`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 8. `/api/admin/customers/profile/tags`

- owner: `aicrm_next.customer_read_model`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tools/check_sidebar_profile_next_owner_readiness.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 9. `/api/admin/hxc-dashboard`

- owner: `aicrm_next.hxc_dashboard`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_hxc_dashboard_api_contract.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

### 10. `/api/admin/hxc-dashboard/send-config`

- owner: `aicrm_next.hxc_dashboard`
- priority: `P0` / `phase_3_readonly` / `readonly`
- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.
- continuity: Current route is documented with no legacy fallback. Preserve the current owner and production behavior, do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, 500, empty-data false success, fixture/local_contract success, or accidental external side effects.
- owner/drift guard: No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and do not restore production_compat or legacy facade fallback.
- verification: tests/test_hxc_dashboard_send_config.py; read-model parity check; admin/browser smoke for the current page or API; route owner drift guard

## Full Backlog Index

- `LRB-001` `/health`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.platform_foundation`
- `LRB-002` `/api/system/health`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.platform_foundation`
- `LRB-003` `/admin`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.admin_shell`
- `LRB-004` `/admin/customers`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-005` `/admin/questionnaires`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-006` `/admin/questionnaires/new`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-007` `/admin/questionnaires/{questionnaire_id}`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-008` `/admin/automation-conversion`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-009` `/admin/automation-conversion/{path:path}`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-010` `/admin/jobs`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.admin_jobs`
- `LRB-011` `/admin/broadcast-jobs`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.admin_jobs`
- `LRB-012` `/admin/user-ops*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-013` `/admin/user-ops`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-014` `/api/admin/user-ops*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-015` `/api/admin/user-ops/overview`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-016` `/api/admin/user-ops/cards`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-017` `/api/admin/user-ops/customers`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-018` `/api/admin/user-ops/customers/{external_userid}`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-019` `/api/admin/user-ops/customers/{external_userid}/timeline`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-020` `/api/admin/user-ops/filters`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-021` `/api/admin/user-ops/send-records`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-022` `/api/admin/user-ops/broadcast/preview`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.ops_enrollment`
- `LRB-023` `/api/admin/user-ops/export/preview`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ops_enrollment`
- `LRB-024` `/admin/owner-migration`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.owner_migration`
- `LRB-025` `/api/admin/owner-migration/preview`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.owner_migration`
- `LRB-026` `/api/admin/owner-migration/execute`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.owner_migration`
- `LRB-027` `/api/admin/owner-migration/transfer-result`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.owner_migration`
- `LRB-028` `/api/admin/owner-migration/template.xlsx`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.owner_migration`
- `LRB-029` `/api/admin/owner-migration/import`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.owner_migration`
- `LRB-030` `/api/admin/owner-migration/sessions/{session_id}/errors.xlsx`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.owner_migration`
- `LRB-031` `/api/admin/owner-migration/results/{result_id}.xlsx`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.owner_migration`
- `LRB-032` `/admin/wechat-pay/products`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-033` `/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-034` `/admin/wechat-pay/transactions`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-035` `/admin/alipay/transactions`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-036` `/admin/image-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-037` `/admin/miniprogram-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-038` `/admin/attachment-library`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-039` `/api/customers`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-040` `/api/customers/{external_userid}`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-041` `/api/customers/{external_userid}/timeline`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-042` `/api/messages/{external_userid}/recent`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-043` `/api/messages/{external_userid}`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-044` `/api/messages/search`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-045` `/api/messages/archive`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-046` `/api/messages/{external_userid}/archive`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-047` `/api/messages/{external_userid}/history`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-048` `/api/messages/send`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.message_archive`
- `LRB-049` `/api/messages/broadcast`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.message_archive`
- `LRB-050` `/api/messages/archive/sync`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.message_archive`
- `LRB-051` `/api/messages*`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.message_archive`
- `LRB-052` `/api/admin/questionnaires*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-053` `/api/admin/questionnaires/{questionnaire_id}/export`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-054` `/api/admin/questionnaires/{questionnaire_id}/share`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-055` `/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-056` `/admin/questionnaires*external-push-logs*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-057` `/api/admin/questionnaires`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-058` `/api/admin/questionnaires/{questionnaire_id}`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-059` `/api/admin/questionnaires/{questionnaire_id}/questions`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-060` `/api/admin/questionnaires/{questionnaire_id}/results`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-061` `/api/admin/questionnaires/{questionnaire_id}/submissions`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-062` `/api/h5/questionnaires*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-063` `/api/h5/questionnaires/{slug}/submit`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-064` `/api/h5/questionnaires/{slug}/client-diagnostics`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.questionnaire`
- `LRB-065` `/s/{slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-066` `/api/h5/wechat/oauth/start`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-067` `/api/h5/wechat/oauth/callback`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-068` `/api/h5/wechat/oauth*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-069` `/api/h5/wechat/oauth/unknown`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-070` `/api/admin/wecom/tags`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-071` `/api/admin/wecom/tags/{tag_id}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-072` `/api/admin/wecom/tags`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-073` `/api/admin/wecom/tags/{tag_id}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-074` `/api/admin/wecom/tags/sync`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-075` `/api/admin/wecom/tags/sync-due`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-076` `/api/admin/wecom/tags/live/gate`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-077` `/api/admin/wecom/tags/live/mark`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-078` `/api/admin/wecom/tags/live/unmark`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-079` `/api/admin/wecom/tags*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-080` `/api/admin/wecom/tag-groups`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-081` `/api/admin/wecom/tag-groups/{group_id}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-082` `/api/admin/wecom/tag-groups`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-083` `/api/admin/wecom/tag-groups/{group_id}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-084` `/api/admin/wecom/tag-groups*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_tags`
- `LRB-085` `/login`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.admin_auth`
- `LRB-086` `/logout`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.admin_auth`
- `LRB-087` `/auth/wecom*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-088` `/auth/wecom/start`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-089` `/auth/wecom/callback`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-090` `/auth/wecom/unknown`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.questionnaire`
- `LRB-091` `/api/admin/automation-conversion/reply-monitor*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-092` `/api/admin/automation-conversion/jobs/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-093` `/api/admin/cloud-orchestrator/campaigns/run-due*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.ai_assist`
- `LRB-094` `/api/admin/cloud-orchestrator/campaigns*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.cloud_orchestrator`
- `LRB-095` `/api/ai-assist/external/campaigns`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.ai_assist`
- `LRB-096` `/api/ai-assist/external/campaigns/{campaign_code}`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.ai_assist`
- `LRB-097` `/admin/cloud-orchestrator/campaigns`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.cloud_orchestrator`
- `LRB-098` `/api/admin/cloud-orchestrator/campaigns*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.cloud_orchestrator`
- `LRB-099` `/api/admin/cloud-orchestrator/media/upload`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.cloud_orchestrator`
- `LRB-100` `/api/admin/automation-conversion/programs*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-101` `/api/admin/automation-conversion/profile-segment-templates*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-102` `/api/admin/automation-conversion/agents*`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-103` `/api/admin/automation-conversion/agent-outputs*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-104` `/api/admin/automation-conversion/agent-runs*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-105` `/api/admin/automation-conversion/agent-replay`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-106` `/api/admin/automation-conversion/agent-orchestration*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-107` `/api/admin/automation-conversion/action-templates*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-108` `/api/admin/automation-conversion/task-groups*`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-109` `/api/admin/automation-conversion/tasks/run-due`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-110` `/api/admin/automation-conversion/tasks*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-111` `/api/admin/automation-conversion/workflows*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-112` `/api/admin/automation-conversion/workflow-nodes*`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-113` `/api/admin/automation-conversion/dashboard`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-114` `/api/admin/automation-conversion/executions*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-115` `/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-116` `/api/admin/automation-conversion/execution-items*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-117` `/api/admin/automation-conversion/member`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-118` `/api/admin/automation-conversion/member/put-in-pool`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-119` `/api/admin/automation-conversion/member/remove-from-pool`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-120` `/api/admin/automation-conversion/member/set-focus`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-121` `/api/admin/automation-conversion/member/set-normal`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-122` `/api/admin/automation-conversion/member/mark-won`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-123` `/api/admin/automation-conversion/member/unmark-won`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-124` `/api/admin/automation-conversion/member/push-openclaw`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-125` `/api/admin/automation-conversion/overview`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-126` `/api/admin/automation-conversion/pools`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-127` `/api/admin/automation-conversion*`: `P1` / `phase_4_internal_write` / `internal_write` / owner `aicrm_next.automation_engine`
- `LRB-128` `/api/customer-automation*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.automation_engine`
- `LRB-129` `/api/customers/automation/signup-conversion/batches*`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-130` `/api/customers/automation/activation-webhook`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-131` `/api/customers/automation/webhook-deliveries`: `P3` / `phase_6_timer_automation` / `timer_or_automation_execution` / owner `aicrm_next.automation_engine`
- `LRB-132` `/api/customers/automation/webhook-deliveries/{delivery_id}/retry`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-133` `/api/customers/automation/webhook-deliveries/retry-due`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-134` `/api/admin/wechat-pay/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-135` `/api/admin/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-136` `/api/admin/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-137` `/api/products*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.public_product`
- `LRB-138` `/p/{page_slug}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.public_product`
- `LRB-139` `/pay/{product_code}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.public_product`
- `LRB-140` `/api/orders*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-141` `/api/external/orders`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-142` `/api/external/orders/{order_no}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-143` `/api/external/users/resolve`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-144` `/api/checkout*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-145` `/api/wechat-pay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-146` `/api/alipay*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.commerce`
- `LRB-147` `/api/h5/wechat-pay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-148` `/api/h5/alipay*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.commerce`
- `LRB-149` `/api/admin/image-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-150` `/api/admin/image-library/upload`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.media_library`
- `LRB-151` `/api/admin/attachment-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-152` `/api/admin/miniprogram-library*`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.media_library`
- `LRB-153` `/sidebar/bind-mobile`: `P0` / `phase_3_readonly` / `shell_or_navigation` / owner `aicrm_next.identity_contact`
- `LRB-154` `/api/sidebar/contact-binding-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.identity_contact`
- `LRB-155` `/api/sidebar/binding-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.identity_contact`
- `LRB-156` `/api/sidebar/customer-context`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-157` `/api/sidebar/profile`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-158` `/api/sidebar/tags`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-159` `/api/admin/customers/profile`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-160` `/api/admin/customers/profile/tags`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-161` `/api/sidebar/bind-mobile`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-162` `/api/sidebar/jssdk-config`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.identity_contact`
- `LRB-163` `/api/sidebar/lead-pool/status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.automation_engine`
- `LRB-164` `/api/sidebar/lead-pool/upsert-class-term`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-165` `/api/sidebar/signup-tags/status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-166` `/api/sidebar/signup-tags/mark`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.sidebar_write`
- `LRB-167` `/api/sidebar/marketing-status`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.customer_read_model`
- `LRB-168` `/api/sidebar/marketing-status/set-followup-segment`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-169` `/api/sidebar/marketing-status/mark-enrolled`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-170` `/api/sidebar/marketing-status/unmark-enrolled`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-171` `/api/sidebar/marketing-status*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_engine`
- `LRB-172` `/api/sidebar/v2/workbench`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-173` `/api/sidebar/v2/questionnaires`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-174` `/api/sidebar/v2/materials`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-175` `/api/sidebar/v2/materials/image/{image_id}/thumbnail`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-176` `/api/sidebar/v2/other-staff-messages`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.customer_read_model`
- `LRB-177` `/api/sidebar/v2/products`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-178` `/api/sidebar/v2/orders`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-179` `/api/sidebar/v2*`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.customer_read_model`
- `LRB-180` `/api/sidebar/v2/profile`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.sidebar_write`
- `LRB-181` `/api/sidebar/v2/materials/send`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.sidebar_write`
- `LRB-182` `/wecom/external-contact/callback`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.channel_entry`
- `LRB-183` `/api/wecom/events`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.channel_entry`
- `LRB-184` `/api/admin/channels/runtime-diagnosis`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.channel_entry`
- `LRB-185` `/api/admin/channels/{channel_id}/runtime-diagnosis`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.channel_entry`
- `LRB-186` `/api/admin/channels/{channel_id}/qrcode/generate`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.channel_entry`
- `LRB-187` `/api/admin/channels/repair-entry`: `P1` / `phase_4_internal_write` / `readonly` / owner `aicrm_next.channel_entry`
- `LRB-188` `/admin/hxc-dashboard`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.hxc_dashboard`
- `LRB-189` `/admin/hxc-send-config`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.hxc_dashboard`
- `LRB-190` `/api/admin/hxc-dashboard`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.hxc_dashboard`
- `LRB-191` `/api/admin/hxc-dashboard/refresh`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.hxc_dashboard`
- `LRB-192` `/api/admin/hxc-dashboard/refresh-directory`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.hxc_dashboard`
- `LRB-193` `/api/admin/hxc-dashboard/send-config`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.hxc_dashboard`
- `LRB-194` `/api/admin/hxc-dashboard/send-config`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.hxc_dashboard`
- `LRB-195` `/api/admin/hxc-dashboard/send-config/{sender_userid}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.hxc_dashboard`
- `LRB-196` `/api/admin/hxc-dashboard/broadcast`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.hxc_dashboard`
- `LRB-197` `/api/admin/hxc-dashboard/{unknown_path}`: `P0` / `phase_3_readonly` / `readonly` / owner `aicrm_next.hxc_dashboard`
- `LRB-198` `/mcp`: `P2` / `phase_5_external_adapter` / `adapter_contract` / owner `aicrm_next.integration_gateway`
- `LRB-199` `/api/admin/class-user-management/export`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.class_user_management`
- `LRB-200` `/api/automation-runtime/v2/*`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.automation_runtime_v2`
- `LRB-201` `/api/admin/cloud-orchestrator/audit`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.cloud_orchestrator`
- `LRB-202` `/api/admin/cloud-orchestrator/observability`: `P2` / `keep_guarded_until_adapter_ready` / `blocked_or_guarded` / owner `aicrm_next.cloud_orchestrator`
- `LRB-203` `/api/admin/wecom-customer-acquisition-links`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.post_legacy_deferred`
- `LRB-204` `/api/admin/wecom-customer-acquisition-links/{link_id}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.post_legacy_deferred`
- `LRB-205` `/api/admin/wecom-customer-acquisition-links/{link_id}/{action}`: `P2` / `phase_5_external_adapter` / `external_side_effect` / owner `aicrm_next.post_legacy_deferred`
