# External Orders Enablement Evidence Template

Status: `READINESS_ONLY`

Use this template after running the external orders diagnostic. Do not commit
real tokens, `Authorization` headers, raw external user identifiers, phone
numbers, or customer secrets. Evidence may include redacted ids, internal
order/event ids, and operator-owned screenshots with secrets removed.

## Operator And Window

- Operator:
- Review date:
- Gray window:
- Environment:
- Source system:
- Approval reference:

## Safety Attestation

- `real_external_call_executed=false` by diagnostic default:
- `production_write_executed=false` by diagnostic default:
- `deploy_or_env_modified=false`:
- Token never logged:
- Request token redacted:
- No raw phone number / raw external_userid / `Authorization` header:

## Diagnostic Command

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders \
  --request-mode <dry_run|no_token|wrong_token|valid_token> \
  --order-no <redacted_internal_order_id_or_not_provided> \
  --external-order-id <redacted_external_order_id_or_not_provided> \
  --idempotency-key <redacted_idempotency_key_or_not_provided> \
  --customer-id <redacted_customer_id_or_not_provided> \
  --channel-id <redacted_channel_id_or_not_provided> \
  --source <source_or_not_provided> \
  --internal-event-id <event_id_or_not_provided> \
  --admin-order-visibility <visible|not_found|not_provided>
```

## Evidence Payload

| Field | Value | Notes |
| --- | --- | --- |
| `token_configured` |  | Do not paste token value. |
| `token_redacted` |  | Must be `true`. |
| `token_never_logged` |  | Must be `true`. |
| `auth_status` |  | Controlled disabled, missing token, invalid token, or valid-token readiness. |
| `route_owner` |  | Expected `ai_crm_next`. |
| `fallback_used` |  | Expected `false`. |
| `controlled_disabled_reason` |  | Required when token is not configured. |
| `request_mode` |  | `dry_run`, `no_token`, `wrong_token`, or `valid_token`. |
| `order_id` |  | Redacted internal order id or `not_provided`. |
| `external_order_id` |  | Redacted external order id or `not_provided`. |
| `idempotency_key` |  | Redacted idempotency key or `not_provided`. |
| `customer_id` |  | Redacted customer id or `not_provided`. |
| `channel_id` |  | Redacted channel id or `not_provided`. |
| `source` |  | Source label, not a secret. |
| `internal_event_id` |  | Internal event id or `not_provided`. |
| `admin_order_visibility` |  | `visible`, `not_found`, or `not_provided`. |
| `reconciliation_status` |  | Expected `order_linked` only after evidence is complete. |
| `retryable` |  | Explain why if true. |
| `operator_action_required` |  | Explain next action. |
| `business_explanation` |  | Business-readable explanation for operators. |

## Blocking Reason Matrix

| Code | Present? | Evidence / next action |
| --- | --- | --- |
| `missing_internal_token_config` |  |  |
| `missing_request_token` |  |  |
| `invalid_request_token` |  |  |
| `token_configured_but_not_executed` |  |  |
| `missing_order_evidence` |  |  |
| `missing_idempotency_evidence` |  |  |
| `missing_customer_channel_link` |  |  |
| `missing_internal_event` |  |  |
| `missing_admin_visibility` |  |  |
| `order_linked` |  |  |

## Idempotency Evidence

- Original external order id:
- Duplicate request id:
- Idempotency key:
- Duplicate handling result:
- Business record count after duplicate:

## Order Linkage Evidence

- Order projection visible:
- Customer linked:
- Channel linked:
- Source linked:
- Internal event linked:
- Admin order visibility:

## Decision

- `READINESS_ONLY`: token or evidence is incomplete, or only dry-run diagnostics
  were collected.
- `ORDER_LINKED_EVIDENCE_ATTACHED`: valid-token readiness plus order,
  idempotency, customer/channel/source, event, and admin visibility evidence are
  attached.

Do not mark external orders as 90%+ until operator-owned evidence reaches
`ORDER_LINKED_EVIDENCE_ATTACHED` without exposing secrets.
