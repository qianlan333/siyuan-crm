from __future__ import annotations

import logging
from typing import Any, Callable

from ...wecom_client import WeComClient, WeComClientError
from . import repo


LEGACY_DESCRIPTION_PREFIX = "external_userid:"
contacts_logger = logging.getLogger("contacts_sync")
wecom_logger = logging.getLogger("wecom_api")


def _select_follow_user(payload: dict[str, Any], owner_userid: str | None = None) -> dict[str, Any]:
    follow_users = payload.get("follow_user") or []
    if owner_userid:
        matched = next((item for item in follow_users if item.get("userid") == owner_userid), None)
        if matched:
            return matched
    return follow_users[0] if follow_users else {}


def normalize_contact_record(payload: dict[str, Any], owner_userid: str | None = None) -> dict[str, Any]:
    external_contact = payload.get("external_contact") or payload
    primary_follow_user = _select_follow_user(payload, owner_userid=owner_userid)
    normalized_owner = owner_userid or primary_follow_user.get("userid") or payload.get("owner_userid") or ""
    return {
        "external_userid": external_contact.get("external_userid", ""),
        "customer_name": external_contact.get("name", ""),
        "owner_userid": normalized_owner,
        "remark": primary_follow_user.get("remark", ""),
        "description": primary_follow_user.get("description", ""),
    }


def target_contact_description(external_userid: str) -> str:
    return str(external_userid or "").strip()


def contact_description_state(description: str | None, external_userid: str) -> str:
    normalized = (description or "").strip()
    target = target_contact_description(external_userid)
    if not normalized:
        return "empty"
    if normalized == target:
        return "target"
    if normalized == f"{LEGACY_DESCRIPTION_PREFIX} {target}" or normalized == f"{LEGACY_DESCRIPTION_PREFIX}{target}":
        return "legacy"
    return "custom"


def needs_contact_description_update(description: str | None, external_userid: str) -> bool:
    return contact_description_state(description, external_userid) in {"empty", "legacy"}


def plan_contact_description_fix(
    payload: dict[str, Any],
    *,
    owner_userid: str | None = None,
    existing_contact: dict[str, Any] | None = None,
    default_owner_userid: str = "",
) -> dict[str, Any]:
    normalized_original = normalize_contact_record(payload, owner_userid=owner_userid)
    external_userid = str(normalized_original.get("external_userid") or "").strip()
    result = {
        "external_userid": external_userid,
        "normalized_original": dict(normalized_original),
        "normalized": dict(normalized_original),
        "should_update": False,
        "target_description": target_contact_description(external_userid) if external_userid else "",
        "description_state": contact_description_state(normalized_original.get("description"), external_userid)
        if external_userid
        else "",
        "resolved_owner_userid": (
            str(normalized_original.get("owner_userid") or "").strip()
            or str(owner_userid or "").strip()
            or str(default_owner_userid or "").strip()
        ),
        "update_payload": None,
    }
    if not external_userid:
        return result
    if existing_contact and contact_description_state(existing_contact.get("description"), external_userid) == "custom":
        normalized = dict(normalized_original)
        normalized["description"] = str(existing_contact.get("description") or "").strip()
        result["normalized"] = normalized
        return result
    if not result["resolved_owner_userid"]:
        return result
    if needs_contact_description_update(normalized_original.get("description"), external_userid):
        normalized = dict(normalized_original)
        normalized["description"] = result["target_description"]
        result["normalized"] = normalized
        result["should_update"] = True
        result["update_payload"] = {
            "userid": result["resolved_owner_userid"],
            "external_userid": external_userid,
            "description": result["target_description"],
        }
    return result


