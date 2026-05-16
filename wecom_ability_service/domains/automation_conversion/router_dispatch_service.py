from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import requests

from ...db import get_db
from . import orchestration_service as orchestration_seams
from . import repo
from .orchestration_service import (
    _REPLY_OUTPUT_TYPES,
    _REVIEW_DECISIONS,
    _ROUTER_ACK_HTTP_STATUS,
    _append_child_agent_reply_output,
    _append_router_callback_rejected_output,
    _append_router_event_output,
    _apply_router_decision,
    _deserialize_json_object_text,
    _iso_now,
    _latest_request_output,
    _normalize_float,
    _normalize_json_dict,
    _normalized_text,
    _resolve_request_run,
    _router_allowed_target_pools,
    _router_decision_target_pool,
    _router_fallback_payload,
    _router_message_entry,
    _router_runtime_strategy,
    _router_signature_headers,
    _serialize_agent_output,
    _should_generate_child_reply,
    _touch_router_runtime_status,
    _validated_router_callback_payload,
    create_agent_run,
    ensure_agent_orchestration_defaults,
    update_agent_run_status,
)


def validate_router_callback_signature(*, body_text: str, headers: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Internal router owner for callback signature validation."""

    ensure_agent_orchestration_defaults()
    router_config = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    secret = _normalized_text(router_config.get("signature_secret"))
    if not secret:
        return True, ""
    header_name = _normalized_text(router_config.get("signature_header")) or "X-Lobster-Signature"
    provided_signature = _normalized_text((headers or {}).get(header_name))
    if not provided_signature:
        return False, "missing callback signature"
    expected_signature = (
        f"sha256={hmac.new(secret.encode('utf-8'), body_text.encode('utf-8'), hashlib.sha256).hexdigest()}"
    )
    if not hmac.compare_digest(provided_signature, expected_signature):
        return False, "invalid callback signature"
    return True, ""


def backfill_missing_child_agent_replies(
    *,
    operator_id: str,
    request_id: str = "",
    external_contact_id: str = "",
    limit: int = 200,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Internal router owner for historical child-reply backfill."""

    ensure_agent_orchestration_defaults()
    filters: dict[str, Any] = {"output_type": "route_decision"}
    if _normalized_text(request_id):
        filters["request_id"] = _normalized_text(request_id)
    if _normalized_text(external_contact_id):
        filters["external_contact_id"] = _normalized_text(external_contact_id)

    route_rows = [
        repo.deserialize_agent_output_row(item)
        for item in repo.list_agent_output_rows(filters=filters, limit=max(1, int(limit or 200)), offset=0)
    ]
    results: list[dict[str, Any]] = []
    created_count = 0
    skipped_count = 0
    failed_count = 0
    seen_request_ids: set[str] = set()

    for route_output in route_rows:
        current_request_id = _normalized_text(route_output.get("request_id"))
        if current_request_id in seen_request_ids:
            skipped_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": _normalized_text(route_output.get("external_contact_id")),
                    "status": "skipped",
                    "reason": "duplicate_route_decision_for_request",
                }
            )
            continue
        if current_request_id:
            seen_request_ids.add(current_request_id)
        decision_payload = dict(route_output.get("normalized_output_json") or {})
        current_agent_code = _normalized_text(decision_payload.get("agent_code") or route_output.get("target_agent_code"))
        current_external_contact_id = _normalized_text(route_output.get("external_contact_id"))
        current_target_pool = _normalized_text(decision_payload.get("target_pool") or route_output.get("target_pool"))
        current_reason = _normalized_text(decision_payload.get("reason") or route_output.get("reason"))
        current_confidence = _normalize_float(decision_payload.get("confidence") or route_output.get("confidence"), default=0.0)
        current_need_human_review = bool(decision_payload.get("need_human_review") or route_output.get("need_human_review"))
        current_userid = _normalized_text(route_output.get("userid"))

        if not current_request_id or not current_external_contact_id:
            skipped_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "status": "skipped",
                    "reason": "missing_request_or_member",
                }
            )
            continue
        if not _should_generate_child_reply(current_agent_code):
            skipped_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "agent_code": current_agent_code,
                    "status": "skipped",
                    "reason": "non_child_agent_or_non_reply_pool",
                }
            )
            continue
        existing_reply = repo.get_latest_agent_output_row_by_request_id(
            current_request_id,
            output_types=["agent_reply_draft", "agent_reply_final"],
        )
        if existing_reply:
            skipped_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "agent_code": current_agent_code,
                    "status": "skipped",
                    "reason": "reply_output_exists",
                    "output_id": _normalized_text((existing_reply or {}).get("output_id")),
                }
            )
            continue

        prebuilt_reply_draft = _normalized_text(
            decision_payload.get("reply_draft")
            or decision_payload.get("draft_reply")
            or ((decision_payload.get("structured_result") or {}).get("reply_draft") if isinstance(decision_payload.get("structured_result"), dict) else "")
            or ((decision_payload.get("structured_result") or {}).get("draft_reply") if isinstance(decision_payload.get("structured_result"), dict) else "")
        )
        prebuilt_reply_final = _normalized_text(
            decision_payload.get("reply_final")
            or decision_payload.get("final_reply")
            or ((decision_payload.get("structured_result") or {}).get("reply_final") if isinstance(decision_payload.get("structured_result"), dict) else "")
            or ((decision_payload.get("structured_result") or {}).get("final_reply") if isinstance(decision_payload.get("structured_result"), dict) else "")
        )

        if dry_run:
            created_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "agent_code": current_agent_code,
                    "target_pool": current_target_pool,
                    "status": "would_create",
                    "source": "prebuilt_reply" if (prebuilt_reply_draft or prebuilt_reply_final) else "llm_backfill",
                }
            )
            continue

        try:
            if prebuilt_reply_draft or prebuilt_reply_final:
                generated = _append_child_agent_reply_output(
                    run_id=_normalized_text(route_output.get("run_id")) or f"arun-{uuid.uuid4().hex}",
                    request_id=current_request_id,
                    userid=current_userid,
                    external_contact_id=current_external_contact_id,
                    agent_code=current_agent_code,
                    target_pool=current_target_pool,
                    confidence=current_confidence,
                    reason=current_reason,
                    need_human_review=current_need_human_review,
                    next_action=_normalized_text(decision_payload.get("next_action")),
                    reply_draft=prebuilt_reply_draft,
                    reply_final=prebuilt_reply_final,
                    source=f"history_backfill:{operator_id}",
                    prompt_version_used=_normalized_text(decision_payload.get("prompt_version_used")),
                    mcp_tools_used=list(decision_payload.get("mcp_tools_used") or []),
                    structured_result=_normalize_json_dict(decision_payload.get("structured_result")),
                    applied_status="generated",
                )
            else:
                # Keep the monkeypatch seam on orchestration_service._generate_child_agent_reply_output.
                generated = orchestration_seams._generate_child_agent_reply_output(
                    request_id=current_request_id,
                    userid=current_userid,
                    external_contact_id=current_external_contact_id,
                    agent_code=current_agent_code,
                    target_pool=current_target_pool,
                    reason=current_reason,
                    confidence=current_confidence,
                    need_human_review=current_need_human_review,
                    structured_result=_normalize_json_dict(decision_payload.get("structured_result")),
                    generation_source=f"history_backfill:{operator_id}",
                )
            if _normalized_text(generated.get("output_type")) not in {"agent_reply_draft", "agent_reply_final"}:
                failed_count += 1
                results.append(
                    {
                        "request_id": current_request_id,
                        "external_contact_id": current_external_contact_id,
                        "agent_code": current_agent_code,
                        "status": "failed",
                        "reason": "reply_generation_not_created",
                        "output_type": _normalized_text(generated.get("output_type")),
                    }
                )
                continue
            created_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "agent_code": current_agent_code,
                    "target_pool": current_target_pool,
                    "status": "created",
                    "output_id": _normalized_text(generated.get("output_id")),
                    "output_type": _normalized_text(generated.get("output_type")),
                }
            )
        except Exception as exc:
            failed_count += 1
            results.append(
                {
                    "request_id": current_request_id,
                    "external_contact_id": current_external_contact_id,
                    "agent_code": current_agent_code,
                    "status": "failed",
                    "reason": str(exc),
                }
            )

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "operator_id": _normalized_text(operator_id),
        "scanned_count": len(route_rows),
        "created_count": created_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "items": results,
    }


