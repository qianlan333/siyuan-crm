# Internal Event Legacy Path Deprecation Observation

## Purpose

P0-2 internal event families now cover the primary business facts that used to trigger direct side effects or queue writes. The remaining legacy direct paths are kept enabled for compatibility, but they are now marked at runtime for a 7-day deprecation observation window.

These markers are observation-only. They do not block legacy execution, do not enable External Effects real execution, and do not change worker pair allowlist behavior.

## Runtime Marker

Legacy paths call:

```python
mark_legacy_path_invoked(
    legacy_path="...",
    replacement_event_type="...",
    replacement_consumer="...",
    source_module="...",
    source_route="...",
    aggregate_id="...",
    reason="...",
)
```

The marker writes a structured log with `event=legacy_internal_event_path_invoked` and updates in-process diagnostics counters:

- `legacy_paths`
- `legacy_path_invocation_count`
- `legacy_path_last_seen`
- `legacy_path_retire_candidate`

The marker redacts aggregate IDs and sensitive values before logging or diagnostics. Raw mobile numbers, `external_userid`, `openid`, `unionid`, token, secret, and webhook URLs must not be stored.

## Configuration

```bash
AICRM_INTERNAL_EVENTS_LEGACY_PATH_MARKERS_ENABLED=1
AICRM_INTERNAL_EVENTS_LEGACY_PATH_RETIRE_AFTER_DAYS=7
```

External Effects must remain disabled unless a separate approval explicitly opens a target:

```bash
AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0
AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=
```

## Legacy Path Matrix

| Legacy path | Replacement event | Replacement consumer | Source module | Observation metric |
| --- | --- | --- | --- | --- |
| `payment.legacy_direct_automation` | `payment.succeeded` | `ai_audience_source_poke_consumer` | `public_product.h5_wechat_pay` | payment direct automation hits replaced by AI Audience dependency poke |
| `questionnaire.legacy_webhook_external_push` | `questionnaire.submitted` | `questionnaire_webhook_consumer` | `platform_foundation.internal_events.questionnaire` | historical webhook-consumer observation hits |
| `questionnaire.legacy_webhook_retry` | `questionnaire.submitted` | `questionnaire_webhook_consumer` | retired in R09; historical `questionnaire_external_push_logs` is read-only | no runtime retry entry remains |
| `questionnaire.legacy_tag_side_effect` | `questionnaire.submitted` | `questionnaire_tag_consumer` | `platform_foundation.internal_events.questionnaire` | questionnaire tag side-effect hits |
| `questionnaire.legacy_automation_trigger` | `questionnaire.submitted` | `automation_questionnaire_consumer` | `platform_foundation.internal_events.questionnaire` | questionnaire automation hits |
| `customer_tag.legacy_side_effect_planning` | `customer.tagged` / `customer.untagged` | `tag_external_effect_shadow_consumer` | `platform_foundation.internal_events.shadow` | tag side-effect planner hits |
| `customer_tag.legacy_wecom_side_effect_planning` | `customer.tagged` / `customer.untagged` | `tag_external_effect_shadow_consumer` | `customer_tags.live_mutation` | direct WeCom tag mutation planner hits |
| `customer.phone_bound.legacy_profile_summary_hook` | `customer.phone_bound` | `customer_summary_consumer` | `platform_foundation.internal_events.customer_identity` | identity/profile summary hits |
| `customer.phone_bound.legacy_automation_hook` | `customer.phone_bound` | `automation_phone_bound_consumer` | `platform_foundation.internal_events.customer_identity` | phone-bound automation hits |
| `customer.phone_bound.legacy_ai_assist_notify` | `customer.phone_bound` | `customer_identity_ai_assist_notify_consumer` | `platform_foundation.internal_events.customer_identity` | phone-bound AI notify hits |
| `ai_campaign.legacy_ai_assist_notify` | `ai_campaign.created` / `ai_campaign.approved` / `ai_campaign.started` | `ai_campaign_ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | AI campaign notify hits |
| `ai_campaign.*.legacy_broadcast_task_planner` | `ai_campaign.created` / `ai_campaign.approved` / `ai_campaign.started` | `broadcast_task_planner_consumer` | `platform_foundation.internal_events.shadow` | planner hook hits |
| `ops_plan.legacy_ai_assist_notify` | `ops_plan.approved` | `ops_plan_ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | ops plan notify hits |
| `ops_plan.legacy_alias_ai_assist_notify` | `ops_plan.approved` | `ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | compatibility alias hits |
| `ops_plan.legacy_automation_schedule_refresh` | `ops_plan.approved` | `automation_schedule_refresh_consumer` | `platform_foundation.internal_events.shadow` | automation schedule refresh hits |
| `broadcast_task.legacy_ai_assist_notify` | `broadcast_task.created` | `broadcast_task_ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | broadcast notify hits |
| `broadcast_task.legacy_alias_ai_assist_notify` | `broadcast_task.created` | `ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | compatibility alias hits |
| `broadcast_task.created.legacy_broadcast_task_planner` | `broadcast_task.created` | `broadcast_task_planner_consumer` | `platform_foundation.internal_events.shadow` | broadcast planner hits |
| `broadcast_task.legacy_group_ops_queue_gateway` | `broadcast_task.created` | `broadcast_queue_projection_consumer` | `integration_gateway.wecom_group_adapter` | group ops queue gateway hits |
| `broadcast_task.legacy_group_ops_private_queue` | `broadcast_task.created` | `broadcast_queue_projection_consumer` | `automation_engine.group_ops.action_dispatcher` | private queue write hits |
| `owner_migration.legacy_ai_assist_notify` | `owner_migration.executed` | `owner_migration_ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | owner migration notify hits |
| `owner_migration.legacy_alias_ai_assist_notify` | `owner_migration.executed` | `ai_assist_notify_consumer` | `platform_foundation.internal_events.shadow` | compatibility alias hits |
| `owner_migration.legacy_webhook_notify` | `owner_migration.executed` | `webhook_owner_migration_consumer` | `platform_foundation.internal_events.shadow` | owner migration webhook hits |

