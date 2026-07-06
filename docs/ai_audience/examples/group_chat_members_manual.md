---
package_key: group_chat_members_manual
name: 指定企微群成员
status: paused
query_mode: snapshot_current
identity_policy: external_userid
refresh_mode: manual
natural_language_definition: 指定企微客户群内的外部联系人，用于手动刷新生成运营人群包。
parameters:
  chat_id: wrbNXyCwAAm0Vx7_OVQ_-PkT6Exeg8pg
senders:
  - sender_userid: HuangYouCan
    display_name: HuangYouCan
    priority: 1
    status: active
  - sender_userid: QianLan
    display_name: QianLan
    priority: 2
    status: active
  - sender_userid: MengYu
    display_name: MengYu
    priority: 3
    status: active
---

# 业务说明

用于把指定企微客户群中的外部联系人生成 AI 自动化运营人群包。刷新方式为手动，不会进入定时刷新队列。成员变化取决于上游 `group_chats.raw_payload` 缓存更新。

# Snapshot SQL

```sql
SELECT
  'external_userid' AS identity_type,
  gm.external_userid AS identity_value,
  'group_chat_member:' || gm.chat_id || ':' || gm.external_userid AS event_source_key,
  gm.payload_json AS payload_json,
  gm.external_userid,
  gm.owner_userid,
  gm.joined_at AS event_at
FROM audience_read.group_chat_members_v1 gm
WHERE gm.chat_id = :chat_id
```
