from __future__ import annotations

from typing import Any

from ...db import get_db
from ..user_ops import page_service as user_ops_page_service
from . import local_projection
from . import repo
from .service import (
    DEFAULT_OWNER_STAFF_ID,
    TOUCH_PROGRAM_SIGNUP_CONVERSION,
    TOUCH_SURFACE_STAGE_MANUAL_SEND,
    _dispatch_private_message_batch,
    _has_existing_touch_delivery,
    _normalized_text,
    _serialize_member,
)



def _iso_now() -> str:
    """Lazy proxy to service._iso_now so monkeypatch on service._iso_now propagates here."""
    from . import service as _svc
    return _svc._iso_now()


def _manual_send_allowed_route_keys() -> set[str]:
    return local_projection.manual_send_allowed_route_keys()


def _manual_send_stage_definition(route_key: str) -> dict[str, Any]:
    return local_projection.manual_send_stage_definition(route_key)



def _normalize_manual_send_image_media_ids(image_media_ids: list[str] | None = None) -> list[str]:
    normalized_image_media_ids: list[str] = []
    for media_id in list(image_media_ids or []):
        normalized_media_id = _normalized_text(media_id)
        if normalized_media_id:
            normalized_image_media_ids.append(normalized_media_id)
    return normalized_image_media_ids


def _stage_manual_send_targets(
    route_key: str = "",
    *,
    members: list[dict[str, Any]] | None = None,
    touch_surface: str = "",
    skip_delivery_tracking: bool = False,
    claim_delivery: bool = False,
    operator_id: str = "",
) -> dict[str, Any]:
    if members is not None:
        rows = [_serialize_member(m) for m in members]
        pool_key = ""
        definition = {}
        normalized_route_key = _normalized_text(touch_surface) or "segment_filtered"
    else:
        definition = _manual_send_stage_definition(route_key)
        normalized_route_key = _normalized_text(definition.get("route_key")) or _normalized_text(route_key)
        pool_key = _normalized_text(definition.get("pool"))
        rows = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
    final_targets: list[dict[str, Any]] = []
    sendable_targets: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}
    for member in rows:
        external_userid = _normalized_text(member.get("external_contact_id"))
        target = {
            "member_id": int(member.get("id") or 0),
            "external_userid": external_userid,
            "owner_userid": DEFAULT_OWNER_STAFF_ID,
            "owner_display_name": DEFAULT_OWNER_STAFF_ID,
            "mobile": _normalized_text(member.get("phone")),
        }
        final_targets.append(target)
        if not external_userid:
            skipped_reasons["missing_external_userid"] = int(skipped_reasons.get("missing_external_userid") or 0) + 1
            continue
        if not skip_delivery_tracking:
            delivery_metadata = {
                "stage_key": normalized_route_key,
                "pool_key": pool_key,
                "operator_id": _normalized_text(operator_id),
            }
            if _has_existing_touch_delivery(
                touch_surface=TOUCH_SURFACE_STAGE_MANUAL_SEND,
                rule_key=normalized_route_key,
                external_contact_id=external_userid,
            ):
                skipped_reasons["already_touched"] = int(skipped_reasons.get("already_touched") or 0) + 1
                continue
        if claim_delivery and not skip_delivery_tracking:
            now_text = _iso_now()
            delivery = repo.claim_touch_delivery_once(
                {
                    "program_code": TOUCH_PROGRAM_SIGNUP_CONVERSION,
                    "touch_surface": TOUCH_SURFACE_STAGE_MANUAL_SEND,
                    "rule_key": normalized_route_key,
                    "member_id": int(member.get("id") or 0) or None,
                    "external_contact_id": external_userid,
                    "detail": "",
                    "metadata": delivery_metadata,
                    "claimed_at": now_text,
                    "created_at": now_text,
                    "updated_at": now_text,
                }
            )
            if not bool(delivery.get("_did_claim")):
                skipped_reasons["already_touched"] = int(skipped_reasons.get("already_touched") or 0) + 1
                continue
            target["delivery_id"] = int(delivery.get("id") or 0)
        sendable_targets.append(target)
    return {
        "definition": definition,
        "pool_key": pool_key,
        "rows": rows,
        "final_targets": final_targets,
        "sendable_targets": sendable_targets,
        "selected_count": len(rows),
        "eligible_count": len(sendable_targets),
        "skipped_count": sum(int(value or 0) for value in skipped_reasons.values()),
        "skipped_reasons": skipped_reasons,
    }


