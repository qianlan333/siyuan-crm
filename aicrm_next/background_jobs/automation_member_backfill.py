from __future__ import annotations

from typing import Any, Protocol

from .db import connect, has_database_url


class AutomationMemberBackfillRepository(Protocol):
    def list_sidebar_bound_contacts(self, *, limit: int, offset: int = 0, external_userid: str = "") -> list[dict[str, Any]]: ...
    def upsert_campaign_ready_member(self, row: dict[str, Any], *, dry_run: bool) -> dict[str, Any]: ...


class PostgresAutomationMemberBackfillRepository:
    def list_sidebar_bound_contacts(self, *, limit: int, offset: int = 0, external_userid: str = "") -> list[dict[str, Any]]:
        clauses = ["ecb.external_userid <> ''"]
        params: list[Any] = []
        if external_userid:
            clauses.append("ecb.external_userid = %s")
            params.append(external_userid)
        params.extend([int(limit), int(offset)])
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ecb.external_userid,
                       ecb.person_id,
                       COALESCE(p.mobile, '') AS mobile,
                       COALESCE(c.owner_userid, ecb.last_owner_userid, ecb.first_owner_userid, '') AS owner_userid
                FROM external_contact_bindings ecb
                LEFT JOIN people p ON p.id = ecb.person_id
                LEFT JOIN contacts c ON c.external_userid = ecb.external_userid
                WHERE {" AND ".join(clauses)}
                ORDER BY ecb.updated_at DESC, ecb.external_userid ASC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_campaign_ready_member(self, row: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        external_userid = _text(row.get("external_userid"))
        if not external_userid:
            return {"ok": False, "status": "skipped", "reason": "missing_external_userid"}
        with connect() as conn:
            existing = conn.execute(
                "SELECT * FROM automation_member WHERE external_contact_id = %s LIMIT 1",
                (external_userid,),
            ).fetchone()
            status = "update" if existing else "insert"
            if dry_run:
                return {"ok": True, "status": status, "external_userid": external_userid, "dry_run": True}
            if existing:
                conn.execute(
                    """
                    UPDATE automation_member
                    SET phone = CASE WHEN COALESCE(phone, '') = '' THEN %s ELSE phone END,
                        master_customer_id = COALESCE(master_customer_id, %s),
                        owner_staff_id = CASE WHEN COALESCE(owner_staff_id, '') = '' THEN %s ELSE owner_staff_id END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE external_contact_id = %s
                    """,
                    (
                        _text(row.get("mobile")),
                        row.get("person_id"),
                        _text(row.get("owner_userid")),
                        external_userid,
                    ),
                )
                return {"ok": True, "status": "update", "external_userid": external_userid, "dry_run": False}
            conn.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, master_customer_id, owner_staff_id,
                    in_pool, current_pool, questionnaire_status, decision_source,
                    source_type, current_audience_code, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, false, 'campaign_ready', 'pending', 'system',
                        'sidebar_binding_campaign_backfill', 'pending_questionnaire',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    external_userid,
                    _text(row.get("mobile")),
                    row.get("person_id"),
                    _text(row.get("owner_userid")),
                ),
            )
            return {"ok": True, "status": "insert", "external_userid": external_userid, "dry_run": False}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _empty_summary(*, limit: int, offset: int, external_userid: str, dry_run: bool, ok: bool = True) -> dict[str, Any]:
    return {
        "ok": ok,
        "job": "automation_member_backfill",
        "limit": int(limit),
        "offset": int(offset),
        "external_userid": external_userid,
        "dry_run": bool(dry_run),
        "processed": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }


def run_automation_member_backfill(
    *,
    limit: int = 5000,
    offset: int = 0,
    external_userid: str = "",
    dry_run: bool = False,
    repo: AutomationMemberBackfillRepository | None = None,
) -> dict[str, Any]:
    summary = _empty_summary(limit=limit, offset=offset, external_userid=_text(external_userid), dry_run=dry_run)
    if int(limit) <= 0:
        return {**summary, "ok": False, "errors": [{"code": "invalid_limit", "message": "limit must be >= 1"}]}
    if int(offset) < 0:
        return {**summary, "ok": False, "errors": [{"code": "invalid_offset", "message": "offset must be >= 0"}]}
    if repo is None and not has_database_url():
        payload = {
            **summary,
            "status": "skipped",
            "skipped": 1,
            "skipped_components": [
                {"component": "postgres_repository", "status": "skipped", "reason": "database_url_missing"}
            ],
        }
        if dry_run:
            return payload
        return {**payload, "ok": False, "errors": [{"code": "database_url_missing", "message": "DATABASE_URL is required"}]}
    repo = repo or PostgresAutomationMemberBackfillRepository()
    try:
        candidates = repo.list_sidebar_bound_contacts(
            limit=int(limit),
            offset=int(offset),
            external_userid=_text(external_userid),
        )
        for candidate in candidates:
            outcome = repo.upsert_campaign_ready_member(candidate, dry_run=dry_run)
            summary["processed"] += 1
            status = _text(outcome.get("status"))
            if status == "insert":
                summary["created"] += 1
            elif status == "update":
                summary["updated"] += 1
            else:
                summary["skipped"] += 1
            if not outcome.get("ok"):
                summary["errors"].append({"external_userid": candidate.get("external_userid"), "reason": outcome.get("reason")})
        summary["ok"] = not summary["errors"]
        return summary
    except Exception as exc:
        return {**summary, "ok": False, "errors": [{"code": "automation_member_backfill_failed", "message": str(exc)}]}
