from __future__ import annotations

import json
import secrets
from typing import Any

from ...db import get_db
from ...infra.helpers import db_bool
from ...infra.json_utils import json_dumps, safe_json_loads


DEFAULT_TENANT_ID = "aicrm"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


def _json_obj(value: Any) -> dict[str, Any]:
    payload = safe_json_loads(value, default={}) if not isinstance(value, dict) else value
    return payload if isinstance(payload, dict) else {}


def _serialize_config(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["enabled"] = bool(payload.get("enabled"))
    payload["custom_params"] = _json_obj(payload.get("custom_params"))
    payload["has_secret"] = bool(_normalized_text(payload.get("secret")))
    payload.pop("secret", None)
    return payload


def _serialize_delivery(row: dict[str, Any] | None, *, include_body: bool = True) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["config_id"] = int(payload.get("config_id") or 0)
    payload["order_id"] = int(payload.get("order_id") or 0)
    payload["product_id"] = int(payload.get("product_id") or 0)
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["request_headers"] = _json_obj(payload.get("request_headers"))
    payload["request_body"] = _json_obj(payload.get("request_body")) if include_body else {}
    payload["response_body"] = _normalized_text(payload.get("response_body"))
    return payload


def _serialize_outbox(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["retry_count"] = int(payload.get("retry_count") or 0)
    payload["payload"] = _json_obj(payload.get("payload"))
    return payload


def generate_delivery_id() -> str:
    return "deliv_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def get_product_config(product_id: int, *, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT *
        FROM external_push_config
        WHERE tenant_id = ?
          AND target_type = 'product'
          AND target_id = ?
          AND event_type = 'transaction.paid'
        LIMIT 1
        """,
        (_normalized_text(tenant_id) or DEFAULT_TENANT_ID, str(int(product_id))),
    ).fetchone()
    return _serialize_config(dict(row) if row else None)


def get_config_with_secret(config_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM external_push_config WHERE id = ? LIMIT 1",
        (int(config_id),),
    ).fetchone()
    return dict(row) if row else None


def upsert_product_config(product_id: int, payload: dict[str, Any], *, operator: str = "", tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    existing = get_product_config(int(product_id), tenant_id=tenant_id)
    existing_secret = ""
    if existing:
        secret_row = get_config_with_secret(int(existing["id"]))
        existing_secret = _normalized_text((secret_row or {}).get("secret"))
    secret = _normalized_text(payload.get("secret")) if "secret" in payload else existing_secret
    row = get_db().execute(
        """
        INSERT INTO external_push_config (
            tenant_id, target_type, target_id, event_type, enabled, webhook_url, push_type,
            expires_at_ts, day, frequency, remark, custom_params, secret, created_by, updated_by,
            created_at, updated_at
        )
        VALUES (?, 'product', ?, 'transaction.paid', ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id, target_type, target_id, event_type)
        DO UPDATE SET
            enabled = EXCLUDED.enabled,
            webhook_url = EXCLUDED.webhook_url,
            push_type = EXCLUDED.push_type,
            expires_at_ts = EXCLUDED.expires_at_ts,
            day = EXCLUDED.day,
            frequency = EXCLUDED.frequency,
            remark = EXCLUDED.remark,
            custom_params = EXCLUDED.custom_params,
            secret = EXCLUDED.secret,
            updated_by = EXCLUDED.updated_by,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            _normalized_text(tenant_id) or DEFAULT_TENANT_ID,
            str(int(product_id)),
            db_bool(payload.get("enabled")),
            _normalized_text(payload.get("webhook_url")),
            _normalized_text(payload.get("push_type")),
            payload.get("expires_at_ts"),
            payload.get("day"),
            payload.get("frequency"),
            _normalized_text(payload.get("remark")),
            _json(payload.get("custom_params") or {}),
            secret,
            _normalized_text(operator),
            _normalized_text(operator),
        ),
    ).fetchone()
    get_db().commit()
    return _serialize_config(dict(row) if row else {}) or {}


