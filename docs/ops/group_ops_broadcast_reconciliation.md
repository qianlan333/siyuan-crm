# Group Ops / Broadcast count-only reconciliation

Run this after migration `0103_broadcast_delivery_state_machine` and after the
broadcast worker and automation scheduler units are installed:

```bash
python scripts/ops/reconcile_group_ops_broadcast.py
```

The command emits aggregate counts only. It does not read payload fields into
its result, list recipients, repair rows, execute a consumer, or call WeCom or
webhook providers. A non-zero count is evidence for investigation, not
permission to retry an `unknown_after_dispatch` job.

The report covers stale dispatches, ambiguous outcomes, cloud-plan projection
mismatches, sent jobs missing delivery evidence, duplicate idempotency keys,
retired P1 runtime artifacts, and retired P1 tables that still declare an
active writer or runtime entrypoint.

Delivery-state checks are scoped to the first completed production deployment
of R10 (`2026-07-13 05:42:30 UTC`). Earlier rows predate the atomic delivery
state machine and remain historical data rather than actionable R10 gaps.
Duplicate idempotency keys remain a global invariant and are not cutover-scoped.

There is intentionally no repair flag. Any repair or resend requires a separate
issue, explicit authorization, and provider-side evidence proving that a retry
cannot duplicate delivery.
