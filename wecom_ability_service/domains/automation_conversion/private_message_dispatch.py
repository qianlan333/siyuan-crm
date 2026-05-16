from __future__ import annotations

from typing import Any

from ..tasks.service import dispatch_wecom_task
from ..user_ops import page_service as user_ops_page_service
from ...wecom_client import WeComClientError


DEFAULT_PRIVATE_MESSAGE_SENDER = "HuangYouCan"
_MINIPROGRAM_FALLBACK_ERRCODES = {41006, 90208}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_private_message_image_media_ids(image_media_ids: list[str] | None = None) -> list[str]:
    normalized_image_media_ids: list[str] = []
    for media_id in list(image_media_ids or []):
        normalized_media_id = _normalized_text(media_id)
        if normalized_media_id:
            normalized_image_media_ids.append(normalized_media_id)
    return normalized_image_media_ids


def _miniprogram_attachment_count(payload: dict[str, Any]) -> int:
    return sum(
        1
        for item in list(payload.get("attachments") or [])
        if isinstance(item, dict) and _normalized_text(item.get("msgtype")).lower() == "miniprogram"
    )


def _without_miniprogram_attachments(payload: dict[str, Any]) -> dict[str, Any]:
    fallback = dict(payload)
    kept_attachments = [
        item
        for item in list(payload.get("attachments") or [])
        if not (isinstance(item, dict) and _normalized_text(item.get("msgtype")).lower() == "miniprogram")
    ]
    if kept_attachments:
        fallback["attachments"] = kept_attachments
    else:
        fallback.pop("attachments", None)
    return fallback


def _should_retry_without_miniprogram(payload: dict[str, Any], exc: Exception) -> bool:
    if not _miniprogram_attachment_count(payload):
        return False
    if not _normalized_text(payload.get("text", {}).get("content") if isinstance(payload.get("text"), dict) else payload.get("content")):
        return False
    if not isinstance(exc, WeComClientError):
        return False
    errcode = (exc.payload or {}).get("errcode")
    try:
        return int(errcode) in _MINIPROGRAM_FALLBACK_ERRCODES
    except (TypeError, ValueError):
        return False


def _dispatch_private_message_batch(
    *,
    target_items: list[dict[str, Any]],
    content: str,
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    miniprogram_library_ids: list[int] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    operator_id: str,
    filter_snapshot: dict[str, Any],
    sender_userid: str | None = None,
) -> dict[str, Any]:
    normalized_sender = _normalized_text(sender_userid) or DEFAULT_PRIVATE_MESSAGE_SENDER
    payload_for_build: dict[str, Any] = {
        "content": _normalized_text(content),
        "image_media_ids": _normalize_private_message_image_media_ids(image_media_ids),
        "images": list(images or []),
    }
    library_ids = [int(i) for i in (miniprogram_library_ids or []) if i]
    extra_attachments: list[dict[str, Any]] = list(attachments or [])
    for library_id in library_ids:
        extra_attachments.append({"msgtype": "miniprogram", "miniprogram": {"library_id": library_id}})
    if extra_attachments:
        payload_for_build["attachments"] = extra_attachments

    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(payload_for_build)
    target_external_userids = [
        _normalized_text(item.get("external_userid"))
        for item in target_items
        if _normalized_text(item.get("external_userid"))
    ]
    request_payload = {
        "sender": normalized_sender,
        "external_userid": target_external_userids,
        **task_payload,
    }

    outbound_task_ids: list[int] = []
    task_results: list[dict[str, Any]] = []
    fail_external_userids: list[str] = []
    try:
        wecom_result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        fail_external_userids = [
            _normalized_text(item)
            for item in (wecom_result.get("wecom_result") or {}).get("fail_list", [])
            if _normalized_text(item)
        ]
        outbound_task_ids.append(int(wecom_result["task_id"]))
        task_results.append(user_ops_page_service._build_sender_success_result(normalized_sender, target_items, wecom_result))
    except Exception as exc:
        if _should_retry_without_miniprogram(request_payload, exc):
            fallback_payload = _without_miniprogram_attachments(request_payload)
            try:
                wecom_result = dispatch_wecom_task("private_message", "create_private_message_task", fallback_payload)
                fail_external_userids = [
                    _normalized_text(item)
                    for item in (wecom_result.get("wecom_result") or {}).get("fail_list", [])
                    if _normalized_text(item)
                ]
                outbound_task_ids.append(int(wecom_result["task_id"]))
                fallback_result = user_ops_page_service._build_sender_success_result(
                    normalized_sender,
                    target_items,
                    wecom_result,
                )
                fallback_result.update(
                    {
                        "fallback_without_miniprogram": True,
                        "fallback_reason": "wecom_miniprogram_rejected",
                        "fallback_error_message": str(exc),
                        "fallback_removed_attachment_count": _miniprogram_attachment_count(request_payload),
                    }
                )
                task_results.append(fallback_result)
            except Exception as fallback_exc:
                fail_external_userids = list(target_external_userids)
                failure_result = user_ops_page_service._build_sender_failure_result(
                    normalized_sender,
                    target_items,
                    fallback_exc,
                )
                failure_result.update(
                    {
                        "fallback_without_miniprogram": True,
                        "fallback_reason": "wecom_miniprogram_rejected",
                        "fallback_error_message": str(exc),
                    }
                )
                task_results.append(failure_result)
        else:
            fail_external_userids = list(target_external_userids)
            task_results.append(user_ops_page_service._build_sender_failure_result(normalized_sender, target_items, exc))

    if fail_external_userids:
        sent_count = max(0, len(target_items) - len(set(fail_external_userids)))
        status = "partial_failed" if sent_count > 0 else "failed"
    else:
        sent_count = sum(
            int(item.get("target_count") or 0)
            for item in task_results
            if _normalized_text(item.get("status")) != "failed"
        )
        status = user_ops_page_service._derive_record_status(task_results, eligible_count=len(target_items))

    record_id = user_ops_page_service._insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=len(target_items),
        eligible_count=len(target_items),
        sent_count=sent_count,
        skipped_count=0,
        skipped_reasons={},
        include_do_not_disturb=False,
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=[normalized_sender],
        filter_snapshot=filter_snapshot,
        operator=_normalized_text(operator_id) or "crm_console",
        status=status,
    )
    error_message = (
        _normalized_text(task_results[0].get("error_message"))
        if status == "failed" and task_results
        else ("dispatch_failed" if fail_external_userids else "")
    )
    return {
        "ok": status != "failed",
        "status": status,
        "record_id": int(record_id),
        "task_ids": outbound_task_ids,
        "task_results": task_results,
        "content_preview": content_preview,
        "image_count": image_count,
        "sent_count": sent_count,
        "fail_external_userids": fail_external_userids,
        "error": error_message if status == "failed" else "",
        "error_message": error_message,
        "sender_userid": normalized_sender,
    }
