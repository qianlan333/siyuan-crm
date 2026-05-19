from __future__ import annotations

from datetime import datetime
from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict
from ...infra.helpers import db_bool, stringify_db_timestamp
from ...infra.json_utils import json_dumps as _json_dumps, safe_json_loads as _json_loads
from .. import attachment_library, miniprogram_library
from ..tasks.private_message import (
    count_private_message_images,
    extract_private_message_text,
    has_private_message_body,
)
from ..tasks.service import dispatch_wecom_task
from ...wecom_client import WeComClientError

AUTO_DND_SIGNUP_STATUSES = {"signed_3999"}
MANUAL_DND_SOURCE_TYPE = "manual"
MANUAL_DND_REASON_CODE = "manual_set"
MANUAL_DND_REASON_TEXT = "运营设置"
PAID_COURSE_DND_REASON = {
    "source_type": "auto",
    "reason_code": "signed_paid_course",
    "reason_text": "已报名正价课",
}
ACTIVATION_BUCKET_LABELS = {
    "activated": "黄小璨已激活",
    "not_activated": "黄小璨未激活",
}
SEND_RECORD_TRACKING_NOTE = "当前只支持任务创建结果追踪，暂无官方发送结果轮询能力。"
SEND_RECORD_STATUS_LABELS = {
    "created": "已创建任务",
    "sent": "已创建完成",
    "partial_failed": "部分创建失败",
    "failed": "创建失败",
}
TASK_RESULT_STATUS_LABELS = {
    "created": "已创建任务",
    "failed": "创建失败",
    "sent": "已创建完成",
    "partial_failed": "部分创建失败",
}


