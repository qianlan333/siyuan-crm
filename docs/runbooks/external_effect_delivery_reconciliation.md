# External effect delivery reconciliation

Run the count-only diagnostic from the repository root:

```bash
python scripts/ops/reconcile_external_effect_dispatch.py
```

The command reads aggregate counts only. It does not mutate the database, include
job payloads or contact identifiers, repair a row, enqueue a retry, or call a provider.

Investigate any non-zero value:

- `unknown_after_dispatch_count`: compare provider-side receipts with the stored
  attempt before deciding whether delivery happened.
- `stale_dispatching_count`: a lease expired while a dispatch was in progress; the
  worker will quarantine the row as unknown.
- `succeeded_without_evidence_count`: an actionable post-cutover success lacks either
  real/internal side-effect evidence or provider-result evidence. Valid in-process
  Automation Agent dispatches use `internal_side_effect_executed=true` and do not count
  as missing delivery evidence.
- `simulated_recorded_as_succeeded_count`: a fake result is incorrectly represented as
  delivered.
- `dispatching_without_active_lease_count` or `lease_on_non_dispatching_count`: the
  durable claim fields disagree with the state machine.

Never bulk-requeue unknown outcomes. After provider reconciliation, use the admin retry
API with an authenticated action token and all three fields:

```json
{
  "actor": "operator-id",
  "reason": "provider confirms no delivery",
  "confirm_duplicate_risk": true
}
```

The retry acknowledgement is auditable and still passes through the normal execution
gates and shared lease claim.

The report keeps pre-cutover delivery-truth defects in `historical_counts`. They remain
auditable but do not make the current queue unhealthy and must not be bulk-replayed.
