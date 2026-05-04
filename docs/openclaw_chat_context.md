# OpenClaw Chat Context

## Goal

This round only makes one read path work:

given an `external_userid`, OpenClaw can load:

- customer detail
- recent chat messages
- optional timeline context

and normalize them into one context object that upper layers can consume
directly for future suggestion generation.

This round does **not** generate suggestions.

## Builder API

Primary entry:

```python
build_customer_chat_context(
    external_userid,
    customers=customers_adapter,
    messages=messages_adapter,
    timeline=timeline_adapter,
    recent_message_limit=20,
    timeline_limit=20,
)
```

## Output Shape

```json
{
  "external_userid": "wm_xxx",
  "customer": {},
  "recent_messages": [],
  "recent_timeline_events": [],
  "source_status": "live",
  "degraded": false,
  "warnings": []
}
```

## CRM Dependencies

- `GET /api/customers`
- `GET /api/customers/<external_userid>`
- `GET /api/customers/<external_userid>/timeline`
- `GET /api/messages/<external_userid>/recent`
- fallback-compatible old routes:
  - `GET /api/contacts`
  - `GET /api/contacts/<external_userid>`

## Envelope Handling

Current CRM response envelopes handled by adapters:

### Customer list

```json
{
  "ok": true,
  "customers": [...],
  "items": [...]
}
```

### Customer detail

```json
{
  "ok": true,
  "customer": {...}
}
```

### Timeline

```json
{
  "ok": true,
  "timeline": {
    "external_userid": "...",
    "items": [...]
  }
}
```

## Degraded / Fallback Semantics

- `source_status = "live"`
  - customer, recent messages, and timeline all resolved without degradation

- `source_status = "fallback"`
  - at least one source degraded
  - but enough context still exists to continue upstream

- `source_status = "degraded"`
  - core context is missing
  - typically customer failed and recent messages are also unavailable

Warnings explain which source failed or degraded.

## What This Does Not Do

- does not generate recommendations
- does not write back to CRM
- does not change CRM service code
- does not query CRM database directly
- does not refactor OpenClaw agent flows
