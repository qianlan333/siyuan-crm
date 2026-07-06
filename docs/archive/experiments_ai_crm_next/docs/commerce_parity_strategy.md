# Commerce Parity Strategy

Status: `partial`.

This first commerce slice locks product, checkout, order, notify, and transaction-management contracts without connecting real payment providers.

## Modes

- Fixture mode compares `tests/fixtures/old_commerce/` with AI-CRM Next TestClient.
- HTTP mode is reserved for isolated dual-run environments and defaults to safe read endpoints only.
- `--old-base-url` mode does not POST checkout or notify endpoints by default. The report marks old write endpoints as `skipped` with `old_write_endpoint_disabled`.
- Checkout parity is verified through old fixtures and AI-CRM Next fake checkout. Notify remains documented contract coverage only in this first slice.
- `--allow-old-write-endpoints` exists only for explicitly isolated non-production labs. Do not use it against the old production service.
- Checkout and notify must not be executed against old production. In this slice they are safe only against Next fake adapters or static fixtures.

## Covered Contracts

- `GET /api/admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products/{product_id}`
- `POST /api/checkout/wechat`
- `POST /api/checkout/alipay`
- `GET /api/admin/wechat-pay/transactions`
- `GET /api/admin/alipay/transactions`

## Allowed Differences

- dynamic `order_no`, `transaction_id`, and timestamps;
- fixture counts;
- fake provider payload details.

## Not Allowed

- missing required product fields;
- missing checkout fields;
- missing transaction item fields;
- real WeChat Pay or Alipay calls;
- real external webhook emission.

Product Management, WeChat Pay, and Alipay remain `partial`. The fake adapters do not verify real signatures and do not replace the old payment system.
