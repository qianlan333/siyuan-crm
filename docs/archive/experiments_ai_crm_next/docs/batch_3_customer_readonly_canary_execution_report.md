# Batch 3 Customer Read Model Readonly Canary Execution Report

This report records a staging-simulated canary execution for Batch 3 Customer Read Model readonly. It is not a production rollout and did not modify production proxy, Nginx, deploy, route, or database configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `customer_readonly` |
| execution mode | `staging_simulated_canary` |
| operator | Codex |
| timestamp | 2026-05-20 19:40:00 CST |
| git commit | `d48082a` |
| old service target | `http://127.0.0.1:5001` GET-only when available |
| next target | AI-CRM Next TestClient |
| staging proxy target | not available / not used |
| database target | AI-CRM Next fixture/in-memory TestClient data plus masked local old Flask test sample |
| external adapters mode | fake / disabled |
| customer sample | `external_user_masked_001` |
| production traffic cut | no |
| production config modified | no |

## Route Flags

Staging-only flag stance used for this simulated canary:

```bash
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=true
AICRM_NEXT_ROUTE_CUSTOMER_WRITES=false
AICRM_NEXT_EXTERNAL_WECOM_SYNC=false
AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC=false
AICRM_NEXT_EXTERNAL_TAG_REFRESH=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
```

These flags were not written to production config and were not committed as a real `.env`.

## Included Routes

- `GET /admin/customers`
- `GET /api/customers`
- `GET /api/customers?limit=5&offset=0`
- `GET /api/customers?owner_userid={owner_userid}`
- `GET /api/customers?is_bound=true`
- `GET /api/customers?keyword={keyword}`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/customers/{external_userid}/timeline?limit=5&offset=0`
- `GET /api/messages/{external_userid}/recent`
- `GET /api/messages/{external_userid}/recent?limit=5`

## Excluded Routes And Operations

- any customer write route
- any old system write route
- WeCom contact sync
- archive sync
- tag refresh
- OpenClaw push or webhook
- production PostgreSQL connection
- production customer data migration/backfill

## Pre-Check Evidence

| check | report | result |
| --- | --- | --- |
| Customer gray smoke | `/tmp/customer_gray_smoke_batch_3.json` | PASS |
| Customer parity | `/tmp/customer_parity_batch_3.json` | PASS |
| readonly dual-run | `/tmp/readonly_dual_run_batch_3_customer.json` | PASS |
| readiness checker | `/tmp/batch_3_customer_canary_readiness.json` | `canary_plan_ready` / `GO_TO_STAGING_CANARY_SIGNOFF` |
| screenshot baseline | `historical removed reference (route_status.json)` | `/admin/customers` present and passing |
| real PostgreSQL evidence | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` | available |

## Customer Gray Smoke Result

Command:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Result: PASS.

- mode: `dual-run`
- sample_external_userid: `external_user_masked_001`
- sample_source: `old`
- compared: 8
- passed: 7
- warnings: 1
- failed: 0
- skipped: 0
- warning: old `/admin/customers` returned `legacy_admin_auth_redirect`; Next `/admin/customers` returned 200.

## Readonly Dual-Run Result

Command:

```bash
.venv/bin/python retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --old-base-url http://127.0.0.1:5001 \
  --next-testclient \
  --scope customer,user_ops \
  --output-md /tmp/readonly_dual_run_batch_3_customer.md \
  --output-json /tmp/readonly_dual_run_batch_3_customer.json
```

Result: PASS.

- compared: 17
- passed: 16
- warnings: 1
- failed: 0
- skipped: 0
- customer sample-dependent routes executed, including detail, timeline, paged timeline, recent messages, and limited recent messages.
- warning: accepted User Ops legacy drift where old overview lacks `激活待录入`; Next satisfies the current contract.

## Side-Effect Safety

| safety flag | result |
| --- | --- |
| `old_write_endpoints_executed` | false |
| `old_service_write_endpoints_executed` | false |
| `external_wecom_call_executed` | false |
| `archive_sync_executed` | false |
| `tag_refresh_executed` | false |
| `openclaw_webhook_executed` | false |
| `production_config_modified` | false |
| `real_traffic_cutover_executed` | false |

## Rollback Dry-Run

Rollback is simulated only because no real staging proxy route is changed.

- rollback instruction: `AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false`
- owner after rollback: old Flask
- rollback verification: dry-run only
- production config modified: false
- real route changed: false

## Blockers

None.

## Warnings

- Customer gray smoke: old `/admin/customers` returned `legacy_admin_auth_redirect`; this is accepted old admin auth/page-layer behavior.
- Readonly dual-run: accepted User Ops legacy drift where old `/api/admin/user-ops/overview` lacks `激活待录入`; Next satisfies the current contract.

## Skipped

None in Customer gray smoke or readonly dual-run.

## Recommendation

`GO_TO_STAGING_CANARY_SIGNOFF`; readiness status is `canary_plan_ready`.

This does not approve production rollout. A real staging proxy canary still requires operator signoff, staging route-owner confirmation, and rollback observation before any production canary.

## Signoff Status

`staging_simulated_only`

## Next Action

Run Batch 3 Customer readonly canary against an actual staging proxy or staging base URL with the same GET-only route scope and rollback owner.
