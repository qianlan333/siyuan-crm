from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import AudienceTransitionEvent


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class AudienceTransitionRepository:
    """Read committed audience transition state for Next application services."""

    def build_current_event(
        self,
        *,
        member_id: int = 0,
        external_userid: str = "",
        operator_id: str = "",
        entry_source: str = "",
    ) -> AudienceTransitionEvent | None:
        member = self._find_member(member_id=member_id, external_userid=external_userid)
        if not member:
            return None
        entry = self._find_current_entry(int(member.get("id") or 0))
        if not entry:
            return None
        return AudienceTransitionEvent(
            member_id=int(member.get("id") or 0),
            external_userid=_text(member.get("external_contact_id") or external_userid),
            program_id=int(member.get("program_id") or 0),
            source_channel_id=int(member.get("source_channel_id") or 0),
            audience_entry_id=int(entry.get("id") or 0),
            audience_code=_text(entry.get("audience_code")),
            entry_reason=_text(entry.get("entry_reason")),
            entry_source=_text(entry.get("entry_source")) or _text(entry_source),
            operator_id=_text(operator_id) or _text(entry_source) or "audience_transition",
            occurred_at=_text(entry.get("entered_at")),
        )

    def _find_member(self, *, member_id: int = 0, external_userid: str = "") -> dict[str, Any] | None:
        db = get_db()
        row = None
        if int(member_id or 0) > 0:
            row = db.execute(
                """
                SELECT m.id, m.external_contact_id, m.source_channel_id, c.program_id
                FROM automation_member m
                LEFT JOIN automation_channel c ON c.id = m.source_channel_id
                WHERE m.id = ?
                LIMIT 1
                """,
                (int(member_id),),
            ).fetchone()
        if not row and _text(external_userid):
            row = db.execute(
                """
                SELECT m.id, m.external_contact_id, m.source_channel_id, c.program_id
                FROM automation_member m
                LEFT JOIN automation_channel c ON c.id = m.source_channel_id
                WHERE m.external_contact_id = ?
                ORDER BY m.updated_at DESC NULLS LAST, m.id DESC
                LIMIT 1
                """,
                (_text(external_userid),),
            ).fetchone()
        return dict(row) if row else None

    def _find_current_entry(self, member_id: int) -> dict[str, Any] | None:
        if _int(member_id) <= 0:
            return None
        row = get_db().execute(
            """
            SELECT id, member_id, audience_code, entered_at, entry_source, entry_reason
            FROM automation_member_audience_entry
            WHERE member_id = ?
              AND is_current = TRUE
            ORDER BY entered_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (int(member_id),),
        ).fetchone()
        return dict(row) if row else None
