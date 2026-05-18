from __future__ import annotations

import json
import time
from datetime import datetime

from flask import current_app

from ..application.identity_contact.commands import (
    BuildExternalContactIdentityRecordCommand,
    MarkExternalContactFollowUserStatusCommand,
    MarkExternalContactIdentityStatusCommand,
    RefreshExternalContactIdentityOwnerCommand,
    ReplaceFollowUsersCommand,
    UpsertExternalContactIdentityCommand,
)
from ..application.identity_contact.dto import (
    MarkExternalContactFollowUserStatusCommandDTO,
    MarkExternalContactIdentityStatusCommandDTO,
    RefreshExternalContactIdentityOwnerCommandDTO,
    ReplaceFollowUsersCommandDTO,
    UpsertExternalContactIdentityCommandDTO,
)
from ..application.automation_engine.commands import HandleQrcodeEnterFromCallbackCommand
from ..application.user_ops.commands import (
    RunDueUserOpsDeferredJobsCommand,
    ScheduleUserOpsAutoAssignClassTermJobCommand,
)
from ..application.user_ops.dto import (
    RunDueUserOpsDeferredJobsCommandDTO,
    ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
)
from ..domains.callbacks.service import (
    finish_external_contact_event_log,
    get_external_contact_event_log,
    mark_external_contact_event_processing,
)
from ..domains.automation_conversion.customer_acquisition_service import handle_customer_acquisition_event
from ..domains.contacts.repo import upsert_contacts
from ..domains.automation_conversion.customer_acquisition_service import handle_customer_acquisition_event
from ..domains.group_chats.repo import get_group_chat_by_chat_id, upsert_group_chats
from ..domains.group_chats.service import normalize_group_chat_record
from ..infra.wecom_runtime import get_app_runtime_client
from ..observability import (
    bind_background_context,
    generate_job_id,
    get_job_id,
    get_parent_request_id,
    get_request_id,
    get_task_name,
    unbind_background_context,
)
from ..infra.task_queue import enqueue_task
from .common import (
    _contact_sync_retry_limit,
    _default_owner_userid,
    callback_logger,
)
from .sync_support import _sync_contact_detail_with_description_fix


def _build_external_contact_identity_record(
    *,
    corp_id: str,
    detail: dict[str, object],
    follow_user_userid: str = "",
    status: str = "",
) -> dict[str, object]:
    return BuildExternalContactIdentityRecordCommand()(
        corp_id=str(corp_id or "").strip(),
        detail=dict(detail or {}),
        follow_user_userid=str(follow_user_userid or "").strip(),
        status=str(status or "").strip(),
    )


def _upsert_external_contact_identity(record: dict[str, object]) -> int:
    return UpsertExternalContactIdentityCommand()(
        UpsertExternalContactIdentityCommandDTO(record=dict(record or {}))
    )


def _replace_external_contact_follow_users(
    *,
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, object]],
    preferred_userid: str = "",
) -> None:
    return ReplaceFollowUsersCommand()(
        ReplaceFollowUsersCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
            follow_users=list(follow_users or []),
            preferred_userid=str(preferred_userid or "").strip(),
        )
    )


def _refresh_external_contact_identity_owner(*, corp_id: str, external_userid: str) -> None:
    return RefreshExternalContactIdentityOwnerCommand()(
        RefreshExternalContactIdentityOwnerCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
        )
    )


def _mark_external_contact_identity_status(
    *,
    corp_id: str,
    external_userid: str,
    status: str,
    follow_user_userid: str = "",
) -> None:
    return MarkExternalContactIdentityStatusCommand()(
        MarkExternalContactIdentityStatusCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
            status=str(status or "").strip(),
            follow_user_userid=str(follow_user_userid or "").strip(),
        )
    )


def _mark_external_contact_follow_user_status(
    *,
    corp_id: str,
    external_userid: str,
    status: str,
    user_id: str = "",
) -> None:
    return MarkExternalContactFollowUserStatusCommand()(
        MarkExternalContactFollowUserStatusCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
            status=str(status or "").strip(),
            user_id=str(user_id or "").strip(),
        )
    )


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, object] | None = None,
    operator_id: str = "",
    send_welcome_message: bool = False,
) -> dict[str, object]:
    normalized_payload_json: dict[str, object] = {}
    if isinstance(payload_json, str):
        try:
            parsed_payload = json.loads(payload_json)
            normalized_payload_json = parsed_payload if isinstance(parsed_payload, dict) else {}
        except json.JSONDecodeError:
            normalized_payload_json = {}
    else:
        normalized_payload_json = dict(payload_json or {})
    return HandleQrcodeEnterFromCallbackCommand()(
        external_contact_id=str(external_contact_id or "").strip(),
        phone=str(phone or "").strip(),
        payload_json=normalized_payload_json,
        operator_id=str(operator_id or "").strip(),
        send_welcome_message=bool(send_welcome_message),
    )


