from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import get_db

JsonDict = dict[str, Any]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _row(row: Any) -> JsonDict | None:
    return dict(row) if row else None


class PostgresSendTargetRepository:
    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_db()

    def fetch_send_target_by_unionid(self, unionid: str) -> JsonDict | None:
        row = self.db.execute(
            """
            SELECT
                unionid,
                primary_external_userid,
                primary_owner_userid,
                primary_owner_userid AS owner_userid,
                customer_name
            FROM crm_user_identity
            WHERE unionid = ?
            LIMIT 1
            """,
            (_text(unionid),),
        ).fetchone()
        return _row(row)

    def fetch_send_target_by_external_userid(self, external_userid: str) -> JsonDict | None:
        row = self.db.execute(
            """
            SELECT
                unionid,
                primary_external_userid,
                primary_owner_userid,
                primary_owner_userid AS owner_userid,
                customer_name
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC, unionid DESC
            LIMIT 1
            """,
            (_text(external_userid), _text(external_userid)),
        ).fetchone()
        return _row(row)

    def fetch_do_not_disturb_reasons(self, unionid: str) -> list[JsonDict]:
        try:
            rows = self.db.execute(
                """
                SELECT reason_code, reason_text, source_type
                FROM user_ops_do_not_disturb_next
                WHERE unionid = ?
                  AND is_active = TRUE
                ORDER BY id ASC
                """,
                (_text(unionid),),
            ).fetchall()
        except Exception:
            rollback = getattr(self.db, "rollback", None)
            if callable(rollback):
                rollback()
            return []
        return [
            {
                "reason_code": _text(row.get("reason_code")),
                "reason_text": _text(row.get("reason_text")),
                "source_type": _text(row.get("source_type")),
            }
            for row in rows
        ]
