# OpenClaw Runtime Tool Bridge

## Goal

This round connects the existing tool registry to the most real upper-layer
entry currently present in this repository.

## Chosen Upper Entry

The chosen bridge point is:

- `openclaw_service.cli.customer_chat_context`

Reason:

- it already exists
- it is the current command-facing entry in `openclaw_service`
- it is the closest real upper request boundary in this repository
- using it avoids inventing a fake runtime or orchestration layer

## What Changed

The CLI entry no longer calls the service directly.

It now bridges through:

- `openclaw_service.tools.registry.call_tool_by_name(...)`

with tool name:

- `get_customer_chat_context`

## Current Call Chain

The active path is now:

1. `openclaw_service.cli.customer_chat_context.main(...)`
2. `load_customer_chat_context(...)`
3. `openclaw_service.tools.registry.call_tool_by_name(...)`
4. `openclaw_service.tools.customer_chat_context_tool.call_tool(...)`
5. `openclaw_service.services.customer_chat_context_service.get_customer_chat_context(...)`
6. CRM adapters + chat context builder

## Why This Bridge Is Minimal and Real

This keeps the current boundaries intact:

- CLI remains the upper command entry
- registry remains discovery and dispatch
- tool remains parameter validation and delegation
- service remains CRM wiring

No new dispatch framework or agent runtime was introduced.

## How Upper Layers Can Use It

If an upper layer wants the same unified path without importing a concrete tool,
it should call:

```python
from openclaw_service.tools.registry import call_tool_by_name

context = call_tool_by_name(
    "get_customer_chat_context",
    {"external_userid": "wm_xxx"},
)
```

If the current command entry is sufficient, it can also use:

```bash
python -m openclaw_service.cli.customer_chat_context --external-userid wm_xxx
```

## What This Does Not Do

- does not generate suggestions
- does not refactor agent orchestration
- does not change CRM service code
- does not change adapter or service responsibilities
- does not introduce a plugin framework
