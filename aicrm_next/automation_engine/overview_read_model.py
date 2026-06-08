from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.runtime import raw_database_url


AUTOMATION_OVERVIEW_ROUTE_FAMILY = "automation_conversion_overview_pools_next_read_model"

STAGE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "pool": "pending_questionnaire",
        "route_key": "pending-questionnaire",
        "label": "未填问卷人群",
        "description": "尚未完成问卷采集，等待提交问卷。",
    },
    {
        "pool": "operating",
        "route_key": "operating",
        "label": "运营中人群",
        "description": "问卷已提交后的统一运营主人群。",
    },
    {
        "pool": "converted",
        "route_key": "converted",
        "label": "已转化人群",
        "description": "人工确认转化后进入成交后运营。",
    },
)


def _text_value(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _business_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_prefix(value: Any) -> str:
    text_value = _text_value(value)
    if len(text_value) >= 10:
        return text_value[:10]
    return ""


def _joined_today(row: dict[str, Any], today: date) -> bool:
    return _date_prefix(row.get("joined_at")) == today.isoformat()


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _message_activity_sync_status_label(value: Any) -> str:
    normalized = _text_value(value)
    return {
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
        "not_configured": "未配置",
    }.get(normalized, normalized or "暂无记录")


def _reply_monitor_status_label(value: Any) -> str:
    normalized = _text_value(value)
    return {
        "idle": "空闲",
        "disabled": "已关闭",
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
        "not_configured": "未配置",
    }.get(normalized, normalized or "暂无记录")


class AutomationStageColumnProjection:
    def __init__(self, rows: list[dict[str, Any]], *, today: date) -> None:
        self._rows = rows
        self._today = today

    def execute(self) -> list[dict[str, Any]]:
        metrics: dict[str, dict[str, int]] = {
            definition["pool"]: {"total_count": 0, "focus_count": 0, "normal_count": 0, "today_new_count": 0}
            for definition in STAGE_DEFINITIONS
        }
        for row in self._rows:
            pool = _text_value(row.get("current_audience_code"))
            if pool not in metrics:
                continue
            metric = metrics[pool]
            metric["total_count"] += 1
            follow_type = _text_value(row.get("follow_type"))
            if follow_type == "focus":
                metric["focus_count"] += 1
            elif follow_type == "normal":
                metric["normal_count"] += 1
            if _joined_today(row, self._today):
                metric["today_new_count"] += 1
        return [
            {
                **definition,
                "total_count": metrics[definition["pool"]]["total_count"],
                "focus_count": metrics[definition["pool"]]["focus_count"],
                "normal_count": metrics[definition["pool"]]["normal_count"],
                "today_new_count": metrics[definition["pool"]]["today_new_count"],
            }
            for definition in STAGE_DEFINITIONS
        ]


class AutomationOverviewReadModel:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        engine: Any | None = None,
        today_provider: Callable[[], date] = _business_today,
    ) -> None:
        self._rows = rows
        self._engine = engine
        self._today_provider = today_provider

    def execute(self) -> dict[str, Any]:
        engine = self._resolve_engine()
        rows = self._load_rows(engine)
        today = self._today_provider()
        counts = self._counts(rows, today=today)
        stage_columns = AutomationStageColumnProjection(rows, today=today).execute()
        operational_status = self._operational_status(engine)
        return {
            "ok": True,
            "cards": self._cards(counts),
            "stage_columns": stage_columns,
            "counts": counts,
            "total": counts["in_pool_total"],
            "filters": {},
            "generated_at": _generated_at(),
            "status": "live",
            "source_status": "next_read_model",
            "route_owner": "ai_crm_next",
            **operational_status,
        }

    def _resolve_engine(self) -> Any | None:
        if self._engine is not None:
            return self._engine
        if not raw_database_url():
            return None
        return _default_engine()

    def _load_rows(self, engine: Any | None) -> list[dict[str, Any]]:
        if self._rows is not None:
            return [dict(row) for row in self._rows]
        if engine is None:
            return []
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT
                        in_pool,
                        current_pool,
                        follow_type,
                        current_audience_code,
                        joined_at
                    FROM automation_member
                    """
                )
            )
            return [dict(row._mapping) for row in result]

    def _operational_status(self, engine: Any | None) -> dict[str, Any]:
        return {
            "message_activity_sync": self._message_activity_sync_status(engine),
            "reply_monitor": self._reply_monitor_status(engine),
            "auto_start_window": self._auto_start_window_status(),
        }

    def _message_activity_sync_status(self, engine: Any | None) -> dict[str, Any]:
        last_run = self._latest_message_activity_sync_run(engine)
        return {
            "db_status": {"configured": bool(last_run), "status": "available" if last_run else "not_configured"},
            "scope_pools": [{"pool": "operating", "label": "运营中人群"}],
            "cron_script_path": "",
            "last_run": last_run,
            "recent_items": [],
        }

    def _latest_message_activity_sync_run(self, engine: Any | None) -> dict[str, Any]:
        if engine is None:
            return {}
        try:
            with engine.connect() as conn:
                row = (
                    conn.execute(
                        text(
                            """
                            SELECT
                                id,
                                trigger_source,
                                operator_type,
                                operator_id,
                                status,
                                candidate_count,
                                matched_count,
                                updated_count,
                                skipped_ambiguous_count,
                                skipped_unmatched_count,
                                skipped_missing_phone_count,
                                focus_count,
                                normal_count,
                                error_message,
                                summary_json,
                                started_at,
                                finished_at
                            FROM automation_message_activity_sync_run
                            ORDER BY finished_at DESC, id DESC
                            LIMIT 1
                            """
                        )
                    )
                    .mappings()
                    .first()
                )
        except Exception:
            return {}
        if row is None:
            return {}
        payload = dict(row)
        skipped_ambiguous_count = _int_value(payload.get("skipped_ambiguous_count"))
        skipped_unmatched_count = _int_value(payload.get("skipped_unmatched_count"))
        skipped_missing_phone_count = _int_value(payload.get("skipped_missing_phone_count"))
        status = _text_value(payload.get("status"))
        return {
            "id": _int_value(payload.get("id")),
            "trigger_source": _text_value(payload.get("trigger_source")),
            "operator_type": _text_value(payload.get("operator_type")),
            "operator_id": _text_value(payload.get("operator_id")),
            "status": status,
            "status_label": _message_activity_sync_status_label(status),
            "candidate_count": _int_value(payload.get("candidate_count")),
            "matched_count": _int_value(payload.get("matched_count")),
            "updated_count": _int_value(payload.get("updated_count")),
            "skipped_ambiguous_count": skipped_ambiguous_count,
            "skipped_unmatched_count": skipped_unmatched_count,
            "skipped_missing_phone_count": skipped_missing_phone_count,
            "skipped_count": skipped_ambiguous_count + skipped_unmatched_count + skipped_missing_phone_count,
            "focus_count": _int_value(payload.get("focus_count")),
            "normal_count": _int_value(payload.get("normal_count")),
            "error_message": _text_value(payload.get("error_message")),
            "started_at": _text_value(payload.get("started_at")),
            "finished_at": _text_value(payload.get("finished_at")),
            "summary": _json_dict(payload.get("summary_json")),
        }

    def _reply_monitor_status(self, engine: Any | None) -> dict[str, Any]:
        config = self._reply_monitor_config(engine)
        enabled = bool(config.get("enabled"))
        last_capture_status = _text_value(config.get("last_capture_status")) or ("disabled" if not enabled else "idle")
        last_dispatch_status = _text_value(config.get("last_dispatch_status")) or ("disabled" if not enabled else "idle")
        return {
            "enabled": enabled,
            "status": "enabled" if enabled else "disabled",
            "status_label": "开启中" if enabled else "已关闭",
            "description": "开启后自动监控自动化范围内用户的新私聊消息；夜间只入队不触发；关闭后停止自动触发但不影响聊天入库。",
            "last_capture_cursor": _int_value(config.get("last_capture_cursor")),
            "last_capture_at": _text_value(config.get("last_capture_at")),
            "last_capture_status": last_capture_status,
            "last_capture_status_label": _reply_monitor_status_label(last_capture_status),
            "last_capture_summary": _json_dict(config.get("last_capture_summary_json")),
            "last_dispatch_at": _text_value(config.get("last_dispatch_at")),
            "last_dispatch_status": last_dispatch_status,
            "last_dispatch_status_label": _reply_monitor_status_label(last_dispatch_status),
            "last_dispatch_summary": _json_dict(config.get("last_dispatch_summary_json")),
            "last_error": _text_value(config.get("last_error")),
            "quiet_hours_start": _text_value(config.get("quiet_hours_start")) or "23:00",
            "quiet_hours_end": _text_value(config.get("quiet_hours_end")) or "09:00",
            "dispatch_interval_seconds": _int_value(config.get("dispatch_interval_seconds")) or 30,
            "queue_counts": self._reply_monitor_queue_counts(engine),
            "recent_items": [],
        }

    def _reply_monitor_config(self, engine: Any | None) -> dict[str, Any]:
        if engine is None:
            return {}
        try:
            with engine.connect() as conn:
                row = (
                    conn.execute(
                        text(
                            """
                            SELECT
                                enabled,
                                last_capture_cursor,
                                last_capture_at,
                                last_capture_status,
                                last_capture_summary_json,
                                last_dispatch_at,
                                last_dispatch_status,
                                last_dispatch_summary_json,
                                last_error,
                                quiet_hours_start,
                                quiet_hours_end,
                                dispatch_interval_seconds
                            FROM automation_reply_monitor_config
                            WHERE config_key = 'default'
                            LIMIT 1
                            """
                        )
                    )
                    .mappings()
                    .first()
                )
        except Exception:
            return {}
        return dict(row) if row else {}

    def _reply_monitor_queue_counts(self, engine: Any | None) -> dict[str, int]:
        counts = {"pending": 0, "deferred_quiet_hours": 0, "dispatched": 0, "failed": 0, "paused": 0}
        if engine is None:
            counts["active_total"] = 0
            return counts
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT status, COUNT(*) AS total
                        FROM automation_reply_monitor_queue
                        GROUP BY status
                        """
                    )
                )
                for row in rows.mappings():
                    status = _text_value(row.get("status"))
                    if status in counts:
                        counts[status] = _int_value(row.get("total"))
        except Exception:
            pass
        counts["active_total"] = counts["pending"] + counts["deferred_quiet_hours"] + counts["paused"]
        return counts

    @staticmethod
    def _auto_start_window_status() -> dict[str, Any]:
        day_start_hour = 9
        quiet_hour_start = 23
        timezone_name = "Asia/Shanghai"
        return {
            "day_start_hour": day_start_hour,
            "quiet_hour_start": quiet_hour_start,
            "timezone": timezone_name,
            "label": f"{day_start_hour:02d}:00 - {quiet_hour_start:02d}:00",
            "description": f"按 {timezone_name} 时区，只有 {day_start_hour:02d}:00 - {quiet_hour_start:02d}:00 之间允许自动启动。",
        }

    @staticmethod
    def _counts(rows: list[dict[str, Any]], *, today: date) -> dict[str, int]:
        counts = {
            "in_pool_total": 0,
            "today_joined": 0,
            "questionnaire_pending": 0,
            "operating_total": 0,
            "converted_total": 0,
        }
        for row in rows:
            if bool(row.get("in_pool")):
                counts["in_pool_total"] += 1
            if _joined_today(row, today):
                counts["today_joined"] += 1
            audience = _text_value(row.get("current_audience_code"))
            if audience == "pending_questionnaire":
                counts["questionnaire_pending"] += 1
            elif audience == "operating":
                counts["operating_total"] += 1
            elif audience == "converted":
                counts["converted_total"] += 1
        return counts

    @staticmethod
    def _cards(counts: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {
                "key": "in_pool_total",
                "label": "在池总人数",
                "value": _int_value(counts.get("in_pool_total")),
                "description": "当前仍在自动化池里的成员数量。",
            },
            {
                "key": "today_joined",
                "label": "今日入池",
                "value": _int_value(counts.get("today_joined")),
                "description": "今天新进入自动化池的成员数量。",
            },
            {
                "key": "questionnaire_pending",
                "label": "未填问卷人群",
                "value": _int_value(counts.get("questionnaire_pending")),
                "description": "已入池但还没提交问卷。",
            },
            {
                "key": "operating_total",
                "label": "运营中人群",
                "value": _int_value(counts.get("operating_total")),
                "description": "问卷提交后的统一运营人群。",
            },
            {
                "key": "converted_total",
                "label": "已转化人群",
                "value": _int_value(counts.get("converted_total")),
                "description": "确认转化后的成员数量。",
            },
        ]


class AutomationPoolReadModel:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        engine: Any | None = None,
        today_provider: Callable[[], date] = _business_today,
    ) -> None:
        self._overview = AutomationOverviewReadModel(rows, engine=engine, today_provider=today_provider)

    def execute(self) -> dict[str, Any]:
        overview = self._overview.execute()
        pools = [
            {
                "pool_key": item.get("pool") or item.get("route_key") or "",
                "label": item.get("label") or "",
                "description": item.get("description") or "",
                "count": _int_value(item.get("total_count")),
                "focus_count": _int_value(item.get("focus_count")),
                "normal_count": _int_value(item.get("normal_count")),
                "today_new_count": _int_value(item.get("today_new_count")),
            }
            for item in overview["stage_columns"]
        ]
        return {
            "ok": True,
            "pools": pools,
            "total": len(pools),
            "generated_at": overview["generated_at"],
            "source_status": "next_read_model",
            "route_owner": "ai_crm_next",
        }


def _default_engine() -> Any:
    database_url = raw_database_url()
    if not database_url:
        return None
    return get_engine(database_url)
