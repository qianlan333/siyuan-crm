from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...db import get_db
from . import repo


CAMPAIGN_READY_POOL = "campaign_ready"
SOURCE_TYPE = "sidebar_binding_campaign_backfill"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class SidebarBindingCandidate:
    external_userid: str
    phone: str
    person_id: int
    owner_staff_id: str
    customer_name: str


def _candidate_from_row(row: dict[str, Any]) -> SidebarBindingCandidate | None:
    external_userid = _text(row.get("external_userid"))
    phone = _text(row.get("phone"))
    person_id = _positive_int(row.get("person_id"))
    if not external_userid or not phone or person_id is None:
        return None
    owner_staff_id = (
        _text(row.get("active_follow_userid"))
        or _text(row.get("last_owner_userid"))
        or _text(row.get("first_owner_userid"))
        or _text(row.get("contact_owner_userid"))
    )
    return SidebarBindingCandidate(
        external_userid=external_userid,
        phone=phone,
        person_id=person_id,
        owner_staff_id=owner_staff_id,
        customer_name=_text(row.get("customer_name")),
    )


def get_sidebar_binding_campaign_candidate(external_userid: str) -> SidebarBindingCandidate | None:
    normalized_external_userid = _text(external_userid)
    if not normalized_external_userid:
        return None
    db = get_db()
    row = db.execute(
        """
        SELECT
            b.external_userid,
            p.id AS person_id,
            p.mobile AS phone,
            b.last_owner_userid,
            b.first_owner_userid,
            c.owner_userid AS contact_owner_userid,
            COALESCE(NULLIF(c.customer_name, ''), NULLIF(c.remark, '')) AS customer_name,
            (
                SELECT wf.user_id
                FROM wecom_external_contact_follow_users wf
                WHERE wf.external_userid = b.external_userid
                  AND wf.relation_status = 'active'
                  AND wf.user_id <> ''
                ORDER BY
                  CASE WHEN wf.is_primary THEN 0 ELSE 1 END ASC,
                  wf.updated_at DESC,
                  wf.id DESC
                LIMIT 1
            ) AS active_follow_userid
        FROM external_contact_bindings b
        JOIN people p ON p.id = b.person_id
        LEFT JOIN contacts c ON c.external_userid = b.external_userid
        WHERE b.external_userid = ?
          AND b.external_userid <> ''
          AND p.mobile <> ''
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    return _candidate_from_row(dict(row) if row else {})


def list_sidebar_binding_campaign_candidates(*, limit: int = 1000, offset: int = 0) -> list[SidebarBindingCandidate]:
    safe_limit = max(1, int(limit or 1000))
    safe_offset = max(0, int(offset or 0))
    db = get_db()
    rows = db.execute(
        """
        SELECT
            b.external_userid,
            p.id AS person_id,
            p.mobile AS phone,
            b.last_owner_userid,
            b.first_owner_userid,
            c.owner_userid AS contact_owner_userid,
            COALESCE(NULLIF(c.customer_name, ''), NULLIF(c.remark, '')) AS customer_name,
            (
                SELECT wf.user_id
                FROM wecom_external_contact_follow_users wf
                WHERE wf.external_userid = b.external_userid
                  AND wf.relation_status = 'active'
                  AND wf.user_id <> ''
                ORDER BY
                  CASE WHEN wf.is_primary THEN 0 ELSE 1 END ASC,
                  wf.updated_at DESC,
                  wf.id DESC
                LIMIT 1
            ) AS active_follow_userid
        FROM external_contact_bindings b
        JOIN people p ON p.id = b.person_id
        LEFT JOIN contacts c ON c.external_userid = b.external_userid
        WHERE b.external_userid <> ''
          AND p.mobile <> ''
        ORDER BY b.updated_at DESC, b.external_userid ASC
        LIMIT ? OFFSET ?
        """,
        (safe_limit, safe_offset),
    ).fetchall()
    candidates: list[SidebarBindingCandidate] = []
    for row in rows:
        candidate = _candidate_from_row(dict(row))
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _member_payload(candidate: SidebarBindingCandidate, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    return {
        "external_contact_id": candidate.external_userid,
        "phone": _text(existing.get("phone")) or candidate.phone,
        "master_customer_id": _positive_int(existing.get("master_customer_id")) or candidate.person_id,
        "owner_staff_id": _text(existing.get("owner_staff_id")) or candidate.owner_staff_id,
        "in_pool": bool(existing.get("in_pool")) if existing else False,
        "current_pool": _text(existing.get("current_pool")) or CAMPAIGN_READY_POOL,
        "follow_type": _text(existing.get("follow_type")),
        "questionnaire_status": _text(existing.get("questionnaire_status")) or "pending",
        "decision_source": _text(existing.get("decision_source")) or SOURCE_TYPE,
        "source_type": _text(existing.get("source_type")) or SOURCE_TYPE,
        "source_channel_id": existing.get("source_channel_id"),
        "last_active_pool": _text(existing.get("last_active_pool")),
        "joined_at": _text(existing.get("joined_at")),
        "last_ai_push_at": _text(existing.get("last_ai_push_at")),
        "ai_cooldown_until": _text(existing.get("ai_cooldown_until")),
        "current_audience_code": _text(existing.get("current_audience_code")) or "pending_questionnaire",
        "current_audience_entered_at": _text(existing.get("current_audience_entered_at")),
    }


def ensure_campaign_member_from_sidebar_binding(
    external_userid: str,
    *,
    dry_run: bool = False,
    commit: bool = True,
) -> dict[str, Any]:
    candidate = get_sidebar_binding_campaign_candidate(external_userid)
    if candidate is None:
        return {
            "ok": False,
            "status": "not_found",
            "external_userid": _text(external_userid),
            "error": "sidebar_binding_candidate_not_found",
            "dry_run": bool(dry_run),
        }

    existing = repo.get_member_by_external_contact_id(candidate.external_userid)
    payload = _member_payload(candidate, existing)
    action = "exists"
    member = existing
    if existing:
        needs_update = (
            not _text(existing.get("phone"))
            or _positive_int(existing.get("master_customer_id")) is None
            or not _text(existing.get("owner_staff_id"))
        )
        action = "update" if needs_update else "exists"
        if needs_update and not dry_run:
            member = repo.update_member(int(existing["id"]), payload)
    else:
        action = "insert"
        if not dry_run:
            member = repo.insert_member(payload)
    if not dry_run and commit:
        get_db().commit()
    return {
        "ok": True,
        "status": action,
        "dry_run": bool(dry_run),
        "external_userid": candidate.external_userid,
        "phone": candidate.phone,
        "person_id": candidate.person_id,
        "owner_staff_id": candidate.owner_staff_id,
        "member_id": _positive_int((member or {}).get("id")),
        "member": member or payload,
    }


def refresh_campaign_members_from_sidebar_bindings(
    *,
    limit: int = 1000,
    offset: int = 0,
    dry_run: bool = False,
    commit: bool = True,
) -> dict[str, Any]:
    candidates = list_sidebar_binding_campaign_candidates(limit=limit, offset=offset)
    items: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            items.append(
                ensure_campaign_member_from_sidebar_binding(
                    candidate.external_userid,
                    dry_run=dry_run,
                    commit=False,
                )
            )
        except Exception as exc:
            failures.append({"external_userid": candidate.external_userid, "error": str(exc)})
    if not dry_run and commit:
        get_db().commit()
    status_counts: dict[str, int] = {}
    for item in items:
        status = _text(item.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "ok": not failures,
        "dry_run": bool(dry_run),
        "source": "sidebar_bindings",
        "selected_count": len(candidates),
        "processed_count": len(items) + len(failures),
        "success_count": len(items),
        "failure_count": len(failures),
        "status_counts": status_counts,
        "items": items,
        "failures": failures,
        "limit": max(1, int(limit or 1000)),
        "offset": max(0, int(offset or 0)),
    }
