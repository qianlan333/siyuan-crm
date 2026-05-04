from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from ...db import get_db, get_db_backend
from ...infra.constants import USER_OPS_LEAD_POOL_ACTIVATION_STATES


@dataclass(frozen=True)
class PoolCoreRuntime:
    """Internal-only dependency bag for user-ops lead-pool current/history flows."""

    db_bool: Callable[[Any], bool | int]
    normalize_mobile: Callable[[str], str]
    stringify_db_timestamp: Callable[[Any], str]
    current_operator_resolver: Callable[[], str]


def normalize_user_ops_lead_pool_activation_state(
    value: str,
    *,
    allow_unknown: bool = True,
) -> str:
    """Internal stable owner for lead-pool activation-state normalization."""

    normalized = str(value or "").strip()
    if not normalized and allow_unknown:
        return "unknown"
    if normalized not in USER_OPS_LEAD_POOL_ACTIVATION_STATES:
        raise ValueError("huangxiaocan_activation_state must be unknown, activated, or not_activated")
    if normalized == "unknown" and not allow_unknown:
        raise ValueError("activation_state must be activated or not_activated")
    return normalized


def serialize_user_ops_lead_pool_current_row(row: dict[str, Any]) -> dict[str, Any]:
    """Internal stable owner for lead-pool current-row serialization."""

    return {
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": str(row.get("external_userid") or "").strip(),
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": str(row.get("owner_userid") or "").strip(),
        "is_wecom_added": bool(row.get("is_wecom_added")),
        "is_mobile_bound": bool(row.get("is_mobile_bound")),
        "huangxiaocan_activation_state": normalize_user_ops_lead_pool_activation_state(
            str(row.get("huangxiaocan_activation_state") or "").strip(),
            allow_unknown=True,
        ),
        "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
        "class_term_label": str(row.get("class_term_label") or "").strip(),
        "first_entry_source": str(row.get("first_entry_source") or "").strip(),
        "last_entry_source": str(row.get("last_entry_source") or "").strip(),
    }


def get_user_ops_lead_pool_current_row_by_id(
    row_id: int,
    *,
    runtime: PoolCoreRuntime,
) -> dict[str, Any] | None:
    """Internal stable owner for loading one lead-pool current row by id."""

    row = get_db().execute(
        """
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label,
            first_entry_source,
            last_entry_source,
            created_at,
            updated_at
        FROM user_ops_lead_pool_current
        WHERE id = ?
        LIMIT 1
        """,
        (int(row_id),),
    ).fetchone()
    if not row:
        return None
    payload = serialize_user_ops_lead_pool_current_row(dict(row))
    payload["id"] = row["id"]
    payload["created_at"] = runtime.stringify_db_timestamp(row.get("created_at"))
    payload["updated_at"] = runtime.stringify_db_timestamp(row.get("updated_at"))
    return payload


