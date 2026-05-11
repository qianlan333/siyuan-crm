from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from .application.integration_gateway import DispatchMcpToolCommand
from .application.platform_foundation import AuthorizeInternalRequestQuery, ListMcpRuntimeToolsQuery
from .infra.settings import get_setting

mcp_bp = Blueprint("mcp", __name__)
mcp_logger = logging.getLogger("mcp")


def _check_mcp_auth() -> Response | None:
    expected = str(request.environ.get("mcp_bearer_token_override") or "").strip()
    if not expected:
        expected = str(get_setting("MCP_BEARER_TOKEN") or current_app.config.get("MCP_BEARER_TOKEN") or "").strip()
    if expected:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if not auth_header.startswith("Bearer "):
            return jsonify({"ok": False, "error": "missing internal token"}), 401
        token = auth_header[7:].strip()
        if token != expected:
            return jsonify({"ok": False, "error": "invalid internal token"}), 401
        return None
    return AuthorizeInternalRequestQuery()()


def _jsonrpc_success(request_id: Any, result: dict[str, Any]) -> Response:
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Response:
    return jsonify({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def get_mcp_http_info() -> dict[str, Any]:
    return {
        "ok": True,
        "transport": "streamable-http",
        "mcp_endpoint": "/mcp",
        "server_name": "openclaw-wecom-mcp",
    }


def initialize_mcp_runtime() -> dict[str, Any]:
    return {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "openclaw-wecom-mcp", "version": "1.0.0"},
    }


TOOL_DEFS = [
    {
        "name": "resolve_customer",
        "description": "Resolve customer_ref (mobile or external_userid) to a CRM customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "include_context": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_contact",
        "description": "Read a single contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_customer_context",
        "description": "Read a customer's aggregated CRM context by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_messages",
        "description": "Read full message history for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "get_recent_messages",
        "description": "Read recent messages for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "search_messages",
        "description": "Search messages for a contact by keyword, using customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "keyword": {"type": "string"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_group_chat",
        "description": "Read a group chat by chat_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
            },
            "required": ["chat_id"],
        },
    },
    {
        "name": "mark_tags",
        "description": "Add one or more tags to a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "add_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "add_tag"],
        },
    },
    {
        "name": "unmark_tags",
        "description": "Remove one or more tags from a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "remove_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "remove_tag"],
        },
    },
    {
        "name": "update_customer_tags",
        "description": "Update a customer's tags with customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "userid": {"type": "string"},
                "add_tags": {"type": "array", "items": {"type": "string"}},
                "remove_tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "create_private_message_task",
        "description": "Create a private message task using a simple business input or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_moment_task",
        "description": "Create a moment task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_group_message_task",
        "description": "Create a group message task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "send_pool_private_message",
        "description": "Send one private-message batch directly to one CRM pool. Supports text, images, attachments, or mixed combinations; CRM filters the pool, sends, and writes send records.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_userid": {"type": "string"},
                "pool_key": {
                    "type": "string",
                    "enum": ["new_user", "inactive_normal", "inactive_focus", "active_normal", "active_focus", "silent"],
                },
                "content": {"type": "string"},
                "images": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "file_name": {"type": "string"},
                                    "content_type": {"type": "string"},
                                    "data_url": {"type": "string"},
                                    "data_base64": {"type": "string"},
                                    "media_id": {"type": "string"},
                                },
                            },
                        ]
                    },
                },
                "image_media_ids": {"type": "array", "items": {"type": "string"}},
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "msgtype": {
                                "type": "string",
                                "enum": ["file"],
                            },
                            "file": {"type": "object"},
                        },
                        "required": ["msgtype"],
                    },
                },
                "confirm": {"type": "boolean"},
                "operator": {"type": "string"},
            },
            "required": ["owner_userid", "pool_key", "confirm"],
        },
    },
    {
        "name": "record_conversion_feedback",
        "description": "Persist conversion feedback from OpenClaw; mark_enrolled/unmark_enrolled feedback types also sync unified conversion truth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feedback_type": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_id": {"type": "string"},
                "actor": {"type": "string"},
                "feedback_payload": {"type": "object"},
            },
            "required": ["feedback_type"],
        },
    },
    {
        "name": "get_owner_role_map",
        "description": "Read the owner role mapping used for routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_signup_tag_rules",
        "description": "Read signup tag rules used for pre/post-signup routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_routing_config",
        "description": "Read both owner role map and signup tag rules in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_pending_message_batches",
        "description": "List pending 3-minute message batches for OpenClaw to judge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_message_batch",
        "description": "Fetch a batch with full message payloads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "cursor": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "ack_message_batch",
        "description": "Acknowledge a batch after OpenClaw has consumed it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "ack_note": {"type": "string"},
                "acked_by": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_signup_conversion_batches",
        "description": "List pending message batches that remain eligible for signup-conversion automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_customer_marketing_profile",
        "description": "Read one CRM-organized marketing profile for OpenClaw without combining customer detail manually.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "person_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "get_pending_conversion_batches",
        "description": "List only the pending conversion batches that have router-approved candidates for OpenClaw.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_conversion_batch",
        "description": "Fetch one OpenClaw-ready conversion batch with CRM-organized marketing profiles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "ack_conversion_batch",
        "description": "Acknowledge a conversion batch after OpenClaw has consumed it and stamp acked_at in dispatch logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "ack_note": {"type": "string"},
                "acked_by": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_signup_conversion_batch",
        "description": "Fetch one filtered signup-conversion batch with CRM-organized customer profiles for OpenClaw.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "mark_enrolled",
        "description": "Mark one customer as enrolled through the unified CRM conversion service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "owner_userid": {"type": "string"},
                "operator": {"type": "string"},
                "source": {"type": "string"},
                "signup_status": {"type": "string"},
            },
            "required": ["external_userid"],
        },
    },
    {
        "name": "unmark_enrolled",
        "description": "Undo one enrolled mark and recompute the customer's stage from CRM facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_userid": {"type": "string"},
                "owner_userid": {"type": "string"},
                "operator": {"type": "string"},
                "source": {"type": "string"},
                "restore_signup_status": {"type": "string"},
            },
            "required": ["external_userid"],
        },
    },
    {
        "name": "get_owner_recent_chat_dump",
        "description": "Read recent private/group archived chat dumps for one owner without ranking or recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_userid": {"type": "string"},
                "lookback_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
                "include_private": {"type": "boolean"},
                "include_group": {"type": "boolean"},
            },
            "required": ["owner_userid"],
        },
    },
    {
        "name": "get_hourly_followup_candidates",
        "description": "List the best customers to follow up with right now using simple CRM rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "lookback_hours": {"type": "integer", "minimum": 1, "maximum": 168},
            },
        },
    },
    {
        "name": "crm.get_member_basic",
        "description": "Read one automation-conversion member's basic CRM profile.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
            },
        },
    },
    {
        "name": "crm.get_member_stage",
        "description": "Read one automation-conversion member's current pool/stage state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
            },
        },
    },
    {
        "name": "crm.get_member_questionnaire",
        "description": "Read one automation-conversion member's questionnaire result and matched rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
            },
        },
    },
    {
        "name": "crm.get_member_recent_events",
        "description": "Read one automation-conversion member's recent timeline events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "crm.get_member_recent_outputs",
        "description": "Read one automation-conversion member's recent agent outputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "crm.get_member_snapshot",
        "description": "Read one automation-conversion member's combined CRM snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
            },
        },
    },
    {
        "name": "script.list_items",
        "description": "List Lobster-editable script items backed by child agent configs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
        },
    },
    {
        "name": "script.get_item",
        "description": "Read one script item backed by a child agent config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "script.search_items",
        "description": "Search script items by keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "script.create_draft",
        "description": "Create or refresh a script draft without publishing it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "from_version": {"type": "string", "enum": ["published", "draft"]},
                "change_summary": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "script.update_draft",
        "description": "Update one script draft without publishing it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "display_name": {"type": "string"},
                "enabled": {"type": "boolean"},
                "role_prompt": {"type": "string"},
                "task_prompt": {"type": "string"},
                "variables": {"type": "array"},
                "output_schema": {"type": "array"},
                "change_summary": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "script.diff_draft",
        "description": "Compare one script draft against the current published version.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "script.submit_for_publish",
        "description": "Submit one script draft for manual publish review without publishing it directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "change_summary": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "script.list_drafts",
        "description": "List script drafts, optionally only the ones that differ from published versions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "changed_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "crm.automation.get_workflow_registry",
        "description": "Read the workflow registry used by CRM automation conversion, including allowed audiences, trigger modes, segmentation bases, and generation modes.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "crm.automation.list_workflows",
        "description": "List CRM automation-conversion workflows. Each workflow bundle includes its nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_archived": {"type": "boolean"},
                "status": {"type": "string", "enum": ["draft", "active", "paused"]},
            },
        },
    },
    {
        "name": "crm.automation.get_workflow_nodes",
        "description": "List all nodes under one CRM automation-conversion workflow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "integer"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "crm.automation.create_workflow",
        "description": "Create one CRM automation-conversion workflow draft. Supports split dimensions for recipient filtering and content segmentation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string"},
                "workflow_code": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "active", "paused"]},
                "recipient_filter_basis": {"type": "string", "enum": ["none", "behavior"]},
                "recipient_behavior_tier_keys": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["lt_2", "between_2_9", "gte_10"]},
                },
                "content_segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "content_profile_segment_template_id": {"type": "integer", "minimum": 1},
                "segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "generation_mode": {
                    "type": "string",
                    "enum": ["manual_layered", "auto_layered_rewrite", "personalized_single"],
                },
                "profile_segment_template_id": {"type": "integer", "minimum": 1},
                "fallback_to_standard_content": {"type": "boolean"},
                "audiences": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["pending_questionnaire", "operating", "converted"],
                    },
                },
                "agent_bindings": {"type": "array", "items": {"type": "object"}},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["workflow_name", "audiences"],
        },
    },
    {
        "name": "crm.automation.create_workflow_node",
        "description": "Create one node under a CRM automation-conversion workflow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "integer"},
                "node_name": {"type": "string"},
                "node_code": {"type": "string"},
                "target_audience_code": {
                    "type": "string",
                    "enum": ["pending_questionnaire", "operating", "converted"],
                },
                "trigger_mode": {"type": "string", "enum": ["scheduled", "daily_recurring", "audience_entered"]},
                "day_offset": {"type": "integer", "minimum": 1},
                "send_time": {"type": "string"},
                "timezone": {"type": "string"},
                "position_index": {"type": "integer", "minimum": 0},
                "enabled": {"type": "boolean"},
                "content_mode": {
                    "type": "string",
                    "enum": ["standard_direct", "manual_layered", "standard_layered_rewrite", "personalized_single"],
                },
                "segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "standard_content_text": {"type": "string"},
                "standard_content_payload": {"type": "object"},
                "fallback_to_standard_content": {"type": "boolean"},
                "content_variants": {"type": "array", "items": {"type": "object"}},
                "agent_bindings": {"type": "array", "items": {"type": "object"}},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["workflow_id", "node_name", "target_audience_code"],
        },
    },
    {
        "name": "crm.automation.update_workflow",
        "description": "Update one existing CRM automation-conversion workflow. Supports split dimensions for recipient filtering and content segmentation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "integer"},
                "workflow_name": {"type": "string"},
                "workflow_code": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "active", "paused"]},
                "recipient_filter_basis": {"type": "string", "enum": ["none", "behavior"]},
                "recipient_behavior_tier_keys": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["lt_2", "between_2_9", "gte_10"]},
                },
                "content_segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "content_profile_segment_template_id": {"type": "integer", "minimum": 1},
                "segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "generation_mode": {
                    "type": "string",
                    "enum": ["manual_layered", "auto_layered_rewrite", "personalized_single"],
                },
                "profile_segment_template_id": {"type": "integer", "minimum": 1},
                "fallback_to_standard_content": {"type": "boolean"},
                "audiences": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["pending_questionnaire", "operating", "converted"],
                    },
                },
                "agent_bindings": {"type": "array", "items": {"type": "object"}},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "crm.automation.update_workflow_node",
        "description": "Update one existing node under a CRM automation-conversion workflow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer"},
                "node_name": {"type": "string"},
                "node_code": {"type": "string"},
                "target_audience_code": {
                    "type": "string",
                    "enum": ["pending_questionnaire", "operating", "converted"],
                },
                "trigger_mode": {"type": "string", "enum": ["scheduled", "daily_recurring", "audience_entered"]},
                "day_offset": {"type": "integer", "minimum": 1},
                "send_time": {"type": "string"},
                "timezone": {"type": "string"},
                "position_index": {"type": "integer", "minimum": 0},
                "enabled": {"type": "boolean"},
                "content_mode": {
                    "type": "string",
                    "enum": ["standard_direct", "manual_layered", "standard_layered_rewrite", "personalized_single"],
                },
                "segmentation_basis": {"type": "string", "enum": ["none", "profile", "behavior"]},
                "standard_content_text": {"type": "string"},
                "standard_content_payload": {"type": "object"},
                "fallback_to_standard_content": {"type": "boolean"},
                "content_variants": {"type": "array", "items": {"type": "object"}},
                "agent_bindings": {"type": "array", "items": {"type": "object"}},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "get_pool_snapshot",
        "description": "Read a pool/stage snapshot for automation conversion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pool_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["pool_key"],
        },
    },
    {
        "name": "list_agent_configs",
        "description": "List all child agent configurations without including the central router webhook config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled_only": {"type": "boolean"},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "create_agent_config",
        "description": "Create a new child agent draft configuration without publishing it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "display_name": {"type": "string"},
                "enabled": {"type": "boolean"},
                "role_prompt": {"type": "string"},
                "task_prompt": {"type": "string"},
                "enabled_context_sources": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["questionnaire", "recent_messages", "user_tags", "activation_info"],
                    },
                },
                "variables": {"type": "array"},
                "output_schema": {"type": "array"},
                "change_summary": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code", "display_name", "role_prompt", "task_prompt"],
        },
    },
    {
        "name": "get_agent_config",
        "description": "Read one child agent's draft/published configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "get_all_agent_prompts",
        "description": "Read all child agent prompts at once, split into role_prompt, task_prompt, variables, and output_schema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled_only": {"type": "boolean"},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "save_agent_prompt_draft",
        "description": "Save one child agent's draft configuration without publishing. Supports partial field patching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "patch": {"type": "object"},
                "display_name": {"type": "string"},
                "enabled": {"type": "boolean"},
                "role_prompt": {"type": "string"},
                "task_prompt": {"type": "string"},
                "enabled_context_sources": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["questionnaire", "recent_messages", "user_tags", "activation_info"],
                    },
                },
                "variables": {"type": "array"},
                "output_schema": {"type": "array"},
                "change_summary": {"type": "string"},
                "expected_draft_version": {"type": "integer", "minimum": 1},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "diff_agent_prompt",
        "description": "Compare one child agent's draft and published prompt configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "submit_agent_prompt_for_publish",
        "description": "Submit one child agent draft for manual publish review without publishing it directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "change_summary": {"type": "string"},
                "expected_draft_version": {"type": "integer", "minimum": 1},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent_code"],
        },
    },
    {
        "name": "list_pending_agent_prompt_publish_requests",
        "description": "List child-agent drafts that either have unpublished changes or have already been submitted for manual publish review.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_code": {"type": "string"},
                "enabled_only": {"type": "boolean"},
                "page": {"type": "integer", "minimum": 1, "maximum": 100000},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "request_id": {"type": "string"},
                "operator": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "list_agent_outputs",
        "description": "Query the unified agent output ledger with filters and pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "page": {"type": "integer", "minimum": 1, "maximum": 100000},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "get_agent_output",
        "description": "Read one agent output record plus its run context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_id": {"type": "string"},
            },
            "required": ["output_id"],
        },
    },
    {
        "name": "get_agent_outputs_by_request",
        "description": "Read agent outputs by request_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
            },
            "required": ["request_id"],
        },
    },
    {
        "name": "get_agent_outputs_by_user",
        "description": "Read recent agent outputs by external_contact_id or userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["userid"],
        },
    },
    {
        "name": "export_agent_outputs",
        "description": "Create an Excel export job for agent outputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "requested_by": {"type": "string"},
            },
        },
    },
    {
        "name": "suggest_pool_action",
        "description": "Return a safe pool-action suggestion for one member without applying it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "external_contact_id": {"type": "string"},
                "phone": {"type": "string"},
                "operator": {"type": "string"},
            },
        },
    },
]


