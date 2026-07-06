# WeCom Auth / Callback Evidence - 2026-06-23

Result: `EVIDENCE_COLLECTED_NOT_READY`

This report records read-only production evidence for the WeCom operator auth
and external-contact callback surfaces. It does not claim scenario-level
`PASS_90_PLUS_CANDIDATE`, and it does not claim global `PASS_90_PLUS`.

The collected evidence shows that the relevant Next-owned routes are reachable
and return controlled responses, but approved operator auth and valid callback
evidence were not available in this window. No callback-linked internal event,
idempotency key, duplicate callback result, or permission-scope evidence was
attached.

This report does not contain tokens, corp secrets, suite secrets,
`Authorization` headers, raw `external_userid`, phone numbers, `openid`,
`unionid`, or raw callback body fields.

## Scope

| Field | Evidence |
| --- | --- |
| Environment | production |
| Review date | 2026-06-23 |
| Scenario | `wecom_auth` |
| Production commit observed | `2a945c16` |
| Auth start route | `/auth/wecom/start` |
| Auth callback route | `/auth/wecom/callback` |
| External contact callback route | `/wecom/external-contact/callback` |
| Alternate callback route | `/api/wecom/events` |
| Admin visibility routes | `/api/admin/internal-events`, `/api/admin/channels/runtime-diagnosis` |
| Route owner | `ai_crm_next` |

## Safety Attestation

| Field | Result |
| --- | --- |
| Runtime code changed by this PR | `false` |
| Route added or changed by this PR | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| Production DB write executed | `false` |
| Real external call executed by probes | `false` |
| Token / secret / Authorization header committed | `false` |
| Raw WeCom/customer identifier committed | `false` |
| Raw callback body committed | `false` |

The production checks used HTTP `GET` requests and read-only admin diagnostics.
No OAuth redirect was followed, no callback payload was submitted, no callback
body was decrypted, and no enqueue/external effect path was executed.

## Operator Evidence Supplied

| Required field | Evidence |
| --- | --- |
| `auth_start_route` | `/auth/wecom/start` |
| `auth_start_http_status` | `503` |
| `redirect_url_redacted` | `not_provided`; no redirect was emitted because the route is controlled blocked |
| `callback_route` | `/auth/wecom/callback` |
| `callback_http_status` | `503` |
| `signature_verification_result` | `invalid_callback_signature` for missing-signature callback probes |
| timestamp / nonce presence | `false`; missing-signature probe only, raw values not submitted |
| `corp_id` | `not_configured`; no value printed |
| `auth_code` | `not_provided` |
| `callback_event_type` | `not_provided` |
| `internal_event_id` | `not_found` |
| `idempotency_key` | `not_found` |
| duplicate callback handling | `not_collected` |
| admin visibility route/status | `/api/admin/internal-events?...` returned HTTP `200` with zero WeCom/channel-entry events; `/api/admin/channels/runtime-diagnosis` returned HTTP `200` |
| `operator_action_required` | `true` |
| `retryable` | `false`; this is not a retryable job failure, it needs operator/config evidence |
| `business_explanation` | WeCom auth/callback routes are Next-owned and controlled, but real operator auth and valid callback evidence are missing. |
| `sensitive_data_redaction_confirmed` | `true` |

## Auth Start Evidence

Read-only probe:

```text
GET /auth/wecom/start
```

Observed controlled response:

| Field | Evidence |
| --- | --- |
| HTTP status | `503` |
| `ok` | `false` |
| `error_code` | `external_call_blocked` |
| `auth_step` | `wecom_sso_start` |
| `adapter_mode` | `real_blocked` |
| `fallback_used` | `false` |
| `real_external_call_executed` | `false` |
| `route_owner` | `ai_crm_next` |

This is not a verified OAuth `302` start. It is useful safety evidence: the
route is owned by Next and does not start a real WeCom authorization exchange by
default.

## Callback / Signature Evidence

Read-only callback probes:

```text
GET /auth/wecom/callback
GET /wecom/external-contact/callback
GET /api/wecom/events
```

Observed results:

| Route | HTTP status | Evidence |
| --- | ---: | --- |
| `/auth/wecom/callback` | `503` | controlled `external_call_blocked`, `auth_step=wecom_sso_callback`, `real_external_call_executed=false` |
| `/wecom/external-contact/callback` | `400` | controlled `invalid callback signature` for missing signature |
| `/api/wecom/events` | `400` | controlled `invalid callback signature` for missing signature |

