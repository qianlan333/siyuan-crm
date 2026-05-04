# OpenClaw Tool Registry

## Goal

This round adds one minimal unified discovery and dispatch entry for OpenClaw
tools.

It does not introduce a new plugin system.

It only gives upper layers one stable place to:

- list registered tools
- fetch tool definitions
- call a tool by name

## Registry Entry

Registry module:

- `openclaw_service.tools.registry`

Primary APIs:

- `get_tool_defs()`
- `list_tools()`
- `call_tool_by_name(name, arguments)`

## Currently Registered Tools

- `get_customer_chat_context`

This tool remains implemented in:

- `openclaw_service.tools.customer_chat_context_tool`

The registry only wires it into a unified entrypoint.

## How Tool Discovery Works

Tool definitions are exposed through:

```python
from openclaw_service.tools.registry import get_tool_defs

tool_defs = get_tool_defs()
```

Tool names are exposed through:

```python
from openclaw_service.tools.registry import list_tools

tool_names = list_tools()
```

## How Tool Dispatch Works

Call by tool name:

```python
from openclaw_service.tools.registry import call_tool_by_name

result = call_tool_by_name(
    "get_customer_chat_context",
    {"external_userid": "wm_xxx"},
)
```

## How Customer Chat Context Is Registered

The registry imports and registers:

- `TOOL_NAME`
- `get_tool_def()`
- `call_tool(arguments)`

from:

- `openclaw_service.tools.customer_chat_context_tool`

The actual CRM loading path is unchanged:

- registry
- `customer_chat_context_tool.call_tool(...)`
- `customer_chat_context_service.get_customer_chat_context(...)`
- CRM adapters + chat context builder

## What This Does Not Do

- does not refactor agent dispatch
- does not generate suggestions
- does not add a plugin framework
- does not change CRM service code
- does not access CRM database directly
- does not replace the existing service or CLI entrypoints
