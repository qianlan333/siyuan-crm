# 外部订单查询 API

## 概述

这组接口给外部系统只读拉取订单数据，覆盖 `wechat`、`alipay`、`wechat_shop` 三类渠道。

接口只查询本地订单读模型，不会创建订单、发起支付、发起退款，也不会主动同步微信小店订单。

## 生产访问地址

生产环境 Base URL：

```text
https://<SIYUAN_PRODUCTION_DOMAIN>
```

当前文档涉及的完整接口地址：

| 能力 | Method | 完整 URL |
|---|---|---|
| 查询用户基础信息 | `GET` | `https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/users/resolve` |
| 批量查询订单 | `GET` | `https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders` |
| 查询订单详情 | `GET` | `https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders/{order_no}` |

可选 shell 变量写法：

```bash
BASE_URL="https://<SIYUAN_PRODUCTION_DOMAIN>"
TOKEN="<AUTOMATION_INTERNAL_API_TOKEN>"
```

## 鉴权

所有请求都必须带 Bearer Token：

```http
Authorization: Bearer <AUTOMATION_INTERNAL_API_TOKEN>
```

服务端读取环境变量：

```bash
AUTOMATION_INTERNAL_API_TOKEN
```

错误语义：

| 场景 | HTTP 状态 | error_code |
|---|---:|---|
| 服务端未配置 token | `503` | `internal_token_not_configured` |
| 请求未带 token | `401` | `missing_internal_token` |
| token 错误 | `401` | `invalid_internal_token` |

## 查询用户基础信息

```http
GET /api/external/users/resolve
```

按用户身份键解析用户基础信息。第一版只读本地身份和客户读模型，不会主动同步企微联系人。

### Query 参数

至少传入以下参数之一。建议订单侧优先使用 `unionid`。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `unionid` | string | 否 | - | 微信 unionid |
| `external_userid` | string | 否 | - | 企业微信外部联系人 ID |
| `mobile` | string | 否 | - | 手机号 |
| `openid` | string | 否 | - | 微信 openid |

