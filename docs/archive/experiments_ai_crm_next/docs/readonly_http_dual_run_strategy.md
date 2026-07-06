# Readonly HTTP Dual-Run Strategy

This strategy covers the first real old-Flask versus AI-CRM Next dual-run phase. It is intentionally read-only. The goal is to compare HTTP response contracts without importing the old Flask app, writing old-system data, or triggering external side effects.

## Why This Exists

Fixture parity proves contract shape against captured examples. Readonly HTTP dual-run adds live old-service evidence before module gray release:

- The old Flask service is called only over HTTP.
- AI-CRM Next can be called through HTTP or FastAPI TestClient.
- Reports focus on shape compatibility, status codes, required keys, and safe skips.
- Data equality is not required because old production data and Next fixture data may differ.

## Tool

The historical readonly HTTP dual-run helper is retired; see
`docs/archive/experiments_ai_crm_next/retired_tools.md`.

If the old Flask service is unreachable, the report must show `old_unreachable`; it must not be interpreted as PASS.

## Supported Scopes

| scope | status | endpoints |
| --- | --- | --- |
| `customer` | historical_evidence_only | Customer list, list filters, detail, timeline, recent messages |
| `user_ops` | historical_evidence_only | User Ops overview, readonly list filters, send-record list |

## Allowed Old-Service Endpoints

The tool only sends `GET` requests to old Flask.

Customer Read Model:

- `GET /api/customers`
- `GET /api/customers?limit=5&offset=0`
- `GET /api/customers?owner_userid=<sample owner>`
- `GET /api/customers?is_bound=true`
- `GET /api/customers?keyword=<sample keyword>`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/customers/{external_userid}/timeline?limit=5&offset=0`
- `GET /api/messages/{external_userid}/recent`
- `GET /api/messages/{external_userid}/recent?limit=5`

User Ops:

- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/list?wecom_status=added`
- `GET /api/admin/user-ops/list?wecom_status=not_added`
- `GET /api/admin/user-ops/list?mobile_binding_status=bound`
- `GET /api/admin/user-ops/list?activation_bucket=activated`
- `GET /api/admin/user-ops/send-records`

## Forbidden Old-Service Endpoints

The dual-run tool must not execute these against old Flask:

- `POST`, `PUT`, `PATCH`, or `DELETE` requests.
- User Ops do-not-disturb writes.
- User Ops batch-send preview or execute.
- Questionnaire submit.
- Checkout or payment notify.
- Activation webhook.
- OpenClaw push.
- Any endpoint that could write data, enqueue work, call WeCom, call OAuth, call payment providers, call OpenClaw, or call cloud storage.

`POST /api/admin/user-ops/batch-send/preview` is intentionally excluded even though it sounds like a preview, because this phase treats all old-service POST requests as unsafe.

## Sample Selection

Customer detail, timeline, and recent-message checks use a sample `external_userid` from the old `/api/customers` list response. The tool does not hard-code real customer IDs.

If the old list response has no sample customer, detail/timeline/message endpoints are skipped with `no_customer_sample`.

Owner and keyword filters use sample values from the old list response when available. If a sample value is missing, that filter endpoint is skipped.

## Comparison Rules

Allowed differences:

- IDs and row ordering.
- Count and total values.
- Created/updated/generated timestamps.
- Fixture data versus real old-service data.
- List length differences.

Blocker differences:

- Old service is unreachable.
- Old service returns `5xx`.
- AI-CRM Next returns `5xx` or misses a required payload key/card.
- Old and AI-CRM Next both miss the same required key/card.
- Next returns `500` or a non-200 status where old returns `200`.
- Customer detail missing `binding`, `identity`, or `sidebar_context`.
- Timeline item missing `event_id`, `event_type`, `event_time`, `title`, `summary`, or `metadata`.
- User Ops list missing old frontend-dependent item fields.
- User Ops send records missing `items`, `total`, `limit`, or `offset`.

Legacy drift warnings:

- Old Flask can be behind the current product contract. If old is missing a required key/card but AI-CRM Next satisfies it, the endpoint is reported as `WARN` with `legacy_drift` instead of a blocker.
- Example: `docs/user_ops_v2.md` requires the User Ops overview card `激活待录入`. If old lacks this card while Next includes it, report `legacy_missing_required_card_label` and keep Next contract unchanged.
- Legacy drift does not block Next replacement by itself, but it must be documented and reviewed before route-level cutover.

## Report Semantics

Markdown and JSON reports include:

- `old_base_url`
- `next_base_url` or `next_testclient`
- `run_time`
- `scope`
- endpoints compared
- per-endpoint status
- blockers
- warnings
- legacy drift
- skipped endpoints
- summary conclusion

Do not commit full old-service responses into the repository. Reports should be written to `/tmp` unless a redacted artifact is explicitly requested.

## Current Status

Readonly HTTP dual-run evidence is retained as historical evidence only. The
first real local old Flask run is archived in
`docs/archive/experiments_ai_crm_next/docs/real_readonly_http_dual_run.md`;
old-only missing `激活待录入` is classified as legacy drift, not a Next blocker.
Old unreachable and Next missing required contract fields remain blockers for
any future replacement harness.