def _build_cloud_orchestrator_tool_defs() -> list[dict[str, Any]]:
    """Cloud 编排端 tool 集 — 在 TOOL_DEFS 末尾追加，让 MCP 列表透出"""
    try:
        from .domains.cloud_orchestrator import mcp_tools as cloud_mcp_tools
    except Exception:  # pragma: no cover - defensive import
        return []
    out: list[dict[str, Any]] = []
    for spec in cloud_mcp_tools.list_cloud_tool_specs():
        side_effect = spec.get("side_effect", "read")
        description = spec.get("description", "")
        if side_effect == "write":
            description = "[WRITE - 需要 approval_token] " + description
        elif side_effect == "draft":
            description = "[DRAFT - 不发送] " + description
        elif side_effect == "async_write":
            description = "[ASYNC] " + description
        out.append(
            {
                "name": spec["name"],
                "description": description,
                "inputSchema": spec.get("input_schema") or {"type": "object", "properties": {}},
            }
        )
    return out


def _build_image_library_tool_defs() -> list[dict[str, Any]]:
    """图片素材库 tool 集 — 给外部 Skill 通过 MCP 读写图片元数据。

    不像 cloud_orchestrator 那样需要 approval_token；写操作（update_metadata /
    upload）只标 ``[WRITE]`` 提示而不强制 token 校验，因为图片库不涉及客户外
    发或 production 表写入，AI 自由打标的成本可控。
    """
    try:
        from .domains.image_library import mcp_tools as image_library_mcp_tools
    except Exception:  # pragma: no cover - defensive import
        return []
    out: list[dict[str, Any]] = []
    for spec in image_library_mcp_tools.list_image_library_tool_specs():
        side_effect = spec.get("side_effect", "read")
        description = spec.get("description", "")
        if side_effect == "write":
            description = "[WRITE] " + description
        out.append(
            {
                "name": spec["name"],
                "description": description,
                "inputSchema": spec.get("input_schema") or {"type": "object", "properties": {}},
            }
        )
    return out