def insert_outbox_event(
    *,
    tenant_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        INSERT INTO domain_event_outbox (
            tenant_id, event_type, aggregate_type, aggregate_id, payload, status,
            retry_count, next_retry_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, CAST(? AS jsonb), 'pending', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id, event_type, aggregate_type, aggregate_id) DO NOTHING
        RETURNING *
        """,
        (
            _normalized_text(tenant_id) or DEFAULT_TENANT_ID,
            _normalized_text(event_type),
            _normalized_text(aggregate_type),
            _normalized_text(aggregate_id),
            _json(payload or {}),
        ),
    ).fetchone()
    return _serialize_outbox(dict(row) if row else None)


def list_due_outbox_events(*, limit: int = 20) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT *
        FROM domain_event_outbox
        WHERE status IN ('pending', 'failed')
          AND event_type = 'transaction.paid'
          AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return [_serialize_outbox(dict(row) if row else None) or {} for row in rows]


def mark_outbox_status(outbox_id: int, *, status: str, retry_count: int | None = None, next_retry_at: str | None = None) -> dict[str, Any] | None:
    normalized_next_retry_at = _normalized_text(next_retry_at) or None
    row = get_db().execute(
        """
        UPDATE domain_event_outbox
        SET status = ?,
            retry_count = COALESCE(?, retry_count),
            next_retry_at = ?::timestamptz,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (_normalized_text(status), retry_count, normalized_next_retry_at, int(outbox_id)),
    ).fetchone()
    get_db().commit()
    return _serialize_outbox(dict(row) if row else None)


def create_delivery_once(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, '{}'::jsonb, '{}'::jsonb, NULL, '', '', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (config_id, order_id, event_type) WHERE order_id > 0
        DO UPDATE SET updated_at = external_push_delivery.updated_at
        RETURNING *
        """,
        (
            _normalized_text(payload.get("tenant_id")) or DEFAULT_TENANT_ID,
            int(payload.get("config_id") or 0),
            _normalized_text(payload.get("event_type")),
            _normalized_text(payload.get("delivery_id")) or generate_delivery_id(),
            _normalized_text(payload.get("target_type")),
            _normalized_text(payload.get("target_id")),
            int(payload.get("order_id") or 0),
            int(payload.get("product_id") or 0),
            _normalized_text(payload.get("request_url")),
        ),
    ).fetchone()
    get_db().commit()
    return _serialize_delivery(dict(row) if row else {}) or {}


def create_test_delivery(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES (?, ?, 'external_push.test', ?, 'product', ?, 0, ?, 'pending', 0, ?, '{}'::jsonb, '{}'::jsonb, NULL, '', '', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("tenant_id")) or DEFAULT_TENANT_ID,
            int(payload.get("config_id") or 0),
            _normalized_text(payload.get("delivery_id")) or generate_delivery_id(),
            _normalized_text(payload.get("target_id")),
            int(payload.get("product_id") or 0),
            _normalized_text(payload.get("request_url")),
        ),
    ).fetchone()
    get_db().commit()
    return _serialize_delivery(dict(row) if row else {}) or {}


def update_delivery_result(
    delivery_id: str,
    *,
    status: str,
    attempt_count: int,
    request_url: str,
    request_headers: dict[str, Any],
    request_body: dict[str, Any],
    response_status: int | None,
    response_body: str,
    error_message: str,
    next_retry_at: str | None,
) -> dict[str, Any]:
    normalized_next_retry_at = _normalized_text(next_retry_at) or None
    row = get_db().execute(
        """
        UPDATE external_push_delivery
        SET status = ?,
            attempt_count = ?,
            request_url = ?,
            request_headers = CAST(? AS jsonb),
            request_body = CAST(? AS jsonb),
            response_status = ?,
            response_body = ?,
            error_message = ?,
            next_retry_at = ?::timestamptz,
            updated_at = CURRENT_TIMESTAMP
        WHERE delivery_id = ?
        RETURNING *
        """,
        (
            _normalized_text(status),
            int(attempt_count),
            _normalized_text(request_url),
            _json(request_headers or {}),
            _json(request_body or {}),
            response_status,
            _normalized_text(response_body),
            _normalized_text(error_message),
            normalized_next_retry_at,
            _normalized_text(delivery_id),
        ),
    ).fetchone()
    get_db().commit()
    return _serialize_delivery(dict(row) if row else {}) or {}


def get_delivery_by_delivery_id(delivery_id: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM external_push_delivery WHERE delivery_id = ? LIMIT 1",
        (_normalized_text(delivery_id),),
    ).fetchone()
    return _serialize_delivery(dict(row) if row else None)


def list_deliveries_for_order(order_id: int, *, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT *
        FROM external_push_delivery
        WHERE tenant_id = ?
          AND order_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (_normalized_text(tenant_id) or DEFAULT_TENANT_ID, int(order_id)),
    ).fetchall()
    return [_serialize_delivery(dict(row) if row else None) or {} for row in rows]


def list_due_deliveries(*, limit: int = 20) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT *
        FROM external_push_delivery
        WHERE status IN ('failed', 'retrying')
          AND next_retry_at IS NOT NULL
          AND next_retry_at <= CURRENT_TIMESTAMP
        ORDER BY next_retry_at ASC, id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return [_serialize_delivery(dict(row) if row else None) or {} for row in rows]
