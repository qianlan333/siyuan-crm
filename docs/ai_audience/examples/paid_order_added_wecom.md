---
package_key: paid_order_added_wecom
name: 已支付且已加微
status: paused
query_mode: incremental_event
identity_policy: external_userid
refresh_mode: incremental_3m_plus_daily_0200
natural_language_definition: 支付成功且已经添加企业微信的用户。
parameters:
  order_status: paid
senders:
  - sender_userid: HuangYouCan
    display_name: HuangYouCan
    priority: 1
    status: active
---

# 业务说明

识别支付成功且已经添加企业微信的用户。增量刷新捕捉新支付，每日 2:00 做一次快照收敛。

# Incremental SQL

```sql
SELECT
  'external_userid' AS identity_type,
  o.external_userid AS identity_value,
  'order:' || o.order_id::text AS event_source_key,
  jsonb_build_object(
    'order_id', o.order_id,
    'paid_at', o.paid_at,
    'status', o.status
  ) AS payload_json,
  o.external_userid,
  o.paid_at AS event_at
FROM audience_read.orders_v1 o
JOIN audience_read.wecom_contacts_v1 wc
  ON wc.external_userid = o.external_userid
WHERE o.status = :order_status
  AND o.paid_at >= :last_watermark_at - (:lookback_seconds || ' seconds')::interval
  AND o.paid_at < :refresh_started_at
```

# Snapshot SQL

```sql
SELECT
  'external_userid' AS identity_type,
  o.external_userid AS identity_value,
  'order:' || o.order_id::text AS event_source_key,
  jsonb_build_object(
    'order_id', o.order_id,
    'paid_at', o.paid_at,
    'status', o.status
  ) AS payload_json,
  o.external_userid,
  o.paid_at AS event_at
FROM audience_read.orders_v1 o
JOIN audience_read.wecom_contacts_v1 wc
  ON wc.external_userid = o.external_userid
WHERE o.status = :order_status
```