TOOL_DEFS.extend(_build_cloud_orchestrator_tool_defs())
TOOL_DEFS.extend(_build_image_library_tool_defs())


def _is_cloud_orchestrator_tool(name: str) -> bool:
    try:
        from .domains.cloud_orchestrator import mcp_tools as cloud_mcp_tools
    except Exception:
        return False
    return any(t["name"] == name for t in cloud_mcp_tools.list_cloud_tool_specs())


def _is_image_library_tool(name: str) -> bool:
    try:
        from .domains.image_library import mcp_tools as image_library_mcp_tools
    except Exception:
        return False
    return any(
        t["name"] == name for t in image_library_mcp_tools.list_image_library_tool_specs()
    )


def execute_mcp_tool_runtime(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Legacy-compatible MCP runtime delegate that now routes through application dispatch."""
    if _is_cloud_orchestrator_tool(name):
        from .domains.cloud_orchestrator import audit, mcp_tools as cloud_mcp_tools

        args = arguments or {}
        # 调用方可在 args 里夹 trace_id / session_id / operator；缺失则现生成
        trace_id = str(args.pop("__trace_id", "") or audit.new_trace_id("mcp"))
        session_id = str(args.pop("__session_id", "") or audit.new_session_id())
        operator = str(args.pop("__operator", "") or "mcp_caller")
        result = cloud_mcp_tools.dispatch_cloud_tool(
            tool_name=name,
            arguments=args,
            session_id=session_id,
            trace_id=trace_id,
            operator=operator,
        )
        return {
            "ok": True,
            "tool": name,
            "trace_id": trace_id,
            "session_id": session_id,
            "result": result,
        }

    if _is_image_library_tool(name):
        from .domains.image_library import mcp_tools as image_library_mcp_tools

        result = image_library_mcp_tools.dispatch_image_library_tool(
            tool_name=name,
            arguments=arguments or {},
        )
        # dispatch_image_library_tool 已经返回 ``{"ok": ..., ...}`` 形态，
        # 直接透传给 MCP 客户端，连同 tool 名一起带回方便调用方做日志关联。
        return {"tool": name, **result}

    return DispatchMcpToolCommand()(name, arguments)


@mcp_bp.route("/mcp", methods=["GET", "POST"])
def streamable_http_mcp():
    auth_error = _check_mcp_auth()
    if auth_error is not None:
        return auth_error
    if request.method == "GET":
        return jsonify(get_mcp_http_info())

    payload = request.get_json(silent=True) or {}
    request_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}
    mcp_logger.info("mcp method=%s", method)

    try:
        if method == "initialize":
            return _jsonrpc_success(request_id, initialize_mcp_runtime())
        if method == "notifications/initialized":
            return Response(status=204)
        if method == "tools/list":
            return _jsonrpc_success(request_id, {"tools": ListMcpRuntimeToolsQuery()()})
        if method == "tools/call":
            result = execute_mcp_tool_runtime(params.get("name", ""), params.get("arguments") or {})
            return _jsonrpc_success(request_id, result)
        if method == "ping":
            return _jsonrpc_success(request_id, {})
        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        mcp_logger.exception("mcp call failed method=%s", method)
        return _jsonrpc_error(request_id, -32000, str(exc))
