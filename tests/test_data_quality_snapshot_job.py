from __future__ import annotations

import json
from datetime import datetime, timezone

from aicrm_next.background_jobs.data_quality_snapshot import run_scheduled_data_quality_snapshot
from scripts.run_data_quality_snapshot import main as run_script


def test_scheduled_data_quality_snapshot_is_registry_only() -> None:
    payload = run_scheduled_data_quality_snapshot(
        now=datetime(2026, 7, 2, 8, 30, tzinfo=timezone.utc),
        operator="pytest",
    )

    assert payload["ok"] is True
    assert payload["job"] == "data_quality_snapshot"
    assert payload["dry_run"] is True
    assert payload["operator"] == "pytest"
    assert payload["source_status"] == "registry_metadata_only"
    assert payload["snapshot_status"] == "generated"
    assert payload["persistence_status"] == "not_configured"
    assert payload["persisted"] is False
    assert payload["database_probe_executed"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["summary"]["total_checks"] == 20
    assert len(payload["checks"]) == 20
    assert payload["snapshot_id"].startswith("dqs_")


def test_scheduled_data_quality_snapshot_execute_mode_is_still_safe_until_persistence_exists() -> None:
    payload = run_scheduled_data_quality_snapshot(
        dry_run=False,
        now=datetime(2026, 7, 2, 8, 30, tzinfo=timezone.utc),
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["persisted"] is False
    assert payload["persistence_status"] == "not_configured"
    assert payload["errors"] == []


def test_scheduled_data_quality_snapshot_does_not_emit_raw_identity_values() -> None:
    payload = run_scheduled_data_quality_snapshot(
        now=datetime(2026, 7, 2, 8, 30, tzinfo=timezone.utc),
    )
    serialized = json.dumps(payload, ensure_ascii=False)

    for forbidden in (
        "external_userid_value",
        "openid_value",
        "mobile_normalized_value",
        "unionid_value",
        "raw_payload_json",
    ):
        assert forbidden not in serialized


def test_run_data_quality_snapshot_script_outputs_json(capsys) -> None:
    exit_code = run_script(["--operator", "pytest-script"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["operator"] == "pytest-script"
    assert payload["dry_run"] is True
    assert payload["summary"]["probe_status_counts"] == {"needs_probe": 20, "registered": 0}