### 请求示例

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/users/resolve?unionid=<UNIONID>"
```

### 响应字段

| 字段 | 说明 |
|---|---|
| `ok` | 是否成功 |
| `user` | 用户基础信息 |
| `route_owner` | 路由归属 |
| `source_status` | 数据来源标记，固定为 `external_user_basic` |
| `fallback_used` | 是否走 fallback |

`user` 固定包含 `mobile`、`customer_name`、`unionid` 三个字段；未解析到具体值时返回空字符串。

| user 字段 | 说明 |
|---|---|
| `person_id` | 系统内部用户 ID |
| `external_userid` | 企业微信外部联系人 ID |
| `mobile` | 手机号 |
| `customer_name` | 客户名称 |
| `unionid` | 微信 unionid |
| `openid` | 微信 openid |
| `owner_userid` | 当前负责人 userid |
| `owner_display_name` | 当前负责人展示名 |
| `remark` | 客户备注 |
| `follow_user_userid` | 身份映射里的跟进员工 userid |
| `follow_user_userids` | 客户详情里的跟进员工 userid 数组 |
| `binding_status` | 绑定状态 |
| `is_bound` | 是否已绑定手机号或身份 |
| `matched_by` | 本次匹配使用的键：`unionid`、`external_userid`、`mobile`、`openid` |
| `identity_map_id` | 身份映射表 ID |
| `detail_url` | 内部客户详情 API 路径 |

响应示例：

```json
{
  "ok": true,
  "user": {
    "person_id": "123",
    "external_userid": "<EXTERNAL_USERID>",
    "mobile": "<MOBILE>",
    "customer_name": "<CUSTOMER_NAME>",
    "unionid": "<UNIONID>",
    "openid": "<OPENID>",
    "owner_userid": "<OWNER_USERID>",
    "owner_display_name": "<OWNER_DISPLAY_NAME>",
    "remark": "<CUSTOMER_REMARK>",
    "follow_user_userid": "<OWNER_USERID>",
    "follow_user_userids": ["<OWNER_USERID>"],
    "binding_status": "bound",
    "is_bound": true,
    "matched_by": "unionid",
    "identity_map_id": 123,
    "detail_url": "/api/customers/<EXTERNAL_USERID>"
  },
  "route_owner": "ai_crm_next",
  "source_status": "external_user_basic",
  "fallback_used": false
}
```

## 当前产品编码对照

以下对照应来自 siyuan 当前生产商品列表 `GET /api/admin/wechat-pay/products?limit=100`，用于 `product_code` 参数。PR-11 不提交真实生产商品、订单或用户示例。

| product_code | 产品名称 | 金额 | 状态 | 备注 |
|---|---|---:|---|---|
| `<PRODUCT_CODE>` | `<PRODUCT_NAME>` | `<AMOUNT_YUAN>` | active | 由部署环境数据决定 |

历史订单编码兼容：

| 历史 product_code | 归并到当前 product_code |
|---|---|
| `<LEGACY_PRODUCT_CODE>` | `<PRODUCT_CODE>` |

调用时传当前编码即可命中兼容的历史编码。例如传 `<PRODUCT_CODE>`，会同时匹配 `<PRODUCT_CODE>` 和 `<LEGACY_PRODUCT_CODE>`。

## 批量查询订单

```http
GET /api/external/orders
```

### Query 参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `provider` | string | 否 | `all` | `all`、`wechat`、`alipay`、`wechat_shop` |
| `paid_from` | integer | 否 | - | 付款开始时间，秒级 Unix 时间戳；传入后只返回已付款订单 |
| `paid_to` | integer | 否 | - | 付款结束时间，秒级 Unix 时间戳；传入后只返回已付款订单 |
| `created_from` | integer | 否 | - | 订单创建开始时间，秒级 Unix 时间戳 |
| `created_to` | integer | 否 | - | 订单创建结束时间，秒级 Unix 时间戳 |
| `product_code` | string | 否 | - | 产品编码，见上方产品编码对照 |
| `payment_status` | string | 否 | - | `pending`、`paid`、`closed`、`failed`、`refund_processing`、`partial_refunded`、`full_refunded` |
| `is_paid` | boolean string | 否 | - | `true` 或 `false` |
| `is_refunded` | boolean string | 否 | - | `true` 或 `false`；退款中也算 `true` |
| `order_no` | string | 否 | - | 商户订单号；微信小店为小店订单号 |
| `transaction_id` | string | 否 | - | 微信/支付宝/微信小店支付单号 |
| `mobile` | string | 否 | - | 手机号 |
| `external_userid` | string | 否 | - | 企业微信外部联系人 ID |
| `unionid` | string | 否 | - | 微信 unionid |
| `limit` | integer | 否 | `100` | 每页条数，最大 `500` |
| `cursor` | string | 否 | - | 下一页游标，使用上一页返回的 `next_cursor` |

不支持按商品名称筛选；外部对接统一使用 `product_code`。

### 请求示例

拉取 2026-06-01 至 2026-06-11 的所有已付款订单：

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders?provider=all&paid_from=<PAID_FROM_TS>&paid_to=<PAID_TO_TS>&is_paid=true&limit=100"
```

按产品编码拉取：

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders?provider=all&product_code=<PRODUCT_CODE>&is_paid=true&limit=100"
```

只拉取微信小店订单：

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders?provider=wechat_shop&is_paid=true&limit=100"
```

### 响应字段

| 字段 | 说明 |
|---|---|
| `ok` | 是否成功 |
| `items` | 订单数组 |
| `next_cursor` | 下一页游标；为空表示没有下一页 |
| `has_more` | 是否还有下一页 |
| `limit` | 当前页大小 |
| `total` | 当前查询估算总数 |

`items[]` 字段：

