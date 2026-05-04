---
name: lobster-crm-automation-workflows
description: Use when Lobster needs to inspect, create, or update CRM automation-conversion workflows and workflow nodes through the `wecom_mcp` proxy. Covers listing all workflows, reading workflow nodes, creating new workflows, adding new workflow nodes, and modifying existing workflow metadata or node metadata without relying on native `crm.automation.*` tools.
---

# Lobster CRM Automation Workflows

This skill is for Lobster to operate the CRM automation-conversion workflow workspace through the `wecom_mcp` proxy tool.

Do not assume native `crm.automation.*` tools are visible in the current session. Use `wecom-preflight` plus `wecom_mcp list/call` instead.

## Use This Skill For

- 查看全部任务流
- 查看某个任务流下的全部节点
- 新增任务流
- 在已有任务流下新增节点
- 修改已有任务流
- 修改已有任务流节点

## Workflow

1. Before the first `wecom_mcp` call in a session, run the `wecom-preflight` skill.
2. Discover the usable CRM MCP category before doing workflow operations:
   - First try `wecom_mcp list crm`
   - If that category is empty or unavailable, try `wecom_mcp list crm.automation`
3. Use the category that returns workflow tools. Call methods through `wecom_mcp call <category> <method> <args>`.
4. Do not guess method names. Prefer the exact method names returned by `wecom_mcp list <category>`.
5. When the category lists the workflow methods, use this mapping:
   - registry lookup: `crm.automation.get_workflow_registry`
   - workflow listing: `crm.automation.list_workflows`
   - node listing: `crm.automation.get_workflow_nodes`
   - workflow creation: `crm.automation.create_workflow`
   - node creation: `crm.automation.create_workflow_node`
   - workflow update: `crm.automation.update_workflow`
   - node update: `crm.automation.update_workflow_node`
6. To create a node, first confirm the target workflow exists.
7. To update an existing workflow or node, first read the current object, then send a minimal patch payload instead of rewriting fields you do not intend to change.

## Operating Rules

- Prefer creating workflows in `draft` status unless the user explicitly asks to activate them immediately.
- Treat workflow config as two independent dimensions:
  - `recipient_filter_basis` / `recipient_behavior_tier_keys` = 发给谁
  - `content_segmentation_basis` / `content_profile_segment_template_id` = 怎么发
- Legacy `segmentation_basis` is still accepted for compatibility, but it is old syntax for the content dimension only. Do not use it as “发给谁”.
- Do not invent `content_profile_segment_template_id` or `agent_bindings`. If the user has not provided them, default to the simplest valid workflow:
  - `recipient_filter_basis = none`
  - `content_segmentation_basis = none`
  - `generation_mode = manual_layered`
- When creating a node, do not invent a `target_audience_code`. It must already belong to the workflow audiences.
- If the user does not provide schedule details, prefer `trigger_mode = audience_entered`.
- For `standard_direct` nodes, always provide `standard_content_text`.
- For updates, prefer changing only the explicitly requested fields. Do not silently rewrite schedule, audience, or generation mode.
- If the create call fails with a validation error, surface the exact constraint and adjust the payload instead of guessing silently.
- If the first guessed category fails, retry with the other candidate category before concluding the workflow tools are unavailable.

## Response Style

- When listing workflows, summarize each workflow with:
  - `workflow_id`
  - `workflow_code`
  - `workflow_name`
  - `status`
  - node count
- When creating a workflow or node, always report the created IDs and codes.
- When updating a workflow or node, always report the updated ID plus the fields that actually changed.

## References

- See [tools.md](references/tools.md) for `wecom_mcp` discovery flow, category fallback, and minimal payloads.
