# Claude Code CRM Integration

This folder is the compact operator-facing contract for using CRM MCP tools
from Claude Code or another compatible assistant.

## Roles

- Assistant: strategy, segmentation, and draft planning.
- CRM: source of truth, audit trail, approval UI, and execution guardrails.
- Copy assistant: final copy variants when a copy-workorder flow is available.

## Setup

1. Generate an MCP credential in the CRM cloud-orchestrator integration page.
2. Add the CRM MCP endpoint and bearer token to the assistant MCP config.
3. Confirm `/mcp` connects before asking the assistant to plan CRM work.

## Operating Rules

- Read-only tools may be called directly.
- Draft tools may create CRM drafts but must report what was created.
- Real sends or state-changing execution require CRM-side approval.
- Do not hardcode final message copy when the copy-workorder flow is available.
- Always report the CRM id or trace id returned by a planning tool.

## Files

- `tools.md`: tool groups and side-effect levels.
- `patterns.md`: safe planning patterns.
- `rules.md`: hard guardrails.
- `troubleshooting.md`: quick failure triage.
