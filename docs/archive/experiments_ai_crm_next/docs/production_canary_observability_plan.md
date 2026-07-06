# Production Canary Observability Plan

This is a monitoring plan for future production canary review. It is not an already deployed observability agent and does not imply production traffic has been cut.

## Common Signals

| signal | purpose | expected source |
| --- | --- | --- |
| route-level status code | confirm route health and rollback impact | proxy/access logs |
| latency | detect regressions under canary traffic | proxy/app metrics |
| 4xx / 5xx | catch auth, routing, and server errors | proxy/app logs |
| error logs | identify stack traces and contract failures | AI-CRM Next logs |
| access logs | confirm route owner and canary cohort | proxy logs |
| side-effect safety signals | verify readonly canary does not write or call external adapters | smoke/readiness report fields and adapter counters |
| external adapter calls | confirm WeCom/OAuth/payment/OpenClaw/cloud remain disabled unless explicitly approved | adapter logs/counters |
| route flag state | confirm active owner and rollback state | deployment/runtime config |
| rollback state | confirm old route owner after rollback | proxy/app route verification |

## Batch-Specific Monitoring

| batch | module | key signals | forbidden signal |
| --- | --- | --- | --- |
| Batch 1 | Media readonly | image/attachment/miniprogram GET status and latency | cloud upload or WeCom media upload |
| Batch 2 | Product readonly | admin products and public product GET status | checkout, payment notify, payment provider call |
| Batch 3 | Customer readonly | list/detail/timeline/recent-message GET status | WeCom sync, archive sync, tag refresh, OpenClaw call |
| Batch 4 | User Ops readonly | overview 8-card integrity, list filters, send-records GET status | DND, batch-send, deferred jobs, WeCom dispatch/media |
| Batch 5 | Questionnaire readonly | admin list/detail/export/debug and public page/read/result GET status | submit, OAuth, WeCom tag, external webhook |

Old Automation Conversion readonly is retired and is not monitored as a canary batch.

## Expected Alerts

- any 5xx on canary route
- sustained 4xx increase not explained by documented auth/page drift
- unexpected external adapter call
- any write endpoint hit during readonly canary
- route flag state differs from approved change request
- rollback verification fails

## Manual Observation Checklist

1. Confirm selected batch and route flags match the approved change request.
2. Confirm canary is readonly and limited to the approved route set.
3. Confirm status code and latency stay within the agreed window.
4. Confirm side-effect safety fields remain false.
5. Confirm no real external adapter call appears.
6. Confirm rollback owner is present.
7. Capture reports before and after canary.
8. Record Go/No-Go decision and any rollback reason.

## Current Limitation

Production observability is not deployed from this document. Before a real production canary, the ops owner must map these signals to concrete dashboards, log queries, alert thresholds, and retention paths.
