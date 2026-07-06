# Gray Rehearsal Batch 1 Route Flags

These route flags document the local dry-run stance for Batch 1 Media Library readonly. They were not applied to production.

## Dry-Run Flags

```bash
# PSEUDO ONLY - local rehearsal record, do not apply to production
AICRM_NEXT_ROUTE_MEDIA_READONLY=true
AICRM_NEXT_ROUTE_MEDIA_WRITES=false
AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_MEDIA_READONLY` | true | Simulates selecting Next as the readonly owner for Media Library routes. |
| `AICRM_NEXT_ROUTE_MEDIA_WRITES` | false | Media create/update/delete routes remain out of scope. |
| `AICRM_NEXT_EXTERNAL_CLOUD_STORAGE` | false | No real cloud storage upload is allowed. |
| `AICRM_NEXT_EXTERNAL_WECOM_MEDIA` | false | No real WeCom media upload is allowed. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - local rehearsal record, do not apply to production
AICRM_NEXT_ROUTE_MEDIA_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy was modified.
- No real route cutover was executed.
- No old Flask write endpoint was executed.
- No cloud storage or WeCom media upload was executed.
