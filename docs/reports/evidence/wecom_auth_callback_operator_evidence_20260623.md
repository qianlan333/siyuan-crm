# WeCom Auth / Callback Approved Operator Evidence - 2026-06-23

Result: `BLOCKED_CONFIG_NOT_APPROVED`

This report records an approved-window recollection attempt after #1350. The
goal was to determine whether WeCom operator auth and callback processing had
advanced from controlled readiness into a real, auditable flow.

The answer is no: production still reports the WeCom auth and callback
configuration as absent, and `/auth/wecom/start` remains controlled blocked with
HTTP `503`. No real WeCom OAuth redirect, valid callback signature, persisted
auth/callback record, internal event, idempotency key, duplicate callback
handling, or permission-scope evidence was available.

This report does not contain tokens, corp secrets, suite secrets, encoding AES
keys, `Authorization` headers, raw `external_userid`, phone numbers, `openid`,
`unionid`, raw callback body fields, or raw timestamp/nonce/signature values.

## Scope

| Field | Evidence |
| --- | --- |
| Environment | production |
| Review date | 2026-06-23 |
| Scenario | `wecom_auth` |
| Production commit observed | `b348e1ea` |
| Prior report | `docs/reports/evidence/wecom_auth_callback_evidence_20260623.md` |
| Auth start route | `/auth/wecom/start` |
| Auth callback route | `/auth/wecom/callback` |
| External contact callback route | `/wecom/external-contact/callback` |
| Alternate callback route | `/api/wecom/events` |
| Admin visibility routes | `/api/admin/internal-events`, `/api/admin/channels/runtime-diagnosis` |
| Route owner | `ai_crm_next` |

## Operator Approval / Config Precondition

The operator evidence window requires all of the following to be true outside
git:

1. WeCom corp/app/callback/redirect configuration approved and present.
2. Production auth start / callback external interaction approved.
3. Callback URL matches the WeCom admin console.
4. Signature verification configuration is usable.
5. Secrets remain only in env/config systems and never enter git, logs, PR
   body, or reports.

Observed precondition status:

| Check | Observed |
| --- | --- |
| `WECOM_CORP_ID` configured | `false` |
| `WECOM_AGENT_ID` configured | `false` |
| `ADMIN_LOGIN_REDIRECT_URI` configured | `false` |
| `WECOM_CALLBACK_TOKEN` configured | `false` |
| `WECOM_CALLBACK_AES_KEY` configured | `false` |
| `WECOM_CONTACT_SECRET` configured | `false` |
| `AICRM_WECOM_CONTACT_CALLBACK_TOKEN` configured | `false` |
| `AICRM_WECOM_CONTACT_CALLBACK_AES_KEY` configured | `false` |
| `AICRM_WECOM_CONTACT_CALLBACK_CORP_ID` configured | `false` |
| live callback adapter enabled | `false` |
| live callback processing approved | `false` |

Because the required configuration and approvals were not active, this report
classifies the recollection as `BLOCKED_CONFIG_NOT_APPROVED`.

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

Judgment: `/auth/wecom/start` did not advance to real redirect/auth flow. No
redirect URL was emitted, so `redirect_url_redacted=not_provided`.

## Callback / Signature Evidence

Read-only probes:

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

Judgment: callback routes remain fail-closed, but no valid WeCom callback was
submitted or verified in this window. Timestamp and nonce were not provided;
raw values are not present in this report.

## Persisted Auth / Callback Record Or Internal Event Evidence

Read-only admin event queries:

```text
GET /api/admin/internal-events?event_type=wecom&limit=10
GET /api/admin/internal-events?source_module=channel_entry&limit=10
```

Observed summary:

| Query | HTTP status | Total |
| --- | ---: | ---: |
| `event_type=wecom` | `200` | `0` |
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
| recent WeCom external-contact event logs | none in the blank-scene diagnostic |

Judgment: no persisted auth/callback record or internal event evidence was
available from the read-only checks.

## Idempotency / Duplicate Handling Evidence

No valid callback event was processed, so duplicate callback behavior could not
be validated.

| Field | Evidence |
| --- | --- |
| callback event id | `not_found` |
| persisted auth/callback record id | `not_found` |
| internal event id | `not_found` |
| idempotency key | `not_found` |
| duplicate callback handling | `not_collected` |

## Permission Scope Evidence

No real operator identity or permission-scope evidence was attached.

| Scope | Evidence |
| --- | --- |
| operator identity | `not_provided` |
| customer event visibility | `not_provided` |
| group ops permission | `not_provided` |
| material permission | `not_provided` |

## Admin Visibility Evidence

Admin visibility is still readiness-only:

- `/api/admin/internal-events` is reachable and returns HTTP `200`.
- `/api/admin/channels/runtime-diagnosis` is reachable and returns HTTP `200`.
- No WeCom/channel-entry internal event was found in the queried admin event
  filters.
- No redacted callback record, idempotency record, or operator permission record
  was attached.

## Sensitive-Data Redaction Evidence

Confirmed not committed:

- token
- corp secret
- suite secret
- encoding AES key
- `Authorization` header
- raw `external_userid`
- phone number
- `openid`
- `unionid`
- raw callback body
- raw timestamp / nonce / signature values
- raw redirect query parameters

The report records only route names, status codes, controlled error names,
boolean configuration presence, non-sensitive counts, and operator-facing
business explanations.

## Result

`BLOCKED_CONFIG_NOT_APPROVED`

This is stricter than `EVIDENCE_COLLECTED_NOT_READY` because the approved
operator precondition did not materialize in production: the required git-external
configuration and live callback approval flags were not present, and the auth
start route remained controlled blocked.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` is not allowed because WeCom Auth / Callback is still
missing all callback-linked evidence:

1. real auth start redirect or approved equivalent,
2. successful auth callback,
3. valid callback signature verification,
4. persisted auth/callback record or internal event,
5. idempotency key and duplicate callback handling,
6. admin-visible record,
7. redacted operator identity,
8. permission scope for customer, group ops, and material capabilities.

## Risk / Rollback

This PR is document-only. Rollback is to revert this report. There is no runtime
rollback, deploy rollback, env rollback, DB rollback, or migration rollback.

## Next Action

Before recollecting WeCom evidence again, complete the git-external operator
setup:

1. configure approved WeCom corp/app/redirect/callback settings outside git,
2. enable the approved auth/callback evidence window,
3. verify `/auth/wecom/start` returns a real redirect or approved equivalent,
4. verify callback signature with a real gray callback,
5. attach redacted callback event/internal event/idempotency/admin visibility
   and permission-scope evidence.

Only after those are present should the scenario be recollected for
`EVIDENCE_COLLECTED` or `PASS_90_PLUS_CANDIDATE`.
