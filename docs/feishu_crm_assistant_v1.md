# Feishu CRM Assistant v1

## 目标

飞书 CRM 助手 v1 是一个接在现有飞书消息入口上的薄业务层。

它不做复杂 agent，不做建议生成，只负责把飞书文本消息识别成少量固定 CRM 意图，然后调用 OpenClaw CRM Operator v1。

## 当前支持的自然语言意图

### 1. 查询客户上下文

示例：
- `看看这个用户 wmb... 什么情况`
- `查一下用户 wmb...`
- `这个用户最近聊了什么 wmb...`

行为：
- 调用 `get_customer_context(...)`
- 返回客户摘要、标签、状态、最近消息

### 2. 打标签

示例：
- `给用户 wmb... 打标签 高意向`
- `给 wmb... 打上 Codex测试标签-20260320-175705`

行为：
- 解析 `external_userid`
- 解析标签名
- 通过 `GET /api/tags` 精确匹配标签名到 `tag_id`
- 调用 `update_customer_tags(..., add_tags=[tag_id])`

### 3. 去标签

示例：
- `把用户 wmb... 的标签 高意向 去掉`
- `给 wmb... 去掉 Codex测试标签-20260320-175705`

行为：
- 解析 `external_userid`
- 解析标签名
- 通过 `GET /api/tags` 精确匹配标签名到 `tag_id`
- 调用 `update_customer_tags(..., remove_tags=[tag_id])`

### 4. “怎么聊”类请求

示例：
- `这个用户 wmb... 我该怎么聊`
- `帮我看看这个用户怎么跟进`

行为：
- 调用 `get_customer_context(...)`
- 返回客户摘要、最近消息、标签、状态
- 明确提示当前版本只返回上下文，不直接生成话术

## external_userid 规则

- 当前版本必须在消息中直接提供 `external_userid`
- 不做客户模糊搜索
- 不做昵称猜测
- 如果没识别到 `external_userid`，直接回复：
  - `请提供客户 external_userid，例如：wmb...`

## 标签解析规则

- 当前版本通过 CRM 的 `GET /api/tags` 读取标签列表
- 只支持按 `tag_name` 精确匹配
- 如果同名多个：
  - 回复 `请明确标签名/标签ID`
- 如果找不到：
  - 回复 `未找到标签`

## 当前消息入口

当前优先接入的真实飞书入口是：

- `openclaw_service/cli/feishu_longconn_bot.py`
- `openclaw_service/feishu/longconn.py`
- `openclaw_service/feishu/commands.py`

HTTP webhook 入口 `openclaw_service/feishu/app.py` 仍然保留，并复用同一个 `handle_text_command(...)`，因此两条入口共享同一套 CRM 助手行为。

## 当前不支持什么

- 不支持真正的话术生成
- 不支持复杂 Prompt 编排
- 不支持客户模糊搜索
- 不支持标签模糊匹配
- 不支持分层 / 状态写入
- 不支持 UI
- 不支持复杂 agent/runtime
