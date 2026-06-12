# External Orders Read API

## Scope

This API is a read-only integration surface for external systems that need local order and customer identity data from siyuan-crm.

It reads only local AI-CRM Next read models:

- unified commerce order read models
- identity contact mappings
- customer read model detail projections

It does not create orders, request payment, request refunds, actively sync WeChat Shop orders, or actively sync WeCom contacts. All successful responses include `route_owner=ai_crm_next` and `fallback_used=false`.

Product codes are owned by the target deployment's product configuration. Documentation and examples use placeholders such as `product_code_example` and `course_example`; do not copy AI-CRM production product tables into this repository.

## Authentication

Set the server-side environment variable in the deployment environment:

```bash
AUTOMATION_INTERNAL_API_TOKEN=<set-on-server>
```

Every request must send:

```http
Authorization: Bearer $TOKEN
```

Error semantics:

| Case | HTTP | error_code |
| --- | ---: | --- |
| Server token is not configured | `503` | `internal_token_not_configured` |
| Request has no bearer token | `401` | `missing_internal_token` |
| Request token is wrong | `401` | `invalid_internal_token` |

## List Orders

```http
GET /api/external/orders
```

Query parameters:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `provider` | string | `all` | `all`, `wechat`, `alipay`, `wechat_shop` |
| `paid_from` | integer | - | Unix timestamp in seconds |
| `paid_to` | integer | - | Unix timestamp in seconds |
| `created_from` | integer | - | Unix timestamp in seconds |
| `created_to` | integer | - | Unix timestamp in seconds |
| `product_code` | string | - | Deployment-owned product code |
| `payment_status` | string | - | `pending`, `paid`, `closed`, `failed`, `refund_processing`, `partial_refunded`, `full_refunded` |
| `is_paid` | string | - | `true` or `false` |
| `is_refunded` | string | - | `true` or `false` |
| `order_no` | string | - | Merchant order number |
| `transaction_id` | string | - | Provider transaction number |
| `mobile` | string | - | Customer mobile value from local read model |
| `external_userid` | string | - | Local WeCom external userid |
| `unionid` | string | - | Local WeChat unionid |
| `limit` | integer | `100` | 1 to 500 |
| `cursor` | string | - | Opaque cursor from the previous response |

The time filters accept only second-level Unix timestamps. Millisecond timestamps such as `1779235200000` are rejected with `400 invalid_request`.

Example:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/external/orders?provider=all&product_code=product_code_example&is_paid=true&limit=100"
```

Response shape:

```json
{
  "ok": true,
  "items": [
    {
      "provider": "wechat",
      "order_no": "order_example_001",
      "transaction_id": "transaction_example_001",
      "paid_at": "2026-05-20 12:01:00",
      "created_at": "2026-05-20 12:01:00",
      "product_code": "course_example",
      "payment_status": "paid",
      "status_label": "已支付",
      "amount_total": 9900,
      "amount_yuan": "99.00",
      "currency": "CNY",
      "is_paid": true,
      "is_refunded": false,
      "refund_status": "",
      "refunded_amount_total": 0,
      "mobile": "mobile_masked_001",
      "unionid": "unionid_masked_001",
      "external_userid": "external_userid_masked_001",
      "detail_url": "/api/external/orders/order_example_001?provider=wechat"
    }
  ],
  "total": 1,
  "limit": 100,
  "next_cursor": "",
  "has_more": false,
  "route_owner": "ai_crm_next",
  "source_status": "external_orders",
  "fallback_used": false
}
```

`items[]` intentionally does not expose `product_name`. External integrations should use `product_code`.

## Get Order Detail

```http
GET /api/external/orders/{order_no}
```

Query parameters:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `provider` | string | `auto` | `auto`, `wechat`, `alipay`, `wechat_shop` |

Example:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/external/orders/order_example_001?provider=wechat"
```

Successful responses reuse the unified order detail projection and include refund fields, callback summary, and timeline when present. The detail projection also removes `product_name`; use `product_code` for product matching.

Not found orders return `404 not_found`. Invalid provider values return `400 invalid_request`. Missing local DB/schema dependencies return a controlled unavailable/degraded error instead of a bare 500.

## Resolve User

```http
GET /api/external/users/resolve
```

Query parameters:

| Parameter | Type | Required | Notes |
| --- | --- | ---: | --- |
| `unionid` | string | no | Local WeChat unionid |
| `external_userid` | string | no | Local WeCom external userid |
| `mobile` | string | no | Local mobile value |
| `openid` | string | no | Local WeChat openid |

At least one identity key is required. No external WeCom sync is triggered.

Example:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/external/users/resolve?unionid=unionid_masked_001"
```

The `user` object always contains:

- `person_id`
- `external_userid`
- `mobile`
- `customer_name`
- `unionid`
- `openid`
- `owner_userid`
- `owner_display_name`
- `remark`
- `follow_user_userid`
- `follow_user_userids`
- `binding_status`
- `is_bound`
- `matched_by`
- `identity_map_id`
- `detail_url`

## Pagination

The list endpoint returns an opaque `next_cursor`. Clients must not construct offsets manually, and responses do not expose raw internal offsets.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/external/orders?provider=all&is_paid=true&limit=100&cursor=$NEXT_CURSOR"
```