No valid signature was submitted in this evidence window. The missing-signature
probes prove the callback routes fail closed, but they do not prove successful
callback processing.

## Internal Event / Auth Record Evidence

Read-only admin event queries:

```text
GET /api/admin/internal-events?event_type=wecom&limit=10
GET /api/admin/internal-events?source_module=wecom&limit=10
GET /api/admin/internal-events?source_module=channel_entry&limit=10
```

Observed summary:

| Query | HTTP status | Total |
| --- | ---: | ---: |
| `event_type=wecom` | `200` | `0` |
| `source_module=wecom` | `200` | `0` |
| `source_module=channel_entry` | `200` | `0` |

Runtime diagnosis:

```text
GET /api/admin/channels/runtime-diagnosis
```

Observed summary:

| Field | Evidence |
| --- | --- |
| HTTP status | `200` |
| `ok` | `true` |
| `recent_wecom_external_contact_event_logs` | `0` for the blank-scene diagnostic |
| `recent_automation_channel_entry_effect_log` | `20` records visible |

No callback-linked internal event or auth record was found by the read-only
checks above. This keeps the scenario below the 90%+ candidate threshold.

## Idempotency Evidence

No valid callback event was available, so callback idempotency could not be
proven in this report.

| Field | Evidence |
| --- | --- |
| callback event id | `not_found` |
| inbound/internal event id | `not_found` |
| idempotency key | `not_found` |
| duplicate callback handling | `not_collected` |

## Admin Visibility Evidence

Admin visibility is partially present:

- `/api/admin/internal-events` is reachable and returns HTTP `200`.
- `/api/admin/channels/runtime-diagnosis` is reachable and returns HTTP `200`.

Admin visibility is not complete:

- No WeCom/channel-entry internal event was present in the queried admin event
  filters.
- No valid callback event or duplicate handling record was attached.
- No redacted operator identity or permission-scope evidence was attached.

## Sensitive-Data Redaction Evidence

Confirmed not committed:

- token
- corp secret
- suite secret
- `Authorization` header
- raw `external_userid`
- phone number
- `openid`
- `unionid`
- raw callback body fields
- raw timestamp / nonce / signature values
- redirect URL query parameters

Only route names, status codes, controlled error names, boolean configuration
presence, internal query totals, and non-secret business explanations are
recorded.

## Result

`EVIDENCE_COLLECTED_NOT_READY`

Reasoning:

- Auth start and auth callback routes are reachable, but both are controlled
  `external_call_blocked` responses with HTTP `503`, not verified WeCom OAuth
  callback evidence.
- External contact callback routes are reachable and fail closed on missing
  signatures with HTTP `400`.
- Required WeCom runtime config was not present in the production evidence
  shell for the checked variables.
- No valid callback signature, callback event, internal event, idempotency key,
  duplicate handling, operator identity, permission scope, or admin-visible
  callback record was attached.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` is not allowed because this WeCom scenario is not yet
callback-linked. The next collection must provide approved, redacted evidence
for:

1. configured WeCom corp/app/redirect state outside git,
2. real operator auth or an approved auth-window equivalent,
3. valid callback signature verification,
4. callback event or auth record,
5. inbound/internal event or equivalent persisted record,
6. idempotency / duplicate callback handling,
7. admin visibility,
8. permission-scope evidence for customer, group ops, and material capabilities.

## Risk / Rollback

This PR is document-only. Rollback is to revert this report. There is no runtime
rollback, deployment rollback, database rollback, migration rollback, or env
rollback.

## Next Action

Run a dedicated WeCom operator evidence window after the approved WeCom
corp/app/redirect/callback configuration is present outside git. Then recollect
the scenario with:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth \
  --auth-start-status verified_302 \
  --callback-missing-code-status observed_400 \
  --callback-invalid-state-status observed_400 \
  --operator-identity-evidence <redacted_operator_identity> \
  --callback-signature-status valid \
  --callback-event-id <redacted_callback_event_id> \
  --internal-event-id <redacted_inbound_event_id> \
  --idempotency-key <redacted_idempotency_key> \
  --duplicate-callback-handling reused_idempotency_key \
  --permission-scope-evidence <redacted_scope_summary> \
  --customer-event-visibility visible \
  --group-ops-permission-evidence <redacted_group_ops_scope> \
  --material-permission-evidence <redacted_material_scope>
```

Do not claim WeCom `PASS_90_PLUS_CANDIDATE` until the callback-linked evidence
above is attached without sensitive data.
