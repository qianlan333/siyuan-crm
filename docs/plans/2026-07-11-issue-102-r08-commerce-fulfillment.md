# R08 Payment / Refund / Entitlement Transaction Closure

Issue: #102
Parent: #67

## Scope

This slice removes split durability boundaries from existing WeChat payment, refund, service-period entitlement, and configured order webhook flows. It adds no route, page, menu, product, payment method, refund type, or provider capability.

## Delivered design

1. Payment callback updates the order and inserts one `payment.succeeded` outbox in the same caller-owned PostgreSQL transaction.
2. Entitlement and configured order push are owned only by `payment.succeeded` consumers. The callback no longer writes `domain_event_outbox` or directly plans an External Effect.
3. Refund request locks the order and writes the refund row, audit event, and refund External Effect job in one transaction.
4. Full refund accounting and one `refund.succeeded` outbox share one transaction; entitlement refund is an idempotent consumer.
5. Caller-owned transactional External Effect creation aligns provider continuation with the business projection.
6. The legacy external-push timer/service is retired-forbidden; its CLI is count-only.
7. Commerce reconciliation is count-only by default. Explicit repair can only ensure durable internal-event outbox rows and requires actor/reason.
8. Revision `0101_commerce_fulfillment_invariants` adds partial refund identity uniqueness and active-refund lookup indexes without destructive schema changes.

## Verification contract

- Real PostgreSQL fault injection for payment/refund/outbox/effect rollback.
- Two-thread refund barrier proving no over-refund.
- Duplicate payment/refund callbacks proving one outbox and no double accounting.
- Missing-unionid retry followed by authoritative DB reload and one entitlement.
- Refund consumer failure followed by retry and one refund event.
- Delivery/effect atomicity and idempotency.
- Count-only/repair-only reconciliation safety.
- Full architecture, lifecycle, ownership, runtime-inventory, migration, frontend, and repository-wide PostgreSQL gates.

## Rollback

Rollback the application to the exact previous release SHA and stop canonical workers if needed. Keep the expand-only `0101` indexes and all durable outbox/jobs. Never restore the retired legacy sender as a rollback mechanism.