def run_agent_router_shadow_decision(
    *,
    external_contact_id: str,
    owner_userid: str = "",
    batch_id: str = "",
    source: str = "reply_monitor",
    recent_messages: list[dict[str, Any]] | None = None,
    member_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal router owner for async router ingress/shadow dispatch."""

    ensure_agent_orchestration_defaults()
    router_config = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    if not bool(router_config.get("enabled")) or not _normalized_text(router_config.get("webhook_url")):
        return {"ok": False, "status": "shadow_disabled", "shadow_called": False}
    member_row = repo.get_member_by_external_contact_id(_normalized_text(external_contact_id))
    detail = member_detail or {
        "profile": {
            "owner_staff_id": _normalized_text((member_row or {}).get("owner_staff_id")),
        },
        "member_exists": bool(member_row),
    }
    if not bool(detail.get("member_exists")) and not member_row:
        return {"ok": False, "status": "member_not_found", "shadow_called": False}
    owner_value = (
        _normalized_text(owner_userid)
        or _normalized_text((detail.get("profile") or {}).get("owner_staff_id"))
        or _normalized_text((member_row or {}).get("owner_staff_id"))
    )
    now_text = _iso_now()
    request_id = f"router-shadow-{uuid.uuid4().hex}"
    run_id = f"arun-{uuid.uuid4().hex}"
    history_messages = list(
        recent_messages
        # Keep the orchestration/service facade seam so callers get the default
        # archive group-chat loader and tests can monkeypatch the legacy path.
        or orchestration_seams.get_recent_messages_by_user(external_contact_id, limit=20)
    )
    request_payload = {
        "request_id": request_id,
        "external_contact_id": _normalized_text(external_contact_id),
        "recent_messages": [_router_message_entry(item, external_contact_id=external_contact_id) for item in history_messages[:20]],
    }
    variables_snapshot = {
        "lobster_mcp_mode": True,
        "input_protocol_version": "lobster-shadow-ingress-async-v3",
        "recent_messages_count": len(request_payload["recent_messages"]),
    }
    create_agent_run(
        {
            "run_id": run_id,
            "request_id": request_id,
            "batch_id": _normalized_text(batch_id),
            "userid": owner_value,
            "external_contact_id": _normalized_text(external_contact_id),
            "agent_code": "central_router_agent",
            "agent_type": "router",
            "provider": "lobster_shadow",
            "input_snapshot": request_payload,
            "variables_snapshot": variables_snapshot,
            "final_prompt_preview": "shadow_router_ingress_webhook",
            "role_prompt_version": "router-webhook",
            "task_prompt_version": "lobster-shadow-ingress-async-v3",
            "status": "queued",
            "source": source,
        }
    )
    _append_router_event_output(
        run_id=run_id,
        request_id=request_id,
        userid=owner_value,
        external_contact_id=_normalized_text(external_contact_id),
        output_type="route_ingress_sent",
        raw_output_text=json.dumps(request_payload, ensure_ascii=False),
        normalized_output=request_payload,
        rendered_output_text="router ingress queued",
        applied_status="queued",
        reason="router ingress queued",
    )
    started_at = time.perf_counter()
    body_text = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
    headers = _router_signature_headers(router_config, body_text=body_text, created_at=now_text)
    timeout_seconds = max(1, int(router_config.get("timeout_seconds") or 8))
    retry_count = max(0, int(router_config.get("retry_count") or 1))
    response_text = ""

    from ...infra.http_client import OutboundHttpError, get_outbound_client

    try:
        client = get_outbound_client(
            "automation_router_webhook",
            timeout=float(timeout_seconds),
            retry_max=retry_count,
        )
        try:
            response = client.post(
                _normalized_text(router_config.get("webhook_url")),
                data=body_text.encode("utf-8"),
                headers=headers,
            )
        except OutboundHttpError as exc:
            original_message = str(exc.cause) if exc.cause else str(exc)
            raise requests.RequestException(original_message) from exc
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if response is None:
            raise requests.RequestException("router webhook request_error")
        response_text = _normalized_text(response.text)
        if int(response.status_code) != _ROUTER_ACK_HTTP_STATUS:
            raise requests.RequestException(response_text or f"http_status_{int(response.status_code)}")

        update_agent_run_status(
            run_id,
            {
                "status": "delivered",
                "error_code": "",
                "error_message": "",
                "latency_ms": latency_ms,
            },
        )
        _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            output_type="route_ingress_acked",
            raw_output_text=response_text,
            normalized_output={"http_status": int(response.status_code), "accepted": True},
            rendered_output_text="router ingress acked",
            applied_status="acked",
            reason="router ingress acked",
        )
        update_agent_run_status(
            run_id,
            {
                "status": "acked",
                "error_code": "",
                "error_message": "",
                "latency_ms": latency_ms,
            },
        )
        _touch_router_runtime_status(status="acked", error_message="", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": True,
            "status": "acked",
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "latency_ms": latency_ms,
        }
    except requests.Timeout as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = str(exc) or "router webhook timeout"
        update_agent_run_status(
            run_id,
            {
                "status": "failed",
                "error_code": "timeout",
                "error_message": error_message,
                "latency_ms": latency_ms,
            },
        )
        _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            output_type="error_output",
            rendered_output_text="router ingress timeout",
            applied_status="failed",
            reason=error_message,
            error_code="timeout",
            error_message=error_message,
        )
        decision = _router_fallback_payload(
            reason_code="timeout",
            error_message=error_message,
            router_config=router_config,
            request_payload=request_payload,
        )
        fallback_output = _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            output_type="fallback_decision",
            raw_output_text="",
            normalized_output=decision,
            rendered_output_text=_normalized_text(decision.get("reason")) or "router webhook timeout",
            target_agent_code=_normalized_text(decision.get("agent_code")),
            target_pool=_router_decision_target_pool(decision),
            confidence=0,
            reason=_normalized_text(decision.get("reason")),
            need_human_review=bool(decision.get("need_human_review")),
            applied_status="pending_fallback",
            error_code="timeout",
            error_message=error_message,
        )
        _apply_router_decision(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            decision=decision,
            output_id=_normalized_text(fallback_output.get("output_id")),
            adopted_by="router_fallback",
            adopted_action_prefix="fallback_apply",
        )
        _touch_router_runtime_status(status="timeout", error_message=error_message, last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "fallback",
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "decision": decision,
            "latency_ms": latency_ms,
        }
    except requests.RequestException as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = str(exc) or "router webhook request_error"
        error_code = "request_error"
        if error_message.startswith("http_status_"):
            error_code = error_message
        decision = _router_fallback_payload(
            reason_code=error_code,
            error_message=error_message,
            router_config=router_config,
            request_payload=request_payload,
            raw_response_text=response_text,
        )
        update_agent_run_status(
            run_id,
            {
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "latency_ms": latency_ms,
            },
        )
        _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            output_type="error_output",
            rendered_output_text="router ingress failed",
            raw_output_text=response_text,
            applied_status="failed",
            reason=error_message,
            error_code=error_code,
            error_message=error_message,
        )
        fallback_output = _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            output_type="fallback_decision",
            raw_output_text=response_text,
            normalized_output=decision,
            rendered_output_text=_normalized_text(decision.get("reason")) or "router webhook request_error",
            target_agent_code=_normalized_text(decision.get("agent_code")),
            target_pool=_router_decision_target_pool(decision),
            confidence=0,
            reason=_normalized_text(decision.get("reason")),
            need_human_review=bool(decision.get("need_human_review")),
            applied_status="pending_fallback",
            error_code=error_code,
            error_message=error_message,
        )
        _apply_router_decision(
            run_id=run_id,
            request_id=request_id,
            userid=owner_value,
            external_contact_id=_normalized_text(external_contact_id),
            decision=decision,
            output_id=_normalized_text(fallback_output.get("output_id")),
            adopted_by="router_fallback",
            adopted_action_prefix="fallback_apply",
        )
        _touch_router_runtime_status(status=error_code, error_message=error_message, last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "fallback",
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "decision": decision,
            "latency_ms": latency_ms,
        }


def handle_agent_router_callback(payload: dict[str, Any]) -> dict[str, Any]:
    """Internal router owner for callback validation + decision application."""

    ensure_agent_orchestration_defaults()
    raw_payload = _normalize_json_dict(payload)
    request_id = _normalized_text(raw_payload.get("request_id"))
    external_contact_id = _normalized_text(raw_payload.get("external_contact_id"))
    raw_payload_text = json.dumps(raw_payload, ensure_ascii=False)
    now_text = _iso_now()

    existing_run = _resolve_request_run(request_id)
    run_id = _normalized_text((existing_run or {}).get("run_id")) or f"arun-{uuid.uuid4().hex}"
    userid = _normalized_text((existing_run or {}).get("userid"))

    if not existing_run:
        orphan_run = create_agent_run(
            {
                "run_id": run_id,
                "request_id": request_id,
                "batch_id": "",
                "userid": userid,
                "external_contact_id": external_contact_id,
                "agent_code": "central_router_agent",
                "agent_type": "router",
                "provider": "lobster_shadow",
                "input_snapshot": {},
                "variables_snapshot": {"callback_orphan": True},
                "final_prompt_preview": "router_callback_orphan",
                "role_prompt_version": "router-webhook",
                "task_prompt_version": "lobster-shadow-ingress-async-v3",
                "status": "rejected",
                "source": "reply_monitor_callback_orphan",
            }
        )
        _append_router_event_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            output_type="callback_received",
            raw_output_text=raw_payload_text,
            normalized_output=raw_payload,
            rendered_output_text="callback received for unknown request",
            applied_status="rejected",
            reason="request_not_found",
            error_code="request_not_found",
            error_message="request_not_found",
        )
        _append_router_callback_rejected_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            raw_output_text=raw_payload_text,
            normalized_output=raw_payload,
            reason="request_not_found",
            rendered_output_text="router callback rejected: request_not_found",
        )
        _touch_router_runtime_status(status="callback_rejected", error_message="request_not_found", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "rejected",
            "error": "request_not_found",
            "run_id": orphan_run.get("run_id"),
            "request_id": request_id,
        }

    terminal_statuses = {"completed", "applied", "rejected", "failed"}
    current_status = _normalized_text(existing_run.get("status"))
    if current_status in terminal_statuses:
        latest_output = _latest_request_output(
            request_id,
            output_types=["route_decision", "fallback_decision", "error_output", "callback_validated", "callback_rejected"],
        )
        return {
            "ok": True,
            "status": "idempotent",
            "request_id": request_id,
            "run_id": run_id,
            "final_status": current_status,
            "output_id": _normalized_text(latest_output.get("output_id")),
        }

    _append_router_event_output(
        run_id=run_id,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        output_type="callback_received",
        raw_output_text=raw_payload_text,
        normalized_output=raw_payload,
        rendered_output_text="router callback received",
        applied_status="received",
        reason="router callback received",
    )

    normalized_callback, schema_error = _validated_router_callback_payload(
        raw_payload,
        expected_request_id=_normalized_text(existing_run.get("request_id")),
        expected_external_contact_id=_normalized_text(existing_run.get("external_contact_id")),
    )
    if schema_error:
        update_agent_run_status(
            run_id,
            {
                "status": "rejected",
                "error_code": schema_error,
                "error_message": schema_error,
            },
        )
        output = _append_router_callback_rejected_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            raw_output_text=raw_payload_text,
            normalized_output=raw_payload,
            rendered_output_text="router callback rejected",
            reason=schema_error,
        )
        _touch_router_runtime_status(status="callback_rejected", error_message=schema_error, last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "rejected",
            "error": schema_error,
            "request_id": request_id,
            "run_id": run_id,
            "output_id": output.get("output_id"),
        }

    if normalized_callback["target_pool"] not in _router_allowed_target_pools():
        update_agent_run_status(
            run_id,
            {
                "status": "rejected",
                "error_code": "invalid_target_pool",
                "error_message": "invalid_target_pool",
            },
        )
        output = _append_router_callback_rejected_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            raw_output_text=raw_payload_text,
            normalized_output=normalized_callback,
            rendered_output_text="router callback rejected: invalid target_pool",
            reason="invalid_target_pool",
        )
        _touch_router_runtime_status(status="callback_rejected", error_message="invalid_target_pool", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "rejected",
            "error": "invalid_target_pool",
            "request_id": request_id,
            "run_id": run_id,
            "output_id": output.get("output_id"),
        }

    member = repo.get_member_by_external_contact_id(external_contact_id)
    if not member:
        update_agent_run_status(
            run_id,
            {
                "status": "rejected",
                "error_code": "automation_member_not_found",
                "error_message": "automation_member_not_found",
            },
        )
        output = _append_router_callback_rejected_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            raw_output_text=raw_payload_text,
            normalized_output=normalized_callback,
            rendered_output_text="router callback rejected: automation_member_not_found",
            reason="automation_member_not_found",
        )
        _touch_router_runtime_status(status="callback_rejected", error_message="automation_member_not_found", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "rejected",
            "error": "automation_member_not_found",
            "request_id": request_id,
            "run_id": run_id,
            "output_id": output.get("output_id"),
        }

    callback_meta = {
        "trace_id": _normalized_text(normalized_callback.get("trace_id")),
        "processing_latency_ms": int(normalized_callback.get("processing_latency_ms") or 0),
        "prompt_version_used": _normalized_text(normalized_callback.get("prompt_version_used")),
        "mcp_tools_used": list(normalized_callback.get("mcp_tools_used") or []),
        "completed_at": _normalized_text(normalized_callback.get("completed_at")) or now_text,
    }
    next_variables_snapshot = dict(existing_run.get("variables_snapshot_json") or {})
    next_variables_snapshot["callback_meta"] = callback_meta
    update_agent_run_status(
        run_id,
        {
            "status": "completed",
            "error_code": "",
            "error_message": "",
            "variables_snapshot": next_variables_snapshot,
        },
    )
    _append_router_event_output(
        run_id=run_id,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        output_type="callback_validated",
        raw_output_text=raw_payload_text,
        normalized_output=normalized_callback,
        rendered_output_text="router callback validated",
        target_agent_code=_normalized_text(normalized_callback.get("agent_code")) or normalized_callback["target_pool"],
        target_pool=normalized_callback["target_pool"],
        confidence=normalized_callback["confidence"],
        reason=_normalized_text(normalized_callback.get("reason")) or "router callback validated",
        need_human_review=bool(normalized_callback.get("need_human_review")),
        applied_status="validated",
    )

    decision = {
        "request_id": request_id,
        "external_contact_id": external_contact_id,
        "agent_code": _normalized_text(normalized_callback.get("agent_code")) or normalized_callback["target_pool"],
        "target_pool": normalized_callback["target_pool"],
        "confidence": normalized_callback["confidence"],
        "reason": _normalized_text(normalized_callback.get("reason")) or normalized_callback["target_pool"],
        "need_human_review": bool(normalized_callback.get("need_human_review")),
        "structured_result": {
            "target_pool": normalized_callback["target_pool"],
            "completed_at": _normalized_text(normalized_callback.get("completed_at")) or now_text,
            "trace_id": _normalized_text(normalized_callback.get("trace_id")),
            "processing_latency_ms": int(normalized_callback.get("processing_latency_ms") or 0),
            "prompt_version_used": _normalized_text(normalized_callback.get("prompt_version_used")),
            "mcp_tools_used": list(normalized_callback.get("mcp_tools_used") or []),
            "next_action": _normalized_text(normalized_callback.get("next_action")),
            "reply_draft": _normalized_text(normalized_callback.get("reply_draft")),
            "reply_final": _normalized_text(normalized_callback.get("reply_final")),
            **_normalize_json_dict(normalized_callback.get("structured_result")),
        },
    }
    decision_output = _append_router_event_output(
        run_id=run_id,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        output_type="route_decision",
        raw_output_text=raw_payload_text,
        normalized_output=decision,
        rendered_output_text=_normalized_text(decision.get("reason")) or normalized_callback["target_pool"],
        target_agent_code=_normalized_text(decision.get("agent_code")),
        target_pool=normalized_callback["target_pool"],
        confidence=normalized_callback["confidence"],
        reason=_normalized_text(decision.get("reason")),
        need_human_review=bool(decision.get("need_human_review")),
        applied_status="pending_apply",
    )

    child_output = {}
    reply_draft = _normalized_text(normalized_callback.get("reply_draft"))
    reply_final = _normalized_text(normalized_callback.get("reply_final"))
    if _should_generate_child_reply(_normalized_text(decision.get("agent_code"))) and (reply_draft or reply_final):
        child_output = _append_child_agent_reply_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            agent_code=_normalized_text(decision.get("agent_code")),
            target_pool=normalized_callback["target_pool"],
            confidence=normalized_callback["confidence"],
            reason=_normalized_text(decision.get("reason")),
            need_human_review=bool(decision.get("need_human_review")),
            next_action=_normalized_text(normalized_callback.get("next_action")),
            reply_draft=reply_draft,
            reply_final=reply_final,
            source="lobster_callback",
            prompt_version_used=_normalized_text(normalized_callback.get("prompt_version_used")),
            mcp_tools_used=list(normalized_callback.get("mcp_tools_used") or []),
            structured_result=_normalize_json_dict(normalized_callback.get("structured_result")),
            applied_status="generated",
        )

    if bool(normalized_callback.get("need_human_review")):
        applied = _apply_router_decision(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            decision=decision,
            output_id=_normalized_text(decision_output.get("output_id")),
            adopted_by="lobster_callback",
            adopted_action_prefix="human_review_apply",
        )
        _touch_router_runtime_status(status="callback_applied", error_message="", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": True,
            "status": "applied",
            "request_id": request_id,
            "run_id": run_id,
            "output_id": applied.get("output_id"),
        }

    router_config = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    min_callback_confidence = float(_router_runtime_strategy(router_config).get("min_confidence") or 0.5)
    if float(normalized_callback.get("confidence") or 0) < min_callback_confidence:
        update_agent_run_status(
            run_id,
            {
                "status": "rejected",
                "error_code": "confidence_too_low",
                "error_message": "confidence_too_low",
            },
        )
        _append_router_callback_rejected_output(
            run_id=run_id,
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            raw_output_text=raw_payload_text,
            normalized_output=decision,
            reason="confidence_too_low",
            rendered_output_text="router callback rejected: confidence_too_low",
        )
        rejected = record_agent_output_outcome(
            _normalized_text(decision_output.get("output_id")),
            outcome_status="rejected",
            outcome_value=json.dumps(
                {
                    "request_id": request_id,
                    "external_contact_id": external_contact_id,
                    "target_pool": normalized_callback["target_pool"],
                    "confidence": normalized_callback["confidence"],
                    "min_confidence": min_callback_confidence,
                },
                ensure_ascii=False,
            ),
            applied_status="rejected",
        )
        _touch_router_runtime_status(status="callback_rejected", error_message="confidence_too_low", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "rejected",
            "error": "confidence_too_low",
            "request_id": request_id,
            "run_id": run_id,
            "output_id": rejected.get("output_id"),
        }

    if not child_output and _should_generate_child_reply(_normalized_text(decision.get("agent_code"))):
        child_output = orchestration_seams._generate_child_agent_reply_output(
            request_id=request_id,
            userid=userid,
            external_contact_id=external_contact_id,
            agent_code=_normalized_text(decision.get("agent_code")),
            target_pool=normalized_callback["target_pool"],
            reason=_normalized_text(decision.get("reason")),
            confidence=normalized_callback["confidence"],
            need_human_review=bool(decision.get("need_human_review")),
            structured_result=_normalize_json_dict(normalized_callback.get("structured_result")),
        )

    applied = _apply_router_decision(
        run_id=run_id,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        decision=decision,
        output_id=_normalized_text(decision_output.get("output_id")),
        adopted_by="lobster_callback",
        adopted_action_prefix="callback_apply",
    )
    _touch_router_runtime_status(status="callback_applied", error_message="", last_called_at=now_text)
    get_db().commit()
    return {
        "ok": True,
        "status": "applied",
        "request_id": request_id,
        "run_id": run_id,
        "output_id": applied.get("output_id"),
        "reply_output_id": _normalized_text(child_output.get("output_id")),
    }


def record_agent_output_outcome(
    output_id: str,
    *,
    outcome_status: str,
    outcome_value: str = "",
    adopted_by: str = "",
    adopted_action: str = "",
    adopted_at: str = "",
    applied_status: str = "",
    applied_at: str = "",
) -> dict[str, Any]:
    """Internal router owner for output adoption/rejection outcome writes."""

    update_payload: dict[str, Any] = {
        "outcome_status": _normalized_text(outcome_status),
        "outcome_value": _normalized_text(outcome_value),
    }
    if _normalized_text(adopted_by):
        update_payload["adopted_by"] = _normalized_text(adopted_by)
    if _normalized_text(adopted_action):
        update_payload["adopted_action"] = _normalized_text(adopted_action)
    if _normalized_text(adopted_at):
        update_payload["adopted_at"] = _normalized_text(adopted_at)
    if _normalized_text(applied_status):
        update_payload["applied_status"] = _normalized_text(applied_status)
    if _normalized_text(applied_at):
        update_payload["applied_at"] = _normalized_text(applied_at)
    row = repo.update_agent_output(_normalized_text(output_id), update_payload)
    get_db().commit()
    return _serialize_agent_output(row)


def review_agent_reply_output(
    output_id: str,
    *,
    decision: str,
    operator_id: str,
    review_note: str = "",
    source: str = "admin_console",
) -> dict[str, Any]:
    """Internal router owner for admin review/adoption of generated replies."""

    row = repo.get_agent_output_row(_normalized_text(output_id))
    if not row:
        raise LookupError("未找到对应话术输出")
    existing = repo.deserialize_agent_output_row(row)
    output_type = _normalized_text(existing.get("output_type"))
    if output_type not in _REPLY_OUTPUT_TYPES:
        raise ValueError("当前只支持对话术草稿/成稿进行采用判断")
    normalized_decision = _normalized_text(decision).lower()
    if normalized_decision in {"adopt", "apply", "accepted"}:
        normalized_decision = "adopted"
    elif normalized_decision in {"reject", "rejected", "not_adopted", "declined"}:
        normalized_decision = "rejected"
    if normalized_decision not in _REVIEW_DECISIONS:
        raise ValueError("decision 必须是 adopted 或 rejected")

    now_text = _iso_now()
    existing_review_payload = _deserialize_json_object_text(existing.get("outcome_value"))
    resolved_review_note = _normalized_text(review_note) or _normalized_text(existing_review_payload.get("review_note"))
    review_payload = {
        **existing_review_payload,
        "review_decision": normalized_decision,
        "review_note": resolved_review_note,
        "reviewed_at": now_text,
        "reviewed_by": _normalized_text(operator_id) or "crm_console",
        "review_source": _normalized_text(source) or "admin_console",
    }
    return record_agent_output_outcome(
        _normalized_text(output_id),
        outcome_status=normalized_decision,
        outcome_value=json.dumps(review_payload, ensure_ascii=False),
        adopted_by=_normalized_text(operator_id) or "crm_console",
        adopted_action=f"manual_review:{normalized_decision}",
        adopted_at=now_text,
        applied_status=normalized_decision,
        applied_at=now_text,
    )


__all__ = [
    "backfill_missing_child_agent_replies",
    "handle_agent_router_callback",
    "record_agent_output_outcome",
    "review_agent_reply_output",
    "run_agent_router_shadow_decision",
    "validate_router_callback_signature",
]
