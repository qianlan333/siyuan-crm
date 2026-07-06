# P0-2 Full Production Verification Report

Verification date: 2026-06-15

Scope: current production baseline for all P0-2 Internal Event Queue families.

This report is production evidence only. It does not authorize real External Effects execution, real webhook delivery, WeCom, Feishu, broadcast send, payment query, refund, non-payment worker auto-execute, or `run_due` batch execution.

## Verdict

**FAIL**

The Internal Event Queue baseline itself remains healthy: all P0-2 event families have production event rows, expected consumer fan-out exists, pair-aware allowlist keeps the effective worker queue payment-only, `failed_terminal_count=0`, stale locks are 0, and External Effects real execution is disabled.

The run failed on the redaction gate. A read-only call to:

```text
GET /api/admin/external-effects/jobs?limit=10
```

returned full `payload_json` fields containing sensitive raw identifiers and external destination material. The response included categories such as raw mobile number, raw external user id, webhook URL/token, and provider transaction id. Raw values are intentionally not copied into this report.

Per the gate definition, `payload/API` sensitive data exposure is a FAIL condition. After this finding, production mutation, safe-sample creation, and single-consumer execute were stopped.

## Production Version

Health check:

- `GET /health`: HTTP 200
- `X-AICRM-Route-Owner=ai_crm_next`
- `service=aicrm-next`
- `database=postgres`
- `production_data_ready=true`
- `runtime_owner=ai_crm_next`
- `legacy_runtime_enabled=false`
- response release header: `d996e6cd4eb08744d0a2568056ab9261f4bab394-hxc-backend-refresh-hotfix`

Production git status via sandbox:

- branch: `main...origin/main`
- latest commit: `25e0cfa6 Polish internal events admin page (#1291)`
- includes `da329df4 Harden owner migration event count semantics (#1290)`

## Runtime Config

Internal Events diagnostics:

- `internal_events_enabled=true`
- all P0-2 feature flags enabled
- `pair_allowlist_enabled=true`
- `allowed_event_types` contains all P0-2 families
- `allowed_event_consumers` is payment-only:
  - `payment.succeeded:order_projection_consumer`
  - `payment.succeeded:customer_business_summary_consumer`
  - `payment.succeeded:dnd_policy_consumer`
  - `payment.succeeded:ai_assist_notify_consumer`
  - `payment.succeeded:automation_payment_consumer`
- `config_warnings=[]`
- `failed_terminal_count=0`
- `blocked_by_pair_allowlist_count=89`
- `real_external_call_executed=false`

External Effects diagnostics:

- `real_execution_enabled=false`
- `execution_mode=disabled`
- `allowed_effect_types=[]`
- `real_external_call_executed=false`
- `failed_terminal_count=0`
- counts before and after read-only verification remained unchanged:
  - `total=40`
  - `queued=1`
  - `blocked=1`
  - `failed=0`
  - `succeeded=31`
  - `cancelled=7`

## Pair Allowlist Evidence

Current full queue:

- `due_count=104`
- non-payment due runs exist as pending shadow runs.

Current effective worker queue:

- `effective_queue_metrics.due_count=15`
- `effective_queue_metrics.due_count_by_event_type` contains only `payment.succeeded`
- effective consumer names:
  - `order_projection_consumer`
  - `customer_business_summary_consumer`
  - `dnd_policy_consumer`
  - `ai_assist_notify_consumer`
  - `automation_payment_consumer`

Explicit preview calls were attempted without internal token and returned 401:

- payment preview: `internal_token_required`, `X-AICRM-Real-External-Call-Executed=false`
- owner migration preview: `internal_token_required`, `X-AICRM-Real-External-Call-Executed=false`

No `run_due` execute was called.

## Event Family Evidence

Because the redaction gate failed before safe-sample creation, the evidence below uses existing current production events. No new business facts were created in this run.

