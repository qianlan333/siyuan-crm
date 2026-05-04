# OpenClaw Customer Chat Context Runbook

## Goal

Expose the already working CRM chat-context read chain behind one minimal
OpenClaw-facing entrypoint.

Input:

- `external_userid`

Output:

- customer detail
- recent messages
- recent timeline events
- degraded / fallback semantics

This runbook is only for loading suggestion input context.

It does **not** generate suggestions.

## Smallest Service Call

```python
from openclaw_service.services.customer_chat_context_service import get_customer_chat_context

context = get_customer_chat_context("wm_xxx")
```

Optional limits:

```python
context = get_customer_chat_context(
    "wm_xxx",
    recent_message_limit=10,
    timeline_limit=10,
)
```

## CLI Usage

```bash
python -m openclaw_service.cli.customer_chat_context \
  --external-userid wm_xxx \
  --recent-message-limit 20 \
  --timeline-limit 20
```

## Environment Variables

- `CRM_API_BASE_URL`
- `CRM_API_TOKEN`
- `CRM_MCP_BEARER_TOKEN`
- optional:
  - `CRM_API_TIMEOUT_MS`
  - `CRM_API_MAX_RETRIES`
  - `CRM_API_RETRY_BACKOFF_SECONDS`
  - `CRM_PREFER_CUSTOMER_ENDPOINTS`
  - `CRM_PREFER_TIMELINE_ENDPOINT`

## Successful Output Shape

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

## Degraded / Fallback Meaning

- `live`
  - customer, recent messages, and timeline all resolved normally

- `fallback`
  - at least one source fell back or degraded
  - upper layers can still consume the result

- `degraded`
  - core context is missing
  - upper layers should avoid treating the context as fully reliable

## What This Runbook Does Not Cover

- suggestion generation
- prompt construction
- CRM writes
- agent refactors
- UI work