def _run_app_task(
    app,
    task_name: str,
    task_fn,
    *args,
    job_id: str = "",
    parent_request_id: str = "",
    **kwargs,
) -> None:
    with app.app_context():
        context_tokens = bind_background_context(
            job_id=job_id,
            parent_request_id=parent_request_id,
            task_name=task_name,
        )
        try:
            callback_logger.info(
                "background task started job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
            task_fn(*args, **kwargs)
            callback_logger.info(
                "background task finished job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        except Exception:
            callback_logger.exception(
                "background task failed job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        finally:
            unbind_background_context(context_tokens)


def _dispatch_background_task(task_name: str, task_fn, *args, **kwargs) -> None:
    app = current_app._get_current_object()
    job_id = generate_job_id()
    parent_request_id = get_request_id()
    if current_app.config.get("CALLBACK_ASYNC_ENABLED", True):
        enqueue_task(
            _run_app_task,
            app,
            task_name,
            task_fn,
            *args,
            task_name=task_name,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )
    else:
        _run_app_task(
            app,
            task_name,
            task_fn,
            *args,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )


def _run_user_ops_deferred_jobs_after_delay(wait_seconds: int = 10, limit: int = 20) -> None:
    delay = max(int(wait_seconds or 0), 0)
    if delay:
        time.sleep(delay)
    result = RunDueUserOpsDeferredJobsCommand()(RunDueUserOpsDeferredJobsCommandDTO(limit=int(limit or 20)))
    callback_logger.info(
        "background task summary job_id=%s task_name=%s parent_request_id=%s "
        "stage=user_ops_auto_assign scanned=%s success=%s conflict=%s skipped=%s failed=%s",
        get_job_id(),
        get_task_name(),
        get_parent_request_id(),
        result.get("scanned_count", 0),
        result.get("success_count", 0),
        result.get("conflict_count", 0),
        result.get("skipped_count", 0),
        result.get("failed_count", 0),
    )


def _handle_group_chat_change(event_data: dict[str, str]) -> dict:
    chat_id = event_data.get("ChatId") or event_data.get("chat_id") or event_data.get("ChatID") or ""
    change_type = (event_data.get("ChangeType") or event_data.get("change_type") or "").lower()
    if not chat_id:
        return {"handled": False, "reason": "missing chat_id"}
    if "dismiss" in change_type:
        existing = get_group_chat_by_chat_id(chat_id) or {"chat_id": chat_id}
        upsert_group_chats(
            [
                {
                    "chat_id": chat_id,
                    "group_name": existing.get("group_name", ""),
                    "owner_userid": existing.get("owner_userid", ""),
                    "notice": existing.get("notice", ""),
                    "member_count": existing.get("member_count", 0),
                    "status": "dismissed",
                    "create_time": existing.get("create_time", ""),
                    "dismissed_at": existing.get("dismissed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "raw_payload": existing.get("raw_payload", "{}"),
                }
            ]
        )
        return {"handled": True, "chat_id": chat_id, "change_type": change_type}

    wecom_client = get_app_runtime_client()
    detail = wecom_client.get_group_chat(chat_id)
    upsert_group_chats([normalize_group_chat_record(detail)])
    return {"handled": True, "chat_id": chat_id, "change_type": change_type}


def _process_external_contact_event(event_log_id: int) -> dict:
    event_log = get_external_contact_event_log(event_log_id)
    if not event_log:
        return {"ok": False, "error": "event_log_not_found"}
    if event_log.get("process_status") == "success":
        return {"ok": True, "status": "success", "event_log_id": event_log_id, "duplicate": True}

    mark_external_contact_event_processing(event_log_id)
    event_log = get_external_contact_event_log(event_log_id) or event_log
    retry_limit = _contact_sync_retry_limit()
    corp_id = event_log.get("corp_id", "")
    event_type = (event_log.get("event_type") or "").lower()
    external_userid = event_log.get("external_userid", "")
    user_id = event_log.get("user_id", "")
    change_type = (event_log.get("change_type") or "").lower()
    from .. import routes as routes_compat

    scheduled_auto_assign_job: dict[str, object] | None = None

    try:
        if event_type == "customer_acquisition":
            customer_acquisition_result = handle_customer_acquisition_event(
                corp_id=corp_id,
                event_data=event_log.get("payload_json") or {},
                event_log_id=event_log_id,
            )
            finish_external_contact_event_log(event_log_id, status="success")
            callback_logger.info(
                "stage=customer_acquisition_callback errcode=0 errmsg=success handled=%s reason=%s owner_userid=%s external_userid=%s",
                customer_acquisition_result.get("handled"),
                customer_acquisition_result.get("reason", ""),
                user_id,
                external_userid,
            )
            return {
                "ok": True,
                "status": "success",
                "event_log_id": event_log_id,
                "customer_acquisition": customer_acquisition_result,
            }

        client = routes_compat._contact_client()
        if change_type in {"add_external_contact", "add_half_external_contact", "edit_external_contact"}:
            detail = client.get_contact(external_userid)
            normalized_contact, _ = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=user_id,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=True,
                log_stage="external_contact.callback",
            )
            upsert_contacts([normalized_contact])
            identity = _build_external_contact_identity_record(
                corp_id=corp_id,
                detail=detail,
                follow_user_userid=user_id,
                status="active",
            )
            _upsert_external_contact_identity(identity)
            _replace_external_contact_follow_users(
                corp_id=corp_id,
                external_userid=external_userid,
                follow_users=detail.get("follow_user") or [],
                preferred_userid=user_id,
            )
            _refresh_external_contact_identity_owner(corp_id=corp_id, external_userid=external_userid)
            qrcode_result = handle_qrcode_enter_from_callback(
                external_contact_id=external_userid,
                phone=str(normalized_contact.get("mobile") or "").strip(),
                payload_json=event_log.get("payload_json") or {},
                operator_id=user_id or "wecom_callback",
                send_welcome_message=change_type in {"add_external_contact", "add_half_external_contact"},
            )
            if bool(qrcode_result.get("handled")):
                callback_logger.info(
                    "external contact qrcode automation handled external_userid=%s welcome=%s entry_tag=%s",
                    external_userid,
                    qrcode_result.get("welcome_message"),
                    qrcode_result.get("entry_tag"),
                )
            if change_type in {"add_external_contact", "add_half_external_contact"}:
                scheduled_auto_assign_job = ScheduleUserOpsAutoAssignClassTermJobCommand()(
                    ScheduleUserOpsAutoAssignClassTermJobCommandDTO(
                        external_userid=external_userid,
                        owner_userid=str(normalized_contact.get("owner_userid") or user_id or "").strip(),
                        delay_seconds=10,
                        operator="system_auto_assign",
                    )
                )
        elif change_type in {"del_external_contact", "del_follow_user"}:
            _mark_external_contact_identity_status(
                corp_id=corp_id,
                external_userid=external_userid,
                status="inactive",
                follow_user_userid=user_id,
            )
            _mark_external_contact_follow_user_status(
                corp_id=corp_id,
                external_userid=external_userid,
                user_id=user_id if change_type == "del_follow_user" else "",
                status="inactive",
            )
            _refresh_external_contact_identity_owner(corp_id=corp_id, external_userid=external_userid)
        else:
            finish_external_contact_event_log(event_log_id, status="ignored")
            callback_logger.info(
                "stage=external_contact_callback errcode=0 errmsg=ignored_change_type change_type=%s owner_userid=%s external_userid=%s chat_id=",
                change_type,
                user_id,
                external_userid,
            )
            return {"ok": True, "status": "ignored", "event_log_id": event_log_id}

        finish_external_contact_event_log(event_log_id, status="success")
        if scheduled_auto_assign_job and scheduled_auto_assign_job.get("scheduled"):
            routes_compat._dispatch_background_task(
                "user_ops_auto_assign_class_term",
                _run_user_ops_deferred_jobs_after_delay,
                11,
                20,
            )
        callback_logger.info(
            "stage=external_contact_callback errcode=0 errmsg=success owner_userid=%s external_userid=%s chat_id=",
            user_id,
            external_userid,
        )
        return {"ok": True, "status": "success", "event_log_id": event_log_id}
    except Exception as exc:
        latest = get_external_contact_event_log(event_log_id) or event_log
        next_retry = int(latest.get("retry_count") or 0) + 1
        final_status = "failed" if next_retry >= retry_limit else "pending"
        finish_external_contact_event_log(
            event_log_id,
            status=final_status,
            error_message=str(exc),
            increment_retry=True,
        )
        callback_logger.error(
            "stage=external_contact_callback errcode=1 errmsg=%s owner_userid=%s external_userid=%s chat_id=",
            str(exc),
            user_id,
            external_userid,
        )
        if final_status == "pending":
            return _process_external_contact_event(event_log_id)
        return {"ok": False, "status": final_status, "event_log_id": event_log_id, "error": str(exc)}
