from __future__ import annotations

from typing import Any

from ..application.identity_contact.commands import (
    BuildExternalContactIdentityRecordCommand,
    RefreshExternalContactIdentityOwnerCommand,
    ReplaceFollowUsersCommand,
    UpsertExternalContactIdentityCommand,
)
from ..application.identity_contact.dto import (
    RefreshExternalContactIdentityOwnerCommandDTO,
    ReplaceFollowUsersCommandDTO,
    ResolveExternalContactIdentityQueryDTO,
    UpsertExternalContactIdentityCommandDTO,
)
from ..application.identity_contact.queries import (
    CountExternalContactIdentityMapsQuery,
    ListIdentityExternalUseridsForCorpQuery,
    ResolveExternalContactIdentityQuery,
)
from ..archive_adapter import ArchiveAdapterClient
from ..domains.archive.service import create_sync_run, finish_sync_run
from ..domains.contacts.repo import count_contacts, list_contacts as list_contacts_from_db, upsert_contacts
from ..domains.contacts.service import (
    contact_description_state,
    normalize_contact_record,
    sync_contact_detail_with_description_fix as _sync_contact_detail_with_description_fix,
    target_contact_description,
    update_contact_description_snapshot,
)
from ..domains.group_chats.repo import (
    count_group_chats,
    list_group_chats as list_group_chats_from_db,
    upsert_group_chats,
)
from ..domains.group_chats.service import normalize_group_chat_record
from ..infra.wecom_runtime import get_app_runtime_client
from ..wecom_client import WeComClientError
from .common import (
    _contact_client,
    _contact_sync_batch_size,
    _corp_id,
    _default_owner_userid,
    _log_wecom_client_error,
    archive_logger,
    contacts_logger,
    wecom_logger,
)


def _list_identity_external_userids_for_corp(corp_id: str) -> list[str]:
    return ListIdentityExternalUseridsForCorpQuery()(str(corp_id or "").strip())


def _resolve_external_contact_identity(
    *,
    corp_id: str,
    unionid: str = "",
    openid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    return ResolveExternalContactIdentityQuery()(
        ResolveExternalContactIdentityQueryDTO(
            corp_id=str(corp_id or "").strip(),
            unionid=str(unionid or "").strip(),
            openid=str(openid or "").strip(),
            external_userid=str(external_userid or "").strip(),
        )
    )


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


def _count_external_contact_identity_maps() -> int:
    return CountExternalContactIdentityMapsQuery()()


def _collect_owner_userids(client: Any) -> list[str]:
    result = client.list_follow_userids()
    owner_userids = [userid for userid in (result.get("follow_user") or []) if userid]
    if not owner_userids:
        default_owner = _default_owner_userid()
        if default_owner:
            owner_userids = [default_owner]
    return owner_userids


def _build_external_contact_event_key(corp_id: str, event_data: dict[str, str]) -> str:
    change_type = (event_data.get("ChangeType") or "").strip()
    external_userid = (event_data.get("ExternalUserID") or "").strip()
    user_id = (event_data.get("UserID") or "").strip()
    create_time = (event_data.get("CreateTime") or "").strip()
    return "|".join([corp_id, change_type, external_userid, user_id, create_time])


def _sync_contacts(*, only_new: bool) -> dict:
    client = get_app_runtime_client()
    owner_userids = _collect_owner_userids(client)
    existing_contacts = {row["external_userid"] for row in list_contacts_from_db(None)}
    records_by_external: dict[str, dict] = {}
    fetched_count = 0
    description_updated_count = 0

    for owner_userid in owner_userids:
        try:
            result = client.list_contacts(owner_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(exc, owner_userid=owner_userid, stage="external_contact.list")
            continue
        for external_userid in result.get("external_userid") or []:
            if not external_userid:
                continue
            if only_new and external_userid in existing_contacts:
                continue
            if external_userid in records_by_external:
                continue
            detail = client.get_contact(external_userid)
            normalized, updated_description = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=owner_userid,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=False,
                log_stage="external_contact.sync",
            )
            if updated_description:
                description_updated_count += 1
            records_by_external[external_userid] = normalized
            fetched_count += 1

    inserted_count, updated_count = upsert_contacts(list(records_by_external.values()))
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "description_updated_count": description_updated_count,
        "contacts_total": count_contacts(),
    }


