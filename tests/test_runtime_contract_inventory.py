from __future__ import annotations

import json
from pathlib import Path

from scripts.ci.runtime_contract_inventory import (
    build_inventory,
    check_inventory,
    render_inventory,
    write_inventory,
)


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "architecture" / "runtime_contract_inventory.json"


def test_runtime_contract_inventory_covers_r00_behavior_surfaces() -> None:
    inventory = build_inventory(ROOT)

    assert inventory["schema_version"] == 1
    assert inventory["composition_root"] == "aicrm_next.main:create_app"
    assert inventory["production_data_accessed"] is False
    assert inventory["fixture_records_included"] is False

    routes = inventory["routes"]
    assert len(routes) >= 600
    assert any(route["path"] == "/health" and route["methods"] == ["GET"] for route in routes)
    assert any(route["kind"] == "page" for route in routes)
    assert all(route["capability_owner"] for route in routes)
    assert all("responses" in route["contract"] for route in routes)

    assert inventory["migration_heads"] == ["0124_questionnaire_continuation_jobs"]
    assert len(inventory["tables"]) >= 150
    owned_lifecycles = {"canonical", "read_model", "event", "queue", "config"}
    assert all(table["write_owner"] for table in inventory["tables"] if table["lifecycle"] in owned_lifecycles)
    assert inventory["internal_event_consumers"]
    assert inventory["external_effects"]
    assert any(unit["unit"] == "openclaw-wecom-callback-ingress.service" for unit in inventory["runtime_units"])
    assert "DATABASE_URL" in inventory["environment_variables"]
    assert {
        "AICRM_AUTH_ARCHIVE_WORKER_CLIENT_ID",
        "AICRM_AUTH_ARCHIVE_WORKER_CLIENT_SECRET_REF",
        "AICRM_AUTH_AUTOMATION_WORKER_CLIENT_ID",
        "AICRM_AUTH_AUTOMATION_WORKER_CLIENT_SECRET_REF",
        "AICRM_AUTH_ISSUER",
        "AICRM_AUTH_JWT_SIGNING_KEY",
    } <= set(inventory["environment_variables"])
    assert "AUTOMATION_INTERNAL_API_TOKEN" not in inventory["environment_variables"]
    assert all("value" not in item for item in inventory["environment_variable_references"])


def test_runtime_contract_inventory_render_is_deterministic() -> None:
    first = render_inventory(build_inventory(ROOT))
    second = render_inventory(build_inventory(ROOT))

    assert first == second
    assert json.loads(first)["schema_version"] == 1


def test_runtime_contract_inventory_write_and_check_detect_drift(tmp_path: Path) -> None:
    destination = tmp_path / "inventory.json"

    write_inventory(ROOT, destination)
    assert check_inventory(ROOT, destination) == ""

    payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["migration_heads"] = ["drifted_head"]
    destination.write_text(json.dumps(payload), encoding="utf-8")

    diff = check_inventory(ROOT, destination)
    assert "drifted_head" in diff
    assert "0100_external_effect_delivery_lease" in diff


def test_checked_in_runtime_contract_inventory_matches_current_runtime() -> None:
    assert check_inventory(ROOT, SNAPSHOT) == ""
