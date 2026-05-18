from __future__ import annotations

from flask import current_app, jsonify, request

from ..domains.automation_conversion import member_segment_search_service
from ..domains.automation_conversion.manual_send_service import send_stage_manual_message
from ._routes_helpers import _operator_from_request
from .internal_auth import validate_admin_console_action_token


def _segment_broadcast_payload() -> dict:
    payload = request.get_json(silent=True) if request.is_json else None
    return dict(payload or {}) if isinstance(payload, dict) else {}


def _request_segment_broadcast_keys(field: str, payload: dict | None = None) -> list[str]:
    """Read multi-select keys from JSON body (preferred) or form/query."""
    payload = _segment_broadcast_payload() if payload is None else payload
    if isinstance(payload, dict):
        raw = payload.get(field) or payload.get(f"{field}[]")
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str) and raw.strip():
            return [raw.strip()]
    raw_list = request.values.getlist(field) or request.values.getlist(f"{field}[]")
    return [str(item).strip() for item in raw_list if str(item).strip()]


def _request_segment_broadcast_keyword(payload: dict | None = None) -> str:
    payload = _segment_broadcast_payload() if payload is None else payload
    if isinstance(payload, dict) and payload.get("keyword") is not None:
        return str(payload.get("keyword") or "").strip()
    return str(request.values.get("keyword") or "").strip()


def api_admin_automation_program_member_segment_search(program_id: int):
    """List members by multi-dim segment filter + return chip metadata."""
    pool_keys = _request_segment_broadcast_keys("pool_keys")
    profile_keys = _request_segment_broadcast_keys("profile_keys")
    behavior_keys = _request_segment_broadcast_keys("behavior_keys")
    keyword = _request_segment_broadcast_keyword()
    page = int(request.values.get("page") or 1)
    page_size = int(request.values.get("page_size") or 50)
    try:
        from ..domains.automation_conversion import workflow_service as _ws

        _ws._build_dashboard_audience_member_details(program_id=int(program_id or 0) or None)
    except Exception:
        pass
    try:
        result = member_segment_search_service.search_members(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
            page=page,
            page_size=page_size,
            program_id=program_id,
        )
        metadata = member_segment_search_service.get_dimension_metadata(
            program_id=program_id,
        )
    except Exception as exc:
        current_app.logger.exception(
            "segment search failed: program_id=%s", program_id
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "metadata": metadata, **result})


def api_admin_automation_program_member_segment_broadcast(program_id: int):
    """Broadcast to the multi-dim filtered audience via the unified send pipeline."""
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) if request.is_json else None
    if not isinstance(payload, dict):
        payload = {}
    pool_keys = _request_segment_broadcast_keys("pool_keys")
    profile_keys = _request_segment_broadcast_keys("profile_keys")
    behavior_keys = _request_segment_broadcast_keys("behavior_keys")
    keyword = _request_segment_broadcast_keyword()
    content = str(payload.get("content") or request.values.get("content") or "").strip()
    images = list(payload.get("images") or [])
    try:
        broadcast_targets = member_segment_search_service.list_broadcast_targets(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
            program_id=program_id,
        )
        snapshot = member_segment_search_service.filter_snapshot(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
        )
        result = send_stage_manual_message(
            members=broadcast_targets,
            filter_snapshot=snapshot,
            skip_delivery_tracking=True,
            content=content,
            images=images,
            operator_id=_operator_from_request(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception(
            "segment broadcast failed: program_id=%s", program_id
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(result)
