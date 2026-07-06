# Batch 1 Media Readonly Production Canary Human Signoff Packet

## A. Summary

| field | value |
| --- | --- |
| target batch | Batch 1 Media readonly |
| target status | `pending_human_signoff` |
| production execution | not executed |
| canary type | readonly route-level canary |
| external adapters | cloud storage disabled; WeCom media disabled |
| write routes | excluded |
| approval boundary | proposed for human review only; do not apply without explicit approval |

This packet prepares the human signoff material for a future production canary request. It does not modify production proxy/deploy configuration, enable route flags, route real traffic, upload to cloud storage, call WeCom media APIs, or authorize Media Library writes.

## B. Target Routes

Included readonly routes:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded routes and operations:

- `POST /api/admin/image-library`
- `POST /api/admin/image-library/from-url`
- `POST /api/admin/image-library/from-base64`
- `PUT /api/admin/image-library/{image_id}`
- `DELETE /api/admin/image-library/{image_id}`
- attachment write routes
- miniprogram write routes
- cloud storage upload
- WeCom media upload
- old system write endpoints
- production route cutover outside the approved canary window

## C. Required Evidence

| evidence | path / status |
| --- | --- |
| production canary approval package | `docs/archive/experiments_ai_crm_next/docs/production_canary_approval_package.md` |
| Batch 1 canary plan | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_plan.md` |
| Batch 1 canary execution report | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_execution_report.md` |
| Batch 1 staging-simulated signoff draft | `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_signoff.md` |
| media parity report | `/tmp/media_parity_after_canary_execute.json` |
| media gray smoke report | `/tmp/media_gray_smoke_staging_simulated_canary.json` |
| production approval checker report | `/tmp/production_canary_approval_media_readonly_audit.json` |
| frontend screenshot baseline | `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`, `historical removed reference (route_status.json)` |
| real PostgreSQL integration evidence | `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md` |

## D. Entry Criteria

| criterion | required status |
| --- | --- |
| ordinary pytest | PASS |
| six parity reports | PASS |
| Media parity | PASS |
| Media gray smoke | PASS |
| PNG screenshot baseline | PASS |
| production canary approval checker | PASS, `approval_status=pending_human_signoff` |
| production config modified | false |
| real traffic cutover | false |
| old write endpoint executed | false |
| cloud upload executed | false |
| WeCom media upload executed | false |
| rollback owner assigned | required before execution |
| human approvers assigned | required before execution |

## E. Human Signoff Roles

| role | name / signoff |
| --- | --- |
| Product owner | pending |
| Engineering owner | pending |
| Ops/deployment owner | pending |
| Rollback owner | pending |
| Data/security reviewer | pending |
| External adapter owner, if applicable | not applicable while cloud storage and WeCom media remain disabled |

## F. Proposed Production Route Flags

Proposed only. Do not apply without human approval. Do not write these into production config until the approved execution window. No secrets or production hosts are recorded here.

```bash
AICRM_NEXT_ROUTE_MEDIA_READONLY=true
AICRM_NEXT_ROUTE_MEDIA_WRITES=false
AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

## G. Stop Conditions

- any 5xx increase on included routes
- route smoke fails
- old route rollback fails
- write endpoint accidentally hit
- cloud upload attempted
- WeCom media attempted
- operator cannot verify route owner
- production config differs from the approved change request
- unknown side effect observed
- rollback owner unavailable

## H. Rollback Summary

| step | expected result |
| --- | --- |
| set `AICRM_NEXT_ROUTE_MEDIA_READONLY=false` | Batch 1 routes stop selecting Next |
| route owner returns to old Flask | old Flask serves the Media readonly routes or expected legacy behavior |
| run old route smoke | old route availability is verified |
| capture rollback evidence | status codes, timestamps, operator, rollback owner, and reason recorded |
| notify stakeholders | release channel receives rollback start and completion notice |

Do not perform destructive database rollback. Do not delete old Media Library routes. Do not enable Media write routes during rollback.

## I. Final Decision Block

| field | value |
| --- | --- |
| approve production canary | pending_human_signoff |
| approved by |  |
| timestamp |  |
| notes |  |
| conditions |  |
| rollback owner |  |
| production execution window |  |

Final decision is intentionally blank/pending. This packet does not mark the production canary as approved.
