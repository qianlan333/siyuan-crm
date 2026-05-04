# Customer Timeline API

## 接口路径

- `GET /api/customers/<external_userid>/timeline`

## 查询参数

- `limit`
  - 可选
  - 默认 `50`
  - 最小 `1`
  - 最大 `100`
- `offset`
  - 可选
  - 默认 `0`
  - 最小 `0`
- `event_type`
  - 可选
  - 当前支持按精确值过滤：
    - `message`
    - `status_change`
    - `questionnaire_submit`
    - `wecom_event`

## 返回结构

```json
{
  "ok": true,
  "timeline": {
    "external_userid": "wm_xxx",
    "items": [],
    "count": 0,
    "limit": 50,
    "offset": 0,
    "filters": {
      "event_type": "",
      "limit": "50",
      "offset": "0"
    },
    "total": 0
  }
}
```

说明：

- 顶层固定保留 `ok`
- 顶层固定保留 `timeline`
- `timeline.external_userid` 固定返回请求中的客户标识
- `count` 表示当前页返回的事件数
- `total` 表示过滤后、分页前的总事件数

## Timeline Item 字段

每个 `timeline.items[]` 至少包含：

- `event_id`
  - 统一事件主键，格式为 `<event_type>:<source_id>`
- `event_type`
  - 当前可能值：`message`、`status_change`、`questionnaire_submit`、`wecom_event`
- `event_time`
  - 统一排序时间字段
- `occurred_at`
  - 与 `event_time` 保持一致，作为兼容字段保留
- `title`
  - 事件标题
- `summary`
  - 事件摘要
- `source_table`
  - 原始来源表名
- `source_id`
  - 原始表主键
- `operator_userid`
  - 操作人或最接近的责任人
- `external_userid`
  - 客户 external_userid
- `metadata`
  - 原始映射字段集合

字段缺失时会返回空字符串或空对象，不因单条脏数据报错。

## 排序与分页

- 所有时间线事件按 `event_time` 倒序
- 当来源表缺少统一时间字段时，采用如下回退规则：
  - `archived_messages`: `send_time`，缺失时回退 `created_at`
  - `class_user_status_history`: `set_at`，缺失时回退 `created_at`
  - `questionnaire_submissions`: `submitted_at`
  - `wecom_external_contact_event_logs`: `event_time`，缺失时回退 `created_at`，再回退 `updated_at`
- 分页为最小实现：`limit + offset`

## 当前已接入来源

### 1. `archived_messages` => `message`

- 关联方式：直接使用 `external_userid`
- `event_time`: `send_time`
- `title`: `消息 · <msgtype>`
- `summary`: `content`
- `operator_userid`: 优先 `decrypted_message.from`，其次 `sender`
- `metadata`: 复用旧消息格式化后的结果，确保与 `/api/messages/*` 的消息字段尽量一致

### 2. `class_user_status_history` => `status_change`

- 关联方式：直接使用 `external_userid`
- `event_time`: `set_at`
- `title`: `状态变更`
- `summary`: `<old_signup_status> -> <new_signup_status>`
- `operator_userid`: `set_by_userid`
- `metadata`: 当前状态变更记录完整字段

### 3. `questionnaire_submissions` => `questionnaire_submit`

- 关联方式：直接使用 `external_userid`
- `event_time`: `submitted_at`
- `title`: `问卷提交 · <questionnaire_title>`
- `summary`: 当前最小版只返回 `score=<total_score>`
- `operator_userid`: `follow_user_userid`，缺失时回退 `staff_id`
- `metadata`: 提交记录字段，加上问卷标题/名称

### 4. `wecom_external_contact_event_logs` => `wecom_event`

- 关联方式：直接使用 `external_userid`
- `event_time`: `event_time`，缺失时回退 `created_at/updated_at`
- `title`: `企微事件`
- `summary`: `<event_type> · <change_type>`
- `operator_userid`: `user_id`
- `metadata`: 事件日志字段，`payload_json` 会被安全解析

## 当前未接入来源

### `outbound_tasks`

本轮未接入，原因如下：

- 当前表没有 `external_userid` 独立列
- 只能从 `request_payload/response_payload` JSON 中猜测客户标识
- 这种关联方式不满足“可靠用 external_userid 直接关联”的约束

因此本轮明确不接入，不伪造关联。

## 空客户 / 不存在客户语义

- 当前语义为 `404`
- 返回：

```json
{
  "ok": false,
  "error": "customer not found"
}
```

这个语义与当前 handler 保持一致。

## 已知限制

- 当前是聚合读模型，不写统一事件表
- 当前没有 cursor 分页，只有最小版 `limit + offset`
- `outbound_tasks` 因无法可靠关联未接入
- `event_time` 目前依赖各来源表的时间字段质量，字符串时间的排序前提是存储格式一致
