# External Orders Enablement Acceptance

Date: 2026-06-22

## Goal

Prepare external order APIs for controlled enablement without changing
production env or committing secrets. The 90%+ readiness target is safe token
behavior, stable read shape, and order/customer/channel correlation evidence.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders \
  --request-mode dry_run \
  --order-no <optional_order_id_or_order_no> \
  --external-order-id <optional_external_order_id> \
  --idempotency-key <optional_idempotency_key> \
  --customer-id <optional_customer_id> \
  --channel-id <optional_channel_id> \
  --source <optional_source> \
  --internal-event-id <optional_internal_event_id> \
  --admin-order-visibility <visible|not_found|not_provided>
```

For gray lifecycle readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders_gray \
  --order-no <gray_order_no>
```

The diagnostic must keep:

- `real_external_call_executed=false`
- `production_write_executed=false`
- token values redacted
- `deploy_or_env_modified=false`
- no raw `Authorization` header, request token, phone number, or raw external
  user identifier in output

## Acceptance Cases

- Missing server token: controlled unavailable state is expected.
- Missing bearer token: request is rejected.
- Wrong bearer token: request is rejected.
- Correct bearer token: local order list/detail can be read.
- Unknown order: controlled not found.
- Duplicate gray order input: no duplicate business record should be created.
- Reconciliation: order/customer/channel/source and internal event/job state are
  visible in admin or diagnostic payloads.

## Evidence Fields

The `external_orders_evidence` payload must include:

- `token_configured`
- `token_redacted` / `token_never_logged`
- `auth_status`
- `route_owner`
- `fallback_used`
- `controlled_disabled_reason`
- `request_mode`: `no_token`, `wrong_token`, `valid_token`, or `dry_run`
- `order_id` / `external_order_id`
- `idempotency_key`
- `customer_id` / `channel_id` / `source`
- `internal_event_id`
- `admin_order_visibility`
- `reconciliation_status`
- `retryable`
- `operator_action_required`
- `business_explanation`
- `real_external_call_executed=false`

## Blocking Reason Matrix

| Code | Meaning | Operator action |
| --- | --- | --- |
| `missing_internal_token_config` | `AUTOMATION_INTERNAL_API_TOKEN` is not configured. | Keep route controlled-disabled until an authorized operator configures the token outside git. |
| `missing_request_token` | The server token exists, but the request token evidence is missing. | Collect a redacted request-token check; never paste the token itself. |
| `invalid_request_token` | The supplied request token does not match the configured token. | Verify auth failure behavior and rotate/reissue credentials outside git if needed. |
| `token_configured_but_not_executed` | Token readiness exists, but dry-run evidence has not linked an order. | Attach order, idempotency, customer/channel/source, event, and admin visibility evidence. |
| `missing_order_evidence` | No order id or external order id was attached. | Attach a redacted internal order id or external order id placeholder. |
| `missing_idempotency_evidence` | Duplicate/idempotency evidence is missing. | Attach the idempotency key or duplicate-order reconciliation id. |
| `missing_customer_channel_link` | Customer, channel, or source correlation is missing. | Attach all three linkage fields before claiming 90%+. |
| `missing_internal_event` | No internal event id was attached. | Attach the event created or reused by the order flow. |
| `missing_admin_visibility` | Admin/order projection visibility is missing. | Attach the admin order view or diagnostic projection evidence. |
| `order_linked` | Order, idempotency, customer/channel/source, event, and admin visibility evidence are attached. | Move evidence into the report template for operator review. |

## Production Preconditions

- `AUTOMATION_INTERNAL_API_TOKEN` configured by an authorized operator.
- Gray source approved.
- Token never appears in logs, docs, scripts, or PR body.
- Evidence report uses only redacted ids or internal order/job/event ids.

## Evidence Template

Use
`docs/reports/external_orders_enablement_evidence_template.md` for operator
evidence. If the operator has not completed a valid-token gray run, the report
must remain `READINESS_ONLY` and must not claim external orders are 90%+
complete.

## Non-Goals

- No token creation in git.
- No production env edit.
- No real external provider call from this PR.
- No production DB write or migration execution from the diagnostic.

## Next Action

Run a separate gray acceptance PR after the operator configures token and gray
source credentials outside git.
