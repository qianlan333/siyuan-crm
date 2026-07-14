# Commerce Fulfillment Reconciliation Runbook

This command diagnoses payment/refund/entitlement continuation gaps without exposing contact data or calling a provider:

```bash
python scripts/ops/reconcile_commerce_fulfillment.py
```

Deployment runs exactly this count-only form. It reports:

- `paid_without_payment_outbox`
- `paid_service_product_without_entitlement_or_open_consumer`
- `successful_full_refund_with_active_entitlement`
- `refund_request_without_effect`
- `duplicate_order_paid_effect` (only duplicates that still contain an open job)
- `stale_succeeded_external_push_delivery_projection`
- `legacy_domain_outbox_pending`

Output contains counts and at most 20 numeric internal IDs per class. It does not include mobile, unionid, openid, external_userid, webhook payloads, questionnaire answers, or messages. Confirm `database_mutation_performed=false`, `consumer_executed=false`, `real_external_call_executed=false`, and `pii_in_output=false`.

Payment-outbox and refund-request gaps are actionable only at or after the explicit production cutover `2026-07-13T09:46:09Z` (production promotion run `29240024773`). The checker does not infer this boundary from the first existing outbox or effect row, because that would hide the first missing row on a fresh tenant. For orders without `paid_at`, it uses immutable `created_at`; a later unrelated `updated_at` must not turn historical data into a post-cutover alert.

## Safe continuation repair

Repair requires an auditable actor and reason:

```bash
python scripts/ops/reconcile_commerce_fulfillment.py \
  --repair \
  --projection-only \
  --actor "$OPERATOR" \
  --reason "reconcile already-succeeded external push projection" \
  --limit 100
```

`--projection-only` is the production-safe default for stale delivery UI state: it only projects an already-succeeded External Effect into its legacy `external_push_delivery` read model. Without that flag, repair may also ensure idempotent `payment.succeeded` or `refund.succeeded` outbox rows. Both modes store hashes of the actor and reason in repair metadata. Neither mode relays outbox rows, runs consumers, edits entitlement state directly, creates/refires refund provider jobs, or dispatches External Effects.

After repair, run count-only mode again, inspect internal-event queue state, and let the normal workers process approved due work. `refund_request_without_effect`, open duplicate effects, and legacy outbox backlog require investigation; this repair command intentionally does not manufacture or dispatch provider work.

## Incident pause and rollback

For incorrect or uncertain provider state, stop the canonical internal-event and external-effect worker timers. Preserve outbox and jobs, follow R07 unknown-after-dispatch reconciliation, and fix forward. Never restart `openclaw-external-push-worker.timer` or `.service`; both are retired-forbidden.
