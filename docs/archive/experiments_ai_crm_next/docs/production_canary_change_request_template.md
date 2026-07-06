# Production Canary Change Request Template

This template supports a human-reviewed production canary request. It cannot authorize production execution by itself. Attach fresh smoke, parity, readiness, rollback, and signoff evidence before any route flag or proxy change.

## Change Metadata

| field | value |
| --- | --- |
| change title |  |
| target batch |  |
| target routes |  |
| execution window |  |
| operator |  |
| approvers |  |
| rollback owner |  |

## Targets

| field | value |
| --- | --- |
| old service target |  |
| next service target |  |
| database target |  |
| external adapters mode |  |
| route flags |  |
| expected blast radius |  |

## Entry Criteria Evidence

- ordinary pytest:
- six parity:
- selected batch readiness:
- selected smoke:
- selected parity:
- frontend screenshot baseline:
- readonly dual-run, if applicable:
- legacy drift review:
- side-effect safety:

## Monitoring Plan

- route-level status code:
- latency:
- 4xx / 5xx:
- application error logs:
- access logs:
- external adapter call counters:
- route flag state:
- rollback state:

## Rollback Plan

- rollback owner:
- rollback trigger:
- route flag rollback command:
- old route verification command:
- Next no-longer-serving verification:
- communication owner:
- evidence path:

## Stop Conditions

- any production config differs from approved change request
- any write route enters readonly batch
- any external adapter call appears unexpectedly
- smoke blocker
- 5xx spike
- rollback owner unavailable

## Communication Plan

- pre-canary notice:
- during-canary channel:
- rollback notice:
- post-canary summary:

## Post-Canary Review

- observed route status:
- observed latency:
- observed errors:
- side-effect safety:
- rollback outcome:
- lessons learned:
- follow-up owner:

## Approval Decision

| field | value |
| --- | --- |
| decision | pending_human_signoff |
| product owner |  |
| engineering owner |  |
| ops/deployment owner |  |
| rollback owner |  |
| data/security reviewer |  |
| external adapter owner | not applicable unless real external service is involved |

Required attachments:

- latest smoke JSON/markdown
- latest parity JSON/markdown
- latest readiness JSON/markdown
- rollback runbook link
- signoff record
