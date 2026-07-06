---
package_key: channel_entry_day_n
name: 渠道进入第 N 天且已加微
status: paused
query_mode: snapshot_current
identity_policy: external_userid
refresh_mode: daily_0200
natural_language_definition: 从指定渠道进入第 N 天，并且已经添加企业微信的用户。
parameters:
  channel_key: q9_channel
  day_n: 3
senders:
  - sender_userid: HuangYouCan
    display_name: HuangYouCan
    priority: 1
    status: active
---

# 业务说明

用于每日 2:00 识别渠道进入第 N 天且已加微的用户。

# Snapshot SQL

```sql
SELECT
  'external_userid' AS identity_type,
  ce.external_userid AS identity_value,
  'channel_entry:' || ce.channel_entry_id::text AS event_source_key,
  jsonb_build_object(
    'channel_key', ce.channel_key,
    'entered_at', ce.entered_at,
    'day_n', :day_n
  ) AS payload_json,
  ce.external_userid,
  ce.entered_at AS event_at
FROM audience_read.channel_entries_v1 ce
JOIN audience_read.wecom_contacts_v1 wc
  ON wc.external_userid = ce.external_userid
WHERE ce.channel_key = :channel_key
  AND ce.entered_at >= (:refresh_started_at::date - (:day_n || ' days')::interval)
  AND ce.entered_at < (:refresh_started_at::date - ((:day_n - 1) || ' days')::interval)
```