def _normalize_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool_flag(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalize_str(value).lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_status(
    value: Any,
    *,
    allowed: set[str],
    default: str = "all",
) -> str:
    normalized = _normalize_str(value).lower() or default
    return normalized if normalized in allowed else default


def _legacy_bool_filter_status(
    value: Any,
    *,
    true_status: str,
    false_status: str,
    default: str = "all",
) -> str:
    normalized = _normalize_str(value).lower()
    if normalized in {"1", "true", "yes"}:
        return true_status
    if normalized in {"0", "false", "no"}:
        return false_status
    return default


def _normalize_filter_payload(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, str]:
    payload = dict(filters or {})
    payload.update({key: value for key, value in kwargs.items() if value is not None})

    wecom_status = _normalize_status(payload.get("wecom_status"), allowed={"all", "added", "not_added"})
    if wecom_status == "all":
        wecom_status = _legacy_bool_filter_status(
            payload.get("is_wecom_added"),
            true_status="added",
            false_status="not_added",
        )

    mobile_binding_status = _normalize_status(
        payload.get("mobile_binding_status"),
        allowed={"all", "bound", "unbound"},
    )
    if mobile_binding_status == "all":
        mobile_binding_status = _legacy_bool_filter_status(
            payload.get("is_mobile_bound"),
            true_status="bound",
            false_status="unbound",
        )

    activation_bucket = _normalize_status(
        payload.get("activation_bucket"),
        allowed={"all", "activated", "not_activated"},
    )
    if activation_bucket == "all":
        legacy_activation = _normalize_str(payload.get("huangxiaocan_activation_state")).lower()
        activation_bucket = {
            "activated": "activated",
            "not_activated": "not_activated",
            "unknown": "not_activated",
        }.get(legacy_activation, "all")

    return {
        "wecom_status": wecom_status,
        "mobile_binding_status": mobile_binding_status,
        "activation_bucket": activation_bucket,
        "class_term_no": _normalize_str(payload.get("class_term_no")),
        "keyword": _normalize_str(payload.get("keyword") or payload.get("query")),
        "mobile": _normalize_str(payload.get("mobile")),
        "owner_userid": _normalize_str(payload.get("owner_userid")),
    }


def _decode_json_list(value: Any) -> list[Any]:
    decoded = _json_loads(value, default=[])
    return decoded if isinstance(decoded, list) else []


def _normalize_id_list(value: Any) -> list[int]:
    if isinstance(value, list):
        source = value
    elif value in (None, ""):
        source = []
    else:
        source = [value]
    result: list[int] = []
    for item in source:
        try:
            normalized = int(item)
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            result.append(normalized)
    return result


def _status_label(status: Any) -> str:
    normalized = _normalize_str(status)
    return SEND_RECORD_STATUS_LABELS.get(normalized, normalized or "-")


def _task_result_status_label(status: Any) -> str:
    normalized = _normalize_str(status)
    return TASK_RESULT_STATUS_LABELS.get(normalized, normalized or "-")


def _build_placeholders(count: int) -> str:
    return ", ".join(["?"] * count)


def _has_class_term_marker_sql(alias: str = "current") -> str:
    return f"({alias}.class_term_no IS NOT NULL OR TRIM(COALESCE({alias}.class_term_label, '')) <> '')"


def _query_base_rows(
    normalized_filters: dict[str, str],
    *,
    pool_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            current.id,
            current.mobile,
            current.external_userid,
            current.customer_name,
            current.owner_userid,
            current.current_status,
            current.is_wecom_bound,
            current.activation_status,
            current.activation_remark,
            current.class_term_no,
            current.class_term_label,
            current.source_type,
            current.created_at,
            current.updated_at,
            COALESCE(owner_map.display_name, '') AS owner_display_name,
            bindings.person_id AS binding_person_id,
            COALESCE(binding_people.mobile, '') AS binding_mobile,
            COALESCE(class_status.signup_status, '') AS signup_status,
            COALESCE(class_status.signup_label_name, '') AS signup_label_name,
            COALESCE(activation_source.activation_status, '') AS activation_source_status
        FROM user_ops_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = current.external_userid
        LEFT JOIN people binding_people
          ON binding_people.id = bindings.person_id
        LEFT JOIN class_user_status_current class_status
          ON class_status.external_userid = current.external_userid
        LEFT JOIN user_ops_activation_status_source activation_source
          ON activation_source.mobile = current.mobile
         AND activation_source.is_active = ?
        WHERE 1 = 1
          AND """ + _has_class_term_marker_sql("current") + """
    """
    params: list[Any] = [db_bool(True)]

    if pool_ids:
        sql += f" AND current.id IN ({_build_placeholders(len(pool_ids))})"
        params.extend(pool_ids)
    if normalized_filters["class_term_no"]:
        sql += " AND COALESCE(CAST(current.class_term_no AS TEXT), '') = ?"
        params.append(normalized_filters["class_term_no"])
    if normalized_filters["owner_userid"]:
        sql += " AND current.owner_userid = ?"
        params.append(normalized_filters["owner_userid"])
    if normalized_filters["mobile"]:
        sql += " AND current.mobile LIKE ?"
        params.append(f"%{normalized_filters['mobile']}%")
    if normalized_filters["keyword"]:
        like_value = f"%{normalized_filters['keyword']}%"
        sql += """
            AND (
                current.mobile LIKE ?
                OR current.external_userid LIKE ?
                OR current.customer_name LIKE ?
                OR current.owner_userid LIKE ?
                OR owner_map.display_name LIKE ?
            )
        """
        params.extend([like_value, like_value, like_value, like_value, like_value])

    sql += " ORDER BY current.updated_at DESC, current.id DESC"
    return fetchall_dicts(get_db(), sql, tuple(params))


def _auto_dnd_reasons(row: dict[str, Any]) -> list[dict[str, str]]:
    signup_status = _normalize_str(row.get("signup_status"))
    if signup_status in AUTO_DND_SIGNUP_STATUSES:
        return [dict(PAID_COURSE_DND_REASON)]
    return []


def _serialize_manual_dnd_reason(row: dict[str, Any]) -> dict[str, str]:
    return {
        "source_type": _normalize_str(row.get("source_type")),
        "reason_code": _normalize_str(row.get("reason_code")),
        "reason_text": _normalize_str(row.get("reason_text")),
    }


def _index_manual_dnd_rows(
    dnd_rows: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    rows_by_external: dict[str, list[dict[str, Any]]] = {}
    rows_by_mobile: dict[str, list[dict[str, Any]]] = {}
    for row in dnd_rows:
        external_userid = _normalize_str(row.get("external_userid"))
        mobile = _normalize_str(row.get("mobile"))
        if external_userid:
            rows_by_external.setdefault(external_userid, []).append(row)
        if mobile:
            rows_by_mobile.setdefault(mobile, []).append(row)
    return rows_by_external, rows_by_mobile


def _manual_dnd_reasons_for_identity(
    *,
    external_userid: str,
    mobile: str,
    rows_by_external: dict[str, list[dict[str, Any]]],
    rows_by_mobile: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    candidate_rows = list(rows_by_external.get(external_userid, [])) + list(rows_by_mobile.get(mobile, []))
    reasons: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in candidate_rows:
        reason = _serialize_manual_dnd_reason(row)
        dedupe_key = (reason["source_type"], reason["reason_code"], reason["reason_text"])
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        reasons.append(reason)
    return reasons


def _derive_activation_bucket(row: dict[str, Any]) -> str:
    activation_source_status = _normalize_str(row.get("activation_source_status"))
    activation_status = _normalize_str(row.get("activation_status"))
    if activation_source_status:
        return "activated" if activation_source_status == "activated" else "not_activated"
    if activation_status == "activated":
        return "activated"
    if not _normalize_str(row.get("mobile")):
        return "not_activated"
    return "not_activated"


def _legacy_activation_state(activation_bucket: str) -> str:
    return activation_bucket if activation_bucket in {"activated", "not_activated"} else "not_activated"


def _collect_manual_dnd_reasons(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, str]]]:
    external_userids = sorted({_normalize_str(row.get("external_userid")) for row in rows if _normalize_str(row.get("external_userid"))})
    mobiles = sorted({_normalize_str(row.get("mobile")) for row in rows if _normalize_str(row.get("mobile"))})
    if not external_userids and not mobiles:
        return {}

    sql = """
        SELECT id, external_userid, mobile, source_type, reason_code, reason_text
        FROM user_ops_do_not_disturb
        WHERE is_active = ?
    """
    params: list[Any] = [db_bool(True)]
    clauses: list[str] = []
    if external_userids:
        clauses.append(f"external_userid IN ({_build_placeholders(len(external_userids))})")
        params.extend(external_userids)
    if mobiles:
        clauses.append(f"mobile IN ({_build_placeholders(len(mobiles))})")
        params.extend(mobiles)
    sql += f" AND ({' OR '.join(clauses)})"

    rows_by_id: dict[int, list[dict[str, str]]] = {}
    dnd_rows = [dict(row) for row in get_db().execute(sql, tuple(params)).fetchall()]
    rows_by_external, rows_by_mobile = _index_manual_dnd_rows(dnd_rows)
    for item in rows:
        external_userid = _normalize_str(item.get("external_userid"))
        mobile = _normalize_str(item.get("mobile"))
        reasons = _manual_dnd_reasons_for_identity(
            external_userid=external_userid,
            mobile=mobile,
            rows_by_external=rows_by_external,
            rows_by_mobile=rows_by_mobile,
        )
        rows_by_id[int(item["id"])] = reasons
    return rows_by_id


def _serialize_pool_item(row: dict[str, Any], manual_dnd_reasons: list[dict[str, str]]) -> dict[str, Any]:
    external_userid = _normalize_str(row.get("external_userid"))
    activation_bucket = _derive_activation_bucket(row)
    is_added_wecom = bool(external_userid)
    is_mobile_bound = bool(external_userid and row.get("binding_person_id") and _normalize_str(row.get("binding_mobile")))
    do_not_disturb_reasons = _auto_dnd_reasons(row) + list(manual_dnd_reasons or [])
    owner_userid = _normalize_str(row.get("owner_userid"))
    return {
        "id": int(row["id"]),
        "mobile": _normalize_str(row.get("mobile")),
        "external_userid": external_userid,
        "customer_name": _normalize_str(row.get("customer_name")),
        "owner_userid": owner_userid,
        "owner_display_name": _normalize_str(row.get("owner_display_name")) or owner_userid,
        "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
        "class_term_label": _normalize_str(row.get("class_term_label")),
        "source_type": _normalize_str(row.get("source_type")),
        "created_at": stringify_db_timestamp(row.get("created_at")),
        "updated_at": stringify_db_timestamp(row.get("updated_at")),
        "is_added_wecom": is_added_wecom,
        "is_wecom_added": is_added_wecom,
        "is_mobile_bound": is_mobile_bound,
        "activation_bucket": activation_bucket,
        "activation_bucket_label": ACTIVATION_BUCKET_LABELS[activation_bucket],
        "huangxiaocan_activation_state": _legacy_activation_state(activation_bucket),
        "huangxiaocan_activation_state_label": ACTIVATION_BUCKET_LABELS[activation_bucket],
        "do_not_disturb": bool(do_not_disturb_reasons),
        "do_not_disturb_reasons": do_not_disturb_reasons,
        "can_open_customer_detail": bool(external_userid),
        "can_batch_send": bool(external_userid),
    }


def _apply_segment_filters(items: list[dict[str, Any]], normalized_filters: dict[str, str]) -> list[dict[str, Any]]:
    filtered = list(items)
    if normalized_filters["wecom_status"] == "added":
        filtered = [item for item in filtered if item["is_added_wecom"]]
    elif normalized_filters["wecom_status"] == "not_added":
        filtered = [item for item in filtered if not item["is_added_wecom"]]

    if normalized_filters["mobile_binding_status"] == "bound":
        filtered = [item for item in filtered if item["is_mobile_bound"]]
    elif normalized_filters["mobile_binding_status"] == "unbound":
        filtered = [item for item in filtered if not item["is_mobile_bound"]]

    if normalized_filters["activation_bucket"] != "all":
        filtered = [item for item in filtered if item["activation_bucket"] == normalized_filters["activation_bucket"]]
    return filtered


def _list_query_items(
    normalized_filters: dict[str, str],
    *,
    pool_ids: list[int] | None = None,
    apply_segment_filters: bool,
) -> list[dict[str, Any]]:
    base_rows = _query_base_rows(normalized_filters, pool_ids=pool_ids)
    manual_reason_map = _collect_manual_dnd_reasons(base_rows)
    items = [_serialize_pool_item(row, manual_reason_map.get(int(row["id"]), [])) for row in base_rows]
    if apply_segment_filters:
        return _apply_segment_filters(items, normalized_filters)
    return items


def _list_class_term_options() -> list[dict[str, Any]]:
    rows = get_db().execute(
        f"""
        SELECT DISTINCT class_term_no, class_term_label
        FROM user_ops_pool_current
        WHERE {_has_class_term_marker_sql("user_ops_pool_current")}
        ORDER BY class_term_no ASC
        """
    ).fetchall()
    return [
        {
            "class_term_no": int(row["class_term_no"]),
            "class_term_label": _normalize_str(row.get("class_term_label")) or f"{int(row['class_term_no'])}期",
        }
        for row in rows
        if row.get("class_term_no") not in (None, "")
    ]


def _build_filter_options() -> dict[str, Any]:
    return {
        "wecom_statuses": [
            {"value": "all", "label": "全部"},
            {"value": "added", "label": "已加微"},
            {"value": "not_added", "label": "未加微"},
        ],
        "mobile_binding_statuses": [
            {"value": "all", "label": "全部"},
            {"value": "bound", "label": "已绑手机号"},
            {"value": "unbound", "label": "未绑手机号"},
        ],
        "activation_buckets": [
            {"value": "all", "label": "全部"},
            {"value": "activated", "label": "黄小璨已激活"},
            {"value": "not_activated", "label": "黄小璨未激活"},
        ],
        "activation_states": [
            {"value": "activated", "label": "黄小璨已激活"},
            {"value": "not_activated", "label": "黄小璨未激活"},
        ],
        "class_terms": _list_class_term_options(),
    }


def list_user_ops_pool(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    normalized_filters = _normalize_filter_payload(filters, **kwargs)
    items = _list_query_items(normalized_filters, apply_segment_filters=True)
    return {
        "items": items,
        "total": len(items),
        "filters": normalized_filters,
        "filter_options": _build_filter_options(),
        "meta": {
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def get_user_ops_overview(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    normalized_filters = _normalize_filter_payload(filters, **kwargs)
    scoped_items = _list_query_items(normalized_filters, apply_segment_filters=False)
    total = len(scoped_items)
    added_count = sum(1 for item in scoped_items if item["is_added_wecom"])
    mobile_bound_count = sum(1 for item in scoped_items if item["is_mobile_bound"])
    activated_count = sum(1 for item in scoped_items if item["activation_bucket"] == "activated")
    not_activated_count = sum(1 for item in scoped_items if item["activation_bucket"] == "not_activated")
    cards = [
        {"key": "lead_pool_total_count", "label": "引流品总数", "value": total},
        {"key": "wecom_added_count", "label": "已加微", "value": added_count},
        {"key": "wecom_not_added_count", "label": "未加微", "value": total - added_count},
        {"key": "mobile_bound_count", "label": "已绑手机号", "value": mobile_bound_count},
        {"key": "mobile_unbound_count", "label": "未绑手机号", "value": total - mobile_bound_count},
        {"key": "huangxiaocan_activated_count", "label": "黄小璨已激活", "value": activated_count},
        {"key": "huangxiaocan_not_activated_count", "label": "黄小璨未激活", "value": not_activated_count},
    ]
    return {
        "lead_pool_total_count": total,
        "wecom_added_count": added_count,
        "wecom_not_added_count": total - added_count,
        "mobile_bound_count": mobile_bound_count,
        "mobile_unbound_count": total - mobile_bound_count,
        "huangxiaocan_activated_count": activated_count,
        "huangxiaocan_not_activated_count": not_activated_count,
        "cards": cards,
        "filters": normalized_filters,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def export_user_ops_pool(filters: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    result = list_user_ops_pool(filters, **kwargs)
    headers = [
        "手机号",
        "是否已加微",
        "是否已绑手机号",
        "班期",
        "黄小璨激活状态",
        "免打扰",
        "免打扰原因",
        "客户昵称",
        "external_userid",
        "跟进人",
        "更新时间",
    ]
    rows = [
        [
            item.get("mobile", ""),
            "已加微" if item.get("is_added_wecom") else "未加微",
            "已绑定" if item.get("is_mobile_bound") else "未绑定",
            item.get("class_term_label", "") or (f"{item['class_term_no']}期" if item.get("class_term_no") else ""),
            item.get("activation_bucket_label", ""),
            "是" if item.get("do_not_disturb") else "否",
            "；".join(reason["reason_text"] for reason in item.get("do_not_disturb_reasons") or []),
            item.get("customer_name", ""),
            item.get("external_userid", ""),
            item.get("owner_display_name", ""),
            item.get("updated_at", ""),
        ]
        for item in result["items"]
    ]
    return {
        "headers": headers,
        "rows": rows,
        "filename": f"user-ops-pool-{datetime.now().strftime('%Y%m%d%H%M%S')}.xls",
    }


def _resolve_pool_target(*, external_userid: str = "", mobile: str = "") -> dict[str, Any] | None:
    normalized_external_userid = _normalize_str(external_userid)
    normalized_mobile = _normalize_str(mobile)
    if normalized_external_userid:
        return fetchone_dict(
            get_db(),
            """
            SELECT id, external_userid, mobile
            FROM user_ops_pool_current
            WHERE external_userid = ?
            LIMIT 1
            """,
            (normalized_external_userid,),
        )
    if normalized_mobile:
        return fetchone_dict(
            get_db(),
            """
            SELECT id, external_userid, mobile
            FROM user_ops_pool_current
            WHERE mobile = ?
            LIMIT 1
            """,
            (normalized_mobile,),
        )
    return None


def set_user_ops_do_not_disturb(payload: dict[str, Any]) -> dict[str, Any]:
    target = _resolve_pool_target(
        external_userid=_normalize_str(payload.get("external_userid")),
        mobile=_normalize_str(payload.get("mobile")),
    )
    if target is None:
        raise LookupError("target is not in user_ops_pool_current")

    external_userid = _normalize_str(target.get("external_userid"))
    mobile = _normalize_str(target.get("mobile"))
    reason_code = _normalize_str(payload.get("reason_code")) or MANUAL_DND_REASON_CODE
    reason_text = _normalize_str(payload.get("reason_text")) or MANUAL_DND_REASON_TEXT
    operator = _normalize_str(payload.get("operator"))
    action = _normalize_str(payload.get("action")).lower()
    is_active = _normalize_bool_flag(payload.get("is_active"), default=action not in {"disable", "cancel", "clear", "remove"})
    db = get_db()

    if is_active:
        existing = db.execute(
            """
            SELECT id
            FROM user_ops_do_not_disturb
            WHERE source_type = ?
              AND reason_code = ?
              AND (
                    (external_userid <> '' AND external_userid = ?)
                 OR (external_userid = '' AND mobile <> '' AND mobile = ?)
              )
            ORDER BY id DESC
            LIMIT 1
            """,
            (MANUAL_DND_SOURCE_TYPE, reason_code, external_userid, mobile),
        ).fetchone()
        if existing:
            db.execute(
                """
                UPDATE user_ops_do_not_disturb
                SET external_userid = ?,
                    mobile = ?,
                    reason_text = ?,
                    is_active = ?,
                    created_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (external_userid, mobile, reason_text, db_bool(True), operator, int(existing["id"])),
            )
        else:
            db.execute(
                """
                INSERT INTO user_ops_do_not_disturb (
                    external_userid, mobile, source_type, reason_code, reason_text, is_active, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    external_userid,
                    mobile,
                    MANUAL_DND_SOURCE_TYPE,
                    reason_code,
                    reason_text,
                    db_bool(True),
                    operator,
                ),
            )
    else:
        sql = """
            UPDATE user_ops_do_not_disturb
            SET is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE source_type = ?
              AND (
                    (external_userid <> '' AND external_userid = ?)
                 OR (mobile <> '' AND mobile = ?)
              )
        """
        params: list[Any] = [db_bool(False), MANUAL_DND_SOURCE_TYPE, external_userid, mobile]
        if reason_code:
            sql += " AND reason_code = ?"
            params.append(reason_code)
        db.execute(sql, tuple(params))

    db.commit()
    item_rows = _list_query_items(_normalize_filter_payload(), pool_ids=[int(target["id"])], apply_segment_filters=False)
    if not item_rows:
        raise LookupError("target is not in current user_ops page pool")
    item = item_rows[0]
    return {
        "target": {
            "id": item["id"],
            "external_userid": item["external_userid"],
            "mobile": item["mobile"],
        },
        "do_not_disturb": item["do_not_disturb"],
        "do_not_disturb_reasons": item["do_not_disturb_reasons"],
    }


def _build_batch_send_selection(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else payload
    normalized_filters = _normalize_filter_payload(filters if isinstance(filters, dict) else {})
    selection_mode = _normalize_str(payload.get("selection_mode")).lower() or "all_filtered"
    selected_ids = _normalize_id_list(payload.get("selected_ids"))
    excluded_ids = set(_normalize_id_list(payload.get("excluded_ids")))

    if selection_mode == "manual":
        items = _list_query_items(normalized_filters, pool_ids=selected_ids, apply_segment_filters=False) if selected_ids else []
    else:
        items = _list_query_items(normalized_filters, apply_segment_filters=True)
    if excluded_ids:
        items = [item for item in items if item["id"] not in excluded_ids]
    return items, normalized_filters


def _build_batch_send_plan(payload: dict[str, Any]) -> dict[str, Any]:
    include_do_not_disturb = _normalize_bool_flag(payload.get("include_do_not_disturb"), default=False)
    selected_items, normalized_filters = _build_batch_send_selection(payload)
    skipped_by_reason: dict[str, int] = {}
    eligible_items: list[dict[str, Any]] = []
    for item in selected_items:
        skip_reason = ""
        if not item["external_userid"]:
            skip_reason = "missing_external_userid"
        elif not include_do_not_disturb and item["do_not_disturb"]:
            skip_reason = "do_not_disturb"
        elif not item["owner_userid"]:
            skip_reason = "missing_owner_userid"
        if skip_reason:
            skipped_by_reason[skip_reason] = skipped_by_reason.get(skip_reason, 0) + 1
            continue
        eligible_items.append(item)

    owner_buckets: list[dict[str, Any]] = []
    owner_map: dict[str, dict[str, Any]] = {}
    for item in eligible_items:
        owner_key = item["owner_userid"]
        bucket = owner_map.setdefault(
            owner_key,
            {
                "owner_userid": owner_key,
                "owner_display_name": item["owner_display_name"],
                "count": 0,
            },
        )
        bucket["count"] += 1
    owner_buckets = sorted(owner_map.values(), key=lambda item: (item["owner_userid"], item["owner_display_name"]))

    final_targets = [
        {
            "id": item["id"],
            "external_userid": item["external_userid"],
            "customer_name": item["customer_name"],
            "owner_userid": item["owner_userid"],
            "owner_display_name": item["owner_display_name"],
            "mobile": item["mobile"],
        }
        for item in eligible_items
    ]
    return {
        "selected_items": selected_items,
        "eligible_items": eligible_items,
        "filters": normalized_filters,
        "selected_count": len(selected_items),
        "eligible_count": len(eligible_items),
        "skipped_count": len(selected_items) - len(eligible_items),
        "skipped_by_reason": skipped_by_reason,
        "include_do_not_disturb": include_do_not_disturb,
        "owner_buckets": owner_buckets,
        "sendable_samples": final_targets[:5],
        "final_targets": final_targets,
    }


def _summarize_skipped_by_reason(skipped_by_reason: dict[str, int]) -> str:
    parts: list[str] = []
    if int(skipped_by_reason.get("do_not_disturb") or 0):
        parts.append(f'{int(skipped_by_reason["do_not_disturb"])} 人免打扰')
    if int(skipped_by_reason.get("missing_external_userid") or 0):
        parts.append(f'{int(skipped_by_reason["missing_external_userid"])} 人缺少 external_userid')
    if int(skipped_by_reason.get("missing_owner_userid") or 0):
        parts.append(f'{int(skipped_by_reason["missing_owner_userid"])} 人缺少发送人')
    if not parts:
        return ""
    skipped_total = sum(int(value or 0) for value in skipped_by_reason.values())
    return f'已跳过 {skipped_total} 人：' + "，".join(parts)


def _build_private_message_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str, int]:
    payload = dict(payload)
    raw_attachments = payload.get("attachments")
    attachment_library_ids = attachment_library._normalize_id_list(payload.get("attachment_library_ids"), max_count=9)
    if attachment_library_ids:
        raw_attachments = list(raw_attachments or []) + [
            {"msgtype": "file", "file": {"library_id": item_id}}
            for item_id in attachment_library_ids
        ]
    if isinstance(raw_attachments, list) and raw_attachments:
        expanded = miniprogram_library.expand_attachments_with_library(raw_attachments)
        expanded = attachment_library.expand_attachments_with_library(expanded)
        payload["attachments"] = expanded
    payload.pop("attachment_library_ids", None)
    content_preview = extract_private_message_text(payload)
    image_count = count_private_message_images(payload)
    if not has_private_message_body(payload):
        raise ValueError("content, images, or attachments is required")
    task_payload: dict[str, Any] = {}
    if content_preview.strip():
        task_payload["text"] = {"content": content_preview}
    images = payload.get("images")
    if isinstance(images, list) and images:
        task_payload["images"] = images
    image_media_ids = payload.get("image_media_ids")
    if isinstance(image_media_ids, list) and image_media_ids:
        task_payload["image_media_ids"] = image_media_ids
    attachments = payload.get("attachments")
    if isinstance(attachments, list) and attachments:
        task_payload["attachments"] = attachments
    return task_payload, content_preview, image_count


def _owner_display_name_map(owner_userids: list[str]) -> dict[str, str]:
    normalized_owner_userids = sorted({_normalize_str(item) for item in owner_userids if _normalize_str(item)})
    if not normalized_owner_userids:
        return {}
    rows = get_db().execute(
        f"""
        SELECT userid, display_name
        FROM owner_role_map
        WHERE userid IN ({_build_placeholders(len(normalized_owner_userids))})
        """,
        tuple(normalized_owner_userids),
    ).fetchall()
    return {
        _normalize_str(row.get("userid")): _normalize_str(row.get("display_name"))
        for row in rows
        if _normalize_str(row.get("userid"))
    }


def _extract_sender_userids_from_request_payload(request_payload: dict[str, Any]) -> list[str]:
    raw_sender = request_payload.get("sender")
    if isinstance(raw_sender, list):
        return [_normalize_str(item) for item in raw_sender if _normalize_str(item)]
    normalized_sender = _normalize_str(raw_sender)
    return [normalized_sender] if normalized_sender else []


def _extract_external_userids_from_request_payload(request_payload: dict[str, Any]) -> list[str]:
    raw_external_userids = request_payload.get("external_userid")
    if isinstance(raw_external_userids, list):
        return [_normalize_str(item) for item in raw_external_userids if _normalize_str(item)]
    normalized_external_userid = _normalize_str(raw_external_userids)
    if normalized_external_userid:
        return [normalized_external_userid]
    raw_external_userids = request_payload.get("external_userids")
    if isinstance(raw_external_userids, list):
        return [_normalize_str(item) for item in raw_external_userids if _normalize_str(item)]
    normalized_external_userid = _normalize_str(raw_external_userids)
    return [normalized_external_userid] if normalized_external_userid else []


def _build_sender_success_result(owner_userid: str, items: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    wecom_result = result.get("wecom_result") if isinstance(result.get("wecom_result"), dict) else {}
    return {
        "owner_userid": owner_userid,
        "sender_userid": owner_userid,
        "owner_display_name": _normalize_str(items[0].get("owner_display_name")) if items else owner_userid,
        "external_userids": [item["external_userid"] for item in items],
        "external_userid_count": len(items),
        "target_count": len(items),
        "task_id": int(result["task_id"]),
        "wecom_task_id": _normalize_str(
            wecom_result.get("msgid")
            or wecom_result.get("jobid")
            or wecom_result.get("task_id")
            or wecom_result.get("moment_id")
        ),
        "msgid": _normalize_str(wecom_result.get("msgid")),
        "status": "created",
        "error_message": "",
    }


def _build_sender_failure_result(owner_userid: str, items: list[dict[str, Any]], exc: Exception) -> dict[str, Any]:
    task_id = getattr(exc, "local_task_id", None)
    payload = getattr(exc, "payload", {}) if isinstance(exc, WeComClientError) else {}
    return {
        "owner_userid": owner_userid,
        "sender_userid": owner_userid,
        "owner_display_name": _normalize_str(items[0].get("owner_display_name")) if items else owner_userid,
        "external_userids": [item["external_userid"] for item in items],
        "external_userid_count": len(items),
        "target_count": len(items),
        "task_id": int(task_id) if isinstance(task_id, int) or (isinstance(task_id, str) and str(task_id).isdigit()) else None,
        "wecom_task_id": _normalize_str(payload.get("msgid") or payload.get("jobid") or payload.get("task_id") or payload.get("moment_id")),
        "msgid": _normalize_str(payload.get("msgid")),
        "status": "failed",
        "error_message": str(exc),
        "error_stage": _normalize_str(getattr(exc, "stage", "")),
        "error_category": _normalize_str(getattr(exc, "category", "")),
    }


def _normalize_task_result_item(item: dict[str, Any], owner_display_names: dict[str, str] | None = None) -> dict[str, Any]:
    external_userids = _extract_external_userids_from_request_payload(item) if "external_userids" not in item else [
        _normalize_str(value) for value in (item.get("external_userids") or []) if _normalize_str(value)
    ]
    owner_userid = _normalize_str(item.get("owner_userid") or item.get("sender_userid"))
    task_id_raw = item.get("task_id")
    task_id = int(task_id_raw) if str(task_id_raw).isdigit() else None
    status = _normalize_str(item.get("status")) or ("failed" if _normalize_str(item.get("error_message")) else "created")
    owner_display_name = _normalize_str(item.get("owner_display_name")) or (owner_display_names or {}).get(owner_userid, "") or owner_userid
    return {
        "owner_userid": owner_userid,
        "sender_userid": _normalize_str(item.get("sender_userid")) or owner_userid,
        "owner_display_name": owner_display_name,
        "external_userids": external_userids,
        "external_userid_count": len(external_userids),
        "target_count": int(item.get("target_count") or len(external_userids) or 0),
        "task_id": task_id,
        "wecom_task_id": _normalize_str(item.get("wecom_task_id")),
        "msgid": _normalize_str(item.get("msgid")),
        "status": status,
        "status_label": _task_result_status_label(status),
        "error_message": _normalize_str(item.get("error_message")),
        "error_stage": _normalize_str(item.get("error_stage")),
        "error_category": _normalize_str(item.get("error_category")),
        "fallback_without_miniprogram": bool(item.get("fallback_without_miniprogram")),
        "fallback_reason": _normalize_str(item.get("fallback_reason")),
        "fallback_error_message": _normalize_str(item.get("fallback_error_message")),
        "fallback_removed_attachment_count": int(item.get("fallback_removed_attachment_count") or 0),
    }


def _derive_record_status(task_results: list[dict[str, Any]], *, eligible_count: int) -> str:
    success_count = sum(1 for item in task_results if _normalize_str(item.get("status")) != "failed")
    failed_count = sum(1 for item in task_results if _normalize_str(item.get("status")) == "failed")
    if success_count and failed_count:
        return "partial_failed"
    if success_count:
        return "sent"
    if failed_count:
        return "failed"
    return "created" if eligible_count == 0 else "failed"


def _fetch_outbound_task_rows(task_ids: list[int]) -> list[dict[str, Any]]:
    normalized_task_ids = [int(task_id) for task_id in task_ids if int(task_id) > 0]
    if not normalized_task_ids:
        return []
    return fetchall_dicts(
        get_db(),
        f"""
        SELECT id, task_type, request_payload, response_payload, wecom_task_id, status, created_at
        FROM outbound_tasks
        WHERE id IN ({_build_placeholders(len(normalized_task_ids))})
        ORDER BY id ASC
        """,
        tuple(normalized_task_ids),
    )


def _task_result_from_outbound_task_row(row: dict[str, Any], owner_display_names: dict[str, str]) -> dict[str, Any]:
    request_payload = _json_loads(row.get("request_payload"), default={})
    response_payload = _json_loads(row.get("response_payload"), default={})
    sender_userids = _extract_sender_userids_from_request_payload(request_payload)
    owner_userid = sender_userids[0] if sender_userids else ""
    status = _normalize_str(row.get("status")) or ("failed" if _normalize_str(response_payload.get("error")) else "created")
    return _normalize_task_result_item(
        {
            "owner_userid": owner_userid,
            "sender_userid": owner_userid,
            "owner_display_name": owner_display_names.get(owner_userid, owner_userid),
            "external_userids": _extract_external_userids_from_request_payload(request_payload),
            "target_count": len(_extract_external_userids_from_request_payload(request_payload)),
            "task_id": row.get("id"),
            "wecom_task_id": _normalize_str(row.get("wecom_task_id")),
            "msgid": _normalize_str(response_payload.get("msgid") or row.get("wecom_task_id")),
            "status": status,
            "error_message": _normalize_str(response_payload.get("error") or response_payload.get("errmsg")),
        },
        owner_display_names=owner_display_names,
    )


def _sender_userids_from_task_results(task_results: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in task_results:
        sender_userid = _normalize_str(item.get("sender_userid") or item.get("owner_userid"))
        if sender_userid and sender_userid not in result:
            result.append(sender_userid)
    return result


def _load_send_record_row(record_id: int) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT
            id,
            task_type,
            outbound_task_ids_json,
            task_results_json,
            selected_count,
            eligible_count,
            sent_count,
            skipped_count,
            skipped_reasons_json,
            include_do_not_disturb,
            content_preview,
            image_count,
            sender_userids_json,
            filter_snapshot_json,
            operator,
            status,
            last_status_sync_at,
            created_at
        FROM user_ops_send_records
        WHERE id = ?
        LIMIT 1
        """,
        (int(record_id),),
    )


def _hydrate_task_results(row: dict[str, Any]) -> list[dict[str, Any]]:
    stored = _decode_json_list(row.get("task_results_json"))
    owner_display_names = _owner_display_name_map(
        [_normalize_str(item.get("owner_userid") or item.get("sender_userid")) for item in stored if isinstance(item, dict)]
    )
    if stored:
        return [_normalize_task_result_item(item, owner_display_names=owner_display_names) for item in stored if isinstance(item, dict)]

    outbound_task_ids = [int(item) for item in _decode_json_list(row.get("outbound_task_ids_json")) if str(item).isdigit()]
    outbound_rows = _fetch_outbound_task_rows(outbound_task_ids)
    owner_display_names = _owner_display_name_map(
        [
            (_extract_sender_userids_from_request_payload(_json_loads(outbound_row.get("request_payload"), default={})) or [""])[0]
            for outbound_row in outbound_rows
        ]
    )
    return [_task_result_from_outbound_task_row(outbound_row, owner_display_names) for outbound_row in outbound_rows]


def _serialize_send_record_summary(row: dict[str, Any], task_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    hydrated_task_results = task_results if task_results is not None else _hydrate_task_results(row)
    sender_userids = [str(item) for item in _decode_json_list(row.get("sender_userids_json")) if _normalize_str(item)]
    if not sender_userids:
        sender_userids = _sender_userids_from_task_results(hydrated_task_results)
    status = _normalize_str(row.get("status")) or _derive_record_status(hydrated_task_results, eligible_count=int(row.get("eligible_count") or 0))
    return {
        "id": int(row["id"]),
        "task_type": _normalize_str(row.get("task_type")),
        "outbound_task_ids": [int(item) for item in _decode_json_list(row.get("outbound_task_ids_json")) if str(item).isdigit()],
        "selected_count": int(row.get("selected_count") or 0),
        "eligible_count": int(row.get("eligible_count") or 0),
        "sent_count": int(row.get("sent_count") or 0),
        "skipped_count": int(row.get("skipped_count") or 0),
        "skipped_reasons": _json_loads(row.get("skipped_reasons_json"), default={}),
        "include_do_not_disturb": bool(row.get("include_do_not_disturb")),
        "content_preview": _normalize_str(row.get("content_preview")),
        "image_count": int(row.get("image_count") or 0),
        "sender_userids": sender_userids,
        "filter_snapshot": _json_loads(row.get("filter_snapshot_json"), default={}),
        "operator": _normalize_str(row.get("operator")),
        "status": status,
        "status_label": _status_label(status),
        "status_source": "task_creation",
        "created_at": stringify_db_timestamp(row.get("created_at")),
        "last_status_sync_at": stringify_db_timestamp(row.get("last_status_sync_at")),
        "sender_count": len(sender_userids),
        "owner_count": len(sender_userids),
    }


def _serialize_send_record_detail(row: dict[str, Any], task_results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _serialize_send_record_summary(row, task_results=task_results)
    return {
        **summary,
        "task_results": task_results,
        "delivery_status_supported": False,
        "status_note": SEND_RECORD_TRACKING_NOTE,
    }


def _update_send_record_tracking(record_id: int, *, task_results: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    sender_userids = _sender_userids_from_task_results(task_results)
    get_db().execute(
        """
        UPDATE user_ops_send_records
        SET task_results_json = ?,
            sender_userids_json = ?,
            status = ?,
            last_status_sync_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            _json_dumps(task_results),
            _json_dumps(sender_userids),
            status,
            int(record_id),
        ),
    )
    get_db().commit()
    return _load_send_record_row(record_id)


def preview_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    task_payload, content_preview, image_count = _build_private_message_payload(payload)
    plan = _build_batch_send_plan(payload)
    return {
        "selected_count": plan["selected_count"],
        "eligible_count": plan["eligible_count"],
        "skipped_count": plan["skipped_count"],
        "skipped_by_reason": plan["skipped_by_reason"],
        "skipped_summary": _summarize_skipped_by_reason(plan["skipped_by_reason"]),
        "include_do_not_disturb": plan["include_do_not_disturb"],
        "sender_buckets": plan["owner_buckets"],
        "owner_buckets": plan["owner_buckets"],
        "sendable_samples": plan["sendable_samples"],
        "final_targets": plan["final_targets"],
        "filters": plan["filters"],
        "content_preview": content_preview,
        "image_count": image_count,
        "has_body": has_private_message_body(task_payload),
    }


def _insert_send_record(
    *,
    outbound_task_ids: list[int],
    task_results: list[dict[str, Any]],
    selected_count: int,
    eligible_count: int,
    sent_count: int,
    skipped_count: int,
    skipped_reasons: dict[str, int],
    include_do_not_disturb: bool,
    content_preview: str,
    image_count: int,
    sender_userids: list[str],
    filter_snapshot: dict[str, Any],
    operator: str,
    status: str,
) -> int:
    row = get_db().execute(
        """
        INSERT INTO user_ops_send_records (
            task_type,
            outbound_task_ids_json,
            task_results_json,
            selected_count,
            eligible_count,
            sent_count,
            skipped_count,
            skipped_reasons_json,
            include_do_not_disturb,
            content_preview,
            image_count,
            sender_userids_json,
            filter_snapshot_json,
            operator,
            status,
            last_status_sync_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            "private_message",
            _json_dumps(outbound_task_ids),
            _json_dumps(task_results),
            selected_count,
            eligible_count,
            sent_count,
            skipped_count,
            _json_dumps(skipped_reasons),
            db_bool(include_do_not_disturb),
            content_preview,
            image_count,
            _json_dumps(sender_userids),
            _json_dumps(filter_snapshot),
            operator,
            status,
        ),
    ).fetchone()
    get_db().commit()
    return int(row["id"])


def execute_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    if not _normalize_bool_flag(payload.get("confirm"), default=False):
        raise ValueError("confirm=true is required")

    task_payload, content_preview, image_count = _build_private_message_payload(payload)

    plan = _build_batch_send_plan(payload)
    task_results: list[dict[str, Any]] = []
    outbound_task_ids: list[int] = []
    sender_userids: list[str] = []
    grouped_targets: dict[str, list[dict[str, Any]]] = {}
    for item in plan["eligible_items"]:
        grouped_targets.setdefault(item["owner_userid"], []).append(item)

    for owner_userid, items in sorted(grouped_targets.items()):
        sender_userids.append(owner_userid)
        request_payload = {
            "sender": owner_userid,
            "external_userid": [item["external_userid"] for item in items],
            **task_payload,
        }
        try:
            result = dispatch_wecom_task(
                "private_message",
                "create_private_message_task",
                request_payload,
            )
            outbound_task_ids.append(int(result["task_id"]))
            task_results.append(_build_sender_success_result(owner_userid, items, result))
        except (WeComClientError, AttributeError) as exc:
            task_results.append(_build_sender_failure_result(owner_userid, items, exc))

    sent_count = sum(int(item.get("target_count") or 0) for item in task_results if _normalize_str(item.get("status")) != "failed")
    status = _derive_record_status(task_results, eligible_count=plan["eligible_count"])
    record_id = _insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=plan["selected_count"],
        eligible_count=plan["eligible_count"],
        sent_count=sent_count,
        skipped_count=plan["skipped_count"],
        skipped_reasons=plan["skipped_by_reason"],
        include_do_not_disturb=plan["include_do_not_disturb"],
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=sender_userids,
        filter_snapshot=plan["filters"],
        operator=_normalize_str(payload.get("operator")),
        status=status,
    )
    return {
        "record_id": record_id,
        "selected_count": plan["selected_count"],
        "eligible_count": plan["eligible_count"],
        "sent_count": sent_count,
        "skipped_count": plan["skipped_count"],
        "skipped_by_reason": plan["skipped_by_reason"],
        "skipped_summary": _summarize_skipped_by_reason(plan["skipped_by_reason"]),
        "include_do_not_disturb": plan["include_do_not_disturb"],
        "image_count": image_count,
        "execution_summary": {
            "selected_count": plan["selected_count"],
            "eligible_count": plan["eligible_count"],
            "sent_count": sent_count,
            "sender_count": len(sender_userids),
            "image_count": image_count,
            "status": status,
            "status_label": _status_label(status),
        },
        "skip_summary": {
            "skipped_count": plan["skipped_count"],
            "skipped_by_reason": plan["skipped_by_reason"],
        },
        "task_results": task_results,
        "filters": plan["filters"],
    }


def list_user_ops_send_records(*, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 20), 200))
    normalized_offset = max(int(offset or 0), 0)
    rows = get_db().execute(
        """
        SELECT
            id,
            task_type,
            outbound_task_ids_json,
            task_results_json,
            selected_count,
            eligible_count,
            sent_count,
            skipped_count,
            skipped_reasons_json,
            include_do_not_disturb,
            content_preview,
            image_count,
            sender_userids_json,
            filter_snapshot_json,
            operator,
            status,
            last_status_sync_at,
            created_at
        FROM user_ops_send_records
        ORDER BY id DESC
        LIMIT ?
        OFFSET ?
        """,
        (normalized_limit, normalized_offset),
    ).fetchall()
    total_row = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_send_records").fetchone()
    return {
        "items": [_serialize_send_record_summary(dict(row)) for row in rows],
        "limit": normalized_limit,
        "offset": normalized_offset,
        "total": int((total_row or {}).get("total") or 0),
    }


def get_user_ops_send_record_detail(record_id: int) -> dict[str, Any]:
    row = _load_send_record_row(int(record_id))
    if row is None:
        raise LookupError("send record not found")
    task_results = _hydrate_task_results(row)
    return {"record": _serialize_send_record_detail(row, task_results)}


def refresh_user_ops_send_record_status(record_id: int) -> dict[str, Any]:
    row = _load_send_record_row(int(record_id))
    if row is None:
        raise LookupError("send record not found")
    task_results = _hydrate_task_results(row)
    status = _derive_record_status(task_results, eligible_count=int(row.get("eligible_count") or 0))
    refreshed_row = _update_send_record_tracking(int(record_id), task_results=task_results, status=status) or row
    return {"record": _serialize_send_record_detail(refreshed_row, task_results)}