def _sync_external_contact_identity_map(*, only_new: bool) -> dict:
    client = _contact_client()
    corp_id = _corp_id()
    batch_size = _contact_sync_batch_size()
    owner_userids = _collect_owner_userids(client)
    existing_external_userids = set()
    if only_new:
        existing_external_userids.update(_list_identity_external_userids_for_corp(corp_id))

    fetched_count = 0
    inserted_count = 0
    updated_count = 0
    counted_external_userids: set[str] = set()

    for owner_userid in owner_userids:
        try:
            result = client.list_contacts(owner_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(
                exc,
                owner_userid=owner_userid,
                stage="external_contact.list",
            )
            continue
        external_userids = [value for value in (result.get("external_userid") or []) if value]
        for start in range(0, len(external_userids), batch_size):
            for external_userid in external_userids[start : start + batch_size]:
                if only_new and external_userid in existing_external_userids:
                    continue
                existing = _resolve_external_contact_identity(corp_id=corp_id, external_userid=external_userid)
                try:
                    detail = client.get_contact(external_userid)
                except WeComClientError as exc:
                    _log_wecom_client_error(
                        exc,
                        owner_userid=owner_userid,
                        external_userid=external_userid,
                        stage="external_contact.get",
                    )
                    continue
                identity = _build_external_contact_identity_record(
                    corp_id=corp_id,
                    detail=detail,
                    follow_user_userid=owner_userid,
                    status="active",
                )
                _upsert_external_contact_identity(identity)
                _replace_external_contact_follow_users(
                    corp_id=corp_id,
                    external_userid=external_userid,
                    follow_users=detail.get("follow_user") or [],
                    preferred_userid=owner_userid,
                )
                _refresh_external_contact_identity_owner(corp_id=corp_id, external_userid=external_userid)
                if external_userid not in counted_external_userids:
                    fetched_count += 1
                    if existing:
                        updated_count += 1
                    else:
                        inserted_count += 1
                    counted_external_userids.add(external_userid)

    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "identity_map_total": _count_external_contact_identity_maps(),
    }


def _ensure_contacts_for_external_userids(external_userids: list[str]) -> dict:
    client = get_app_runtime_client()
    existing_contacts = {row["external_userid"] for row in list_contacts_from_db(None)}
    records = []
    description_updated_count = 0
    fetched_count = 0
    skipped_count = 0
    for external_userid in dict.fromkeys([value for value in external_userids if value]):
        try:
            detail = client.get_contact(external_userid)
        except WeComClientError as exc:
            if exc.category == "external_userid 不存在":
                skipped_count += 1
                continue
            raise
        try:
            normalized, updated_description = _sync_contact_detail_with_description_fix(
                client,
                detail,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=False,
                log_stage="external_contact.archive_sync",
            )
        except WeComClientError as exc:
            if exc.category == "external_userid 不存在":
                skipped_count += 1
                continue
            raise
        if updated_description:
            description_updated_count += 1
        records.append(normalized)
        fetched_count += 1
    inserted_count, updated_count = upsert_contacts(records)
    new_count = sum(1 for row in records if row["external_userid"] not in existing_contacts)
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "description_updated_count": description_updated_count,
        "new_count": new_count,
        "skipped_count": skipped_count,
    }


def _sync_group_chats(*, only_new: bool) -> dict:
    client = get_app_runtime_client()
    owner_userids = _collect_owner_userids(client)
    existing_chat_ids = set()
    if only_new:
        existing_chat_ids = {row["chat_id"] for row in list_group_chats_from_db(None)}
    records_by_chat_id: dict[str, dict] = {}
    fetched_count = 0

    for owner_userid in owner_userids:
        cursor = ""
        while True:
            payload = {"limit": 100, "status_filter": 0, "owner_filter": {"userid_list": [owner_userid]}}
            if cursor:
                payload["cursor"] = cursor
            result = client.list_group_chats(payload)
            for item in result.get("group_chat_list") or []:
                chat_id = item.get("chat_id", "")
                if not chat_id:
                    continue
                if only_new and chat_id in existing_chat_ids:
                    continue
                detail = client.get_group_chat(chat_id)
                records_by_chat_id[chat_id] = normalize_group_chat_record(detail, owner_userid=owner_userid)
                fetched_count += 1
            cursor = result.get("next_cursor", "")
            if not cursor:
                break

    inserted_count, updated_count = upsert_group_chats(list(records_by_chat_id.values()))
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "group_chats_total": count_group_chats(),
    }


def _normalize_contact_descriptions() -> dict:
    client = get_app_runtime_client()
    contacts = list_contacts_from_db(None)
    updated_count = 0
    skipped_count = 0
    untouched_count = 0

    for contact in contacts:
        external_userid = contact.get("external_userid", "")
        state = contact_description_state(contact.get("description"), external_userid)
        if state == "target":
            untouched_count += 1
            continue
        if state == "custom":
            skipped_count += 1
            continue

        owner_userid = contact.get("owner_userid") or _default_owner_userid()
        target_description = target_contact_description(external_userid)
        client.update_contact_description(
            {
                "userid": owner_userid,
                "external_userid": external_userid,
                "description": target_description,
            }
        )
        update_contact_description_snapshot(external_userid, target_description)
        updated_count += 1
        contacts_logger.info(
            "contact description normalized external_userid=%s previous_state=%s",
            external_userid,
            state,
        )

    return {
        "scanned_count": len(contacts),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "untouched_count": untouched_count,
        "contacts_total": count_contacts(),
    }
