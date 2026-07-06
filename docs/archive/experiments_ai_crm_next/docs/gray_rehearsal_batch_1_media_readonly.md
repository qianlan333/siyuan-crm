# Gray Rehearsal Batch 1: Media Library Readonly

This document records a local/test route-level gray rehearsal. It is not a production cutover.

## Summary

| field | value |
| --- | --- |
| batch name | `media_readonly` |
| execution mode | `local_rehearsal / dry_run` |
| operator | Codex |
| timestamp | 2026-05-20 18:50:47 CST |
| old service target | not used in this Next TestClient rehearsal |
| next target | AI-CRM Next TestClient |
| signoff template | `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md` |
| rehearsal markdown report | `/tmp/gray_rehearsal_batch_1_media_readonly.md` |
| rehearsal json report | `/tmp/gray_rehearsal_batch_1_media_readonly.json` |

## Route List

Included readonly routes:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded routes:

- `POST /api/admin/image-library`
- `POST /api/admin/image-library/from-url`
- `POST /api/admin/image-library/from-base64`
- `PUT /api/admin/image-library/{image_id}`
- `DELETE /api/admin/image-library/{image_id}`
- `POST /api/admin/attachment-library`
- `PUT /api/admin/attachment-library/{attachment_id}`
- `DELETE /api/admin/attachment-library/{attachment_id}`
- `POST /api/admin/miniprogram-library`
- `PUT /api/admin/miniprogram-library/{item_id}`
- `DELETE /api/admin/miniprogram-library/{item_id}`

## External Adapters Mode

| adapter | mode |
| --- | --- |
| cloud storage | disabled / fake |
| WeCom media | disabled / fake |
| old Flask writes | disabled |
| production route cutover | not executed |

## Pre-Check Results

| check | result | notes |
| --- | --- | --- |
| route-level runbook available | PASS | `docs/archive/experiments_ai_crm_next/docs/route_level_gray_release_runbook.md` |
| proxy template pseudo-only | PASS | `docs/archive/experiments_ai_crm_next/docs/route_level_proxy_template.md` |
| signoff template available | PASS | `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md` |
| acceptance checklist available | PASS | `docs/archive/experiments_ai_crm_next/docs/gray_release_acceptance_checklist.md` |
| frontend screenshot baseline | PASS | `historical removed reference (route_status.json)`, 14 routes passed, 14 PNG screenshots generated |

## Smoke Results

Command:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Result: PASS / `recommendation=GO`.

| route | result |
| --- | --- |
| `GET /admin/image-library` | 200 / PASS |
| `GET /api/admin/image-library` | 200 / PASS |
| `GET /admin/attachment-library` | 200 / PASS |
| `GET /api/admin/attachment-library` | 200 / PASS |
| `GET /admin/miniprogram-library` | 200 / PASS |
| `GET /api/admin/miniprogram-library` | 200 / PASS |

## Parity Results

Media parity was executed by the rehearsal tool with:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

Result: PASS.

## Screenshot Baseline Reference

- `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`
- `historical removed reference (route_status.json)`
- required Media routes: `/admin/image-library`, `/admin/attachment-library`, `/admin/miniprogram-library`
- missing required routes: none
- failed required routes: none

## Side Effect Safety

| safety flag | result |
| --- | --- |
| `production_config_modified` | false |
| `old_write_endpoints_executed` | false |
| `cloud_storage_upload_executed` | false |
| `wecom_media_upload_executed` | false |
| `real_traffic_cutover_executed` | false |
| `default_endpoints_get_only` | true |

## Rollback Rehearsal

Rollback was dry-run only.

- route flag rollback instruction: `AICRM_NEXT_ROUTE_MEDIA_READONLY=false`
- expected owner after rollback: old Flask
- rollback verified: dry-run only
- production config modified: false

## Blockers

None.

## Warnings

None.

## Skipped

- `fake_writes_not_requested`: expected for Batch 1 readonly.
- `old_base_url_not_provided`: no old Flask GET comparison was requested in this local rehearsal.

## Go / No-Go Conclusion

GO for local/test Batch 1 Media Library readonly rehearsal evidence.

No production traffic was switched. No production proxy was modified. No cloud upload, WeCom media upload, or old-system write endpoint was executed.

## Next Action

Repeat Batch 1 with optional old Flask GET-only dual mode, or prepare a production-like staging rehearsal with the same signoff and rollback template before any real canary.
