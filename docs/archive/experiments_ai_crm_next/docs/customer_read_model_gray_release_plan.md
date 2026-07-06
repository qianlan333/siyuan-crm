# Customer Read Model Readonly Gray Release Preparation Plan

This document prepares Customer Read Model for a future route-level readonly gray release. It does not switch production traffic, connect production PostgreSQL, call real WeCom/OpenClaw, sync message archives, refresh tags, or add any write path.

## Scope

Readonly routes in scope:

- `GET /admin/customers`
- `GET /api/customers`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/messages/{external_userid}/recent`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | partial adapter | Customer center uses copied legacy admin templates through the AI-CRM Next frontend compatibility layer. |
| backend | parity-ready partial | Customer list/detail/timeline/recent-message contracts are covered by fixture parity. |
| database | PostgreSQL-ready / integration-tested | SQL repository and migrations exist for Customer Read Model and passed local test PostgreSQL integration; production PostgreSQL is not connected. |
| external adapter | fake / fixture-backed | Real WeCom contact sync, message archive sync, OpenClaw webhook, and tag refresh are not connected. |
| production replacement | not ready | No production route cutover or production data backfill has happened. |

Summary status: readonly gray release preparation only; not `production_ready`.

## Gray-Eligible Items

- Customer center page readonly smoke.
- Customer list API shape.
- Customer detail API shape.
- Timeline API shape.
- Recent messages API shape.
- OpenClaw read contract shape.
- Route-level screenshot baseline for `/admin/customers`.
- Readonly HTTP dual-run against old Flask when a safe old test service is available.

## Not Gray-Eligible In This Phase

- Real WeCom contact sync.
- Real message archive sync.
- Real tag refresh.
- Real OpenClaw webhook or push.
- Production data migration or backfill.
- Production read traffic switch.
- Any write interface.
- Any old Flask write request.

## Preconditions

| condition | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| customer parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-fixture-dir ... --next-testclient` |
| frontend smoke pass | route-level frontend smoke and screenshot baseline |
| screenshot baseline pass | `/admin/customers` has HTML snapshot and PNG screenshot |
| real PostgreSQL integration pass | local test PostgreSQL evidence in `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |
| readonly dual-run pass or accepted legacy drift only | `retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md` or customer gray smoke dual report |
| sample external_userid coverage available | old test service list returns at least one safe sample external_userid |
| no old backend imports | architecture boundary scan/tests |
| no production external calls | WeCom/OpenClaw/archive/tag refresh adapters remain fake or absent |
| rollback checklist ready | route-level rollback remains old Flask by default |

## Rollback Strategy

- Route-level rollback target is old Flask.
- Disable any future Next customer readonly route flag before switching traffic back.
- Keep old customer center routes active until production verification is complete.
- Do not perform destructive operations; this module is readonly for gray preparation.
- If sample data is incomplete, keep detail/timeline/recent-message routes in pending-sample status.
- Old Flask `/admin/customers` may return a login redirect in local unauthenticated runs. Classify `302 Location: /login?next=/admin/customers` as `legacy_admin_auth_redirect`; keep API dual-run judgment on readonly `/api/customers*` and `/api/messages*` routes.

## Go / No-Go

Go only when all are true:

- Ordinary pytest passes.
- Customer parity passes.
- Customer gray smoke passes in Next-only readonly mode.
- Readonly dual-run has no blocker or only accepted legacy drift.
- Sample data covers customer detail, timeline, and recent messages.
- No old backend imports exist in AI-CRM Next.
- No real WeCom, OpenClaw, archive sync, or tag refresh call is configured.
- Rollback route remains old Flask.

No-Go if any are true:

- Any customer readonly route returns 5xx.
- Required API contract keys are missing from Next.
- Customer detail/timeline/recent-message sample is unavailable for full dual-run.
- A smoke or dual-run tool attempts POST/PUT/PATCH/DELETE against old Flask.
- Real WeCom/OpenClaw/archive/tag refresh is triggered.
- Production route cutover is attempted without rollback owner approval.
- Any module is mislabeled `production_ready`.

## Next Action

Run Customer Read Model gray smoke in Next-only readonly mode. When a safe old Flask test service has representative sample data, run dual mode with `--old-base-url` and record skipped/sample gaps explicitly.

## 2026-05-20 Masked Sample Evidence

- Seed tool: `retired customer sample seed helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`.
- Seed target: local `aicrm_old_flask_test` only.
- Seed sample: `external_user_masked_001`, `customer_masked_001`, `mobile_masked_001`, `owner_masked_001`, `tag_masked_001`, `msg_masked_001`.
- Old API verification passed for list, detail, timeline, and recent messages.
- Customer gray smoke dual report: `/tmp/customer_read_model_gray_smoke_dual_after_sample.md`, result `PASS`, `skipped=0`.
- Readonly HTTP dual-run report: `/tmp/aicrm_next_readonly_dual_run_after_customer_sample.md`, result `PASS`, `skipped=0`.
- No old write endpoints, real WeCom calls, archive sync, tag refresh, or OpenClaw webhook calls were executed.
- This is readonly gray-preparation evidence only and does not make Customer Read Model `production_ready`.