def list_user_ops_lead_pool_matches(
    *,
    mobile: str,
    external_userid: str,
    runtime: PoolCoreRuntime,
) -> list[dict[str, Any]]:
    """Internal stable owner for lead-pool duplicate/match enumeration."""

    conditions: list[str] = []
    params: list[Any] = []
    if mobile:
        conditions.append("mobile = ?")
        params.append(mobile)
    if external_userid:
        conditions.append("external_userid = ?")
        params.append(external_userid)
    if not conditions:
        return []
    rows = get_db().execute(
        f"""
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label,
            first_entry_source,
            last_entry_source,
            created_at,
            updated_at
        FROM user_ops_lead_pool_current
        WHERE {" OR ".join(conditions)}
        ORDER BY id ASC
        """,
        tuple(params),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = serialize_user_ops_lead_pool_current_row(dict(row))
        item["id"] = row["id"]
        item["created_at"] = runtime.stringify_db_timestamp(row.get("created_at"))
        item["updated_at"] = runtime.stringify_db_timestamp(row.get("updated_at"))
        items.append(item)
    return items


def plan_user_ops_lead_pool_member_upsert(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
    runtime: PoolCoreRuntime,
) -> dict[str, Any]:
    """Internal stable owner for lead-pool current-row merge planning."""

    normalized_mobile = runtime.normalize_mobile(mobile) if str(mobile or "").strip() else ""
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_mobile and not normalized_external_userid:
        raise ValueError("mobile or external_userid is required")

    normalized_entry_source = str(entry_source or "").strip() or "manual"
    normalized_customer_name = str(customer_name or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_class_term_label = str(class_term_label or "").strip()
    normalized_activation_state = normalize_user_ops_lead_pool_activation_state(
        huangxiaocan_activation_state,
        allow_unknown=True,
    )
    matches = list_user_ops_lead_pool_matches(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
        runtime=runtime,
    )
    target: dict[str, Any] | None = None
    if normalized_mobile:
        target = next((item for item in matches if item["mobile"] == normalized_mobile), None)
    if target is None and normalized_external_userid:
        target = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
    duplicate_ids = [item["id"] for item in matches if target is not None and item["id"] != target["id"]]

    merged = serialize_user_ops_lead_pool_current_row(target or {})
    for item in matches:
        if not merged["mobile"] and item["mobile"]:
            merged["mobile"] = item["mobile"]
        if not merged["external_userid"] and item["external_userid"]:
            merged["external_userid"] = item["external_userid"]
        if not merged["customer_name"] and item["customer_name"]:
            merged["customer_name"] = item["customer_name"]
        if not merged["owner_userid"] and item["owner_userid"]:
            merged["owner_userid"] = item["owner_userid"]
        if not merged["first_entry_source"] and item["first_entry_source"]:
            merged["first_entry_source"] = item["first_entry_source"]
        if not merged["last_entry_source"] and item["last_entry_source"]:
            merged["last_entry_source"] = item["last_entry_source"]
        if merged["class_term_no"] is None and item["class_term_no"] is not None:
            merged["class_term_no"] = item["class_term_no"]
            merged["class_term_label"] = item["class_term_label"]
        if merged["huangxiaocan_activation_state"] == "unknown" and item["huangxiaocan_activation_state"] != "unknown":
            merged["huangxiaocan_activation_state"] = item["huangxiaocan_activation_state"]
        merged["is_wecom_added"] = bool(merged["is_wecom_added"] or item["is_wecom_added"])
        merged["is_mobile_bound"] = bool(merged["is_mobile_bound"] or item["is_mobile_bound"])

    if normalized_mobile:
        merged["mobile"] = normalized_mobile
    if normalized_external_userid:
        merged["external_userid"] = normalized_external_userid
    if normalized_customer_name:
        merged["customer_name"] = normalized_customer_name
    if normalized_owner_userid:
        merged["owner_userid"] = normalized_owner_userid
    if is_wecom_added is not None:
        merged["is_wecom_added"] = bool(is_wecom_added)
    if is_mobile_bound is not None:
        merged["is_mobile_bound"] = bool(is_mobile_bound)
    elif merged["mobile"] and merged["external_userid"]:
        merged["is_mobile_bound"] = True
    if normalized_activation_state != "unknown" or not target:
        merged["huangxiaocan_activation_state"] = normalized_activation_state
    if class_term_no is not None or normalized_class_term_label:
        merged["class_term_no"] = class_term_no
        merged["class_term_label"] = normalized_class_term_label
    if not merged["first_entry_source"]:
        merged["first_entry_source"] = normalized_entry_source
    merged["last_entry_source"] = normalized_entry_source

    before_payload = serialize_user_ops_lead_pool_current_row(target) if target else {}
    action_type = "lead_pool_insert"
    if target is not None:
        action_type = "lead_pool_merge_upsert" if duplicate_ids else "lead_pool_update"
        if not duplicate_ids and before_payload == merged:
            action_type = "lead_pool_noop"
    return {
        "matches": matches,
        "target": target,
        "duplicate_ids": duplicate_ids,
        "before_payload": before_payload,
        "after_payload": merged,
        "action_type": action_type,
        "entry_source": normalized_entry_source,
    }


def list_user_ops_history(
    limit: int = 100,
    *,
    runtime: PoolCoreRuntime,
) -> dict[str, Any]:
    """Internal stable owner for lead-pool history readout."""

    normalized_limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT
            id,
            mobile,
            external_userid,
            action_type,
            before_json,
            after_json,
            operator,
            source_type,
            remark,
            created_at
        FROM user_ops_lead_pool_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_limit,),
    ).fetchall()
    total_row = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_history").fetchone()
    return {
        "items": [
            {
                "id": int(row["id"]),
                "mobile": str(row.get("mobile") or "").strip(),
                "external_userid": str(row.get("external_userid") or "").strip(),
                "action_type": str(row.get("action_type") or "").strip(),
                "before_json": str(row.get("before_json") or "").strip() or "{}",
                "after_json": str(row.get("after_json") or "").strip() or "{}",
                "operator": str(row.get("operator") or "").strip(),
                "source_type": str(row.get("source_type") or "").strip(),
                "remark": str(row.get("remark") or "").strip(),
                "created_at": runtime.stringify_db_timestamp(row.get("created_at")),
            }
            for row in rows
        ],
        "total": int((total_row or {}).get("total") or 0),
        "limit": normalized_limit,
    }