## Diagnostics Checks

Use the internal event diagnostics endpoint:

```bash
GET /api/admin/internal-events/diagnostics
```

Expected marker fields:

- `legacy_path_markers_enabled=true`
- `legacy_path_retire_after_days=7`
- `legacy_path_invocation_count`
- `legacy_path_last_seen`
- `legacy_path_retire_candidate`
- `legacy_paths[]`

Each `legacy_paths[]` entry should include:

- `legacy_path`
- `replacement_event_type`
- `replacement_consumer`
- `legacy_path_invocation_count`
- `last_invoked_at`
- `last_aggregate_id_redacted`
- `last_source_module`
- `last_source_route`
- `retire_after`

Diagnostics counters are in-process and may reset on app restart. The structured logs are the durable observation source for a 7-day window.

## 7-Day Delete Conditions

A legacy path can be proposed for removal in a separate PR only when all conditions are true:

1. `legacy_path_invocation_count` is 0 during the observation window, or hits are only confirmed safe tests.
2. The replacement `internal_event` continues to generate reliably.
3. The replacement consumer has passed P1 cutover, or product/ops confirms the consumer is not needed.
4. `failed_terminal_count=0`.
5. `stale_lock_count=0`.
6. External Effects remain disabled, or the target real execution has separate approval.
7. No user complaints, operations incidents, payment anomalies, or broadcast anomalies were observed.

## Rollback

The marker is observation-only. If diagnostics noise, log volume, or redaction concerns appear:

1. Set `AICRM_INTERNAL_EVENTS_LEGACY_PATH_MARKERS_ENABLED=0`.
2. Keep all legacy paths enabled.
3. Keep Internal Event Queue settings unchanged.
4. Investigate logs for `legacy_internal_event_path_invoked`.
5. Remove or adjust marker calls in a follow-up PR if needed.

Do not disable External Effects safeguards, do not add non-payment pairs to `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS`, and do not delete legacy logic as part of marker rollback.
