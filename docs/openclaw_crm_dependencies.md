# OpenClaw CRM Dependencies

## Scope

This round only builds an independent OpenClaw-side CRM integration layer.

- No direct CRM database access
- No CRM service code changes
- No OpenClaw agent-wide refactor
- No UI work

The integration goal is to hide current CRM route details behind a stable
OpenClaw-side adapter surface so future route migration does not leak upward.

## Current CRM API Dependencies

### Baseline service checks

- `GET /health`
- `GET /api/ops/status`

### Legacy customer-compatible reads

- `GET /api/contacts`
- `GET /api/contacts/<external_userid>`

### Legacy timeline-compatible reads

- `GET /api/messages/<external_userid>`
- `GET /api/messages/<external_userid>/recent`
- `GET /api/messages/search`

### Current batch compatibility path

- `POST /mcp`

This is only used as the current compatibility bridge for batch-oriented
operations where a stable REST route is not yet treated as the OpenClaw-side
contract.

## Future Reserved CRM API Dependencies

The adapter layer already reserves these stable semantic targets:

- `GET /api/customers`
- `GET /api/customers/<external_userid>`
- `GET /api/customers/<external_userid>/timeline`

OpenClaw upper layers should depend on `customer` and `timeline` semantics, not
on `contacts` or `messages` route details.

## Auth Assumptions

The client currently assumes:

- CRM REST APIs use bearer token auth via `CRM_API_TOKEN`
- CRM MCP-compatible batch bridge can use a dedicated bearer token via `CRM_MCP_BEARER_TOKEN`

Headers are centralized in `CrmApiClient`:

- `Authorization: Bearer <token>`
- `Accept: application/json`
- `Content-Type: application/json`
- `X-OpenClaw-Source: openclaw-cloud`
- `X-Request-Id: <uuid>`

## Error Handling Strategy

The integration layer maps failures into four categories:

- `CrmTransportError`
  - DNS failure
  - connection failure
  - timeout
  - TLS / low-level request failure

- `CrmHttpError`
  - non-2xx status codes

- `CrmBusinessError`
  - successful HTTP response with explicit business failure payload
  - example: `{"ok": false, "error": "..."}`

- `CrmMappingError`
  - CRM payload shape does not match adapter expectations

## Fallback Strategy

Only two layers are implemented in this round:

### 1. New route to old route fallback

- `CustomersAdapter`
  - prefer `/api/customers*`
  - fallback to `/api/contacts*`

- `TimelineAdapter`
  - prefer `/api/customers/<external_userid>/timeline`
  - fallback to `/api/messages/<external_userid>/recent`

### 2. Degraded return when CRM is unavailable

- customer list: empty list
- customer detail: `Customer(status="degraded")`
- timeline: degraded event with source `degraded`

No complex business fallback is implemented in this round.

## Integration Boundary Rule

Upper layers must only call adapters such as:

- `CustomersAdapter.list_customers`
- `CustomersAdapter.get_customer`
- `TimelineAdapter.get_customer_timeline`
- `BatchesAdapter.get_message_batch`
- `BatchesAdapter.ack_message_batch`

Upper layers should not call raw CRM routes directly.
