# Batch 4 User Ops Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 4 User Ops readonly. It does not switch production routes, execute User Ops writes, run DND, preview or execute batch-send, run deferred jobs, call real WeCom dispatch, upload real WeCom media, or modify production proxy/deploy configuration.

## Summary

| field | value |
| --- | --- |
| batch name | `user_ops_readonly` |
| production rollout | not approved |
| User Ops writes | excluded |
| external WeCom adapters | fake / disabled |
| accepted legacy drift | old Flask overview may miss `激活待录入`; Next must satisfy the 8-card contract |

## Execution Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `staging_simulated` | AI-CRM Next TestClient plus old Flask GET-only dual-run evidence | No route owner changes. |
| `staging_proxy` | Staging proxy/router only | Requires rollback owner and staging operator signoff. |
| `header_allowlist` | One operator/session in staging | Route only requests with canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with canary cookie. |

## Included Readonly Routes

- `GET /admin/user-ops/ui`
- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/list?wecom_status=added`
- `GET /api/admin/user-ops/list?wecom_status=not_added`
- `GET /api/admin/user-ops/list?mobile_binding_status=bound`
- `GET /api/admin/user-ops/list?activation_bucket=activated`
- `GET /api/admin/user-ops/send-records`
- `GET /api/admin/user-ops/send-records/{record_id}` only when a stable sample is available; otherwise shape coverage stays on the list endpoint.

## Excluded Operations

- DND write
- batch-send preview
- batch-send execute
- deferred jobs
- internal user ops jobs
- WeCom dispatch
- WeCom media upload
- old system writes
- production route cutover

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| User Ops parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md` |
| User Ops readonly gray smoke pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-base-url ... --next-testclient` |
| User Ops readonly dual mode pass | `retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md --scope customer,user_ops` with only accepted legacy drift |
| real PostgreSQL integration evidence available | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |
| PNG screenshot baseline pass | `historical removed reference (route_status.json)` includes `/admin/user-ops/ui` |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | deploy/production config status scan and side-effect report |
| accepted legacy drift documented | old missing `激活待录入`; Next satisfies current 8-card contract |

## Exit Criteria

- all readonly User Ops API routes return 200
- old admin page redirects are handled only as legacy page/auth drift if encountered
- overview, list, filter, and send-records evidence is present
- Next overview includes `激活待录入`
- forbidden placeholders remain absent through frontend screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff draft is complete
- no write route appears in canary route results

## No-Go Conditions

- any User Ops write route executed
- DND executed
- batch-send preview or execute executed
- deferred jobs executed
- WeCom dispatch executed
- WeCom media upload executed
- production config modified
- old service write endpoint called
- smoke blocker
- parity blocker
- missing rollback owner
- Next missing `激活待录入`

## Readiness Command

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

## Conclusion

Batch 4 readiness can only reach `canary_plan_ready` or `staging_simulated_canary_pass`. It is not `production_ready` and does not approve DND, batch-send, deferred jobs, internal jobs, WeCom dispatch, WeCom media upload, or User Ops writes.
