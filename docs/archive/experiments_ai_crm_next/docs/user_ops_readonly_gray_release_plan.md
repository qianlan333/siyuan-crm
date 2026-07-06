# User Ops Readonly Gray Release Plan

This plan prepares User Ops for a future route-level readonly gray release. It is not a production cutover and does not enable real WeCom dispatch.

## Scope

- `/admin/user-ops/ui`
- `/api/admin/user-ops/overview`
- `/api/admin/user-ops/list`
- `/api/admin/user-ops/history`
- `/api/admin/user-ops/send-records`
- `/api/admin/user-ops/send-records/{record_id}`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | copied legacy template / partial adapter | Route smoke and screenshot baseline exist for `/admin/user-ops/ui`; no redesign is planned in this phase. |
| backend | parity-ready partial | Overview, list, filters, DND contract, fake preview/execute, and send-record contracts are covered by tests/parity. |
| database | PostgreSQL-ready / integration-tested | Local test PostgreSQL integration has passed for User Ops SQL repo and migrations. Production PostgreSQL is not connected. |
| external adapter | WeCom fake / disabled | Real group send, private message, moments, media upload, and deferred jobs are out of scope. |
| production replacement | not ready | No production route cutover, no production data backfill, and no real WeCom verification. |

## Gray-Eligible Items

- User Ops page readonly smoke.
- Overview API shape, including the current 8-card contract.
- List API shape and readonly filters:
  - `wecom_status=added`
  - `wecom_status=not_added`
  - `mobile_binding_status=bound`
  - `activation_bucket=activated`
- Send records readonly API shape.
- Frontend screenshot baseline linkage.
- Readonly HTTP dual-run evidence with accepted legacy drift only.

## Not Gray-Eligible

- DND writes.
- Batch-send preview against old Flask.
- Batch-send execute.
- Deferred job execution.
- Real WeCom dispatch for group/private/moments messages.
- Real WeCom media upload.
- Production data migration or backfill.
- Production write route cutover.

## Legacy Drift

The current product contract in `docs/user_ops_v2.md` requires 8 overview cards:

- `引流品总数`
- `已加微`
- `未加微`
- `已绑手机号`
- `未绑手机号`
- `黄小璨已激活`
- `黄小璨未激活`
- `激活待录入`

The local old Flask runtime may return only 7 cards and miss `激活待录入`. AI-CRM Next keeps `激活待录入` required. Old missing this card while Next satisfies the contract is recorded as `legacy_missing_required_card_label` and does not block readonly gray preparation. Next missing this card remains a blocker.

Unauthenticated old `/admin/user-ops/ui` may redirect to login. That is page-layer/admin-auth behavior and can be recorded as `legacy_admin_auth_redirect` when Next `/admin/user-ops/ui` returns `200`; it does not relax the API contract.

## Preconditions

| condition | required evidence |
| --- | --- |
| Ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| User Ops parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` |
| Frontend smoke pass | `retired frontend route smoke test; see docs/archive/experiments_ai_crm_next/retired_tools.md` and screenshot baseline |
| Screenshot baseline pass | `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md` and `artifacts/frontend_screenshots/` |
| Real PostgreSQL integration pass | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |
| Readonly dual-run pass or accepted drift only | `docs/archive/experiments_ai_crm_next/docs/real_readonly_http_dual_run.md` |
| No old backend imports | boundary scan over `experiments/ai_crm_next` |
| No old write endpoints | gray smoke side-effect safety flags remain false |
| No real WeCom calls | fake/disabled adapters only |
| Rollback checklist ready | route-level rollback to old Flask documented below |

## Rollback

1. Keep old User Ops routes active during gray preparation.
2. Route-level rollback sends `/admin/user-ops/ui` and readonly User Ops API traffic back to old Flask.
3. Disable the Next User Ops readonly route flag.
4. Do not run destructive operations during preparation; no production write path is moved.
5. Re-run readonly smoke after rollback to verify old Flask route availability.

## Go / No-Go

Go only when:

- Ordinary pytest, User Ops parity, frontend smoke, screenshot baseline, PostgreSQL integration, and readonly dual-run are green.
- The only old/next mismatch is accepted legacy drift such as old missing `激活待录入`.
- The gray smoke report has `old_write_endpoints_executed=false`, `wecom_dispatch_executed=false`, `media_upload_executed=false`, and `deferred_jobs_executed=false`.

No-Go if:

- Any write endpoint is included in default smoke.
- Old Flask receives POST/PUT/PATCH/DELETE.
- Next misses any required current-contract field/card.
- Real WeCom dispatch/media/deferred job execution is triggered.
- A production route or database is modified.
