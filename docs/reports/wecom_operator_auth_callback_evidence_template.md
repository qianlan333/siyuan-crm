# WeCom Operator Auth And Callback Evidence Template

Status: `READINESS_ONLY`

Use this template after running the WeCom auth/callback diagnostic. Do not
commit real WeCom tokens, callback secrets, `corpsecret`, `access_token`,
`Authorization` headers, raw `external_userid`, receiver tokens, phone numbers,
or customer secrets. Evidence may include redacted operator identity, redacted
callback event ids, internal event ids, and operator-owned screenshots with
secrets removed.

## Operator And Window

- Operator:
- Review date:
- Gray window:
- Environment:
- Test corp / app reference:
- Approval reference:

## Safety Attestation

- `real_external_call_executed=false` by diagnostic default:
- `production_write_executed=false` by diagnostic default:
- `deploy_or_env_modified=false`:
- Token never logged:
- Callback secret redacted:
- No raw external_userid / `Authorization` header / `access_token` /
  `corpsecret`:

## Diagnostic Command

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth \
  --redirect-uri-expected <expected_redirect_uri_or_not_provided> \
  --auth-start-status <expected_302|verified_302|not_provided> \
  --callback-missing-code-status <controlled_400_expected|observed_400> \
  --callback-invalid-state-status <controlled_400_expected|observed_400> \
  --operator-identity-evidence <redacted_operator_identity_or_not_provided> \
  --callback-signature-status <not_provided|invalid|valid> \
  --callback-event-id <redacted_callback_event_id_or_not_provided> \
  --internal-event-id <inbound_event_id_or_not_provided> \
  --idempotency-key <redacted_idempotency_key_or_not_provided> \
  --duplicate-callback-handling <not_collected|reused_idempotency_key> \
  --permission-scope-evidence <scope_evidence_or_not_provided> \
  --customer-event-visibility <visible|not_provided> \
  --group-ops-permission-evidence <evidence_or_not_provided> \
  --material-permission-evidence <evidence_or_not_provided>
```

## Evidence Payload

| Field | Value | Notes |
| --- | --- | --- |
| `corp_id_configured` |  | Do not paste corp secret. |
| `agent_id_configured` |  | Do not paste app secret. |
| `redirect_uri_configured` |  |  |
| `redirect_uri_expected` |  | Expected redirect URI, not a secret. |
| `auth_start_status` |  | Expected or observed 302 readiness. |
| `callback_missing_code_status` |  | Controlled failure evidence. |
| `callback_invalid_state_status` |  | Controlled failure evidence. |
| `operator_identity_evidence` |  | Redacted operator/admin identity only. |
| `token_redacted` |  | Must be `true`. |
| `token_never_logged` |  | Must be `true`. |
| `callback_signature_status` |  | `not_provided`, `invalid`, or `valid`. |
| `callback_event_id` |  | Redacted callback event id or `not_provided`. |
| `inbound_event_id` |  | Internal event id or `not_provided`. |
| `idempotency_key` |  | Redacted idempotency key or `not_provided`. |
| `duplicate_callback_handling` |  | Duplicate callback behavior. |
| `permission_scope_evidence` |  | Operator/customer/group/material scope summary. |
| `customer_event_visibility` |  | Customer event visible or `not_provided`. |
| `group_ops_permission_evidence` |  | Group ops permission evidence. |
| `material_permission_evidence` |  | Material permission evidence. |
| `retryable` |  | Explain why if true. |
| `operator_action_required` |  | Explain next action. |
| `business_explanation` |  | Business-readable explanation for operators. |

## Blocking Reason Matrix

| Code | Present? | Evidence / next action |
| --- | --- | --- |
| `missing_corp_id` |  |  |
| `missing_agent_id` |  |  |
| `missing_redirect_uri` |  |  |
| `auth_start_not_verified` |  |  |
| `missing_operator_identity` |  |  |
| `missing_callback_signature_evidence` |  |  |
| `invalid_callback_signature` |  |  |
| `missing_callback_event` |  |  |
| `missing_inbound_event` |  |  |
| `missing_idempotency_evidence` |  |  |
| `missing_permission_scope` |  |  |
| `operator_auth_ready` |  |  |
| `callback_linked` |  |  |

## Operator Auth Evidence

- Auth start route expected status:
- Callback missing code controlled failure:
- Callback invalid state controlled failure:
- Redacted operator identity:
- Permission scope summary:

## Callback Evidence

- Signature status:
- Enqueue allowed:
- Callback event id:
- Inbound event id:
- Idempotency key:
- Duplicate callback handling:
- Customer event visibility:

## Decision

- `READINESS_ONLY`: config, operator identity, callback, or permission evidence
  is incomplete, or only dry-run diagnostics were collected.
- `OPERATOR_AUTH_READY_EVIDENCE_ATTACHED`: operator auth readiness and
  permission evidence are attached, but callback gray linkage is not complete.
- `CALLBACK_LINKED_EVIDENCE_ATTACHED`: operator auth, signature, callback event,
  inbound event, idempotency, duplicate handling, and permission evidence are
  attached.

Do not mark WeCom auth/callback as 90%+ until operator-owned evidence reaches
`CALLBACK_LINKED_EVIDENCE_ATTACHED` without exposing secrets.
