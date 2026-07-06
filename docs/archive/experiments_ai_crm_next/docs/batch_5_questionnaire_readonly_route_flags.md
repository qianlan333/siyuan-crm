# Batch 5 Questionnaire Readonly Route Flags

These route flags document the local dry-run or staging-simulated stance for Batch 5 Questionnaire readonly. They must not be applied to production from this document.

## Dry-Run Flags

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true
AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false
AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false
AICRM_NEXT_QUESTIONNAIRE_OAUTH=false
AICRM_NEXT_EXTERNAL_WECOM_TAG=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

## Meaning

| flag | rehearsal value | meaning |
| --- | --- | --- |
| `AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY` | true | Simulates selecting Next as readonly owner for Questionnaire admin/public routes. |
| `AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES` | false | Admin writes remain out of scope. |
| `AICRM_NEXT_QUESTIONNAIRE_SUBMIT` | false | H5 submit remains disabled in readonly canary. |
| `AICRM_NEXT_QUESTIONNAIRE_OAUTH` | false | Real OAuth remains disabled. |
| `AICRM_NEXT_EXTERNAL_WECOM_TAG` | false | Real WeCom tag mutation remains disabled. |
| `AICRM_NEXT_EXTERNAL_WEBHOOK` | false | Real external webhook push/retry remains disabled. |

## Rollback

Dry-run rollback instruction:

```bash
# PSEUDO ONLY - staging simulated record, do not apply to production
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
```

Expected route owner after rollback: old Flask.

## Safety Notes

- No production host or secret is included.
- No production proxy is modified.
- No real route cutover is executed.
- No old Flask write endpoint is executed.
- No submit, real OAuth, WeCom tag mutation, or external webhook is executed.
