from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.pii_audit import PiiAuditEvent


class PiiAuditWriteError(RuntimeError):
    pass


class AdminConfigPiiAuditRepository:
    def __init__(self, *, engine: Engine | None = None) -> None:
        self._engine = engine

    def record_pii_access(self, event: PiiAuditEvent) -> None:
        engine = self._engine or get_engine()
        json_value = "CAST(:after_json AS jsonb)" if engine.dialect.name == "postgresql" else ":after_json"
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"""
                        INSERT INTO admin_operation_logs (
                            operator, action_type, target_type, target_id,
                            before_json, after_json, created_at
                        )
                        VALUES (
                            :operator, 'pii_access', :target_type, :target_id,
                            {"CAST('{}' AS jsonb)" if engine.dialect.name == "postgresql" else "'{}'"},
                            {json_value}, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "operator": event.actor_fingerprint,
                        "target_type": event.route_name,
                        "target_id": event.resource_fingerprint,
                        "after_json": json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True),
                    },
                )
        except SQLAlchemyError:
            raise PiiAuditWriteError("PII audit persistence failed") from None
