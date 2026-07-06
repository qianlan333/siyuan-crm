# Batch 2 Product Readonly Route Flags

These route flags document the local dry-run or staging-simulated stance for Batch 2 Product Management readonly. They must not be applied to production from this document.

## Dry-Run Flags

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_PRODUCT_READONLY=true
AICRM_NEXT_ROUTE_PRODUCT_WRITES=false
AICRM_NEXT_ROUTE_CHECKOUT=false
AICRM_NEXT_EXTERNAL_WECHAT_PAY=false
AICRM_NEXT_EXTERNAL_ALIPAY=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_PRODUCT_READONLY` | true | Simulates selecting Next as readonly owner for Product Management routes. |
| `AICRM_NEXT_ROUTE_PRODUCT_WRITES` | false | Product create/update/enable/disable/delete routes remain out of scope. |
| `AICRM_NEXT_ROUTE_CHECKOUT` | false | Checkout stays disabled/out of scope for Batch 2. |
| `AICRM_NEXT_EXTERNAL_WECHAT_PAY` | false | No real WeChat Pay provider call is allowed. |
| `AICRM_NEXT_EXTERNAL_ALIPAY` | false | No real Alipay provider call is allowed. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy is modified.
- No real route cutover is executed.
- No old Flask write endpoint is executed.
- No checkout, notify, WeChat Pay, or Alipay call is executed.
