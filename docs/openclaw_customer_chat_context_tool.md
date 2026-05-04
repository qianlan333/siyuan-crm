# OpenClaw Customer Chat Context Tool

## Goal

This round exposes the existing CRM-backed customer chat context read chain as a
formal OpenClaw-callable entry.

Input:

- `external_userid`

Output:

- customer detail
- recent messages
- recent timeline events
- degraded / fallback semantics

This tool only returns suggestion input context.

It does **not** generate suggestions.

## Formal Callable Entry

Tool module:

- `openclaw_service.tools.customer_chat_context_tool`

Primary callable:

- `call_tool(arguments)`

Tool name:

- `get_customer_chat_context`

## Input Parameters

- `external_userid` (required)
- `recent_message_limit` (optional, default `20`)
- `timeline_limit` (optional, default `20`)

## Output Structure

The tool returns the service result unchanged:

```json
{
  "external_userid": "wm_xxx",
  "customer": {},
  "recent_messages": [],
  "recent_timeline_events": [],
  "source_status": "live",
  "degraded": false,
  "warnings": []
}
```

## Internal Dependency

The tool does not create CRM adapters itself.

It delegates directly to:

- `openclaw_service.services.customer_chat_context_service.get_customer_chat_context`

The service then:

- creates `CrmApiConfig`
- creates `CrmApiClient`
- builds `CustomersAdapter`
- builds `MessagesAdapter`
- builds `TimelineAdapter`
- calls `build_customer_chat_context(...)`

## What This Tool Does Not Do

- does not generate suggestions
- does not construct prompts
- does not write back to CRM
- does not modify CRM service code
- does not access CRM database directly
- does not refactor OpenClaw agents

## How Upper Layers Should Use It

Upper layers should call the tool entry instead of wiring CRM adapters by hand.

Minimal example:

```python
from openclaw_service.tools.customer_chat_context_tool import call_tool

context = call_tool({"external_userid": "wm_xxx"})
```

If a higher-level tool registry is added later, it can register:

- `get_tool_def()`
- `call_tool(...)`

without changing CRM adapter or service boundaries.
