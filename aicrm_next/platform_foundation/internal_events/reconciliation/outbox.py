from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.shared.db_session import connect_raw_postgres, get_session_factory
from aicrm_next.shared.runtime import raw_database_url

from ..consumer_registry import InternalEventConsumerRegistry, current_internal_event_consumer_registry
from ..models import InternalEvent, InternalEventConsumerSpec, InternalEventCreateRequest
from ..outbox import InternalEventOutboxRelay, enqueue_transactional_internal_event_outbox
from ..payment import PAYMENT_SUCCEEDED_EVENT_TYPE, build_payment_succeeded_event_request
from ..repository import InternalEventRepository, automatic_due_predicate_sql, build_internal_event_repository


_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT = "2026-07-13T09:46:09Z"
_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL = "TIMESTAMPTZ '2026-07-13 09:46:09+00'"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _request_from_event(event: InternalEvent) -> InternalEventCreateRequest:
    return InternalEventCreateRequest(
        event_type=event.event_type,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        payload=dict(event.payload_json or {}),
        payload_summary=dict(event.payload_summary_json or {}),
        context=CommandContext(
            actor_id=event.actor_id,
            actor_type=event.actor_type,
            trace_id=event.trace_id,
            request_id=event.request_id,
            source_route=event.source_route,
        ),
        event_version=event.event_version,
        subject_type=event.subject_type,
        subject_id=event.subject_id,
        idempotency_key=event.idempotency_key,
        source_module=event.source_module,
        source_command_id=event.source_command_id,
        correlation_id=event.correlation_id,
        tenant_id=event.tenant_id,
    )