def enrich_contact_context(
    contact: dict[str, Any],
    *,
    get_owner_role: Callable[[str], dict[str, Any] | None],
    get_contact_tag_snapshots: Callable[[str], list[dict[str, Any]]],
    resolve_signup_status_from_tags: Callable[[list[dict[str, Any]]], dict[str, Any]],
    resolve_contact_routing_context: Callable[[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    owner_userid = str(contact.get("owner_userid") or "").strip()
    owner_role = get_owner_role(owner_userid) or {}
    enriched = dict(contact)
    tags = get_contact_tag_snapshots(str(contact.get("external_userid") or ""))
    if owner_userid:
        owner_scoped_tags = [item for item in tags if str(item.get("userid") or "").strip() == owner_userid]
        if owner_scoped_tags:
            tags = owner_scoped_tags
    signup_context = resolve_signup_status_from_tags(tags)
    enriched["tags"] = tags
    enriched["owner_role"] = owner_role.get("role", "") or ""
    enriched["owner_role_map"] = owner_role or {}
    enriched["signup_status"] = signup_context["signup_status"]
    enriched["matched_signup_rules"] = signup_context["matched_signup_rules"]
    enriched["routing_context"] = resolve_contact_routing_context(
        owner_userid=owner_userid,
        owner_role=enriched["owner_role"],
        signup_status=enriched["signup_status"],
    )
    return enriched


def get_contact_by_external_userid(
    external_userid: str,
    *,
    refresh_tags: bool = False,
    refresh_contact_tags_for_external_userid: Callable[..., dict[str, Any]],
    enrich_contact_context: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    if refresh_tags:
        refresh_contact_tags_for_external_userid(external_userid=normalized_external_userid)
    row = repo.get_contact_row_by_external_userid(normalized_external_userid)
    if not row:
        return None
    return enrich_contact_context(dict(row))


def list_contacts(owner_userid: str | None = None) -> list[dict[str, Any]]:
    return repo.list_contacts(owner_userid)


def upsert_contacts(records: list[dict[str, Any]]) -> tuple[int, int]:
    return repo.upsert_contacts(records)


def update_contact_description_snapshot(external_userid: str, description: str) -> None:
    repo.update_contact_description_snapshot(external_userid, description)


def _log_wecom_client_error(
    exc: WeComClientError,
    *,
    owner_userid: str = "",
    external_userid: str = "",
    stage: str = "",
) -> None:
    errcode = (exc.payload or {}).get("errcode")
    errmsg = (exc.payload or {}).get("errmsg")
    wecom_logger.error(
        "stage=%s errcode=%s errmsg=%s owner_userid=%s external_userid=%s",
        stage or exc.stage or "",
        errcode,
        errmsg or str(exc),
        owner_userid,
        external_userid,
    )


def sync_contact_detail_with_description_fix(
    client: WeComClient,
    detail: dict[str, Any],
    *,
    owner_userid: str = "",
    default_owner_userid: str = "",
    tolerate_update_error: bool,
    log_stage: str,
    get_contact_by_external_userid_fn: Callable[[str], dict[str, Any] | None] | None = None,
) -> tuple[dict[str, Any], bool]:
    external_userid = str(((detail.get("external_contact") or detail).get("external_userid")) or "").strip()
    existing_contact = (
        get_contact_by_external_userid_fn(external_userid)
        if external_userid and get_contact_by_external_userid_fn is not None
        else repo.get_contact_row_by_external_userid(external_userid)
        if external_userid
        else None
    )
    plan = plan_contact_description_fix(
        detail,
        owner_userid=owner_userid or None,
        existing_contact=dict(existing_contact) if existing_contact else None,
        default_owner_userid=default_owner_userid,
    )
    normalized = dict(plan["normalized"])
    if not plan["should_update"]:
        return normalized, False
    try:
        client.update_contact_description(plan["update_payload"])
        contacts_logger.info(
            "contact description updated external_userid=%s mode=%s",
            external_userid,
            log_stage,
        )
        return normalized, True
    except WeComClientError as exc:
        _log_wecom_client_error(
            exc,
            owner_userid=str(plan.get("resolved_owner_userid") or ""),
            external_userid=external_userid,
            stage=f"{log_stage}.update_description",
        )
        if not tolerate_update_error:
            raise
        return dict(plan["normalized_original"]), False


def sync_contacts_for_owner_from_wecom(
    owner_userid: str,
    *,
    default_owner_userid: str,
) -> list[dict[str, Any]]:
    client = WeComClient.from_app()
    result = client.list_contacts(owner_userid)
    records: list[dict[str, Any]] = []
    for external_userid in result.get("external_userid") or []:
        if not external_userid:
            continue
        detail = client.get_contact(external_userid)
        normalized, _ = sync_contact_detail_with_description_fix(
            client,
            detail,
            owner_userid=owner_userid,
            default_owner_userid=default_owner_userid,
            tolerate_update_error=True,
            log_stage="external_contact.read_list",
        )
        records.append(normalized)
    if records:
        repo.upsert_contacts(records)
    return records


def sync_contact_from_wecom(
    external_userid: str,
    *,
    owner_userid: str = "",
    default_owner_userid: str,
) -> dict[str, Any]:
    client = WeComClient.from_app()
    detail = client.get_contact(external_userid)
    normalized, _ = sync_contact_detail_with_description_fix(
        client,
        detail,
        owner_userid=owner_userid,
        default_owner_userid=default_owner_userid,
        tolerate_update_error=True,
        log_stage="external_contact.read_detail",
    )
    repo.upsert_contacts([normalized])
    return normalized


def update_contact_description_from_wecom(
    *,
    external_userid: str,
    description: str,
    userid: str,
) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = client.update_contact_description(
        {
            "userid": userid,
            "external_userid": external_userid,
            "description": description,
        }
    )
    detail = client.get_contact(external_userid)
    repo.upsert_contacts([normalize_contact_record(detail, owner_userid=userid)])
    return result