def preview_stage_manual_send(
    *,
    route_key: str,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    targets_payload = _stage_manual_send_targets(route_key)
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(
        {
            "content": _normalized_text(content),
            "image_media_ids": list(image_media_ids or []),
            "images": list(images or []),
            "attachments": list(attachments or []),
        }
    )
    return {
        "ok": True,
        "stage_key": _normalized_text(route_key),
        "pool_key": _normalized_text(targets_payload.get("pool_key")),
        "stage_label": _normalized_text((targets_payload.get("definition") or {}).get("label")),
        "selected_count": int(targets_payload.get("selected_count") or 0),
        "eligible_count": int(targets_payload.get("eligible_count") or 0),
        "skipped_count": int(targets_payload.get("skipped_count") or 0),
        "skipped_reasons": dict(targets_payload.get("skipped_reasons") or {}),
        "final_targets": list(targets_payload.get("final_targets") or []),
        "task_payload": task_payload,
        "content_preview": content_preview,
        "image_count": image_count,
    }


def send_stage_manual_message(
    *,
    route_key: str = "",
    members: list[dict[str, Any]] | None = None,
    filter_snapshot: dict[str, Any] | None = None,
    skip_delivery_tracking: bool = False,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    user_ops_page_service._build_private_message_payload(
        {
            "content": _normalized_text(content),
            "image_media_ids": list(image_media_ids or []),
            "images": list(images or []),
            "attachments": list(attachments or []),
        }
    )
    targets_payload = _stage_manual_send_targets(
        route_key,
        members=members,
        skip_delivery_tracking=skip_delivery_tracking,
        claim_delivery=not skip_delivery_tracking,
        operator_id=_normalized_text(operator_id) or "crm_console",
    )
    sendable_targets = list(targets_payload.get("sendable_targets") or [])
    if int(targets_payload.get("eligible_count") or 0) > 0:
        resolved_snapshot = filter_snapshot or {
            "selection_mode": "automation_conversion_stage",
            "stage_key": _normalized_text(route_key),
            "pool_key": _normalized_text(targets_payload.get("pool_key")),
        }
        dispatch_result = _dispatch_private_message_batch(
            target_items=sendable_targets,
            content=_normalized_text(content),
            image_media_ids=list(image_media_ids or []),
            images=list(images or []),
            operator_id=_normalized_text(operator_id) or "crm_console",
            filter_snapshot=resolved_snapshot,
        )
        if not skip_delivery_tracking:
            _finalize_stage_manual_touch_deliveries(sendable_targets, dispatch_result)
    else:
        dispatch_result = {
            "ok": False,
            "status": "skipped",
            "record_id": 0,
            "task_ids": [],
            "task_results": [],
            "content_preview": _normalized_text(content),
            "image_count": len(list(image_media_ids or [])) + len(list(images or [])),
            "sent_count": 0,
            "fail_external_userids": [],
            "error": "",
        }
    return {
        "ok": bool(dispatch_result.get("ok")) or int(targets_payload.get("eligible_count") or 0) == 0,
        "stage_key": _normalized_text(route_key),
        "pool_key": _normalized_text(targets_payload.get("pool_key")),
        "stage_label": _normalized_text((targets_payload.get("definition") or {}).get("label")),
        "total_target_count": int(targets_payload.get("selected_count") or 0),
        "eligible_count": int(targets_payload.get("eligible_count") or 0),
        "sent_count": int(dispatch_result.get("sent_count") or 0),
        "skipped_count": int(targets_payload.get("skipped_count") or 0),
        "skipped_reasons": dict(targets_payload.get("skipped_reasons") or {}),
        "record_id": int(dispatch_result.get("record_id") or 0),
        "task_ids": list(dispatch_result.get("task_ids") or []),
        "task_results": list(dispatch_result.get("task_results") or []),
        "content_preview": _normalized_text(dispatch_result.get("content_preview")),
        "image_count": int(dispatch_result.get("image_count") or 0),
        "error": _normalized_text(dispatch_result.get("error")),
    }


def _finalize_stage_manual_touch_deliveries(target_items: list[dict[str, Any]], dispatch_result: dict[str, Any]) -> None:
    if not target_items:
        return
    now_text = _iso_now()
    dispatch_status = _normalized_text(dispatch_result.get("status"))
    fail_external_userids = {
        _normalized_text(item)
        for item in list(dispatch_result.get("fail_external_userids") or [])
        if _normalized_text(item)
    }
    if dispatch_status == "failed":
        fail_external_userids = {
            _normalized_text(item.get("external_userid"))
            for item in target_items
            if _normalized_text(item.get("external_userid"))
        }
    for item in target_items:
        delivery_id = int(item.get("delivery_id") or 0)
        external_userid = _normalized_text(item.get("external_userid"))
        if delivery_id <= 0 or not external_userid:
            continue
        delivery_status = "failed" if external_userid in fail_external_userids else "sent"
        repo.update_touch_delivery_log_status(
            delivery_id,
            status=delivery_status,
            send_record_id=int(dispatch_result.get("record_id") or 0) or None,
            detail=_normalized_text(dispatch_result.get("error")) if delivery_status == "failed" else "",
            metadata={
                "dispatch_status": dispatch_status,
                "task_ids": list(dispatch_result.get("task_ids") or []),
                "task_results": list(dispatch_result.get("task_results") or []),
            },
            sent_at=now_text if delivery_status == "sent" else "",
            updated_at=now_text,
        )
    get_db().commit()