def write_user_ops_lead_pool_history(
    *,
    mobile: str = "",
    external_userid: str = "",
    action_type: str,
    source_type: str,
    operator: str = "",
    before_payload: dict[str, Any] | None = None,
    after_payload: dict[str, Any] | None = None,
    remark: str = "",
    runtime: PoolCoreRuntime,
) -> None:
    """Internal stable owner for lead-pool history writes."""

    get_db().execute(
        """
        INSERT INTO user_ops_lead_pool_history (
            mobile, external_userid, action_type, source_type, operator, before_json, after_json, remark, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            str(mobile or "").strip(),
            str(external_userid or "").strip(),
            str(action_type or "").strip(),
            str(source_type or "").strip(),
            str(operator or runtime.current_operator_resolver()).strip() or "system",
            json.dumps(before_payload or {}, ensure_ascii=False),
            json.dumps(after_payload or {}, ensure_ascii=False),
            str(remark or "").strip(),
        ),
    )


def _insert_user_ops_lead_pool_member_row(
    db,
    payload: dict[str, Any],
    *,
    runtime: PoolCoreRuntime,
) -> int:
    db.execute(
        """
        INSERT INTO user_ops_lead_pool_current (
            mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
            huangxiaocan_activation_state, class_term_no, class_term_label, first_entry_source, last_entry_source,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            payload["mobile"],
            payload["external_userid"],
            payload["customer_name"],
            payload["owner_userid"],
            runtime.db_bool(bool(payload["is_wecom_added"])),
            runtime.db_bool(bool(payload["is_mobile_bound"])),
            payload["huangxiaocan_activation_state"],
            payload["class_term_no"],
            payload["class_term_label"],
            payload["first_entry_source"],
            payload["last_entry_source"],
        ),
    )
    if get_db_backend() != "postgres":
        return int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    row = db.execute(
        """
        SELECT id
        FROM user_ops_lead_pool_current
        WHERE mobile = ? OR external_userid = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (payload["mobile"], payload["external_userid"]),
    ).fetchone()
    return int(row["id"])


def _update_user_ops_lead_pool_member_row(
    db,
    row_id: int,
    payload: dict[str, Any],
    *,
    runtime: PoolCoreRuntime,
) -> None:
    db.execute(
        """
        UPDATE user_ops_lead_pool_current
        SET
            mobile = ?,
            external_userid = ?,
            customer_name = ?,
            owner_userid = ?,
            is_wecom_added = ?,
            is_mobile_bound = ?,
            huangxiaocan_activation_state = ?,
            class_term_no = ?,
            class_term_label = ?,
            first_entry_source = ?,
            last_entry_source = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            payload["mobile"],
            payload["external_userid"],
            payload["customer_name"],
            payload["owner_userid"],
            runtime.db_bool(bool(payload["is_wecom_added"])),
            runtime.db_bool(bool(payload["is_mobile_bound"])),
            payload["huangxiaocan_activation_state"],
            payload["class_term_no"],
            payload["class_term_label"],
            payload["first_entry_source"],
            payload["last_entry_source"],
            int(row_id),
        ),
    )


def _delete_user_ops_lead_pool_duplicate_rows(db, duplicate_ids: list[int]) -> None:
    if not duplicate_ids:
        return
    placeholders = ", ".join("?" for _ in duplicate_ids)
    db.execute(
        f"DELETE FROM user_ops_lead_pool_current WHERE id IN ({placeholders})",
        tuple(duplicate_ids),
    )


def _user_ops_lead_pool_history_remark(remark: str, duplicate_ids: list[int]) -> str:
    normalized_remark = str(remark or "").strip()
    if normalized_remark:
        return normalized_remark
    if duplicate_ids:
        return f"merged duplicate ids: {', '.join(str(item) for item in duplicate_ids)}"
    return ""


