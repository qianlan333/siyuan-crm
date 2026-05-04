# OpenClaw Customer Chat Context Preflight

## Goal

This round adds a minimal runtime assurance layer for the existing customer chat
context chain.

It answers three practical questions before deeper OpenClaw integration:

- is the required environment present
- can the unified tool path be invoked
- does the chain return live, fallback, or degraded context

## What Was Added

- `openclaw_service.services.customer_chat_context_preflight`
- `openclaw_service.cli.customer_chat_context_preflight`

The preflight service validates environment and then calls the existing unified
tool path through:

- `call_tool_by_name("get_customer_chat_context", {...})`

It does not call adapters directly.

## When To Use Which CLI

Use the normal CLI when you want the full context payload:

```bash
python -m openclaw_service.cli.customer_chat_context --external-userid wm_xxx
```

Use the preflight CLI when you want a compact operational verdict:

```bash
python -m openclaw_service.cli.customer_chat_context_preflight --external-userid wm_xxx
```

## Environment Variables

Required:

- `CRM_API_BASE_URL`
- `CRM_API_TOKEN`

Optional:

- `CRM_MCP_BEARER_TOKEN`
- `CRM_API_TIMEOUT_MS`
- `CRM_API_MAX_RETRIES`
- `CRM_API_RETRY_BACKOFF_SECONDS`

## Exit Codes

- `0`: live
- `2`: fallback or degraded, but the chain ran
- `1`: missing environment or runtime error

## Output Shape

Example:

```json
{
  "ok": true,
  "external_userid": "wm_xxx",
  "env": {
    "ok": true,
    "required_env": {
      "CRM_API_BASE_URL": true,
      "CRM_API_TOKEN": true
    },
    "optional_env": {
      "CRM_MCP_BEARER_TOKEN": true,
      "CRM_API_TIMEOUT_MS": false,
      "CRM_API_MAX_RETRIES": false,
      "CRM_API_RETRY_BACKOFF_SECONDS": false
    },
    "missing_required": []
  },
  "tool_name": "get_customer_chat_context",
  "source_status": "live",
  "degraded": false,
  "warnings": [],
  "customer_present": true,
  "recent_messages_count": 5,
  "recent_timeline_events_count": 5,
  "sample_customer_fields": {
    "external_userid": "wm_xxx",
    "customer_name": "Alice",
    "owner_userid": "sales_01"
  },
  "error": ""
}
```

## Degraded / Fallback Semantics

- `live`
  - the chain returned normally without degradation

- `fallback`
  - the chain ran, but at least one source fell back

- `degraded`
  - the chain ran, but source quality is reduced

- `error`
  - required env is missing or the unified tool call failed

The preflight output intentionally returns only a compact summary, not the full
customer payload.

## What This Does Not Do

- does not generate suggestions
- does not change CRM service code
- does not change adapter, service, tool, or registry responsibilities
- does not return full customer privacy-sensitive data
