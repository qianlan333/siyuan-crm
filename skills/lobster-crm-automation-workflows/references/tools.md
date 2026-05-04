# CRM Automation Workflow Via `wecom_mcp`

## Required Entry Point

Always use the generic proxy tool:

- `wecom-preflight` first, once per session before the first `wecom_mcp` call
- `wecom_mcp` for discovery and execution

The proxy format is:

- list tools under one category:

```text
wecom_mcp list <category>
```

- call one MCP method through the proxy:

```text
wecom_mcp call <category> <method> '<jsonArgs>'
```

## Category Discovery

Do not assume the workflow category name. Discover it in this order:

1. `wecom_mcp list crm`
2. if empty or unavailable, `wecom_mcp list crm.automation`

Use whichever category returns the workflow methods. Call the method names exactly as returned by `list`.

## Workflow Method Mapping

### Registry

Preferred method name:

- `crm.automation.get_workflow_registry`

Example:

```json
{
  "action": "call",
  "category": "crm",
  "method": "crm.automation.get_workflow_registry",
  "args": {}
}
```

Returns at least:

- `audiences`
- `recipient_filter_bases`
- `segmentation_bases`
- `generation_modes`
- `node_trigger_modes`
- `workflow_statuses`

### Workflow List

Preferred method name:

- `crm.automation.list_workflows`

Example args:

```json
{
  "include_archived": false,
  "status": "draft"
}
```

The result should include workflow bundles with:

- workflow metadata
- audiences
- workflow-level agent bindings
- nodes

### Update Workflow

Preferred method name:

- `crm.automation.update_workflow`

Minimum patch payload:

```json
{
  "workflow_id": 12,
  "workflow_name": "新客欢迎流 V2",
  "description": "补充基础信息后的版本。"
}
```

Notes:

- `workflow_id` is required.
- Only send the fields you want to change.
- Split workflow semantics:
  - 发给谁: `recipient_filter_basis` + `recipient_behavior_tier_keys`
  - 怎么发: `content_segmentation_basis` + `content_profile_segment_template_id`
- Legacy `segmentation_basis` remains accepted, but only as the old content-dimension field.
- If you change recipient filter, content segmentation, `generation_mode`, or `audiences`, make sure the existing node structure still remains valid.

### Workflow Nodes

Preferred method name:

- `crm.automation.get_workflow_nodes`

Required args:

```json
{
  "workflow_id": 12
}
```

### Create Workflow

Preferred method name:

- `crm.automation.create_workflow`

Minimum safe payload:

```json
{
  "workflow_name": "新客欢迎流",
  "workflow_code": "welcome_flow",
  "status": "draft",
  "recipient_filter_basis": "none",
  "content_segmentation_basis": "none",
  "generation_mode": "manual_layered",
  "audiences": ["operating"]
}
```

Allowed values:

- `status`: `draft`, `active`, `paused`
- `recipient_filter_basis`: `none`, `behavior`
- `recipient_behavior_tier_keys`: `lt_2`, `between_2_9`, `gte_10`
- `content_segmentation_basis`: `none`, `profile`, `behavior`
- `generation_mode`: `manual_layered`, `auto_layered_rewrite`, `personalized_single`
- `audiences`: `pending_questionnaire`, `operating`, `converted`

Notes:

- `content_profile_segment_template_id` is required only when `content_segmentation_basis = profile`.
- If `recipient_filter_basis = behavior`, `recipient_behavior_tier_keys` must contain at least one tier key.
- `agent_bindings` are required only for non-manual generation modes.
- Legacy payloads may still send `segmentation_basis` / `profile_segment_template_id`; treat them as old content-dimension fields only.

### Create Workflow Node

Preferred method name:

- `crm.automation.create_workflow_node`

Minimum safe payload for an immediate-on-entry text node:

```json
{
  "workflow_id": 12,
  "node_name": "欢迎首触达",
  "node_code": "welcome_touch_1",
  "target_audience_code": "operating",
  "trigger_mode": "audience_entered",
  "content_mode": "standard_direct",
  "standard_content_text": "欢迎加入，我们先带你完成第一步设置。"
}
```

Allowed values:

- `target_audience_code`: must belong to the workflow's audiences
- `trigger_mode`: `scheduled`, `audience_entered`
- `content_mode`: `standard_direct`, `manual_layered`, `standard_layered_rewrite`, `personalized_single`
- `segmentation_basis`: `none`, `profile`, `behavior`

Extra rules:

- If `trigger_mode = scheduled`, both `day_offset` and `send_time` are required.
- If `content_mode = standard_direct`, `standard_content_text` is required.
- If `content_mode = manual_layered`, `content_variants` are required.
- If `content_mode = standard_layered_rewrite` or `personalized_single`, valid `agent_bindings` are required.

### Update Workflow Node

Preferred method name:

- `crm.automation.update_workflow_node`

Minimum patch payload:

```json
{
  "node_id": 34,
  "node_name": "欢迎首触达 V2"
}
```

Notes:

- `node_id` is required.
- Only send the fields you intend to change.
- When switching a node to `standard_direct`, you must also provide `standard_content_text`.
- When switching a node to `manual_layered`, you must also provide valid `content_variants`.
- In inherited modes like `personalized_single`, prefer updating metadata fields first unless you are intentionally changing behavior.

## Practical Call Pattern

When the category is confirmed, the actual proxy invocations should look like:

```json
{
  "action": "call",
  "category": "crm",
  "method": "crm.automation.list_workflows",
  "args": {
    "status": "draft"
  }
}
```

```json
{
  "action": "call",
  "category": "crm",
  "method": "crm.automation.create_workflow_node",
  "args": {
    "workflow_id": 12,
    "node_name": "欢迎首触达",
    "node_code": "welcome_touch_1",
    "target_audience_code": "operating",
    "trigger_mode": "audience_entered",
    "content_mode": "standard_direct",
    "standard_content_text": "欢迎加入，我们先带你完成第一步设置。"
  }
}
```

If `crm` does not expose those methods, retry the same method names under category `crm.automation`.
