# OpenClaw CRM Adapter

## Directory Tree

```text
openclaw_service/
  integrations/
    crm/
      __init__.py
      client.py
      auth.py
      errors.py
      models.py
      config.py
      adapters/
        __init__.py
        customers.py
        timeline.py
        batches.py
        contacts.py
        messages.py
```

## Purpose

This package keeps OpenClaw independently deployed and forces all CRM reads/writes
through a stable HTTP API boundary.

- No direct CRM database access
- No coupling to current CRM route shapes outside adapters
- New `customers` / `timeline` routes can replace legacy routes without changing callers

## Current Route Dependencies

### Legacy-compatible routes

- `GET /api/contacts`
- `GET /api/contacts/<external_userid>`
- `GET /api/messages/<external_userid>`
- `GET /api/messages/<external_userid>/recent`
- `GET /api/messages/search`
- `POST /mcp` for current message-batch compatibility

### Future routes already reserved in adapters

- `GET /api/customers`
- `GET /api/customers/<external_userid>`
- `GET /api/customers/<external_userid>/timeline`

## Error Handling

`CrmApiClient` maps failures into a small error taxonomy:

- `CrmTransportError`: DNS / connect / timeout / TLS / network failure
- `CrmHttpError`: non-2xx response
- `CrmBusinessError`: `200` with explicit business failure payload such as `{"ok": false}`
- `CrmMappingError`: payload shape does not match the adapter contract

## Fallback Rules

- `CustomersAdapter`
  - prefer `/api/customers*`
  - fallback to `/api/contacts*`
- `TimelineAdapter`
  - prefer `/api/customers/<external_userid>/timeline`
  - fallback to `/api/messages/<external_userid>/recent`
- `BatchesAdapter`
  - current compatibility path uses `POST /mcp`

## Degraded Behavior

- customer list: return empty list if both preferred and fallback reads fail
- customer detail: return a `Customer(status="degraded")`
- timeline: return a single degraded timeline event

This keeps fallback intentionally small and avoids hidden business logic.
