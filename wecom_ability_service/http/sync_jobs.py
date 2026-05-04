from __future__ import annotations

from ..infra.wecom_runtime import get_app_runtime_client
from ..wecom_client import WeComClientError
from .common import _default_owner_userid, archive_logger, wecom_logger
from .sync_support import (
    _ensure_contacts_for_external_userids,
    _sync_contacts,
    _sync_external_contact_identity_map,
    _sync_group_chats,
)
from ..domains.archive.service import create_sync_run, finish_sync_run
from ..domains.group_chats.repo import upsert_group_chats
from ..domains.group_chats.service import normalize_group_chat_record


def run_contacts_sync(*, only_new: bool) -> dict:
    return _sync_contacts(only_new=only_new)


def run_external_contact_identity_sync(*, only_new: bool) -> dict:
    return _sync_external_contact_identity_map(only_new=only_new)


def run_group_chat_sync(*, only_new: bool) -> dict:
    return _sync_group_chats(only_new=only_new)


def run_archive_health_check() -> dict:
    from .. import routes as routes_compat

    client = routes_compat.ArchiveAdapterClient.from_app()
    return client.health()


def run_manual_archive_sync(
    *,
    start_time: str,
    end_time: str,
    owner_userid: str,
    cursor: str = "",
) -> dict:
    run_id = create_sync_run(start_time, end_time, owner_userid, cursor)
    from .. import routes as routes_compat

    try:
        archive_logger.info(
            "manual archive sync requested run_id=%s owner_userid=%s cursor=%s window=%s..%s",
            run_id,
            owner_userid,
            cursor,
            start_time,
            end_time,
        )
        client = routes_compat.ArchiveAdapterClient.from_app()
        result = client.sync_messages(start_time, end_time, owner_userid, cursor)
        if result.get("external_userids"):
            result["contacts_sync"] = _ensure_contacts_for_external_userids(result.get("external_userids") or [])
        if result.get("group_chat_ids"):
            wecom_client = get_app_runtime_client()
            group_records = []
            for chat_id in result.get("group_chat_ids") or []:
                try:
                    detail = wecom_client.get_group_chat(chat_id)
                except WeComClientError:
                    continue
                group_records.append(normalize_group_chat_record(detail))
            upsert_group_chats(group_records)
        fetched_count = int(result.get("fetched_count", 0))
        inserted_count = int(result.get("inserted_count", 0))
        finish_sync_run(run_id, "success", fetched_count, inserted_count, raw_response=result)
        archive_logger.info(
            "manual archive sync finished run_id=%s fetched=%s inserted=%s last_seq=%s",
            run_id,
            fetched_count,
            inserted_count,
            result.get("last_seq", 0),
        )
        return {
            "ok": True,
            "sync_run": {
                "id": run_id,
                "status": "success",
                "fetched_count": fetched_count,
                "inserted_count": inserted_count,
                "has_more": bool(result.get("has_more")),
                "next_cursor": result.get("next_cursor", ""),
                "last_seq": result.get("last_seq", 0),
            },
        }
    except Exception as exc:
        archive_logger.exception("manual archive sync failed run_id=%s", run_id)
        finish_sync_run(run_id, "failed", 0, 0, error_message=str(exc))
        return {"ok": False, "error": str(exc), "sync_run_id": run_id}


def _trigger_incremental_archive_sync() -> dict:
    archive_logger.info("incremental archive sync triggered by callback")
    start_time = "2000-01-01 00:00:00"
    end_time = "2099-12-31 23:59:59"
    owner_userid = _default_owner_userid()
    run_id = create_sync_run(start_time, end_time, owner_userid, "")
    from .. import routes as routes_compat

    client = routes_compat.ArchiveAdapterClient.from_app()
    try:
        result = client.sync_messages(start_time, end_time, owner_userid, "")
        contact_result = _ensure_contacts_for_external_userids(result.get("external_userids") or [])
        group_chat_ids = result.get("group_chat_ids") or []
        if group_chat_ids:
            wecom_client = get_app_runtime_client()
            group_records = []
            for chat_id in group_chat_ids:
                try:
                    detail = wecom_client.get_group_chat(chat_id)
                except WeComClientError as exc:
                    wecom_logger.error(
                        "stage=%s errcode=%s errmsg=%s owner_userid=%s external_userid=%s chat_id=%s",
                        exc.stage or "",
                        (exc.payload or {}).get("errcode"),
                        (exc.payload or {}).get("errmsg", str(exc)),
                        owner_userid,
                        "",
                        chat_id,
                    )
                    continue
                group_records.append(normalize_group_chat_record(detail))
            upsert_group_chats(group_records)
        result["contacts_sync"] = contact_result
        finish_sync_run(
            run_id,
            "success",
            int(result.get("fetched_count", 0)),
            int(result.get("inserted_count", 0)),
            raw_response=result,
        )
        archive_logger.info(
            "incremental archive sync completed fetched=%s inserted=%s last_seq=%s",
            result.get("fetched_count", 0),
            result.get("inserted_count", 0),
            result.get("last_seq", 0),
        )
        return result
    except Exception as exc:
        archive_logger.exception("incremental archive sync failed run_id=%s", run_id)
        finish_sync_run(run_id, "failed", 0, 0, error_message=str(exc))
        raise
