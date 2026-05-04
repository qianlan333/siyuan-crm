from __future__ import annotations

from typing import Any

from flask import current_app

_MISSING_KEY_LABELS = {
    "host": "MESSAGE_ACTIVITY_DB_HOST",
    "database": "MESSAGE_ACTIVITY_DB_NAME",
    "user": "MESSAGE_ACTIVITY_DB_USER",
    "password": "MESSAGE_ACTIVITY_DB_PASS",
}


MESSAGE_ACTIVITY_SQL = """
SELECT
  LEFT(TRIM(u.phone), 3) AS phone_prefix3,
  RIGHT(TRIM(u.phone), 4) AS phone_last4,
  CONCAT(LEFT(TRIM(u.phone), 3), '_', RIGHT(TRIM(u.phone), 4)) AS phone_match_key,
  COUNT(m.id) AS message_count
FROM new_version_users u
LEFT JOIN new_version_messages m
  ON m.user_id = u.id
 AND m.is_deleted = 0
 AND m.role = 'user'
WHERE u.is_deleted = 0
  AND u.phone IS NOT NULL
  AND TRIM(u.phone) <> ''
  AND CHAR_LENGTH(TRIM(u.phone)) >= 7
  AND (
    u.nickname IS NULL
    OR (
      u.nickname NOT LIKE '%neo%'
      AND u.nickname NOT LIKE '%Neo%'
    )
  )
GROUP BY
  LEFT(TRIM(u.phone), 3),
  RIGHT(TRIM(u.phone), 4),
  CONCAT(LEFT(TRIM(u.phone), 3), '_', RIGHT(TRIM(u.phone), 4))
"""


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _db_config() -> dict[str, Any]:
    return {
        "host": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_DB_HOST")),
        "port": int(current_app.config.get("MESSAGE_ACTIVITY_DB_PORT") or 3306),
        "database": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_DB_NAME")),
        "user": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_DB_USER")),
        "password": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_DB_PASS")),
    }


def get_message_activity_db_status() -> dict[str, Any]:
    config = _db_config()
    missing = [key for key, value in config.items() if key != "port" and not value]
    return {
        "configured": not missing,
        "missing_keys": [_MISSING_KEY_LABELS.get(key, f"MESSAGE_ACTIVITY_DB_{key.upper()}") for key in missing],
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "user": config["user"],
    }


def query_message_activity_counts() -> list[dict[str, Any]]:
    status = get_message_activity_db_status()
    if not status["configured"]:
        raise ValueError("message activity db is not configured")
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError("PyMySQL is required for message activity sync") from exc

    config = _db_config()
    connection = pymysql.connect(
        host=config["host"],
        port=int(config["port"] or 3306),
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(MESSAGE_ACTIVITY_SQL)
            rows = cursor.fetchall() or []
    finally:
        connection.close()
    return [
        {
            "phone_prefix3": _normalized_text(row.get("phone_prefix3")),
            "phone_last4": _normalized_text(row.get("phone_last4")),
            "phone_match_key": _normalized_text(row.get("phone_match_key")),
            "message_count": int(row.get("message_count") or 0),
        }
        for row in rows
        if _normalized_text(row.get("phone_match_key"))
    ]
