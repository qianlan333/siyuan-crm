# Batch 3 Customer Read Model Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 3 Customer Read Model readonly. It does not switch production routes, connect production PostgreSQL, call real WeCom, sync message archives, refresh tags, push OpenClaw webhooks, or execute any customer write path.

## Summary

| field | value |
| --- | --- |
| batch name | `customer_readonly` |
| production rollout | not approved |
| customer writes | excluded |
| external customer adapters | fake / disabled |
| required sample | `external_user_masked_001` or equivalent masked old-test sample |

## Execution Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `staging_simulated` | AI-CRM Next TestClient plus old Flask GET-only dual-run evidence | No route owner changes. |
| `staging_proxy` | Staging proxy/router only | Requires rollback owner and staging operator signoff. |
| `header_allowlist` | One operator/session in staging | Route only requests with canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with canary cookie. |

## Included Readonly Routes

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
- production customer data migration/backfill
- production PostgreSQL connection
- production route cutover

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| Customer parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md` |
| Customer gray smoke pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-base-url ... --next-testclient` |
| Customer full readonly dual-run pass | `retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md --scope customer,user_ops` with customer sample-dependent routes executed |
| real PostgreSQL integration evidence available | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |
| PNG screenshot baseline pass | `historical removed reference (route_status.json)` includes `/admin/customers` |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | deploy/production config status scan and side-effect report |
| masked customer sample available | old test data includes `external_user_masked_001` or equivalent safe sample |

## Exit Criteria

- all readonly customer API routes return 200
- old `/admin/customers` may return accepted `legacy_admin_auth_redirect`; Next `/admin/customers` must return 200
- sample detail, timeline, paged timeline, recent messages, and limited recent messages execute
- forbidden placeholders remain absent through frontend screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff draft is complete
- no write route appears in canary route results

## No-Go Conditions

- any write route executed
- any WeCom, archive sync, tag refresh, or OpenClaw call
- production config modified
- old service write endpoint called
- smoke blocker
- parity blocker
- missing rollback owner
- missing sample `external_userid`
- customer detail/timeline/recent-message routes skipped for missing sample

## Readiness Command

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

## Conclusion

Batch 3 readiness can only reach `canary_plan_ready` or `staging_simulated_canary_pass`. It is not `production_ready` and does not approve production PostgreSQL, WeCom sync, archive sync, tag refresh, OpenClaw push, or customer writes.
