# Product Management Gray Release Preparation Plan

This document prepares Product Management for a future route-level gray release. It does not cut production traffic, replace old Flask routes, connect real WeChat Pay or Alipay, or enable production checkout.

## Scope

Routes in scope:

- `GET /admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products/{product_id}`
- `GET /api/products/{page_slug}`
- `GET /p/{page_slug}`

Related checkout routes are recorded for safety only and are not gray-eligible in this phase:

- `POST /api/checkout/wechat`
- `POST /api/checkout/alipay`

## Current Status

| area | status | notes |
| --- | --- | --- |
| frontend | partial adapter | Product management uses the legacy admin shell partial adapter. |
| backend | parity-ready partial | Product list/detail/create/update/enable/disable/delete contracts exist. |
| product storage | fake / in-memory / fixture | No production product database or migration is connected. |
| payment dependency | fake/stubbed | WeChat Pay and Alipay adapters are fake; no real signing or provider call. |
| production replacement | not ready | No production traffic, production database, or payment provider cutover has happened. |

Summary status: production replacement: not ready.

## Gray-Eligible Items

- Product admin page read-only smoke.
- Product list/detail API shape checks.
- Public product page read-only smoke.
- Fixture-backed create/update/enable/disable/delete behavior in AI-CRM Next fake mode only.
- Route-level screenshot baseline for `/admin/wechat-pay/products` and `/p/course-masked-001`.

## Not Gray-Eligible In This Phase

- Real payment checkout (`真实支付 checkout`).
- Real production order creation.
- Real product-page publishing to production traffic.
- Production product data migration.
- Production write-route replacement.
- Any old Flask write call during gray smoke or parity checks.

## Preconditions

| condition | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| commerce parity pass | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --old-fixture-dir ... --next-testclient` |
| frontend smoke pass | `retired frontend route smoke test; see docs/archive/experiments_ai_crm_next/retired_tools.md` and screenshot baseline |
| screenshot baseline pass | 14-route baseline includes product admin and public product routes |
| no old backend imports | architecture boundary scan/tests |
| no production external calls | fake payment adapters remain active; no provider credentials used |
| rollback checklist ready | route-level rollback remains old Flask by default |

## Rollback Strategy

- Route-level rollback target is old Flask.
- Disable any future Next product route flag before switching traffic back.
- Keep old product and payment routes active until production verification is complete.
- Do not perform destructive product data operations during gray preparation.
- Because this phase uses fixture/in-memory data, no production data rollback should be required.

## Go / No-Go

Go only when all are true:

- Ordinary pytest passes.
- Commerce parity passes.
- Product gray smoke passes in default read-only mode.
- Optional fake-write smoke passes only against Next TestClient.
- Frontend PNG screenshot baseline includes product admin and public product pages.
- No old backend imports exist in AI-CRM Next.
- No real payment provider call is configured.
- Rollback route remains old Flask.

No-Go if any are true:

- Any product page route returns 5xx.
- Any required API shape key is missing.
- A gray smoke run attempts POST/PUT/DELETE against old Flask.
- Checkout or payment provider execution is triggered.
- Any module is mislabeled `production_ready`.
- Production route cutover is attempted without rollback owner approval.

## Next Action

Run Product Management gray smoke in read-only mode, then optionally run fake-write smoke against AI-CRM Next TestClient only. Use the resulting reports as preparation evidence for later gray-release review.
