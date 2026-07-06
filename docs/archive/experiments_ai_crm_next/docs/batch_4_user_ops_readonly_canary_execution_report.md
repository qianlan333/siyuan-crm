# Batch 4 User Ops Readonly Canary Execution Report

This report records a staging-simulated canary execution for Batch 4 User Ops readonly. It is not a production rollout and did not modify production proxy, Nginx, deploy, or route configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `user_ops_readonly` |
| execution mode | `staging_simulated_canary` |
| operator | Codex |
| timestamp | 2026-05-20 20:08:00 CST |
| git commit | `d48082a` |
| old service target | `http://127.0.0.1:5001` GET-only when available |
| next target | AI-CRM Next TestClient |
| staging proxy target | not available / not used |
| database target | AI-CRM Next fixture/in-memory TestClient data plus old local test DB GET-only comparison |
| external adapters mode | fake / disabled |
| DND executed | no |
| batch-send preview executed | no |
| batch-send execute executed | no |
| deferred jobs executed | no |
| WeCom dispatch called | no |
| WeCom media upload called | no |
| production traffic cut | no |
| production config modified | no |

## Route Flags

Staging-only flag stance used for this simulated canary:

```bash
AICRM_NEXT_ROUTE_USER_OPS_READONLY=true
AICRM_NEXT_ROUTE_USER_OPS_WRITES=false
AICRM_NEXT_USER_OPS_DND=false
AICRM_NEXT_USER_OPS_BATCH_SEND=false
AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

These flags were not written to production config and were not committed as a real `.env`.

## Included Routes

- `GET /admin/user-ops/ui`
- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/list?wecom_status=added`
- `GET /api/admin/user-ops/list?wecom_status=not_added`
- `GET /api/admin/user-ops/list?mobile_binding_status=bound`
- `GET /api/admin/user-ops/list?activation_bucket=activated`
- `GET /api/admin/user-ops/send-records`

## Excluded Routes

- `POST /api/admin/user-ops/do-not-disturb`
- `POST /api/admin/user-ops/batch-send/preview`
- `POST /api/admin/user-ops/batch-send/execute`
- `POST /api/admin/user-ops/run-deferred-jobs`
- `POST /api/internal/user-ops/*`
- real WeCom dispatch
- real WeCom media upload
- old system writes

## Pre-Check Evidence

| check | report | result |
| --- | --- | --- |
| User Ops readonly gray smoke | `/tmp/user_ops_readonly_gray_smoke_batch_4.json` | PASS with accepted legacy drift |
| User Ops parity | `/tmp/user_ops_parity_batch_4.json` | PASS |
| readonly dual-run | `/tmp/readonly_dual_run_batch_4_user_ops.json` | PASS with accepted legacy drift |
| readiness checker | `/tmp/batch_4_user_ops_canary_readiness.json` | `canary_plan_ready` / `GO_TO_STAGING_CANARY_SIGNOFF` |
| screenshot baseline | `historical removed reference (route_status.json)` | `/admin/user-ops/ui` present and passing |
| real PostgreSQL integration | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` | evidence available |

## Canary Smoke Result

Command:

```bash
AICRM_NEXT_ROUTE_USER_OPS_READONLY=true \
AICRM_NEXT_ROUTE_USER_OPS_WRITES=false \
AICRM_NEXT_USER_OPS_DND=false \
AICRM_NEXT_USER_OPS_BATCH_SEND=false \
AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false \
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false \
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false \
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Result: PASS with accepted legacy drift.

## Readonly Dual-Run Result

Command:

```bash
.venv/bin/python retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --old-base-url http://127.0.0.1:5001 \
  --next-testclient \
  --scope customer,user_ops \
  --output-md /tmp/readonly_dual_run_batch_4_user_ops.md \
  --output-json /tmp/readonly_dual_run_batch_4_user_ops.json
```

Result: PASS. The old User Ops overview missing `激活待录入` remains accepted legacy drift because Next satisfies the current 8-card contract.

## Side-Effect Safety

| safety flag | result |
| --- | --- |
| `old_write_endpoints_executed` | false |
| `old_service_write_endpoints_executed` | false |
| `wecom_dispatch_executed` | false |
| `media_upload_executed` | false |
| `deferred_jobs_executed` | false |
| `production_config_modified` | false |
| `real_traffic_cutover_executed` | false |
| `default_endpoints_get_only` | true |

## Rollback Dry-Run

Rollback is simulated only because no real staging proxy route is changed.

- rollback instruction: `AICRM_NEXT_ROUTE_USER_OPS_READONLY=false`
- owner after rollback: old Flask
- rollback verification: dry-run only
- production config modified: false
- real route changed: false

## Blockers

None.

## Warnings

- accepted legacy page/auth drift: old `/admin/user-ops/ui` returned admin auth redirect; Next page returned 200.
- accepted legacy drift: old `/api/admin/user-ops/overview` may lack `激活待录入`; Next satisfies the current contract.

## Skipped

- real staging proxy rollback: skipped because execution mode is `staging_simulated_canary`.
- send-records detail route: not included because Batch 4 evidence is based on stable send-records list shape.

## Recommendation

GO for staging-simulated canary evidence.

This does not approve production rollout. A real staging proxy canary still requires operator signoff, staging route-owner confirmation, and rollback observation before any production canary.

## Signoff Status

`staging_simulated_only`

## Next Action

Run Batch 4 User Ops readonly canary against an actual staging proxy or staging base URL with the same GET-only route scope and rollback owner.
