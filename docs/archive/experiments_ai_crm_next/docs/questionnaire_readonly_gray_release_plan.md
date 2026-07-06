# Questionnaire Readonly Gray Release Plan

This plan prepares Questionnaire admin/public readonly routes for a future route-level gray release. It is not a production cutover, does not enable real OAuth, and does not submit production questionnaire data.

## Scope

- `/admin/questionnaires`
- `/admin/questionnaires/ui`
- `/api/admin/questionnaires`
- `/api/admin/questionnaires/{questionnaire_id}`
- `/api/admin/questionnaires/preflight`
- `/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug`
- `/api/admin/questionnaires/{questionnaire_id}/export`
- `/s/{slug}`
- `/api/h5/questionnaires/{slug}`
- `/api/h5/questionnaires/{slug}/result/{submission_id}`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | partial adapter | Admin and public H5 templates are copied legacy-compatible adapters; no redesign in this phase. |
| backend | parity-ready partial | Admin list/detail/preflight and public read/submit/result contracts are covered by fixture tests/parity. |
| OAuth | fake/stubbed | WeChat OAuth start/callback are fake contract boundaries only. |
| submit | fixture-backed partial | Submit can be exercised only in Next TestClient fake mode; production submit is not in readonly gray scope. |
| external push / WeCom tag | fake/disabled | No real tag mutation, webhook push, retry, or WeCom call. |
| production replacement | not ready | No production route cutover, no production DB migration/backfill, no real provider verification. |

## Gray-Eligible Items

- Questionnaire admin page readonly smoke.
- Admin list/detail API shape.
- Preflight and latest-submit-debug shape.
- Export route shape.
- Public H5 page readonly smoke.
- Public questionnaire read API shape.
- Result endpoint readonly shape when a submission sample exists.
- Frontend screenshot baseline.
- Questionnaire fixture parity.

## Not Gray-Eligible

- Real WeChat OAuth.
- Real questionnaire submit to production.
- Real WeCom tagging.
- Real external webhook push or retry.
- Admin create/update/delete/enable/disable production writes.
- Production data migration/backfill.

## Preconditions

| condition | required evidence |
| --- | --- |
| Ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| Questionnaire parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` |
| Frontend smoke pass | `retired frontend route smoke test; see docs/archive/experiments_ai_crm_next/retired_tools.md` and screenshot baseline |
| Screenshot baseline pass | `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md` and `artifacts/frontend_screenshots/` |
| No old backend imports | boundary scan over `experiments/ai_crm_next` |
| No old write endpoints | gray smoke side-effect safety flags remain false |
| No real OAuth / WeCom / webhook calls | fake/disabled adapters only |
| Rollback checklist ready | route-level rollback to old Flask documented below |

## Local Dual-Run Evidence

2026-05-20 local old Flask evidence uses the masked sample created by `retired questionnaire sample seed helper; see docs/archive/experiments_ai_crm_next/retired_tools.md` in `aicrm_old_flask_test`.

Verified old readonly routes:

- `GET /api/admin/questionnaires`
- `GET /api/admin/questionnaires/{questionnaire_id}`
- `GET /api/admin/questionnaires/{questionnaire_id}/export`
- `GET /api/admin/questionnaires/{questionnaire_id}/latest-submit-debug`
- `GET /s/{slug}`
- `GET /api/h5/questionnaires/{slug}` returns the legacy WeChat-browser gate in local HTTP checks and is recorded as accepted legacy drift when Next satisfies the read contract.
- Old Flask result rendering exists at `GET /s/{slug}/result/{result_token}`. The Next JSON result API path is recorded as legacy route drift when old Flask returns 404 and Next satisfies the contract.

Latest report paths:

- `/tmp/questionnaire_readonly_gray_smoke_dual_after_sample.md`
- `/tmp/questionnaire_readonly_gray_smoke_dual_after_sample.json`

This evidence is local test-only. It does not authorize production submit, real OAuth, WeCom tag mutation, external webhook push, or production route cutover.

## Fake-Only Boundaries

- `POST /api/h5/questionnaires/{slug}/submit` may be tested only with `--include-fake-submit` against Next TestClient.
- OAuth start/callback routes are fake/stubbed and must not be treated as production provider readiness.
- Old Flask must never receive submit/admin write/OAuth callback write requests from gray smoke.

## Rollback

1. Keep old Questionnaire admin/public routes active during gray preparation.
2. Route-level rollback sends Questionnaire admin/public read traffic back to old Flask.
3. Disable the Next Questionnaire readonly route flag.
4. Do not run destructive operations during preparation; no production write path is moved.
5. Re-run readonly smoke after rollback to verify old Flask route availability.

## Go / No-Go

Go only when:

- Ordinary pytest, Questionnaire parity, frontend smoke, screenshot baseline, and readonly gray smoke are green.
- Any skipped sample-dependent route has an explicit reason.
- The gray smoke report has `old_write_endpoints_executed=false`, `old_submit_executed=false`, `real_oauth_executed=false`, `wecom_tag_executed=false`, and `external_webhook_executed=false`.

No-Go if:

- Any old-service POST/PUT/PATCH/DELETE is executed.
- Default smoke includes submit, admin write, OAuth callback, external push, retry, or webhook routes.
- Real OAuth, WeCom tag mutation, or webhook push is triggered.
- A fake adapter is labeled production-ready.
- Production route or database configuration is modified.
