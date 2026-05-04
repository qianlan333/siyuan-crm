# OpenClaw CRM MCP Usage

## 目标

这是当前给 OpenClaw 使用的最小 CRM MCP。

它只做少量、稳定、直接面向业务的事情：

1. 找到客户
2. 读取客户上下文
3. 改标签
4. 创建触达任务
5. 按顾问读取最近时间窗内的聊天 dump

它不是复杂平台，不做 scheduler，不做复杂 agent 编排，也不要求上层理解 CRM 原始 HTTP payload。

## Endpoint

- `GET /mcp`
- `POST /mcp`

传输协议是 JSON-RPC 风格的 streamable HTTP。

## Authentication

所有 MCP 请求都使用 Bearer Token。

```http
Authorization: Bearer <MCP_BEARER_TOKEN>
```

如果 token 缺失或错误，`/mcp` 返回 `401`。

## CustomerRef 规则

所有客户相关工具都优先支持：

- `customer_ref`
- `external_userid`

其中 `customer_ref` 可以是：

- CRM `external_userid`
- 已绑定手机号，例如 `13800138000`

解析规则：

1. 如果传了 `external_userid`，直接使用它
2. 否则如果 `customer_ref` 看起来像手机号，先走 CRM 已有的手机号解析能力
3. 解析成功后统一得到 `external_userid`
4. 如果手机号解析不到，MCP 直接返回明确错误，不会静默失败

典型错误：

- `customer_ref or external_userid is required`
- `customer not found for mobile: 13800138000`
- `customer not found`

## Core Methods

### initialize

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

### tools/list

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