def upsert_user_ops_lead_pool_member(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
    operator: str = "",
    remark: str = "",
    runtime: PoolCoreRuntime,
) -> dict[str, Any]:
    """Internal stable owner for lead-pool current/history upsert + dedupe writes."""

    plan = plan_user_ops_lead_pool_member_upsert(
        mobile=mobile,
        external_userid=external_userid,
        customer_name=customer_name,
        owner_userid=owner_userid,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        class_term_label=class_term_label,
        entry_source=entry_source,
        runtime=runtime,
    )
    if plan["action_type"] == "lead_pool_noop":
        return {
            "ok": True,
            "action_type": plan["action_type"],
            "member": plan["target"],
            "merged_duplicate_ids": plan["duplicate_ids"],
        }

    merged = plan["after_payload"]
    db = get_db()
    target = plan["target"]
    if target is None:
        row_id = _insert_user_ops_lead_pool_member_row(db, merged, runtime=runtime)
    else:
        row_id = int(target["id"])
        _update_user_ops_lead_pool_member_row(db, row_id, merged, runtime=runtime)
    _delete_user_ops_lead_pool_duplicate_rows(db, plan["duplicate_ids"])

    current = get_user_ops_lead_pool_current_row_by_id(row_id, runtime=runtime)
    write_user_ops_lead_pool_history(
        mobile=(current or {}).get("mobile", merged["mobile"]),
        external_userid=(current or {}).get("external_userid", merged["external_userid"]),
        action_type=plan["action_type"],
        source_type=plan["entry_source"],
        operator=operator,
        before_payload=plan["before_payload"],
        after_payload=serialize_user_ops_lead_pool_current_row(current or merged),
        remark=_user_ops_lead_pool_history_remark(remark, plan["duplicate_ids"]),
        runtime=runtime,
    )
    db.commit()
    return {
        "ok": True,
        "action_type": plan["action_type"],
        "member": current,
        "merged_duplicate_ids": plan["duplicate_ids"],
    }


def apply_user_ops_huangxiaocan_activation_source_to_existing_member(
    *,
    mobile: str,
    activation_state: str,
    operator: str = "",
    source_type: str = "huangxiaocan_activation_source",
    remark: str = "",
    runtime: PoolCoreRuntime,
) -> dict[str, Any]:
    """Internal stable owner for activation-status patching of existing lead-pool members."""

    normalized_mobile = runtime.normalize_mobile(mobile)
    normalized_state = normalize_user_ops_lead_pool_activation_state(activation_state, allow_unknown=False)
    current_row = get_db().execute(
        """
        SELECT id
        FROM user_ops_lead_pool_current
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    if not current_row:
        get_db().commit()
        return {"ok": True, "matched_member": False, "created_member": False, "member": None}

    member = get_user_ops_lead_pool_current_row_by_id(int(current_row["id"]), runtime=runtime) or {}
    before_payload = serialize_user_ops_lead_pool_current_row(member)
    get_db().execute(
        """
        UPDATE user_ops_lead_pool_current
        SET huangxiaocan_activation_state = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (normalized_state, int(current_row["id"])),
    )
    current = get_user_ops_lead_pool_current_row_by_id(int(current_row["id"]), runtime=runtime)
    write_user_ops_lead_pool_history(
        mobile=normalized_mobile,
        external_userid=(current or {}).get("external_userid", ""),
        action_type="lead_pool_activation_patch",
        source_type=source_type,
        operator=operator,
        before_payload=before_payload,
        after_payload=serialize_user_ops_lead_pool_current_row(current or {}),
        remark=remark,
        runtime=runtime,
    )
    get_db().commit()
    return {"ok": True, "matched_member": True, "created_member": False, "member": current}


__all__ = [
    "PoolCoreRuntime",
    "apply_user_ops_huangxiaocan_activation_source_to_existing_member",
    "get_user_ops_lead_pool_current_row_by_id",
    "list_user_ops_history",
    "list_user_ops_lead_pool_matches",
    "normalize_user_ops_lead_pool_activation_state",
    "plan_user_ops_lead_pool_member_upsert",
    "serialize_user_ops_lead_pool_current_row",
    "upsert_user_ops_lead_pool_member",
    "write_user_ops_lead_pool_history",
]
