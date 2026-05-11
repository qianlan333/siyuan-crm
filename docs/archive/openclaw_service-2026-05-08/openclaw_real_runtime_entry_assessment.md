# OpenClaw Real Runtime Entry Assessment

## Scope

This assessment checks whether the current repository contains a more realistic
OpenClaw upper-layer runtime entry than the existing customer chat context CLI
bridge.

The goal is not to invent a new runtime. The goal is to identify a real
existing entry if one already exists.

## Scanned Candidate Entry Types

The repository was scanned for these categories inside current code:

- HTTP handlers
- command handlers
- conversation or session entrypoints
- orchestration or dispatch loops
- runners
- task entrypoints
- CLI command entrypoints

## What Actually Exists

### In `openclaw_service`

The real files currently present are limited to:

- CRM integration layer
- service layer
- tool layer
- one CLI entry:
  - `openclaw_service.cli.customer_chat_context`

There is no existing:

- conversation runtime
- session runtime
- orchestration entry
- task runner
- command router beyond the CLI file
- HTTP layer inside `openclaw_service`

### In `wecom_ability_service`

There are many real HTTP handlers and Flask routes, including:

- `/api/customers`
- `/api/customers/<external_userid>`
- `/api/customers/<external_userid>/timeline`
- `/api/messages/...`
- `/mcp`

But these belong to the CRM / WeCom service boundary, not the OpenClaw runtime
boundary.

They cannot be treated as the OpenClaw upper-layer entry requested in this
task, because that would cross the separation boundary we intentionally kept in
this branch.

## Conclusion

No entry more real than the current CLI bridge exists inside `openclaw_service`
at this time.

So the current result is:

- the existing CLI bridge is the most real OpenClaw upper-layer entry in this repository
- there is no deeper current OpenClaw conversation/session/orchestration entry to wire into
- creating one now would be inventing architecture, which this round explicitly forbids

## Current Most Real Entry

The most real current entry is:

- `openclaw_service.cli.customer_chat_context`

Current call chain:

1. `main(...)`
2. `load_customer_chat_context(...)`
3. `openclaw_service.tools.registry.call_tool_by_name(...)`
4. `openclaw_service.tools.customer_chat_context_tool.call_tool(...)`
5. `openclaw_service.services.customer_chat_context_service.get_customer_chat_context(...)`
6. CRM adapters + context builder

## Why We Did Not Add Another Runtime Layer

Adding any of the following would be artificial in the current repository:

- `runtime/dispatcher.py`
- fake conversation loop
- fake orchestration facade
- fake session entry

That would not be a real integration with an existing upper-layer flow. It
would only add another wrapper without evidence that the wrapper is actually
used.

## Minimal Future Bridge When a Real Entry Appears

When a real OpenClaw upper entry appears later, it should bridge in the
smallest possible way:

```python
from openclaw_service.tools.registry import call_tool_by_name

context = call_tool_by_name(
    "get_customer_chat_context",
    {"external_userid": external_userid},
)
```

That future entry should:

- parse incoming params
- call the registry
- return the result
- avoid importing CRM adapters directly
- avoid bypassing the tool registry

## Final Assessment

For the repository as it exists today:

- no more realistic OpenClaw runtime entry than the CLI bridge was found
- the current CLI-based bridge is the correct stopping point for this round
- the next real integration step depends on a real OpenClaw session/command/runtime entry appearing in code
