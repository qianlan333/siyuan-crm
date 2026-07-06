# Customer Read Model Parity Strategy

## Purpose

Customer Center, Customer Detail, Customer Timeline, and Recent Messages are stable read surfaces used by the copied admin frontend, MCP, and OpenClaw-style assistants. The new backend may replace internals, but it must keep paths, envelopes, and core fields compatible with the old Flask service.

This strategy keeps the slice honest: Customer Read Model is `partial`, PostgreSQL-ready, and parity-tooling-ready. It is not production-complete and has not replaced the old Customer Center.

## Compared Surfaces

- `GET /api/customers`
- `GET /api/customers?owner_userid=...`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/messages/{external_userid}/recent`

The required fields are defined in the root source package at `aicrm_next/customer_read_model/parity_spec.py`.

## Fixture Mode

Fixture mode compares anonymized old response samples with AI-CRM Next TestClient responses:

Historical fixture wrapper command retired. See
`docs/archive/experiments_ai_crm_next/retired_tools.md` for the archived tool
index.

Fixtures must use obvious mask values such as `mobile_masked_001`, `external_user_masked_001`, and `customer_masked_001`. They must not contain real phone numbers, real `external_userid`, or real customer names.

## HTTP Mode

HTTP mode is for later old Flask / AI-CRM Next dual-run checks:

Historical HTTP wrapper command retired. See
`docs/archive/experiments_ai_crm_next/retired_tools.md` for the archived tool
index.

The tool only issues read requests. It must not import the old Flask app or any `wecom_ability_service.*` package.

## Allowed Differences

- Dynamic counts and fixture row volume.
- `id`, `event_id`, `msgid`, and timestamp values.
- Additional fields beyond the required contract.
- Masked fixture values versus local Next fixture values.

## Disallowed Differences

- Missing required top-level keys.
- Missing required customer, timeline item, or recent-message keys.
- Type-family mismatches for required fields.
- Changing `customers` / `items` envelope semantics.
- Returning customer detail through a mobile fallback that pretends a mobile is an `external_userid`.
- MCP bypassing application queries to read repositories directly.

## Repository Status

The default app runtime remains `InMemoryCustomerReadModelRepository`. `SqlAlchemyCustomerReadModelRepository` and Alembic migration `0002_customer_read_model_postgresql_ready.py` are PostgreSQL-ready partial infrastructure, tested through SQLAlchemy with an in-memory database. The slice is not connected to production PostgreSQL and has not imported historical WeCom/archive/class-user data.

## Side-Effect Safety

Customer Read Model parity uses read-only endpoints only. It does not trigger WeCom sends, does not mutate production data, and does not call external WeCom APIs.
