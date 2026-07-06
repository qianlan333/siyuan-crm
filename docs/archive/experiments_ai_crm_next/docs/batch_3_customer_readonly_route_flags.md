# Batch 3 Customer Readonly Route Flags

These route flags document the local dry-run or staging-simulated stance for Batch 3 Customer Read Model readonly. They must not be applied to production from this document.

## Dry-Run Flags

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=true
AICRM_NEXT_ROUTE_CUSTOMER_WRITES=false
AICRM_NEXT_EXTERNAL_WECOM_SYNC=false
AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC=false
AICRM_NEXT_EXTERNAL_TAG_REFRESH=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_CUSTOMER_READONLY` | true | Simulates selecting Next as readonly owner for Customer Read Model routes. |
| `AICRM_NEXT_ROUTE_CUSTOMER_WRITES` | false | Customer writes remain out of scope. |
| `AICRM_NEXT_EXTERNAL_WECOM_SYNC` | false | Real WeCom contact sync is disabled. |
| `AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC` | false | Real message archive sync is disabled. |
| `AICRM_NEXT_EXTERNAL_TAG_REFRESH` | false | Real tag refresh is disabled. |
| `AICRM_NEXT_EXTERNAL_OPENCLAW` | false | Real OpenClaw push/webhook is disabled. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy is modified.
- No real route cutover is executed.
- No old Flask write endpoint is executed.
- No WeCom sync, archive sync, tag refresh, or OpenClaw call is executed.
