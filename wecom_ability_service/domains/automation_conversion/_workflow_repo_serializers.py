"""Row deserialization helpers for workflow_repo (阶段 6.1).

Extracted from workflow_repo.py. External callers keep using
``automation_conversion.workflow_repo.X``.
"""

from __future__ import annotations

from typing import Any

from ._repo_helpers import (  # noqa: F401
    _json_loads,
    _normalized_text,
    _row_bool,
)


def _serialize_profile_segment_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "program_id": int(row.get("program_id") or 0) or None,
        "questionnaire_id": int(row.get("questionnaire_id") or 0) or None,
        "segmentation_question_id": int(row.get("segmentation_question_id") or 0) or None,
        "enabled": _row_bool(row.get("enabled")),
        "version": int(row.get("version") or 1),
    }


def _serialize_profile_segment_category_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
        "sort_order": int(row.get("sort_order") or 0),
    }


def _serialize_profile_segment_option_mapping_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "template_id": int(row.get("template_id") or 0),
        "category_id": int(row.get("category_id") or 0),
        "question_id": int(row.get("question_id") or 0),
        "option_id": int(row.get("option_id") or 0),
    }


def _serialize_workflow_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "program_id": int(row.get("program_id") or 0) or None,
        "profile_segment_template_id": int(row.get("profile_segment_template_id") or 0) or None,
        "enabled": _row_bool(row.get("enabled")),
        "fallback_to_standard_content": _row_bool(row.get("fallback_to_standard_content")),
    }


def _serialize_workflow_audience_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "workflow_id": int(row.get("workflow_id") or 0),
    }


def _serialize_workflow_agent_binding_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "workflow_id": int(row.get("workflow_id") or 0),
        "node_id": int(row.get("node_id") or 0) or None,
    }


def _serialize_workflow_node_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "workflow_id": int(row.get("workflow_id") or 0),
        "day_offset": int(row.get("day_offset") or 1),
        "trigger_mode": _normalized_text(row.get("trigger_mode")) or "scheduled",
        "position_index": int(row.get("position_index") or 0),
        "enabled": _row_bool(row.get("enabled")),
    }


def _serialize_member_audience_entry_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "member_id": int(row.get("member_id") or 0),
        "is_current": _row_bool(row.get("is_current")),
        "source_snapshot_json": _json_loads(row.get("source_snapshot_json"), default={}),
    }


def _serialize_automation_member_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": int(row.get("id") or 0),
        "master_customer_id": int(row.get("master_customer_id") or 0) or None,
        "in_pool": _row_bool(row.get("in_pool")),
        "customer_name": _normalized_text(row.get("customer_name")),
        "profile_segment_key": _normalized_text(row.get("profile_segment_key")),
        "behavior_tier_key": _normalized_text(row.get("behavior_tier_key")),
        "segment_refreshed_at": _normalized_text(row.get("segment_refreshed_at")),
    }


def _serialize_customer_marketing_state_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "person_id": int(row.get("person_id") or 0) or None,
        "activated": _row_bool(row.get("activated")),
        "converted": _row_bool(row.get("converted")),
        "eligible_for_conversion": _row_bool(row.get("eligible_for_conversion")),
        "state_payload_json": _json_loads(row.get("state_payload_json"), default={}),
    }


def _serialize_node_content_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "node_id": int(row.get("node_id") or 0),
        "fallback_to_standard_content": _row_bool(row.get("fallback_to_standard_content")),
        "standard_content_payload_json": _json_loads(row.get("standard_content_payload_json"), default={}),
    }


def _serialize_node_content_variant_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "node_content_id": int(row.get("node_content_id") or 0),
        "content_payload_json": _json_loads(row.get("content_payload_json"), default={}),
    }


def _serialize_workflow_execution_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "program_id": int(row.get("program_id") or 0) or None,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def _serialize_workflow_execution_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "content_snapshot_json": _json_loads(row.get("content_snapshot_json"), default={}),
    }




__all__ = [
    "_serialize_automation_member_row",
    "_serialize_customer_marketing_state_row",
    "_serialize_member_audience_entry_row",
    "_serialize_node_content_row",
    "_serialize_node_content_variant_row",
    "_serialize_profile_segment_category_row",
    "_serialize_profile_segment_option_mapping_row",
    "_serialize_profile_segment_template_row",
    "_serialize_workflow_agent_binding_row",
    "_serialize_workflow_audience_row",
    "_serialize_workflow_execution_item_row",
    "_serialize_workflow_execution_row",
    "_serialize_workflow_node_row",
    "_serialize_workflow_row",
]
