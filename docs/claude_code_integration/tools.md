# CRM MCP Tool Groups

Tools are grouped by side-effect level:

| Level | Meaning | Assistant behavior |
| --- | --- | --- |
| `read` | Reads CRM state only | Safe to call directly |
| `draft` | Creates draft CRM records | Call and report created ids |
| `async_write` | Creates workorders/tasks | Call only for the requested workflow |
| `write` | Executes live sends or production state changes | Requires CRM approval token |

## Segments

- `list_segments`
- `get_segment`
- `validate_segment_sql`
- `preview_segment_members`
- `propose_segment`
- `update_segment`
- `archive_segment`

Use `validate_segment_sql` before proposing custom SQL. Segment SQL must return
`member_id`, use allowed tables, and avoid destructive keywords.

## Interaction And Review

- `query_segment_dimensions`
- `search_segment_members`
- `query_member_interaction_stats`
- `query_recent_touch_outcomes`
- `scan_silent_for_revival`

Use these to estimate audience size, inspect behavior, and review outcomes.

## Campaigns And Broadcasts

- `propose_campaign`
- `submit_campaign_for_review`
- `get_campaign`
- `list_campaigns`
- `pause_campaign`
- `resume_campaign`
- `propose_single_broadcast`
- `simulate_broadcast`

Live execution tools such as `start_campaign` or `commit_broadcast_plan` require
CRM-issued approval. Do not manufacture or reuse approval tokens.

## Copy Workorders

- `request_copy_workorder`

Ask the copy system for variants after the assistant has identified audience,
intent, and constraints.

## Audit

- `evaluate_transition`

When a tool returns `trace_id`, include it in the user-facing summary.
