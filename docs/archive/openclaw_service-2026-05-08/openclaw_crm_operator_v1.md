# OpenClaw CRM Operator v1

## 目标

OpenClaw CRM 操作层 v1 是一个直接面向业务的最小入口层。

它的职责不是继续扩底层抽象，而是把已经存在的 CRM context 读取能力和最小标签写能力收束成统一调用面，供上层直接使用。

本轮目标只有两个：

1. 读取单客户 CRM 上下文
2. 对单客户打标签 / 去标签

## 当前支持的能力

### 1. `get_customer_context(external_userid, *, recent_message_limit=20, timeline_limit=20)`

用途：
- 读取单客户的 CRM chat context

输入：
- `external_userid: str`
- `recent_message_limit: int = 20`
- `timeline_limit: int = 20`

输出：
- 直接返回当前稳定的 `get_customer_chat_context` 结果结构
- 返回内容包含当前链路已经稳定输出的字段，例如：
  - `external_userid`
  - `customer`
  - `recent_messages`
  - `recent_timeline_events`
  - `source_status`
  - `degraded`
  - `warnings`

内部依赖链路：
- `crm_operator_service.get_customer_context()`
- `openclaw_service.tools.registry.call_tool_by_name("get_customer_chat_context", ...)`
- `openclaw_service.tools.customer_chat_context_tool`
- `openclaw_service.services.customer_chat_context_service`
- CRM adapters / `CrmApiClient`

设计说明：
- 业务入口层不再要求上层自己去拼 tool / registry / adapter
- 这层直接复用现有稳定 context 链路，不重写 adapter 装配逻辑

### 2. `update_customer_tags(external_userid, *, userid, add_tags=None, remove_tags=None)`

用途：
- 给单客户打标签
- 给单客户去标签

输入：
- `external_userid: str`
- `userid: str`
- `add_tags: list[str] | None`
- `remove_tags: list[str] | None`

规则：
- `add_tags` 和 `remove_tags` 至少要提供一个
- 两者都为空时直接报错
- 支持仅打标签、仅去标签、同时执行两者
- 空字符串标签会被过滤，重复标签会去重

输出：
- 返回稳定结果结构：

```python
{
    "ok": True,
    "external_userid": "wm_ext_001",
    "userid": "sales_01",
    "add_tags": ["tag-001"],
    "remove_tags": [],
    "results": {
        "mark": {
            "ok": True,
            "response": {...}
        }
    }
}
```

如果部分操作失败，则：
- 顶层 `ok` 会变成 `False`
- 对应子结果会返回 `error` 和 `error_type`
- 已成功的子操作结果会保留，不会被悄悄吞掉

内部依赖链路：
- `crm_operator_service.update_customer_tags()`
- `openclaw_service.integrations.crm.adapters.tags.TagsAdapter`
- `openclaw_service.integrations.crm.client.CrmApiClient`
- CRM HTTP API
  - `POST /api/tags/mark`
  - `POST /api/tags/unmark`

## 本轮明确不做什么

本轮只做最小 CRM 操作层 v1，明确不包含以下范围：

- 不做建议生成
- 不做分层 / 状态写入
- 不做事件接收
- 不做 UI
- 不做复杂 agent / runtime 编排
- 不改 CRM 主服务
- 不直连 CRM 数据库
- 不扩标签库管理、标签组管理等额外能力

## 推荐调用方式

```python
from openclaw_service.services.crm_operator_service import (
    get_customer_context,
    update_customer_tags,
)

context = get_customer_context(
    "wm_ext_001",
    recent_message_limit=10,
    timeline_limit=10,
)

tag_result = update_customer_tags(
    "wm_ext_001",
    userid="sales_01",
    add_tags=["tag-001"],
    remove_tags=["tag-002"],
)
```

这层的定位是“给上层直接用的业务入口”，而不是再暴露底层技术装配细节。