### tools/call

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "resolve_customer",
    "arguments": {
      "customer_ref": "13800138000"
    }
  }
}
```

## 最小能力面

### 1. `resolve_customer`

作用：

- 输入手机号或 `external_userid`
- 返回统一客户对象

最小输入：

```json
{
  "customer_ref": "13800138000"
}
```

可选输入：

- `external_userid`
- `include_context`
- `recent_message_limit`
- `timeline_limit`

说明：

- 如果 `include_context=true`，会一并返回最近消息和最近 timeline 事件
- 如果手机号解析不到，直接返回明确错误

### 2. `get_customer_context`

作用：

- 读取单客户完整上下文

最小输入：

```json
{
  "customer_ref": "13800138000"
}
```

可选输入：

- `external_userid`
- `recent_message_limit`
- `timeline_limit`

返回至少包含：

- `external_userid`
- `customer`
- `recent_messages`
- `recent_timeline_events`
- `source_status`
- `degraded`
- `warnings`

### 3. `get_contact`

作用：

- 读取单客户 contact 视图

最小输入：

```json
{
  "customer_ref": "13800138000"
}
```

### 4. `get_recent_messages`

作用：

- 读取单客户最近消息

最小输入：

```json
{
  "customer_ref": "13800138000",
  "limit": 20
}
```

### 5. `update_customer_tags`

作用：

- 给单客户打标签 / 去标签

最小输入：

```json
{
  "customer_ref": "13800138000",
  "add_tags": ["tag-001"]
}
```

可选输入：

- `external_userid`
- `userid`
- `remove_tags`

规则：

- `add_tags` / `remove_tags` 至少一个非空
- 如果 `userid` 为空，优先使用解析出的 `customer.owner_userid`
- 如果仍然拿不到 owner，返回明确错误

### 6. `get_owner_recent_chat_dump`

作用：

- 按指定顾问读取最近时间窗内的聊天 dump
- 只做 owner 过滤和时间窗过滤
- 不做“谁最该联系”的判断
- 适合作为 OpenClaw 每小时轮询最近一小时消息的主输入工具

最小输入：

```json
{
  "owner_userid": "ZhaoYanFang"
}
```

可选输入：

- `lookback_minutes`
- `include_private`
- `include_group`

默认值：

- `lookback_minutes=60`
- `include_private=true`
- `include_group=true`

返回结构至少包含：

- `owner_userid`
- `window_start`
- `window_end`
- `private_conversations`
- `group_conversations`

其中：

- `private_conversations` 按 `external_userid` 分组
- `group_conversations` 按 `roomid/chat_id` 分组
- 每个 conversation 内的 `messages` 按时间顺序返回
- MCP 不会对会话做优先级排序

### 7. `create_private_message_task`

作用：

- 给单客户创建私信群发任务

最小输入：

```json
{
  "customer_ref": "13800138000",
  "content": "你好，来跟进一下"
}
```

可选输入：

- `external_userid`
- `userid`

规则：

- 内部先统一解析客户
- 再拿 `external_userid` 执行原有逻辑
- 如果 `userid` 为空，优先使用解析出的 owner
- 如果手机号解析不到，直接报错

### 8. `create_group_message_task`

作用：

- 给一个或多个客户创建客户群群发任务

最小输入：

```json
{
  "customer_refs": ["13800138000", "wmb..."],
  "content": "今晚八点直播提醒"
}
```

可选输入：

- `customer_ref`
- `external_userid`
- `external_userids`
- `userid`

规则：

- 支持单个客户或多个客户
- 如果 `userid` 为空，优先收集解析出的 owner 列表
- 如果任一手机号解析不到，直接报错

### 9. `create_moment_task`

作用：

- 给一个或多个客户对应顾问创建朋友圈任务

最小输入：

```json
{
  "customer_refs": ["13800138000", "wmb..."],
  "content": "今天有新活动说明"
}
```

可选输入：

- `customer_ref`
- `external_userid`
- `external_userids`
- `userid`

规则：

- 内部不会把上层暴露到底层企微 payload
- 会根据 `userid` 或解析出的 owner 生成最小底层 payload

### 10. `get_hourly_followup_candidates`

作用：

- 兼容保留的旧工具
- 会输出“现在最该联系谁”
- 不再作为新的每小时轮询主输入
- 它本身不是 scheduler

最小输入：

```json
{
  "limit": 20,
  "lookback_hours": 24
}
```

当前最小规则版会综合：

- 最近消息时间
- 最近是否有客户消息
- 客户最后一条消息后是否还没被跟进
- 当前标签 / 状态是否带高意向信号

返回至少包含：

- `rank`
- `external_userid`
- `customer_name`
- `reason`
- `suggested_action`
- `last_message_at`
- `tags`
- `class_user_status`

## 兼容保留工具

当前 MCP 仍保留以下兼容工具：

- `get_messages`
- `search_messages`
- `mark_tags`
- `unmark_tags`
- `get_group_chat`
- `record_conversion_feedback`
- batch 相关工具
- `get_hourly_followup_candidates`

但面向 OpenClaw 的推荐调用面，现在优先使用 `get_owner_recent_chat_dump`。

## Batch Processing Flow

如果只用消息批次能力，仍然是：

1. `initialize`
2. `tools/list`
3. `get_pending_message_batches`
4. `get_message_batch`
5. OpenClaw 在外部判断
6. 必要时调用标签或任务工具
7. `ack_message_batch`

## 建议调用顺序

如果上层从手机号开始：

1. `resolve_customer`
2. `get_customer_context`
3. `update_customer_tags`
4. `create_private_message_task` / `create_group_message_task` / `create_moment_task`

如果上层要做“每小时轮询最近一个小时消息”：

1. `get_owner_recent_chat_dump(owner_userid, lookback_minutes=60)`
2. OpenClaw 自己判断谁最该联系
3. 对目标客户调用 `get_customer_context`
4. 如需要，再调用 `update_customer_tags`
5. 如需要，再调用任务工具

一句话说，这个 MCP 的定位就是：

- 让 OpenClaw 用手机号或 `external_userid` 直接做 CRM 最小业务动作
- 让 OpenClaw 按顾问读取最近消息 dump，自行判断谁最值得联系
- 不再把上层暴露给 CRM 底层参数细节