| 字段 | 说明 |
|---|---|
| `provider` | 渠道：`wechat`、`alipay`、`wechat_shop` |
| `order_no` | 商户订单号；微信小店为小店订单号 |
| `transaction_id` | 平台支付单号 |
| `paid_at` | 付款时间，服务端展示格式 |
| `created_at` | 创建时间，服务端展示格式 |
| `product_code` | 产品编码 |
| `payment_status` | 标准支付状态 |
| `status_label` | 状态展示文案 |
| `amount_total` | 金额，单位分 |
| `amount_yuan` | 金额，单位元，字符串 |
| `currency` | 币种 |
| `is_paid` | 是否已付款 |
| `is_refunded` | 是否退款或退款中 |
| `refund_status` | 退款状态 |
| `refunded_amount_total` | 已退款金额，单位分 |
| `mobile` | 手机号 |
| `unionid` | 微信 unionid |
| `external_userid` | 企业微信外部联系人 ID |
| `detail_url` | 详情接口路径 |

响应示例：

```json
{
  "ok": true,
  "items": [
    {
      "provider": "wechat",
      "order_no": "<ORDER_NO>",
      "transaction_id": "<TRANSACTION_ID>",
      "paid_at": "2026-06-11 10:30:22",
      "created_at": "2026-06-11 10:29:58",
      "product_code": "<PRODUCT_CODE>",
      "payment_status": "paid",
      "status_label": "已支付",
      "amount_total": 1990,
      "amount_yuan": "19.90",
      "currency": "CNY",
      "is_paid": true,
      "is_refunded": false,
      "refund_status": "",
      "refunded_amount_total": 0,
      "mobile": "<MOBILE>",
      "unionid": "<UNIONID>",
      "external_userid": "<EXTERNAL_USERID>",
      "detail_url": "/api/external/orders/<ORDER_NO>?provider=wechat"
    }
  ],
  "next_cursor": "",
  "has_more": false
}
```

## 查询订单详情

```http
GET /api/external/orders/{order_no}
```

### Query 参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `provider` | string | 否 | `auto` | `auto`、`wechat`、`alipay`、`wechat_shop` |

### 请求示例

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders/<ORDER_NO>?provider=wechat"
```

微信小店详情：

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders/<WECHAT_SHOP_ORDER_ID>?provider=wechat_shop"
```

详情响应复用统一订单详情投影，包含客户、商品编码、金额、可退款金额、已退款/退款中金额、回调摘要和时间线。外部对接统一按 `product_code` 识别产品。

## 分页规则

首次请求不传 `cursor`。如果响应中：

```json
{
  "has_more": true,
  "next_cursor": "xxxx"
}
```

下一页请求原筛选条件保持不变，追加 `cursor`：

```bash
curl -H "Authorization: Bearer $TOKEN" \
"https://<SIYUAN_PRODUCTION_DOMAIN>/api/external/orders?provider=all&is_paid=true&limit=100&cursor=<NEXT_CURSOR>"
```

不要自行拼 `offset`。

## 微信小店订单来源

微信小店订单查询读取本地 `wechat_shop_orders`。当前订单进入本地库的链路是：

1. 微信小店回调 `/api/wechat-shop/notify`。
2. 系统从回调中提取 `order_id`。
3. 系统使用 `WECHAT_SHOP_APPID` 和 `WECHAT_SHOP_APPSECRET` 获取 `stable_token`。
4. 系统调用微信官方 `/channels/ec/order/get` 拉取该订单详情。
5. 系统写入 `wechat_shop_orders` 和 `wechat_shop_order_events`。
6. 外部订单 API 再从本地读模型读取。

如果已知订单号但本地没有记录，可由受控后台入口按订单号补同步：

```http
POST /api/admin/wechat-shop/orders/{order_id}/sync
```

## 时间戳说明

`paid_from`、`paid_to`、`created_from`、`created_to` 都必须传秒级 Unix 时间戳。

示例值请由调用方按查询窗口生成，例如 `<PAID_FROM_TS>`、`<PAID_TO_TS>`。

不要传毫秒级时间戳，例如 `<MILLISECONDS_TS>` 会被拒绝。