class InternalEventOutboxReconciliationService:
    """Count-only diagnostics and idempotent technical-gap repair.

    Repair only creates internal outbox/event/consumer-run rows. It never invokes
    a consumer handler or an external provider.
    """

    def __init__(
        self,
        repository: InternalEventRepository | None = None,
        consumer_registry: InternalEventConsumerRegistry | None = None,
        *,
        database_url: str = "",
    ) -> None:
        self._database_url = _text(database_url) or raw_database_url()
        self._repo = repository or build_internal_event_repository()
        self._registry = consumer_registry or current_internal_event_consumer_registry()
        self._session_factory = get_session_factory(self._database_url) if self._database_url else None

    def _payment_specs(self) -> list[InternalEventConsumerSpec]:
        return [
            InternalEventConsumerSpec(
                consumer_name=consumer.consumer_name,
                consumer_type=consumer.consumer_type,
                max_attempts=consumer.max_attempts,
            )
            for consumer in self._registry.list_for_event_type(PAYMENT_SUCCEEDED_EVENT_TYPE)
        ]

    def diagnose(self) -> dict[str, Any]:
        if self._session_factory is None:
            return {
                "ok": False,
                "error": "database_url_required",
                "real_external_call_executed": False,
                "pii_in_output": False,
            }
        with self._session_factory() as session:
            paid_without_outbox = int(
                session.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM wechat_pay_orders p
                        WHERE (p.status = 'paid' OR p.trade_state = 'SUCCESS')
                          AND COALESCE(p.paid_at, p.created_at) >= {_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL}
                          AND NOT EXISTS (
                              SELECT 1 FROM internal_event_outbox o
                              WHERE o.tenant_id = 'aicrm'
                                AND o.idempotency_key = 'payment.succeeded:' || p.out_trade_no
                          )
                        """
                    )
                ).scalar_one()
            )
            legacy_paid_without_outbox = int(
                session.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM wechat_pay_orders p
                        WHERE (p.status = 'paid' OR p.trade_state = 'SUCCESS')
                          AND COALESCE(p.paid_at, p.created_at) < {_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL}
                          AND NOT EXISTS (
                              SELECT 1 FROM internal_event_outbox o
                              WHERE o.tenant_id = 'aicrm'
                                AND o.idempotency_key = 'payment.succeeded:' || p.out_trade_no
                          )
                        """
                    )
                ).scalar_one()
            )
            relayed_outbox_without_event = int(
                session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM internal_event_outbox o
                        LEFT JOIN internal_event e ON e.event_id = o.internal_event_id
                        WHERE o.status = 'relayed'
                          AND (o.internal_event_id = '' OR e.id IS NULL)
                        """
                    )
                ).scalar_one()
            )
            stale_running_consumer_count = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM internal_event_consumer_run "
                        "WHERE status = 'running' AND locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'"
                    )
                ).scalar_one()
            )
            stale_running_outbox_count = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM internal_event_outbox "
                        "WHERE status = 'running' AND locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'"
                    )
                ).scalar_one()
            )
            manual_only_count = int(
                session.execute(
                    text("SELECT COUNT(*) FROM internal_event_consumer_run WHERE status IN ('failed_terminal', 'blocked')")
                ).scalar_one()
            )
            manual_only_in_automatic_due_count = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM internal_event_consumer_run r "
                        f"WHERE r.status IN ('failed_terminal', 'blocked') AND ({automatic_due_predicate_sql('r')})"
                    )
                ).scalar_one()
            )
            missing_by_consumer: dict[str, int] = {}
            legacy_missing_by_consumer: dict[str, int] = {}
            for spec in self._payment_specs():
                missing_by_consumer[spec.consumer_name] = int(
                    session.execute(
                        text(
                            f"""
                            SELECT COUNT(*)
                            FROM internal_event e
                            WHERE e.event_type = :event_type
                              AND e.created_at >= {_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL}
                              AND NOT EXISTS (
                                  SELECT 1 FROM internal_event_consumer_run r
                                  WHERE r.event_id = e.event_id AND r.consumer_name = :consumer_name
                              )
                            """
                        ),
                        {"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE, "consumer_name": spec.consumer_name},
                    ).scalar_one()
                )
                legacy_missing_by_consumer[spec.consumer_name] = int(
                    session.execute(
                        text(
                            f"""
                            SELECT COUNT(*)
                            FROM internal_event e
                            WHERE e.event_type = :event_type
                              AND e.created_at < {_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL}
                              AND NOT EXISTS (
                                  SELECT 1 FROM internal_event_consumer_run r
                                  WHERE r.event_id = e.event_id AND r.consumer_name = :consumer_name
                              )
                            """
                        ),
                        {"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE, "consumer_name": spec.consumer_name},
                    ).scalar_one()
                )
        outbox_metrics = self._repo.outbox_metrics()
        queue_metrics = self._repo.queue_metrics({"event_type": PAYMENT_SUCCEEDED_EVENT_TYPE})
        return {
            "ok": True,
            "paid_without_outbox_count": paid_without_outbox,
            "legacy_paid_without_outbox_count": legacy_paid_without_outbox,
            "relayed_outbox_without_event_count": relayed_outbox_without_event,
            "event_missing_consumer_run_count": sum(missing_by_consumer.values()),
            "event_missing_consumer_run_by_consumer": missing_by_consumer,
            "legacy_event_missing_consumer_run_count": sum(legacy_missing_by_consumer.values()),
            "legacy_event_missing_consumer_run_by_consumer": legacy_missing_by_consumer,
            "actionable_cutover_at": _INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT,
            "manual_only_consumer_count": manual_only_count,
            "manual_only_in_automatic_due_count": manual_only_in_automatic_due_count,
            "stale_running_consumer_count": stale_running_consumer_count,
            "stale_running_outbox_count": stale_running_outbox_count,
            "queue_metrics": queue_metrics,
            "outbox_metrics": outbox_metrics,
            "real_external_call_executed": False,
            "pii_in_output": False,
        }

    def repair(self, *, dry_run: bool = True, limit: int = 100) -> dict[str, Any]:
        before = self.diagnose()
        if not before.get("ok") or dry_run:
            return {
                "ok": bool(before.get("ok")),
                "dry_run": True,
                "before": before,
                "repaired": {"payment_outbox_count": 0, "outbox_event_count": 0, "consumer_run_count": 0},
                "real_external_call_executed": False,
                "pii_in_output": False,
            }
        if not self._database_url or self._session_factory is None:
            return {"ok": False, "error": "database_url_required", "dry_run": False, "real_external_call_executed": False, "pii_in_output": False}

        payment_outbox_count = self._repair_paid_without_outbox(limit=limit)
        with self._session_factory() as session:
            reset = session.execute(
                text(
                    """
                    UPDATE internal_event_outbox o
                    SET status = 'pending', internal_event_id = '', relayed_at = NULL,
                        next_retry_at = CURRENT_TIMESTAMP, lease_token = '', locked_at = NULL, locked_by = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE o.status = 'relayed'
                      AND NOT EXISTS (SELECT 1 FROM internal_event e WHERE e.event_id = o.internal_event_id)
                    """
                )
            )
            outbox_event_count = int(reset.rowcount or 0)
            session.commit()

        relay_result = InternalEventOutboxRelay(self._repo, self._registry).relay_due(limit=limit)
        consumer_run_count = self._repair_missing_consumer_runs(limit=limit)
        after = self.diagnose()
        return {
            "ok": bool(relay_result.get("ok")) and bool(after.get("ok")),
            "dry_run": False,
            "before": before,
            "after": after,
            "repaired": {
                "payment_outbox_count": payment_outbox_count,
                "outbox_event_count": outbox_event_count,
                "consumer_run_count": consumer_run_count,
            },
            "relay": relay_result,
            "real_external_call_executed": False,
            "pii_in_output": False,
        }

    def _repair_paid_without_outbox(self, *, limit: int) -> int:
        from psycopg.rows import dict_row

        repaired = 0
        with connect_raw_postgres(self._database_url) as conn:
            conn.row_factory = dict_row
            rows = conn.execute(
                f"""
                SELECT p.*
                FROM wechat_pay_orders p
                WHERE (p.status = 'paid' OR p.trade_state = 'SUCCESS')
                  AND COALESCE(p.paid_at, p.created_at) >= {_INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT_SQL}
                  AND NOT EXISTS (
                      SELECT 1 FROM internal_event_outbox o
                      WHERE o.tenant_id = 'aicrm'
                        AND o.idempotency_key = 'payment.succeeded:' || p.out_trade_no
                  )
                ORDER BY p.id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (max(1, min(int(limit or 100), 500)),),
            ).fetchall()
            for raw in rows:
                order = dict(raw)
                transaction = _json_object(order.get("notify_payload_json"))
                request = build_payment_succeeded_event_request(
                    order=order,
                    transaction=transaction,
                    domain_event_outbox_id=None,
                    source_route="internal_event_outbox_reconciliation",
                )
                if request is None:
                    continue
                enqueue_transactional_internal_event_outbox(conn, request)
                repaired += 1
            conn.commit()
        return repaired

    def _repair_missing_consumer_runs(self, *, limit: int) -> int:
        events, _ = self._repo.list_events(
            {
                "event_type": PAYMENT_SUCCEEDED_EVENT_TYPE,
                "created_from": _INTERNAL_EVENT_RECONCILIATION_CUTOVER_AT,
            },
            limit=max(1, min(int(limit or 100), 200)),
        )
        repaired = 0
        specs = self._payment_specs()
        for event in events:
            existing, _ = self._repo.list_consumer_runs({"event_id": event.event_id}, limit=200)
            existing_names = {run.consumer_name for run in existing}
            missing = [spec for spec in specs if spec.consumer_name not in existing_names]
            if not missing:
                continue
            self._repo.create_event_with_consumer_runs(_request_from_event(event), missing)
            repaired += len(missing)
        return repaired
