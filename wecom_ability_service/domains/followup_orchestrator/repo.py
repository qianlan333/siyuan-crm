from __future__ import annotations

import json
from typing import Any

from ...db import get_db


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_storage(value: Any, *, default: str) -> str:
    if value in (None, ""):
        return default
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return default


def _required_tenant_key(tenant_key: str) -> str:
    normalized = _normalized_text(tenant_key)
    if not normalized:
        raise ValueError("tenant_key is required")
    return normalized


def _nullable_int(value: Any) -> int | None:
    if value in (None, "", 0):
        return None
    return int(value)


def _fetchone_dict(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dict(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _deserialize_mission_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "mission_key": _normalized_text(row.get("mission_key")),
        "tenant_key": _normalized_text(row.get("tenant_key")),
        "mission_type": _normalized_text(row.get("mission_type")),
        "mission_status": _normalized_text(row.get("mission_status")) or "unassigned",
        "owner_userid": _normalized_text(row.get("owner_userid")),
        "team_scope_key": _normalized_text(row.get("team_scope_key")),
        "source_type": _normalized_text(row.get("source_type")),
        "summary": _normalized_text(row.get("summary")),
        "priority_score": float(row.get("priority_score") or 0),
        "item_count": int(row.get("item_count") or 0),
        "requires_manager_approval": bool(row.get("requires_manager_approval")),
        "payload": _json_loads(row.get("payload_json"), default={}),
        "created_by": _normalized_text(row.get("created_by")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _deserialize_mission_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "mission_id": int(row.get("mission_id") or 0),
        "tenant_key": _normalized_text(row.get("tenant_key")),
        "mission_item_key": _normalized_text(row.get("mission_item_key")),
        "item_status": _normalized_text(row.get("item_status")) or "suggested",
        "assignment_status": _normalized_text(row.get("assignment_status")) or "suggested",
        "external_userid": _normalized_text(row.get("external_userid")),
        "customer_name": _normalized_text(row.get("customer_name")),
        "owner_userid": _normalized_text(row.get("owner_userid")),
        "suggested_assignee_userid": _normalized_text(row.get("suggested_assignee_userid")),
        "pulse_card_id": int(row.get("pulse_card_id") or 0),
        "pulse_snapshot_id": int(row.get("pulse_snapshot_id") or 0),
        "payload": _json_loads(row.get("payload_json"), default={}),
        "evidence_refs": _json_loads(row.get("evidence_refs_json"), default=[]),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _deserialize_assignment_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "mission_id": int(row.get("mission_id") or 0),
        "mission_item_id": int(row.get("mission_item_id") or 0),
        "tenant_key": _normalized_text(row.get("tenant_key")),
        "decision_type": _normalized_text(row.get("decision_type")),
        "decision_status": _normalized_text(row.get("decision_status")) or "suggested",
        "current_owner_userid": _normalized_text(row.get("current_owner_userid")),
        "suggested_owner_userid": _normalized_text(row.get("suggested_owner_userid")),
        "decided_by_userid": _normalized_text(row.get("decided_by_userid")),
        "approved_by_userid": _normalized_text(row.get("approved_by_userid")),
        "payload": _json_loads(row.get("payload_json"), default={}),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _deserialize_execution_log_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "mission_id": int(row.get("mission_id") or 0),
        "mission_item_id": int(row.get("mission_item_id") or 0),
        "tenant_key": _normalized_text(row.get("tenant_key")),
        "action_type": _normalized_text(row.get("action_type")),
        "execution_status": _normalized_text(row.get("execution_status")),
        "operator": _normalized_text(row.get("operator")),
        "actor_userid": _normalized_text(row.get("actor_userid")),
        "actor_role": _normalized_text(row.get("actor_role")),
        "resource_type": _normalized_text(row.get("resource_type")),
        "resource_id": _normalized_text(row.get("resource_id")),
        "tenant_context": _json_loads(row.get("tenant_context_json"), default={}),
        "request_payload": _json_loads(row.get("request_payload_json"), default={}),
        "result_payload": _json_loads(row.get("result_payload_json"), default={}),
        "error_message": _normalized_text(row.get("error_message")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def list_followup_orchestrator_policies(*, tenant_key: str) -> list[dict[str, Any]]:
    rows = _fetchall_dict(
        """
        SELECT id, tenant_key, policy_key, policy_type, policy_scope, payload_json, created_by, created_at, updated_at
        FROM followup_orchestrator_policies
        WHERE tenant_key = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (_required_tenant_key(tenant_key),),
    )
    return [
        {
            "id": int(row.get("id") or 0),
            "tenant_key": _normalized_text(row.get("tenant_key")),
            "policy_key": _normalized_text(row.get("policy_key")),
            "policy_type": _normalized_text(row.get("policy_type")),
            "policy_scope": _normalized_text(row.get("policy_scope")),
            "payload": _json_loads(row.get("payload_json"), default={}),
            "created_by": _normalized_text(row.get("created_by")),
            "created_at": _normalized_text(row.get("created_at")),
            "updated_at": _normalized_text(row.get("updated_at")),
        }
        for row in rows
    ]


def get_followup_orchestrator_mission(mission_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_missions
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(mission_id)),
    )
    return _deserialize_mission_row(row) if row else None


def get_followup_orchestrator_mission_by_key(mission_key: str, *, tenant_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_missions
        WHERE tenant_key = ?
          AND mission_key = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), _normalized_text(mission_key)),
    )
    return _deserialize_mission_row(row) if row else None


def list_followup_orchestrator_missions(
    *,
    tenant_key: str,
    owner_userid: str = "",
    mission_status: str = "",
    mission_type: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    normalized_owner_userid = _normalized_text(owner_userid)
    normalized_status = _normalized_text(mission_status)
    normalized_type = _normalized_text(mission_type)
    if normalized_owner_userid:
        clauses.append("(owner_userid = ? OR owner_userid = '')")
        params.append(normalized_owner_userid)
    if normalized_status:
        clauses.append("mission_status = ?")
        params.append(normalized_status)
    if normalized_type:
        clauses.append("mission_type = ?")
        params.append(normalized_type)
    params.append(max(1, min(int(limit or 20), 200)))
    rows = _fetchall_dict(
        f"""
        SELECT *
        FROM followup_orchestrator_missions
        WHERE {' AND '.join(clauses)}
        ORDER BY priority_score DESC, updated_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_deserialize_mission_row(row) for row in rows]


def list_followup_orchestrator_missions_for_actor(
    *,
    tenant_key: str,
    actor_userid: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    normalized_actor_userid = _normalized_text(actor_userid)
    if not normalized_actor_userid:
        return []
    rows = _fetchall_dict(
        """
        SELECT DISTINCT m.*
        FROM followup_orchestrator_missions AS m
        LEFT JOIN followup_orchestrator_mission_items AS i
          ON i.tenant_key = m.tenant_key
         AND i.mission_id = m.id
        WHERE m.tenant_key = ?
          AND (
            m.owner_userid = ?
            OR i.owner_userid = ?
            OR i.suggested_assignee_userid = ?
          )
        ORDER BY m.priority_score DESC, m.updated_at DESC, m.id DESC
        LIMIT ?
        """,
        (_required_tenant_key(tenant_key), normalized_actor_userid, normalized_actor_userid, normalized_actor_userid, max(1, min(int(limit or 50), 200))),
    )
    return [_deserialize_mission_row(row) for row in rows]


def upsert_followup_orchestrator_mission(
    *,
    tenant_key: str,
    mission_key: str,
    mission_type: str,
    mission_status: str,
    owner_userid: str,
    team_scope_key: str,
    source_type: str,
    summary: str,
    priority_score: float,
    item_count: int,
    requires_manager_approval: bool,
    payload: Any,
    created_by: str,
) -> dict[str, Any]:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    normalized_mission_key = _normalized_text(mission_key)
    if not normalized_mission_key:
        raise ValueError("mission_key is required")
    db = get_db()
    existing = get_followup_orchestrator_mission_by_key(normalized_mission_key, tenant_key=resolved_tenant_key)
    if existing:
        db.execute(
            """
            UPDATE followup_orchestrator_missions
            SET mission_type = ?,
                mission_status = ?,
                owner_userid = ?,
                team_scope_key = ?,
                source_type = ?,
                summary = ?,
                priority_score = ?,
                item_count = ?,
                requires_manager_approval = ?,
                payload_json = ?,
                created_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_key = ?
              AND mission_key = ?
            """,
            (
                _normalized_text(mission_type),
                _normalized_text(mission_status),
                _normalized_text(owner_userid),
                _normalized_text(team_scope_key),
                _normalized_text(source_type),
                _normalized_text(summary),
                float(priority_score or 0),
                int(item_count or 0),
                bool(requires_manager_approval),
                _json_storage(payload, default="{}"),
                _normalized_text(created_by),
                resolved_tenant_key,
                normalized_mission_key,
            ),
        )
        db.commit()
        return get_followup_orchestrator_mission_by_key(normalized_mission_key, tenant_key=resolved_tenant_key) or {}
    row = db.execute(
        """
        INSERT INTO followup_orchestrator_missions (
            tenant_key,
            mission_key,
            mission_type,
            mission_status,
            owner_userid,
            team_scope_key,
            source_type,
            summary,
            priority_score,
            item_count,
            requires_manager_approval,
            payload_json,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            resolved_tenant_key,
            normalized_mission_key,
            _normalized_text(mission_type),
            _normalized_text(mission_status),
            _normalized_text(owner_userid),
            _normalized_text(team_scope_key),
            _normalized_text(source_type),
            _normalized_text(summary),
            float(priority_score or 0),
            int(item_count or 0),
            bool(requires_manager_approval),
            _json_storage(payload, default="{}"),
            _normalized_text(created_by),
        ),
    ).fetchone()
    db.commit()
    return get_followup_orchestrator_mission(int((row or {}).get("id") or 0), tenant_key=resolved_tenant_key) or {}


def update_followup_orchestrator_mission(mission_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {
        "mission_status",
        "owner_userid",
        "team_scope_key",
        "summary",
        "priority_score",
        "item_count",
        "requires_manager_approval",
        "payload_json",
    }
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "payload_json":
            value = _json_storage(value, default="{}")
        if key == "priority_score":
            value = float(value or 0)
        if key == "item_count":
            value = int(value or 0)
        assignments.append(f"{key} = ?")
        params.append(value)
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not assignments:
        return get_followup_orchestrator_mission(int(mission_id), tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    get_db().execute(
        f"""
        UPDATE followup_orchestrator_missions
        SET {", ".join(assignments)}
        WHERE tenant_key = ?
          AND id = ?
        """,
        tuple([*params, resolved_tenant_key, int(mission_id)]),
    )
    get_db().commit()
    return get_followup_orchestrator_mission(int(mission_id), tenant_key=resolved_tenant_key) or {}


def get_followup_orchestrator_mission_item(item_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_mission_items
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(item_id)),
    )
    return _deserialize_mission_item_row(row) if row else None


def get_followup_orchestrator_mission_item_by_key(mission_item_key: str, *, tenant_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_mission_items
        WHERE tenant_key = ?
          AND mission_item_key = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), _normalized_text(mission_item_key)),
    )
    return _deserialize_mission_item_row(row) if row else None


def list_followup_orchestrator_mission_items(
    *,
    tenant_key: str,
    mission_id: int | None = None,
    external_userid: str = "",
    owner_userid: str = "",
    suggested_assignee_userid: str = "",
    item_status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    if mission_id is not None and int(mission_id) > 0:
        clauses.append("mission_id = ?")
        params.append(int(mission_id))
    normalized_external_userid = _normalized_text(external_userid)
    normalized_owner_userid = _normalized_text(owner_userid)
    normalized_assignee_userid = _normalized_text(suggested_assignee_userid)
    normalized_status = _normalized_text(item_status)
    if normalized_external_userid:
        clauses.append("external_userid = ?")
        params.append(normalized_external_userid)
    if normalized_owner_userid:
        clauses.append("owner_userid = ?")
        params.append(normalized_owner_userid)
    if normalized_assignee_userid:
        clauses.append("suggested_assignee_userid = ?")
        params.append(normalized_assignee_userid)
    if normalized_status:
        clauses.append("item_status = ?")
        params.append(normalized_status)
    params.append(max(1, min(int(limit or 50), 500)))
    rows = _fetchall_dict(
        f"""
        SELECT *
        FROM followup_orchestrator_mission_items
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_deserialize_mission_item_row(row) for row in rows]


def upsert_followup_orchestrator_mission_item(
    *,
    tenant_key: str,
    mission_id: int,
    mission_item_key: str,
    item_status: str,
    assignment_status: str,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
    suggested_assignee_userid: str,
    pulse_card_id: int | None,
    pulse_snapshot_id: int | None,
    payload: Any,
    evidence_refs: Any,
) -> dict[str, Any]:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_followup_orchestrator_mission(int(mission_id), tenant_key=resolved_tenant_key):
        raise ValueError("mission_id does not belong to tenant")
    normalized_key = _normalized_text(mission_item_key)
    if not normalized_key:
        raise ValueError("mission_item_key is required")
    db = get_db()
    existing = get_followup_orchestrator_mission_item_by_key(normalized_key, tenant_key=resolved_tenant_key)
    if existing:
        db.execute(
            """
            UPDATE followup_orchestrator_mission_items
            SET mission_id = ?,
                item_status = ?,
                assignment_status = ?,
                external_userid = ?,
                customer_name = ?,
                owner_userid = ?,
                suggested_assignee_userid = ?,
                pulse_card_id = ?,
                pulse_snapshot_id = ?,
                payload_json = ?,
                evidence_refs_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_key = ?
              AND mission_item_key = ?
            """,
            (
                int(mission_id),
                _normalized_text(item_status),
                _normalized_text(assignment_status),
                _normalized_text(external_userid),
                _normalized_text(customer_name),
                _normalized_text(owner_userid),
                _normalized_text(suggested_assignee_userid),
                _nullable_int(pulse_card_id),
                _nullable_int(pulse_snapshot_id),
                _json_storage(payload, default="{}"),
                _json_storage(evidence_refs, default="[]"),
                resolved_tenant_key,
                normalized_key,
            ),
        )
        db.commit()
        return get_followup_orchestrator_mission_item_by_key(normalized_key, tenant_key=resolved_tenant_key) or {}
    row = db.execute(
        """
        INSERT INTO followup_orchestrator_mission_items (
            mission_id,
            tenant_key,
            mission_item_key,
            item_status,
            assignment_status,
            external_userid,
            customer_name,
            owner_userid,
            suggested_assignee_userid,
            pulse_card_id,
            pulse_snapshot_id,
            payload_json,
            evidence_refs_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(mission_id),
            resolved_tenant_key,
            normalized_key,
            _normalized_text(item_status),
            _normalized_text(assignment_status),
            _normalized_text(external_userid),
            _normalized_text(customer_name),
            _normalized_text(owner_userid),
            _normalized_text(suggested_assignee_userid),
            _nullable_int(pulse_card_id),
            _nullable_int(pulse_snapshot_id),
            _json_storage(payload, default="{}"),
            _json_storage(evidence_refs, default="[]"),
        ),
    ).fetchone()
    db.commit()
    return get_followup_orchestrator_mission_item(int((row or {}).get("id") or 0), tenant_key=resolved_tenant_key) or {}


def update_followup_orchestrator_mission_item(item_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {
        "mission_id",
        "item_status",
        "assignment_status",
        "owner_userid",
        "suggested_assignee_userid",
        "payload_json",
        "evidence_refs_json",
    }
    assignments: list[str] = []
    params: list[Any] = []
    resolved_tenant_key = _required_tenant_key(tenant_key)
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "mission_id":
            if not get_followup_orchestrator_mission(int(value), tenant_key=resolved_tenant_key):
                raise ValueError("mission_id does not belong to tenant")
            value = int(value)
        if key == "payload_json":
            value = _json_storage(value, default="{}")
        if key == "evidence_refs_json":
            value = _json_storage(value, default="[]")
        assignments.append(f"{key} = ?")
        params.append(value)
    if not assignments:
        return get_followup_orchestrator_mission_item(int(item_id), tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    get_db().execute(
        f"""
        UPDATE followup_orchestrator_mission_items
        SET {", ".join(assignments)}
        WHERE tenant_key = ?
          AND id = ?
        """,
        tuple([*params, resolved_tenant_key, int(item_id)]),
    )
    get_db().commit()
    return get_followup_orchestrator_mission_item(int(item_id), tenant_key=resolved_tenant_key) or {}


def list_followup_orchestrator_unresolved_counts(
    *,
    tenant_key: str,
    external_userids: list[str],
) -> dict[str, int]:
    normalized_userids = [_normalized_text(item) for item in external_userids if _normalized_text(item)]
    if not normalized_userids:
        return {}
    placeholders = ",".join(["?"] * len(normalized_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, COUNT(*) AS total_count
        FROM followup_orchestrator_mission_items
        WHERE tenant_key = ?
          AND external_userid IN ({placeholders})
          AND item_status IN ('unassigned', 'suggested', 'skipped', 'escalated')
        GROUP BY external_userid
        """,
        (_required_tenant_key(tenant_key), *normalized_userids),
    )
    return {_normalized_text(row.get("external_userid")): int(row.get("total_count") or 0) for row in rows}


def mark_followup_orchestrator_missing_items_stale(
    *,
    mission_id: int,
    tenant_key: str,
    active_item_keys: list[str],
    stale_status: str = "skipped",
) -> int:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    normalized_keys = [_normalized_text(item) for item in active_item_keys if _normalized_text(item)]
    clauses = ["tenant_key = ?", "mission_id = ?"]
    params: list[Any] = [resolved_tenant_key, int(mission_id)]
    if normalized_keys:
        placeholders = ",".join(["?"] * len(normalized_keys))
        clauses.append(f"mission_item_key NOT IN ({placeholders})")
        params.extend(normalized_keys)
    params.extend([_normalized_text(stale_status), int(mission_id)])
    cursor = get_db().execute(
        f"""
        UPDATE followup_orchestrator_mission_items
        SET item_status = ?,
            assignment_status = CASE WHEN assignment_status = 'accepted' THEN assignment_status ELSE 'rejected' END,
            updated_at = CURRENT_TIMESTAMP
        WHERE tenant_key = ?
          AND mission_id = ?
          {'AND mission_item_key NOT IN (' + ','.join(['?'] * len(normalized_keys)) + ')' if normalized_keys else ''}
          AND item_status IN ('unassigned', 'suggested')
        """,
        tuple([_normalized_text(stale_status), resolved_tenant_key, int(mission_id), *normalized_keys]),
    )
    get_db().commit()
    return int(getattr(cursor, "rowcount", 0) or 0)


def get_followup_orchestrator_assignment_decision(decision_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_assignment_decisions
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(decision_id)),
    )
    return _deserialize_assignment_decision_row(row) if row else None


def get_followup_orchestrator_assignment_decision_for_item(
    *,
    mission_item_id: int,
    decision_type: str = "",
    tenant_key: str,
) -> dict[str, Any] | None:
    clauses = ["tenant_key = ?", "mission_item_id = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key), int(mission_item_id)]
    normalized_type = _normalized_text(decision_type)
    if normalized_type:
        clauses.append("decision_type = ?")
        params.append(normalized_type)
    row = _fetchone_dict(
        f"""
        SELECT *
        FROM followup_orchestrator_assignment_decisions
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return _deserialize_assignment_decision_row(row) if row else None


def list_followup_orchestrator_assignment_decisions(
    *,
    tenant_key: str,
    mission_id: int | None = None,
    mission_item_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    if mission_id is not None and int(mission_id) > 0:
        clauses.append("mission_id = ?")
        params.append(int(mission_id))
    if mission_item_id is not None and int(mission_item_id) > 0:
        clauses.append("mission_item_id = ?")
        params.append(int(mission_item_id))
    params.append(max(1, min(int(limit or 100), 500)))
    rows = _fetchall_dict(
        f"""
        SELECT *
        FROM followup_orchestrator_assignment_decisions
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_deserialize_assignment_decision_row(row) for row in rows]


def upsert_followup_orchestrator_assignment_decision(
    *,
    tenant_key: str,
    mission_id: int,
    mission_item_id: int,
    decision_type: str,
    decision_status: str,
    current_owner_userid: str,
    suggested_owner_userid: str,
    decided_by_userid: str = "",
    approved_by_userid: str = "",
    payload: Any = None,
) -> dict[str, Any]:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_followup_orchestrator_mission(int(mission_id), tenant_key=resolved_tenant_key):
        raise ValueError("mission_id does not belong to tenant")
    if not get_followup_orchestrator_mission_item(int(mission_item_id), tenant_key=resolved_tenant_key):
        raise ValueError("mission_item_id does not belong to tenant")
    normalized_type = _normalized_text(decision_type)
    if not normalized_type:
        raise ValueError("decision_type is required")
    db = get_db()
    existing = get_followup_orchestrator_assignment_decision_for_item(
        mission_item_id=int(mission_item_id),
        decision_type=normalized_type,
        tenant_key=resolved_tenant_key,
    )
    if existing:
        db.execute(
            """
            UPDATE followup_orchestrator_assignment_decisions
            SET mission_id = ?,
                decision_status = ?,
                current_owner_userid = ?,
                suggested_owner_userid = ?,
                decided_by_userid = ?,
                approved_by_userid = ?,
                payload_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_key = ?
              AND id = ?
            """,
            (
                int(mission_id),
                _normalized_text(decision_status),
                _normalized_text(current_owner_userid),
                _normalized_text(suggested_owner_userid),
                _normalized_text(decided_by_userid),
                _normalized_text(approved_by_userid),
                _json_storage(payload, default="{}"),
                resolved_tenant_key,
                int(existing["id"]),
            ),
        )
        db.commit()
        return get_followup_orchestrator_assignment_decision(int(existing["id"]), tenant_key=resolved_tenant_key) or {}
    row = db.execute(
        """
        INSERT INTO followup_orchestrator_assignment_decisions (
            mission_id,
            mission_item_id,
            tenant_key,
            decision_type,
            decision_status,
            current_owner_userid,
            suggested_owner_userid,
            decided_by_userid,
            approved_by_userid,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(mission_id),
            int(mission_item_id),
            resolved_tenant_key,
            normalized_type,
            _normalized_text(decision_status),
            _normalized_text(current_owner_userid),
            _normalized_text(suggested_owner_userid),
            _normalized_text(decided_by_userid),
            _normalized_text(approved_by_userid),
            _json_storage(payload, default="{}"),
        ),
    ).fetchone()
    db.commit()
    return get_followup_orchestrator_assignment_decision(int((row or {}).get("id") or 0), tenant_key=resolved_tenant_key) or {}


def update_followup_orchestrator_assignment_decision(decision_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {"decision_status", "decided_by_userid", "approved_by_userid", "payload_json"}
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "payload_json":
            value = _json_storage(value, default="{}")
        assignments.append(f"{key} = ?")
        params.append(value)
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not assignments:
        return get_followup_orchestrator_assignment_decision(int(decision_id), tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    get_db().execute(
        f"""
        UPDATE followup_orchestrator_assignment_decisions
        SET {", ".join(assignments)}
        WHERE tenant_key = ?
          AND id = ?
        """,
        tuple([*params, resolved_tenant_key, int(decision_id)]),
    )
    get_db().commit()
    return get_followup_orchestrator_assignment_decision(int(decision_id), tenant_key=resolved_tenant_key) or {}


def insert_followup_orchestrator_execution_log(
    *,
    tenant_key: str,
    mission_id: int,
    mission_item_id: int | None,
    action_type: str,
    execution_status: str,
    operator: str,
    actor_userid: str,
    actor_role: str,
    resource_type: str,
    resource_id: str,
    tenant_context: Any,
    request_payload: Any,
    result_payload: Any,
    error_message: str = "",
) -> dict[str, Any]:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_followup_orchestrator_mission(int(mission_id), tenant_key=resolved_tenant_key):
        raise ValueError("mission_id does not belong to tenant")
    nullable_mission_item_id = _nullable_int(mission_item_id)
    if nullable_mission_item_id is not None and not get_followup_orchestrator_mission_item(nullable_mission_item_id, tenant_key=resolved_tenant_key):
        raise ValueError("mission_item_id does not belong to tenant")
    row = get_db().execute(
        """
        INSERT INTO followup_orchestrator_execution_logs (
            mission_id,
            mission_item_id,
            tenant_key,
            action_type,
            execution_status,
            operator,
            actor_userid,
            actor_role,
            resource_type,
            resource_id,
            tenant_context_json,
            request_payload_json,
            result_payload_json,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(mission_id),
            nullable_mission_item_id,
            resolved_tenant_key,
            _normalized_text(action_type),
            _normalized_text(execution_status),
            _normalized_text(operator),
            _normalized_text(actor_userid),
            _normalized_text(actor_role),
            _normalized_text(resource_type),
            _normalized_text(resource_id),
            _json_storage(tenant_context, default="{}"),
            _json_storage(request_payload, default="{}"),
            _json_storage(result_payload, default="{}"),
            _normalized_text(error_message),
        ),
    ).fetchone()
    get_db().commit()
    log_id = int((row or {}).get("id") or 0)
    fetched = _fetchone_dict(
        """
        SELECT *
        FROM followup_orchestrator_execution_logs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (resolved_tenant_key, log_id),
    )
    return _deserialize_execution_log_row(fetched or {}) if fetched else {}


def list_followup_orchestrator_execution_logs(
    *,
    tenant_key: str,
    mission_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = _fetchall_dict(
        """
        SELECT *
        FROM followup_orchestrator_execution_logs
        WHERE tenant_key = ?
          AND mission_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (_required_tenant_key(tenant_key), int(mission_id), max(1, min(int(limit or 50), 200))),
    )
    return [_deserialize_execution_log_row(row) for row in rows]
