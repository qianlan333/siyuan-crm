# Batch 1 Media Readonly Production Execution Checklist

This is a manual checklist for an approved future production canary. It is not an automation script, does not execute route changes, and does not authorize production execution by itself.

## Before Execution

- Verify git commit and branch match the approved change request.
- Verify production config diff is clean before the approved change.
- Verify old route owner for:
  - `GET /admin/image-library`
  - `GET /api/admin/image-library`
  - `GET /admin/attachment-library`
  - `GET /api/admin/attachment-library`
  - `GET /admin/miniprogram-library`
  - `GET /api/admin/miniprogram-library`
- Verify Next route owner is deployed and healthy.
- Verify proposed route flag state:
  - `AICRM_NEXT_ROUTE_MEDIA_READONLY=true`
  - `AICRM_NEXT_ROUTE_MEDIA_WRITES=false`
  - `AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false`
  - `AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false`
- Verify external adapters remain disabled.
- Verify latest Media smoke, Media parity, and production approval checker reports are attached.
- Verify rollback owner is online for the full window.
- Verify human signoff is complete and the execution window is active.

## During Execution

- Enable the approved readonly route flag only through the approved production change workflow.
- Verify included readonly routes return the expected status.
- Verify excluded Media write routes still point to old owner or remain disabled.
- Watch access logs and application logs.
- Verify no cloud upload occurs.
- Verify no WeCom media upload occurs.
- Verify no Media Library write endpoint is hit.
- Verify no old system write endpoint is hit.
- Record status codes and route owner evidence.

## After Execution

- Run Media readonly smoke.
- Run screenshot route check if feasible.
- Record status codes.
- Record latency if available.
- Record operator observations.
- Confirm side-effect safety remains false.
- Decide continue / rollback with product, engineering, ops, rollback, and security owners.

## Rollback

- Disable the readonly route flag:

```bash
AICRM_NEXT_ROUTE_MEDIA_READONLY=false
```

- Verify old routes serve Media readonly pages/APIs or expected legacy behavior.
- Verify Next is no longer serving canary routes.
- Verify no cloud storage upload, WeCom media upload, Media write, or old write occurred.
- Capture rollback report with timestamps, owner, trigger, and verification evidence.

## Completion Record

| field | value |
| --- | --- |
| operator |  |
| rollback owner |  |
| execution window |  |
| route flag final state |  |
| smoke result |  |
| screenshot result |  |
| side-effect safety |  |
| continue / rollback |  |
| notes |  |
