# WeCom Auth And Callback Operator Acceptance

Date: 2026-06-22

## Goal

Define readiness for WeCom operator auth and callback gray validation without
enabling real token exchange or committing callback secrets.

## Diagnostics

Operator auth readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth \
  --redirect-uri-expected <expected_redirect_uri> \
  --auth-start-status <expected_302|verified_302> \
  --operator-identity-evidence <redacted_operator_identity_or_not_provided> \
  --permission-scope-evidence <scope_evidence_or_not_provided>
```

Callback gray readiness:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth \
  --callback-signature-status <not_provided|invalid|valid> \
  --callback-event-id <redacted_callback_event_id_or_not_provided> \
  --internal-event-id <inbound_event_id_or_not_provided> \
  --idempotency-key <redacted_idempotency_key_or_not_provided> \
  --duplicate-callback-handling <not_collected|reused_idempotency_key> \
  --customer-event-visibility <visible|not_provided> \
  --group-ops-permission-evidence <evidence_or_not_provided> \
  --material-permission-evidence <evidence_or_not_provided>
```

Both diagnostics must report:

- `real_external_call_executed=false`
- `production_write_executed=false`
- configured env values redacted
- `token_redacted=true`
- `token_never_logged=true`
- no raw `external_userid`, `Authorization` header, `access_token`,
  `corpsecret`, or callback secret in output

## Evidence Fields

The `wecom_evidence` payload must include:

- `corp_id_configured`
- `agent_id_configured`
- `redirect_uri_configured`
- `redirect_uri_expected`
- `auth_start_status`
- `callback_missing_code_status`
- `callback_invalid_state_status`
- `operator_identity_evidence`
- `token_redacted` / `token_never_logged`
- `callback_signature_status`
- `callback_event_id`
- `inbound_event_id`
- `idempotency_key`
- `duplicate_callback_handling`
- `permission_scope_evidence`
- `customer_event_visibility`
- `group_ops_permission_evidence`
- `material_permission_evidence`
- `retryable`
- `operator_action_required`
- `business_explanation`
- `real_external_call_executed=false`

## Blocking Reason Matrix

| Code | Meaning | Operator action |
| --- | --- | --- |
| `missing_corp_id` | `WECOM_CORP_ID` is not configured. | Configure it outside git before operator auth readiness. |
| `missing_agent_id` | `WECOM_AGENT_ID` is not configured. | Configure it outside git before auth start readiness. |
| `missing_redirect_uri` | `ADMIN_LOGIN_REDIRECT_URI` is not configured. | Configure and verify the expected redirect URI outside git. |
| `auth_start_not_verified` | Auth start 302 expectation or observation is not attached. | Attach `expected_302` or `verified_302` readiness evidence. |
| `missing_operator_identity` | Redacted operator identity evidence is missing. | Attach a redacted operator/admin identity reference. |
| `missing_callback_signature_evidence` | Callback signature verification evidence is missing. | Attach signature verification evidence before callback readiness. |
| `invalid_callback_signature` | Callback signature failed verification. | Confirm no work was enqueued and collect failure evidence. |
| `missing_callback_event` | Callback event id evidence is missing. | Attach a redacted callback event id. |
| `missing_inbound_event` | Inbound/internal event evidence is missing. | Attach the inbound event id generated or reused by the callback. |
| `missing_idempotency_evidence` | Duplicate callback/idempotency evidence is missing. | Attach idempotency key or duplicate handling evidence. |
| `missing_permission_scope` | Customer/group/material/operator permission evidence is incomplete. | Attach all required permission readiness fields. |
| `operator_auth_ready` | Operator auth readiness and permission evidence are attached. | Continue to callback gray evidence collection. |
| `callback_linked` | Operator auth, signature, callback event, inbound event, idempotency, and permission evidence are attached. | Move evidence into the report template for operator review. |

## Acceptance Cases

- Auth start route is reachable.
- Callback missing code returns controlled failure.
- Invalid state returns controlled failure.
- Token exchange remains blocked unless separately approved.
- Invalid callback signature creates no job.
- Duplicate callback reuses the idempotency key.
- Accepted callback is traceable to event/job status.

## Production Preconditions

- `WECOM_CORP_ID`
- `WECOM_AGENT_ID`
- `ADMIN_LOGIN_REDIRECT_URI`
- `WECOM_CONTACT_SECRET` for contact callback gray validation
- approved test operator / receiver scope
- evidence uses only redacted operator identity, internal event ids, and
  redacted callback/event placeholders

## Non-Goals

- No raw external_userid committed.
- No WeCom secret committed.
- No production deploy/systemd/nginx/env modification.
- No broad callback migration in this PR.
- No real OAuth token exchange or real external callback execution from this
  diagnostic.

## Evidence Template

Use
`docs/reports/wecom_operator_auth_callback_evidence_template.md` for operator
evidence. If callback evidence has not been collected in an approved gray
window, the report must remain `READINESS_ONLY` or `OPERATOR_AUTH_READY` and
must not claim WeCom auth/callback is 90%+ complete.

## Next Action

Run the operator-owned gray acceptance only after auth/callback configuration is
approved outside git.
