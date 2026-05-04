# OpenClaw CRM Read Contract

## 目标

这份文档只固化 OpenClaw 当前可以稳定依赖的 CRM 读接口契约。

本轮原则：

- 不改 path
- 不改 schema
- 不改业务语义
- 只把当前已实现、已可读的字段固化成回归护栏

说明：

- “最少保证”表示 OpenClaw 现在可以把这些字段当成稳定依赖
- “best effort”表示当前通常会返回，但后续使用时不应作为唯一强依赖

## 1. `GET /api/customers`

### 用途

OpenClaw 读取客户中心列表时的首选列表接口。

### 当前稳定读契约

顶层最少保证存在：

- `ok`
- `customers`
- `count`
- `items`
- `total`
- `limit`
- `offset`
- `filters`

### 字段语义

- `items`：当前分页下的客户列表
- `customers`：与 `items` 对齐的兼容别名，OpenClaw 可任选其一，但建议优先读 `items`
- `count`：当前返回条数
- `total`：总条数
- `limit`：当前 limit
- `offset`：当前 offset
- `filters`：服务端实际识别并回显的筛选条件

### 每个 customer list item 当前可稳定读取的常用字段

- `external_userid`
- `customer_name`
- `owner_userid`
- `mobile`
- `is_bound`
- `tags`
- `class_user_status`
- `last_message_at`
- `last_touch_at`

### best effort 字段

- `owner_display_name`
- `remark`
- `description`
- `signup_status`
- `signup_label_name`
- `follow_user_userids`

## 2. `GET /api/customers/<external_userid>`

### 用途

OpenClaw 读取单客户聚合上下文时的首选 detail 接口。

### 当前稳定读契约

顶层最少保证存在：

- `ok`
- `customer`

`customer` 内最少保证存在：

- `external_userid`
- `customer_name`
- `owner_userid`
- `last_message_at`
- `last_touch_at`
- `tags`
- `class_user_status`

### 额外当前通常存在的字段

- `remark`
- `description`
- `mobile`
- `binding`
- `identity`
- `contact`
- `sidebar_context`
- `follow_users`
- `owner_display_name`

### 说明

- OpenClaw 若只需要“客户主上下文”，优先读这里，不要自己拼 contacts + identity + class_user
- `tags` 是当前客户标签快照
- `class_user_status` 是当前 class_user 视角状态快照

## 3. `GET /api/customers/<external_userid>/timeline`

### 用途

OpenClaw 获取扩展上下文和多事件历史时的首选 timeline 接口。

### 当前稳定读契约

顶层最少保证存在：

- `ok`
- `timeline`

`timeline` 内最少保证存在：

- `external_userid`
- `items`
- `count`
- `limit`
- `offset`
- `filters`
- `total`

### 每个 timeline item 最少保证字段

- `event_id`
- `event_type`
- `event_time`
- `title`
- `summary`
- `source_table`
- `source_id`
- `metadata`

### 额外当前通常存在的字段

- `occurred_at`
- `operator_userid`
- `external_userid`

### 说明

- `metadata` 是每条事件的原始上下文容器
- OpenClaw 应把 `event_type + title + summary + metadata` 作为 timeline 读取主入口

## 4. `GET /api/messages/<external_userid>/recent`

### 用途

OpenClaw 读取最近对话上下文时的首选轻量消息接口。

### 当前稳定读契约

顶层最少保证存在：

- `ok`
- `messages`

每条消息最少保证字段：

- `msgid`
- `msgtype`
- `content`
- `send_time`
- `external_userid`

### 额外当前通常存在的字段

- `chat_type`
- `owner_userid`
- `sender`
- `from`
- `seq`
- `roomid`
- `chat_id`
- `group_name`
- `tolist`

## OpenClaw 当前优先读取建议

### 1. customer detail

首选：

- `GET /api/customers/<external_userid>`

强依赖字段：

- `customer.external_userid`
- `customer.customer_name`
- `customer.owner_userid`
- `customer.last_message_at`
- `customer.last_touch_at`
- `customer.tags`
- `customer.class_user_status`

best effort 字段：

- `customer.remark`
- `customer.description`
- `customer.identity`
- `customer.binding`
- `customer.follow_users`

### 2. recent chat

首选：

- `GET /api/messages/<external_userid>/recent`

强依赖字段：

- `messages[*].msgid`
- `messages[*].msgtype`
- `messages[*].content`
- `messages[*].send_time`
- `messages[*].external_userid`

best effort 字段：

- `messages[*].chat_type`
- `messages[*].owner_userid`
- `messages[*].group_name`
- `messages[*].chat_id`

### 3. extended context

首选：

- `GET /api/customers/<external_userid>/timeline`

强依赖字段：

- `timeline.external_userid`
- `timeline.items`
- `timeline.count`
- `timeline.limit`
- `timeline.offset`
- `timeline.filters`
- `timeline.total`
- `timeline.items[*].event_id`
- `timeline.items[*].event_type`
- `timeline.items[*].event_time`
- `timeline.items[*].title`
- `timeline.items[*].summary`
- `timeline.items[*].source_table`
- `timeline.items[*].source_id`
- `timeline.items[*].metadata`

best effort 字段：

- `timeline.items[*].occurred_at`
- `timeline.items[*].operator_userid`

## 契约边界

这份契约只保证“当前 OpenClaw 已应依赖的读取结构”。

不在本轮承诺的内容：

- timeline 来源扩展
- customer_center 聚合逻辑扩展
- 问卷逻辑重构
- auth 行为变化