| event_type | production event count | latest event_id | expected run count on latest event | latest run statuses | SQL failed_terminal | SQL stale_locks |
|---|---:|---|---:|---|---:|---:|
| `payment.succeeded` | 5 | `iev_7758d4630a734d37ba930319b53c90ce` | 6 | all pending | 0 | 0 |
| `questionnaire.submitted` | 3 | `iev_1c52a2452fbd424582f9b32ff0846503` | 5 | all pending | 0 | 0 |
| `customer.tagged` | 3 | `iev_c8508601f2a546fc8593255029f2e509` | 3 | `tag_external_effect_shadow_consumer=succeeded`, `tag_summary_consumer=skipped`, `ai_assist_notify_consumer=pending` | 0 | 0 |
| `customer.untagged` | 3 | `iev_f5910f11e59a4430ab0cfe48fccf729b` | 3 | all pending | 0 | 0 |
| `customer.phone_bound` | 3 | `iev_e67d3a0af09f41cfb97e1f4b67b4c25c` | 4 | all pending | 0 | 0 |
| `ai_campaign.created` | 1 | `iev_ddd54cd1ff1d460195ef1a158ed38693` | 4 | `campaign_summary_consumer=skipped`, others pending | 0 | 0 |
| `ai_campaign.approved` | 1 | `iev_caecec84c08d4b12b6aca4fec2792254` | 4 | all pending | 0 | 0 |
| `ai_campaign.started` | 1 | `iev_d23df01af6da4a928a5b1b4366839818` | 4 | all pending | 0 | 0 |
| `ops_plan.approved` | 2 | `iev_974c65ba814f4b218042fe402fb07d2e` | 4 | `audit_projection_consumer=succeeded`, others pending | 0 | 0 |
| `broadcast_task.created` | 7 | `iev_c7cf8d861da0436e9fccbc1dbbd8d8b8` | 4 | all pending | 0 | 0 |
| `owner_migration.executed` | 2 | `iev_594c41a15eab4d619b8dc7d82584c075` | 4 | all pending | 0 | 0 |

SQL evidence:

- every P0-2 event type has production rows in `internal_event`
- consumer runs exist for every event family in `internal_event_consumer_run`
- per-family `failed_terminal=0`
- per-family stale lock count is 0

## Redaction Evidence

Internal Event payload summaries were scanned for common raw sensitive patterns:

- raw mobile number
- raw `external_userid`
- `openid` / `unionid`
- token / secret / webhook URL

Result: no hits in `payload_summary_json` for the latest event from each P0-2 family.

External Effects admin API redaction failed:

- endpoint: `GET /api/admin/external-effects/jobs?limit=10`
- response included full `payload_json`
- sensitive categories observed:
  - raw mobile number
  - raw external user id
  - webhook URL/token
  - provider transaction id

This is the blocking issue for this verification.

## Single-Consumer Evidence

Not executed in this run.

Reason:

- redaction gate failed before production writes or consumer execution
- no internal token was available for preview
- event-center page uses an operator-entered admin action credential; no reusable credential was provided
- no `force=true` was used
- no single-consumer execute was attempted after the sensitive-data finding

Previously observed production single-consumer successes remain useful historical evidence, but they are not counted as a fresh PASS for this run.

## External Effects And Side-Effect Safety

No production configuration was changed.

No calls were made to:

- real webhook execute
- WeCom execute
- Feishu execute
- broadcast send
- payment query
- refund
- run_due execute

External Effects diagnostics before and after read-only verification:

- `real_execution_enabled=false`
- `execution_mode=disabled`
- `allowed_effect_types=[]`
- `real_external_call_executed=false`
- counts unchanged

Direct SQL read of `external_effect_attempt` was not available to the sandbox role:

- result: `permission denied for table external_effect_attempt`

Attempt delta is therefore evidenced through External Effects diagnostics counts and `real_external_call_executed=false`, not direct table count.

## Legacy Path Marker Evidence

This run stopped before creating new safe samples, so no new legacy-path marker hit was intentionally generated.

Current legacy marker status should be verified after the redaction fix with:

```text
GET /api/admin/internal-events/diagnostics
GET /api/admin/legacy-webhook-cleanup/status
```

Do not infer cleanup eligibility from this failed run.

## Recommendation

FAIL action:

1. Keep `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` payment-only.
2. Keep External Effects real execution disabled.
3. Do not run P1 consumer auto-execute expansion.
4. Patch External Effects admin list/detail redaction so `payload_json` is not returned by list APIs and sensitive values are redacted in detail APIs.
5. Add regression tests covering:
   - raw mobile not exposed
   - raw `external_userid` not exposed
   - webhook URL/token not exposed
   - provider transaction id redaction policy
6. Re-run this full production verification after deployment.

Rollback if any related config drifts while patching:

```bash
AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer,payment.succeeded:automation_payment_consumer
AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0
AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=
```

No event family should be removed from `allowed_event_types` solely because of this report; the failure is API redaction, not Internal Event Queue emission/fan-out.

## GitHub Evidence

Total-control issue was not uniquely identified from local context. This report should be pasted back to the P0-2 final gate control issue once the issue number is confirmed.

Suggested comment title:

```text
P0-2 full production verification under current baseline
```
