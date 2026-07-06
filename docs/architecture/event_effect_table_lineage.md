# Event And External Effect Table Lineage

This document records the PR #13 boundary between internal events, business
outboxes, legacy webhook delivery ledgers, and the canonical external-effect
queue. It is intentionally a lineage view first; high-risk physical table
merges must be done in later PRs with producer/consumer evidence.

## Canonical Roles

| Table | Role | Lifecycle | Current owner | Convergence rule |
| --- | --- | --- | --- | --- |
| `internal_event` | Canonical internal event ledger | event | `platform_foundation.internal_events.service` | Keep. Internal handlers must not execute real external calls directly. |
| `internal_event_consumer_run` | Internal event consumer queue state | queue | `platform_foundation.internal_events.worker` | Keep. One row per event/consumer execution state. |
| `internal_event_consumer_attempt` | Internal consumer attempt audit | audit | `platform_foundation.internal_events.worker` | Keep. Append-only execution evidence. |
| `external_effect_job` | Canonical external side-effect queue | queue | `platform_foundation.external_effects.service` | Keep. Real external calls should enter here. |
| `external_effect_attempt` | External side-effect attempt audit | audit | `platform_foundation.external_effects.worker` | Keep. Append-only execution evidence. |
| `domain_event_outbox` | Commerce business-event outbox | event | `commerce.external_push_outbox` | Candidate to converge after commerce outbox events can be represented by internal events/effects. |
| `external_push_delivery` | Legacy commerce external-push delivery ledger | legacy_boundary | `commerce.external_push_admin` | Candidate to project from external effects after retry/status parity is proven. |
| `outbound_webhook_deliveries` | Legacy outbound webhook delivery queue/ledger | queue | outbound webhook runtime/admin jobs | Candidate to converge to external effects after webhook retry parity is proven. |
| `outbound_event_outbox` | Legacy outbound event outbox | event | legacy outbound publisher | Candidate after producers/readers are audited. |

## Allowed Flow

```text
domain business action
  -> internal_event for in-process business state fanout
  -> internal_event_consumer_run / internal_event_consumer_attempt for handler execution
  -> external_effect_job for real external side effects
  -> external_effect_attempt for external execution evidence
```

Commerce-specific legacy flow still exists:

```text
commerce action
  -> domain_event_outbox
  -> external_push_delivery
  -> external_effect_job when retry/test execution is delegated to the external-effect queue
```

Webhook-specific legacy flow still exists:

```text
outbound event
  -> outbound_event_outbox / outbound_webhook_deliveries
  -> future external_effect_job convergence after retry and status parity is proved
```

## PR #13 Guardrails

1. `internal_event*` remains internal only; external calls must be queued through
   `external_effect_job`.
2. `external_effect_job` and `external_effect_attempt` are the canonical external
   side-effect queue and audit pair.
3. `domain_event_outbox`, `external_push_delivery`,
   `outbound_webhook_deliveries`, and `outbound_event_outbox` are not deleted in
   PR #13 because active runtime references still exist.
4. Later deletion PRs must prove producer and reader parity before marking any of
   the legacy boundary tables as retired.
