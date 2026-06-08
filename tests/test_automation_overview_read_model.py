from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from aicrm_next.automation_engine.overview_read_model import (
    AutomationOverviewReadModel,
    AutomationPoolReadModel,
    AutomationStageColumnProjection,
)
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def automation_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_member (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_contact_id TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    owner_staff_id TEXT NOT NULL DEFAULT '',
                    in_pool BOOLEAN NOT NULL DEFAULT FALSE,
                    current_pool TEXT NOT NULL DEFAULT 'removed',
                    follow_type TEXT NOT NULL DEFAULT '',
                    current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
                    joined_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
    return engine


def _seed_member(
    engine,
    *,
    external_contact_id: str,
    in_pool: bool = True,
    current_pool: str = "operating",
    follow_type: str = "normal",
    current_audience_code: str = "operating",
    joined_at: str = "2026-04-06 09:00:00",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool,
                    current_pool, follow_type, current_audience_code, joined_at
                )
                VALUES (
                    :external_contact_id, :phone, 'sales_01', :in_pool,
                    :current_pool, :follow_type, :current_audience_code, :joined_at
                )
                """
            ),
            {
                "external_contact_id": external_contact_id,
                "phone": external_contact_id[-11:],
                "in_pool": in_pool,
                "current_pool": current_pool,
                "follow_type": follow_type,
                "current_audience_code": current_audience_code,
                "joined_at": joined_at,
            },
        )


def _today() -> date:
    return date(2026, 4, 6)


def test_overview_read_model_matches_legacy_automation_member_counts(automation_engine) -> None:
    _seed_member(
        automation_engine,
        external_contact_id="wm_overview_001",
        current_audience_code="pending_questionnaire",
        follow_type="normal",
    )
    _seed_member(automation_engine, external_contact_id="wm_overview_002", current_audience_code="operating", follow_type="focus")
    _seed_member(
        automation_engine,
        external_contact_id="wm_overview_003",
        current_audience_code="operating",
        follow_type="normal",
        joined_at="2026-04-05 09:20:00",
    )
    _seed_member(
        automation_engine,
        external_contact_id="wm_overview_004",
        current_audience_code="converted",
        follow_type="focus",
        in_pool=False,
    )

    payload = AutomationOverviewReadModel(engine=automation_engine, today_provider=_today).execute()
    pools = AutomationPoolReadModel(engine=automation_engine, today_provider=_today).execute()

    assert payload["source_status"] == "next_read_model"
    assert "compatibility_facade" not in payload
    assert payload["counts"] == {
        "in_pool_total": 3,
        "today_joined": 3,
        "questionnaire_pending": 1,
        "operating_total": 2,
        "converted_total": 1,
    }
    assert {card["key"]: card["value"] for card in payload["cards"]} == {
        "in_pool_total": 3,
        "today_joined": 3,
        "questionnaire_pending": 1,
        "operating_total": 2,
        "converted_total": 1,
    }
    by_pool = {item["pool_key"]: item for item in pools["pools"]}
    assert by_pool["pending_questionnaire"]["count"] == 1
    assert by_pool["operating"]["count"] == 2
    assert by_pool["operating"]["focus_count"] == 1
    assert by_pool["operating"]["normal_count"] == 1
    assert by_pool["operating"]["today_new_count"] == 1
    assert by_pool["converted"]["count"] == 1


def test_empty_data_read_model_is_safe(automation_engine) -> None:
    overview = AutomationOverviewReadModel(engine=automation_engine, today_provider=_today).execute()
    pools = AutomationPoolReadModel(engine=automation_engine, today_provider=_today).execute()

    assert overview["ok"] is True
    assert overview["total"] == 0
    assert all(card["value"] == 0 for card in overview["cards"])
    assert pools["ok"] is True
    assert pools["total"] == 3
    assert all(item["count"] == 0 for item in pools["pools"])


def test_focus_to_normal_change_updates_overview_and_pools(automation_engine) -> None:
    _seed_member(automation_engine, external_contact_id="wm_focus_switch", current_audience_code="operating", follow_type="normal")

    before = AutomationPoolReadModel(engine=automation_engine, today_provider=_today).execute()
    with automation_engine.begin() as conn:
        conn.execute(text("UPDATE automation_member SET follow_type = 'focus' WHERE external_contact_id = 'wm_focus_switch'"))
    after = AutomationPoolReadModel(engine=automation_engine, today_provider=_today).execute()

    before_operating = {item["pool_key"]: item for item in before["pools"]}["operating"]
    after_operating = {item["pool_key"]: item for item in after["pools"]}["operating"]
    assert before_operating["normal_count"] == 1
    assert before_operating["focus_count"] == 0
    assert after_operating["normal_count"] == 0
    assert after_operating["focus_count"] == 1


def test_overview_read_model_includes_operational_status_without_side_effects(automation_engine) -> None:
    with automation_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_message_activity_sync_run (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_source TEXT NOT NULL DEFAULT 'manual',
                    operator_type TEXT NOT NULL DEFAULT 'system',
                    operator_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'success',
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    matched_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    skipped_ambiguous_count INTEGER NOT NULL DEFAULT 0,
                    skipped_unmatched_count INTEGER NOT NULL DEFAULT 0,
                    skipped_missing_phone_count INTEGER NOT NULL DEFAULT 0,
                    focus_count INTEGER NOT NULL DEFAULT 0,
                    normal_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_message_activity_sync_run (
                    trigger_source, operator_type, operator_id, status, candidate_count,
                    matched_count, updated_count, focus_count, normal_count, summary_json,
                    started_at, finished_at
                )
                VALUES (
                    'manual', 'user', 'tester', 'success', 10, 6, 4, 2, 2,
                    '{"note": "ok"}', '2026-04-06 08:00:00', '2026-04-06 08:01:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_reply_monitor_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT NOT NULL UNIQUE,
                    enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    last_capture_cursor INTEGER NOT NULL DEFAULT 0,
                    last_capture_at TEXT NOT NULL DEFAULT '',
                    last_capture_status TEXT NOT NULL DEFAULT '',
                    last_capture_summary_json TEXT NOT NULL DEFAULT '{}',
                    last_dispatch_at TEXT NOT NULL DEFAULT '',
                    last_dispatch_status TEXT NOT NULL DEFAULT '',
                    last_dispatch_summary_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT NOT NULL DEFAULT '',
                    quiet_hours_start TEXT NOT NULL DEFAULT '23:00',
                    quiet_hours_end TEXT NOT NULL DEFAULT '09:00',
                    dispatch_interval_seconds INTEGER NOT NULL DEFAULT 30
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_reply_monitor_config (
                    config_key, enabled, last_capture_cursor, last_capture_at, last_capture_status,
                    last_capture_summary_json, last_dispatch_at, last_dispatch_status,
                    last_dispatch_summary_json, quiet_hours_start, quiet_hours_end, dispatch_interval_seconds
                )
                VALUES (
                    'default', 1, 42, '2026-04-06 09:00:00', 'success', '{"captured": 3}',
                    '2026-04-06 09:01:00', 'idle', '{"sent": 2}', '23:00', '09:00', 30
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_reply_monitor_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
        )
        conn.execute(text("INSERT INTO automation_reply_monitor_queue (status) VALUES ('pending'), ('paused'), ('failed')"))

    payload = AutomationOverviewReadModel(engine=automation_engine, today_provider=_today).execute()

    assert payload["message_activity_sync"]["last_run"]["status_label"] == "成功"
    assert payload["message_activity_sync"]["last_run"]["updated_count"] == 4
    assert payload["message_activity_sync"]["last_run"]["summary"] == {"note": "ok"}
    assert payload["reply_monitor"]["enabled"] is True
    assert payload["reply_monitor"]["last_capture_status_label"] == "成功"
    assert payload["reply_monitor"]["queue_counts"]["active_total"] == 2
    assert payload["auto_start_window"]["timezone"] == "Asia/Shanghai"


def test_stage_column_projection_keeps_legacy_stage_contract() -> None:
    rows = [
        {"current_audience_code": "pending_questionnaire", "follow_type": "normal", "joined_at": "2026-04-06 10:00:00"},
        {"current_audience_code": "operating", "follow_type": "focus", "joined_at": "2026-04-06 10:00:00"},
        {"current_audience_code": "converted", "follow_type": "focus", "joined_at": "2026-04-05 10:00:00"},
    ]

    columns = AutomationStageColumnProjection(rows, today=_today()).execute()

    assert [item["pool"] for item in columns] == ["pending_questionnaire", "operating", "converted"]
    assert [item["route_key"] for item in columns] == ["pending-questionnaire", "operating", "converted"]
    assert {item["pool"]: item["today_new_count"] for item in columns} == {
        "pending_questionnaire": 1,
        "operating": 1,
        "converted": 0,
    }


def test_overview_and_pool_apis_are_next_read_model_without_legacy_facade(monkeypatch: pytest.MonkeyPatch, automation_engine) -> None:
    monkeypatch.setenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr("aicrm_next.automation_engine.overview_read_model._default_engine", lambda: automation_engine)
    _seed_member(automation_engine, external_contact_id="wm_api_001", current_audience_code="pending_questionnaire")

    client = TestClient(create_app(), raise_server_exceptions=False)
    overview = client.get("/api/admin/automation-conversion/overview")
    pools = client.get("/api/admin/automation-conversion/pools")

    for response in (overview, pools):
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert response.headers["X-AICRM-Fallback-Used"] == "false"
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        body = response.json()
        assert body["source_status"] == "next_read_model"
        assert "compatibility_facade" not in body

    assert overview.json()["counts"]["questionnaire_pending"] == 1
    assert {item["pool_key"]: item["count"] for item in pools.json()["pools"]}["pending_questionnaire"] == 1


def test_automation_conversion_page_renders_next_native_program_list_without_legacy_facade(
    monkeypatch: pytest.MonkeyPatch, automation_engine
) -> None:
    monkeypatch.setenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr("aicrm_next.automation_engine.overview_read_model._default_engine", lambda: automation_engine)
    _seed_member(automation_engine, external_contact_id="wm_page_001", current_audience_code="operating", follow_type="focus")
    _seed_member(
        automation_engine,
        external_contact_id="wm_page_002",
        current_audience_code="operating",
        follow_type="normal",
        joined_at="2026-04-05 09:20:00",
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/admin/automation-conversion")
    html = response.text

    assert response.status_code == 200
    assert response.headers.get("X-AICRM-Compatibility-Facade") is None
    assert "客户管理后台" in html
    assert "方案列表" in html
    assert "每个方案人数按 automation_program_member 的 program_id 独立统计。" in html
    assert "X-AICRM-Compatibility-Facade" not in html


def test_overview_api_source_no_longer_imports_legacy_overview_or_pools() -> None:
    api_source = (ROOT / "aicrm_next/automation_engine/api.py").read_text(encoding="utf-8")

    assert "get_automation_overview_from_legacy" not in api_source
    assert "list_automation_pools_from_legacy" not in api_source
    assert "LegacyAutomationDataUnavailable" not in api_source
    assert not (ROOT / "aicrm_next/integration_gateway/legacy_automation_facade.py").exists()
