# Batch 1 Media Readonly Human Signoff Submission

## A. Decision Requested

Request a human decision on whether to approve Batch 1 Media readonly production canary.

Current status: `pending_human_signoff`.

This document is not an execution instruction. Codex will not execute production canary, modify production configuration, set production route flags, or switch real traffic. A real canary can only proceed after the required human owners complete the signoff fields and schedule an execution window.

## B. Scope

Included readonly routes:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded:

- all Media write routes
- cloud storage upload
- WeCom media upload
- old system write routes
- Media Library create/update/delete/import routes

## C. Evidence Summary

| evidence | result | path |
| --- | --- | --- |
| ordinary pytest | PASS, latest validation `387 passed, 3 skipped` | local command output |
| Media parity | PASS | `/tmp/media_parity_after_human_signoff_submission.json` |
| Media gray smoke | PASS | `/tmp/media_gray_smoke_staging_simulated_canary.json` |
| screenshot baseline | PASS | `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`, `historical removed reference (route_status.json)` |
| Batch 1 rehearsal | PASS / GO | `docs/archive/experiments_ai_crm_next/docs/gray_rehearsal_batch_1_media_readonly.md` |
| staging/simulated canary | PASS / GO | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_execution_report.md` |
| approval readiness checker | PASS / `pending_human_signoff` | `/tmp/production_canary_approval_media_readonly_audit.json` |
| signoff packet readiness checker | PASS / `pending_human_signoff` | `/tmp/batch_1_media_production_signoff_readiness_final.json` |
| human signoff packet | prepared, pending | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_production_canary_signoff_packet.md` |
| production execution checklist | prepared, manual only | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_production_execution_checklist.md` |

## D. Safety Status

| safety item | status |
| --- | --- |
| production config modified | false |
| real traffic cutover executed | false |
| old write endpoints executed | false |
| cloud upload executed | false |
| WeCom media upload executed | false |
| production approval | not granted yet |

## E. Human Signoff Fields

| field | value |
| --- | --- |
| Product owner |  |
| Engineering owner |  |
| Ops/deployment owner |  |
| Rollback owner |  |
| Data/security reviewer |  |
| Approval decision | approve / reject / request changes |
| Approved execution window |  |
| Conditions |  |
| Notes |  |

## F. If Approved, Next Manual Action

Human operators, not Codex, should:

1. Choose the approved execution window.
2. Confirm the rollback owner is online.
3. Set the approved readonly route flag through the approved production change workflow.
4. Execute `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_production_execution_checklist.md`.
5. Observe route status, latency, logs, and side-effect safety.
6. Keep rollback ready with `AICRM_NEXT_ROUTE_MEDIA_READONLY=false`.
7. Record canary result and attach smoke, logs, and operator observations.

## G. If Rejected / Changes Requested

Record the reason below and create a follow-up task. Do not execute production canary.

| field | value |
| --- | --- |
| rejection / requested change reason |  |
| follow-up owner |  |
| follow-up task link |  |
| retest evidence required |  |

## Submission Boundary

This submission remains `pending_human_signoff`. It does not authorize production execution, route changes, cloud upload, WeCom media upload, old-system writes, or Media write routes.
