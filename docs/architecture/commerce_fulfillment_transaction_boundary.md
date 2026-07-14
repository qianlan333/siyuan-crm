# Commerce Fulfillment Transaction Boundary

Issue #102 (Epic #67 R08) makes payment, refund, entitlement, and configured order-push continuation durable without adding product behavior.

## Ownership

| Fact or continuation | Sole write/execute owner | Atomic boundary |
| --- | --- | --- |
| paid order + `payment.succeeded` | H5 WeChat Pay callback | one PostgreSQL transaction |
| entitlement grant/renew | `payment.succeeded:service_period_entitlement_consumer` | idempotent service-period transaction |
| order webhook planning | `payment.succeeded:webhook_order_paid_consumer` | `external_push_delivery` + `external_effect_job` in one transaction |
| refund request | commerce refund command | refund row + audit event + refund External Effect job in one transaction |
| full refund + `refund.succeeded` | WeChat refund callback | one PostgreSQL transaction |
| entitlement refund | `refund.succeeded:service_period_refund_consumer` | idempotent service-period transaction |
| real provider call | External Effect worker | lease/CAS/attempt boundary from R07 |

The payment callback no longer writes `domain_event_outbox` and never plans an external push. The retired legacy external-push worker cannot send or retry webhooks.

## Failure and replay rules

- A `payment.succeeded` outbox insert failure rolls back the paid-order update; WeChat receives `FAIL` and can retry.
- Duplicate payment notification/outbox relay is collapsed by `payment.succeeded:{out_trade_no}`.
- The entitlement consumer reloads the authoritative order. Missing unionid and DB faults remain retryable; after identity backfill, retry grants exactly once.
- Refund requests lock the order with `FOR UPDATE`, recalculate successful/in-flight refund value, and reject concurrent over-refund.
- Any refund row, audit, or External Effect insertion fault rolls the request transaction back.
- A `refund.succeeded` outbox insertion fault rolls back refund/order accounting. Duplicate success notifications do not increment refunded value twice.
- Entitlement refund failure does not lose continuation. Consumer retry is collapsed by the service-period `refunded` event key.
- Internal-event consumers and reconciliation never invoke a provider. Only the External Effect worker may do so.

## Rollback

Schema revision `0101_commerce_fulfillment_invariants` is expand-only. Code rollback uses the prior release SHA while retaining indexes and pending outbox/jobs. Do not restore the legacy sender as a rollback path. If continuation processing is unhealthy, stop the internal-event and external-effect workers, fix forward, then replay durable work.

## Evidence

`tests/test_r08_commerce_fulfillment_postgres.py` proves transaction rollback, duplicate callbacks, missing-identity recovery, concurrent refund serialization, external-push planning atomicity, entitlement refund retry, count-only reconciliation, and the migration indexes against real PostgreSQL.
