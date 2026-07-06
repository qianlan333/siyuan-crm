# Production Canary Rollback Runbook

This runbook defines route-level rollback for a future readonly production canary. It does not execute destructive database rollback, delete old-system routes, or cut write routes.

## Roles

| role | responsibility |
| --- | --- |
| rollback owner | Makes rollback decision and executes approved route flag/proxy rollback. |
| operator | Runs verification commands and captures evidence. |
| engineering owner | Diagnoses Next route failure and confirms no writes/external calls occurred. |
| product owner | Communicates user-facing impact. |

## Rollback Triggers

- canary route 5xx
- unexpected 4xx outside documented legacy drift
- latency regression beyond approved threshold
- any write route receives traffic
- any external adapter call appears unexpectedly
- production config differs from approved change request
- rollback owner or monitoring owner becomes unavailable

## Decision Tree

1. Detect trigger.
2. Pause any further batch expansion.
3. Confirm trigger with logs/smoke output.
4. If trigger is safety-related, rollback immediately.
5. Disable the selected readonly route flag.
6. Restore old route owner.
7. Verify old route behavior.
8. Verify Next is no longer serving the selected route.
9. Capture evidence and communicate rollback result.

## Route Flag Rollback Commands

```bash
# PSEUDO ONLY - execute only through approved production change workflow
AICRM_NEXT_ROUTE_MEDIA_READONLY=false
AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
```

## Verification

| step | expected result |
| --- | --- |
| disable route flag | selected route no longer points to Next |
| restore old route owner | old Flask handles the route or returns its expected legacy auth redirect |
| verify old route | expected old status/page/API response |
| verify Next no longer serving route | canary header/cookie/flag no longer selects Next |
| check side-effect safety | no write/external call was executed |
| capture evidence | smoke output, logs, timestamp, operator, rollback owner |

## Communication

- Notify release channel when rollback starts.
- Include batch, route, trigger, rollback owner, and expected verification time.
- Notify when old route owner is restored.
- Attach rollback evidence and post-canary review.

## Postmortem Template

| field | value |
| --- | --- |
| batch |  |
| trigger |  |
| detection time |  |
| rollback start |  |
| rollback complete |  |
| route owner after rollback | old Flask |
| customer impact |  |
| side-effect safety |  |
| root cause |  |
| follow-up owner |  |

## Guardrails

- Do not run destructive database rollback from this runbook.
- Do not delete old-system routes.
- Do not cut write routes.
- Do not enable real external adapters during rollback.
- Do not continue to the next batch until rollback evidence is reviewed.
