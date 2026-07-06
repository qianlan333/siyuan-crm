# External Orders Customer Projection Backfill Runbook

This runbook describes how to validate and, after approval, backfill External
Orders / H5 payment customer projection into the Next customer read model.

It is safe-by-default. Do not run production writes from this runbook unless an
operator approval, backup, rollback owner, and exact target scope are recorded
outside git.

## Safety Rules

- Default mode is dry-run.
- Do not commit tokens, `Authorization` headers, raw `external_userid`, mobile
  numbers, `openid`, `unionid`, full order numbers, customer secrets, or payment
  credentials.
- Do not modify deploy/systemd/nginx/env from this runbook.
- Do not run production migration from this runbook.
- Do not execute internal event consumers from this runbook.
- Do not trigger external effects from this runbook.
- Keep all evidence redacted. Use internal numeric ids and masked identifiers
  only.

## Projection Source

The customer read model live source includes:

- customer/contact identity tables
- `automation_channel_contact.external_contact_id`
- `wechat_pay_orders.external_userid` for paid H5/external order evidence

This means a paid H5 order with a customer identity and channel contact linkage
can be discovered as a customer read-model source row. If the source row exists
but `customer_list_index_next` / `customer_detail_snapshot_next` are still
missing, the state is `backfill_required`, not `runtime_projection_repair_required`.

## Dry-Run Validation

Run readonly diagnostics first:

```bash
.venv/bin/python scripts/diagnose_external_orders_blockers.py --order-id <internal_order_id>
```

Expected dry-run evidence fields:

- `projection_source_found=true`
- `projection_target_found=false` before backfill
- `backfill_required=true`
- `can_claim_external_orders_90_plus=false` while internal event consumers are
  still pending

Then run customer read-model backfill in dry-run mode. Use a redacted or
operator-local external identity allowlist; do not paste it into git.

```bash
.venv/bin/python scripts/backfill_customer_read_model.py \
  --source fixture \
  --limit 1
```

For production operator execution, the source and target command must be decided
in an approved operations note. This repository does not include a production
write command in this runbook.

## Approval Checklist Before Any Production Write

Record outside git:

- operator name
- approval window
- exact order ids / customer identities, redacted in any committed evidence
- readonly diagnostic output showing source exists
- backup snapshot location
- rollback owner
- rollback command or restore procedure
- expected row count
- post-backfill verification command

## Production Write Guardrails

Any production backfill PR or runbook extension must preserve these constraints:

- explicit `--execute` flag
- explicit operator approval flag
- exact scoped allowlist
- preflight row count
- post-write row count
- transaction boundary
- rollback note
- no raw identifiers in committed artifacts

The existing `scripts/backfill_customer_read_model.py` remains dry-run by
default and only writes when explicitly executed against an approved target.

## Post-Backfill Verification

After approved execution, collect only redacted evidence:

```bash
.venv/bin/python scripts/diagnose_external_orders_blockers.py --order-id <internal_order_id>
```

Expected projection result:

- `customer_read_model_linkage_decision.projection_status=projection_fixed`
- `projection_source_found=true`
- `projection_target_found=true`
- `customer_list_index_next_lookup_result > 0` or
  `customer_detail_snapshot_next_lookup_result > 0`

External Orders still cannot claim 90%+ until the remaining internal event
consumer blocker is resolved.

## Rollback

This document does not authorize any production write. For a future approved
write, rollback must be documented before execution and should include:

- restore from backup, or
- scoped delete/update of only rows created by the approved backfill, and
- post-rollback readonly diagnostic confirmation.

If approval is missing, keep the state as `backfill_required` and do not write.
