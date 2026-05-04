# Customer Center API

本轮新增了最小可用的 `customer_center` 只读聚合层，为后续 CRM UI 和 openclaw 提供统一客户语义入口。

当前实际对外入口仍然是：

- `GET /api/customers`
- `GET /api/customers/<external_userid>`

实际 Flask 路由注册落在 `wecom_ability_service/routes.py`，`wecom_ability_service/customer_center/service.py` 提供聚合逻辑，`repo.py` 负责底层读取。

## 新接口

### `GET /api/customers`

返回客户列表聚合结果。

支持的查询参数：

- `owner_userid`
- `tag`
- `status`
- `is_bound`
- `mobile`
- `keyword`
- `limit`
- `offset`

兼容说明：

- 为了和当前已有调用习惯兼容，列表接口同时接受 `owner` 作为 `owner_userid` 的别名。

返回结构：

```json
{
  "ok": true,
  "customers": [],
  "count": 0,
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0,
  "filters": {
    "owner_userid": "",
    "tag": "",
    "status": "",
    "is_bound": "",
    "mobile": "",
    "keyword": "",
    "limit": "50",
    "offset": "0"
  }
}
```

### `GET /api/customers/<external_userid>`

返回单个客户统一 DTO。

返回结构：

```json
{
  "ok": true,
  "customer": {
    "external_userid": "wm_xxx",
    "customer_name": "",
    "owner_userid": "",
    "remark": "",
    "description": "",
    "mobile": "",
    "is_bound": false,
    "binding_status": "unbound",
    "follow_user_userids": [],
    "tags": [],
    "class_user_status": {},
    "last_message_at": "",
    "last_touch_at": ""
  }
}
```

## DTO 字段说明

- `external_userid`：企微客户主键
- `customer_name`：客户名称，优先来自 `contacts.customer_name`
- `owner_userid`：当前聚合出的主跟进人
- `owner_display_name`：跟进人展示名，来自 `owner_role_map`
- `remark`：联系人备注
- `description`：联系人描述
- `mobile`：手机号，优先来自 `external_contact_bindings -> people`
- `is_bound`：是否已绑定手机号
- `binding_status`：当前绑定状态，最小口径只区分 `bound / unbound`
- `follow_user_userids`：当前客户关联到的企微跟进人列表
- `tags`：当前本地标签快照列表，来自 `contact_tags`
- `class_user_status`：班期用户状态聚合，来自 `class_user_status_current`
- `last_message_at`：最近一条归档消息时间，来自 `archived_messages`
- `last_touch_at`：当前先保守等于 `last_message_at`
- `updated_at`：用于列表排序的聚合更新时间，优先使用 `class_user_status_current.updated_at`，否则回落到 `contacts / bindings / last_message_at`

## 当前聚合来源

本轮只做读聚合，不新增 schema，也不改写旧接口。

聚合读取来源包括：

- `contacts`
- `people`
- `external_contact_bindings`
- `wecom_external_contact_identity_map`
- `wecom_external_contact_follow_users`
- `contact_tags`
- `class_user_status_current`
- `archived_messages`
- `owner_role_map`

## 已知限制

- `last_touch_at` 本轮没有接入任务、问卷、动作等更多触点来源，所以暂时保守等于 `last_message_at`
- 列表过滤是最小可用版，先支持 `owner_userid / tag / status / is_bound / mobile / keyword`
- `customer_center` 当前是读聚合层，不负责复杂写操作
- 旧接口 `/api/contacts`、`/api/contacts/<external_userid>`、`/api/identity/resolve`、`/api/sidebar/*` 保持原行为不变
- `/api/customers` 列表返回当前同时保留 `customers/count` 和 `items/total` 两套字段，并补充 `filters`，用来兼容现有 contract 护栏
