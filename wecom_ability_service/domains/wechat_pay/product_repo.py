from __future__ import annotations

from typing import Any

from ...db import get_db
from ...infra.json_utils import json_dumps, safe_json_loads


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


def _json_obj(value: Any) -> dict[str, Any]:
    payload = safe_json_loads(value, default={}) if not isinstance(value, dict) else value
    return payload if isinstance(payload, dict) else {}


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _serialize_product(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["amount_total"] = int(payload.get("amount_total") or 0)
    payload["enabled"] = bool(payload.get("enabled"))
    payload["require_mobile"] = bool(payload.get("require_mobile"))
    payload["lead_program_id"] = int(payload.get("lead_program_id") or 0) or None
    payload["lead_channel_id"] = int(payload.get("lead_channel_id") or 0) or None
    payload["metadata_json"] = _json_obj(payload.get("metadata_json"))
    if "slice_count" in payload:
        payload["slice_count"] = int(payload.get("slice_count") or 0)
    return payload


def insert_product(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_products (
            product_code,
            name,
            amount_total,
            currency,
            status,
            enabled,
            cta_text,
            require_mobile,
            lead_program_id,
            lead_channel_id,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("product_code")),
            _normalized_text(payload.get("name")),
            int(payload.get("amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("status")) or "draft",
            bool(payload.get("enabled")),
            _normalized_text(payload.get("cta_text")) or "立即报名",
            bool(payload.get("require_mobile")),
            int(payload.get("lead_program_id") or 0) or None,
            int(payload.get("lead_channel_id") or 0) or None,
            _json(payload.get("metadata") or {}),
        ),
    ).fetchone()
    return _serialize_product(dict(row) if row else {}) or {}


def update_product(product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_products
        SET name = ?,
            amount_total = ?,
            currency = ?,
            status = ?,
            enabled = ?,
            cta_text = ?,
            require_mobile = ?,
            lead_program_id = ?,
            lead_channel_id = ?,
            metadata_json = CAST(? AS jsonb),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("name")),
            int(payload.get("amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("status")) or "draft",
            bool(payload.get("enabled")),
            _normalized_text(payload.get("cta_text")) or "立即报名",
            bool(payload.get("require_mobile")),
            int(payload.get("lead_program_id") or 0) or None,
            int(payload.get("lead_channel_id") or 0) or None,
            _json(payload.get("metadata") or {}),
            int(product_id),
        ),
    ).fetchone()
    return _serialize_product(dict(row) if row else {}) or {}


def get_product_by_id(product_id: int) -> dict[str, Any] | None:
    return _serialize_product(
        _fetchone_dict(
            """
            SELECT *
            FROM wechat_pay_products
            WHERE id = ?
            LIMIT 1
            """,
            (int(product_id),),
        )
    )


def get_product_by_code(product_code: str) -> dict[str, Any] | None:
    return _serialize_product(
        _fetchone_dict(
            """
            SELECT *
            FROM wechat_pay_products
            WHERE product_code = ?
            LIMIT 1
            """,
            (_normalized_text(product_code),),
        )
    )


def list_admin_products() -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT
            p.id,
            p.product_code,
            p.name,
            p.amount_total,
            p.currency,
            p.status,
            p.enabled,
            p.cta_text,
            p.require_mobile,
            p.lead_program_id,
            p.lead_channel_id,
            p.metadata_json,
            p.created_at,
            p.updated_at,
            COUNT(s.id) AS slice_count
        FROM wechat_pay_products p
        LEFT JOIN wechat_pay_product_page_slices s
          ON s.product_id = p.id AND s.enabled = TRUE
        GROUP BY
            p.id,
            p.product_code,
            p.name,
            p.amount_total,
            p.currency,
            p.status,
            p.enabled,
            p.cta_text,
            p.require_mobile,
            p.lead_program_id,
            p.lead_channel_id,
            p.metadata_json,
            p.created_at,
            p.updated_at
        ORDER BY p.updated_at DESC, p.id DESC
        """
    )
    return [_serialize_product(row) or {} for row in rows]


def list_active_db_products() -> list[dict[str, Any]]:
    return [
        _serialize_product(row) or {}
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM wechat_pay_products
            WHERE enabled = TRUE
              AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            """
        )
    ]


def delete_product(product_id: int) -> None:
    get_db().execute("DELETE FROM wechat_pay_products WHERE id = ?", (int(product_id),))


def count_orders_for_product_code(product_code: str) -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM wechat_pay_orders WHERE product_code = ?",
        (str(product_code or "").strip(),),
    ).fetchone()
    return int((row or {}).get("total") or 0)


def list_product_slices(
    product_id: int,
    *,
    enabled_only: bool = True,
    include_image_data: bool = True,
) -> list[dict[str, Any]]:
    where = ["s.product_id = ?"]
    params: list[Any] = [int(product_id)]
    if enabled_only:
        where.append("s.enabled = TRUE")
        where.append("image.enabled = TRUE")
    image_data_columns = (
        "image.source_url,\n            image.data_base64"
        if include_image_data
        else "'' AS source_url,\n            '' AS data_base64"
    )
    rows = _fetchall_dicts(
        f"""
        SELECT
            s.id,
            s.product_id,
            s.image_library_id,
            s.sort_order,
            s.enabled,
            s.created_at,
            s.updated_at,
            image.name AS image_name,
            image.file_name,
            {image_data_columns},
            image.mime_type,
            image.file_size
        FROM wechat_pay_product_page_slices s
        JOIN image_library image ON image.id = s.image_library_id
        WHERE {" AND ".join(where)}
        ORDER BY s.sort_order ASC, s.id ASC
        """,
        tuple(params),
    )
    return [dict(row) for row in rows]


def replace_product_slices(product_id: int, slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db = get_db()
    db.execute("DELETE FROM wechat_pay_product_page_slices WHERE product_id = ?", (int(product_id),))
    for index, item in enumerate(slices):
        image_library_id = int(item.get("image_library_id") or 0)
        if image_library_id <= 0:
            continue
        db.execute(
            """
            INSERT INTO wechat_pay_product_page_slices (
                product_id,
                image_library_id,
                sort_order,
                enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (int(product_id), image_library_id, int(item.get("sort_order") or index + 1)),
        )
    return list_product_slices(int(product_id), enabled_only=False, include_image_data=False)


def add_product_slice(product_id: int, image_library_id: int, *, sort_order: int | None = None) -> dict[str, Any]:
    if sort_order is None:
        row = get_db().execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM wechat_pay_product_page_slices WHERE product_id = ?",
            (int(product_id),),
        ).fetchone()
        sort_order = int((row or {}).get("next_order") or 1)
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_product_page_slices (
            product_id,
            image_library_id,
            sort_order,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (int(product_id), int(image_library_id), int(sort_order)),
    ).fetchone()
    return dict(row) if row else {}


def reorder_product_slices(product_id: int, slice_ids: list[int]) -> list[dict[str, Any]]:
    db = get_db()
    for index, slice_id in enumerate(slice_ids):
        db.execute(
            """
            UPDATE wechat_pay_product_page_slices
            SET sort_order = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND product_id = ?
            """,
            (index + 1, int(slice_id), int(product_id)),
        )
    return list_product_slices(int(product_id), enabled_only=False, include_image_data=False)


def delete_product_slice(product_id: int, slice_id: int) -> None:
    get_db().execute(
        "DELETE FROM wechat_pay_product_page_slices WHERE id = ? AND product_id = ?",
        (int(slice_id), int(product_id)),
    )


