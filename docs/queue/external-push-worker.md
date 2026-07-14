# Legacy External Push Worker Retirement

`scripts/run_external_push_worker.py` is a retired compatibility entrypoint. It is count-only and cannot consume `domain_event_outbox`, retry `external_push_delivery`, create an External Effect job, or call a webhook.

## Canonical owner

```text
WeChat payment callback
  -> paid order + payment.succeeded internal_event_outbox (one transaction)
  -> internal-event relay
  -> payment.succeeded:webhook_order_paid_consumer
  -> external_push_delivery + external_effect_job (one transaction)
  -> openclaw-external-effect-worker
  -> provider attempt evidence
```

`domain_event_outbox` remains readable for historical parity and reconciliation only. New payment callbacks do not write it.

## Runtime retirement

- `openclaw-external-push-worker.timer` and `.service` are absent from `deploy/`.
- Both unit names are in `deploy/production_runtime_units.json:retired_forbidden`.
- Every deploy runs `systemctl disable --now` and verifies that neither unit is active.
- The compatibility CLI delegates only to commerce fulfillment count-only reconciliation and reports `real_external_call_executed=false`.

Do not reinstall or manually start the retired units. To pause outbound order webhooks, stop the canonical internal-event/external-effect workers while leaving durable outbox/jobs intact.

## Verification

```bash
python scripts/run_external_push_worker.py
systemctl is-active openclaw-external-push-worker.timer || true
systemctl is-active openclaw-external-push-worker.service || true
python scripts/ops/reconcile_commerce_fulfillment.py
```

Expected CLI fields include `legacy_worker_retired=true`, `mode=count_only`, `database_mutation_performed=false`, and `real_external_call_executed=false`.
