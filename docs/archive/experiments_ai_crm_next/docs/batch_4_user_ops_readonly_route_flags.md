# Batch 4 User Ops Readonly Route Flags

These route flags document the local dry-run or staging-simulated stance for Batch 4 User Ops readonly. They must not be applied to production from this document.

## Dry-Run Flags

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_USER_OPS_READONLY=true
AICRM_NEXT_ROUTE_USER_OPS_WRITES=false
AICRM_NEXT_USER_OPS_DND=false
AICRM_NEXT_USER_OPS_BATCH_SEND=false
AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_USER_OPS_READONLY` | true | Simulates selecting Next as readonly owner for User Ops routes. |
| `AICRM_NEXT_ROUTE_USER_OPS_WRITES` | false | User Ops writes remain out of scope. |
| `AICRM_NEXT_USER_OPS_DND` | false | DND write remains disabled. |
| `AICRM_NEXT_USER_OPS_BATCH_SEND` | false | Batch-send preview and execute remain disabled. |
| `AICRM_NEXT_USER_OPS_DEFERRED_JOBS` | false | Deferred jobs remain disabled. |
| `AICRM_NEXT_EXTERNAL_WECOM_DISPATCH` | false | Real WeCom dispatch is disabled. |
| `AICRM_NEXT_EXTERNAL_WECOM_MEDIA` | false | Real WeCom media upload is disabled. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy is modified.
- No real route cutover is executed.
- No old Flask write endpoint is executed.
- No DND, batch-send, deferred job, WeCom dispatch, or WeCom media upload is executed.
