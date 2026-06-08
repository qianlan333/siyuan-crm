from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_customer_webhook_registry_records_are_locked():
    records = {item.get("route_id"): item for item in _records(REGISTRY)}

    expected = {
        "customer_automation_activation_webhook_next_command": (
            "/api/customers/automation/activation-webhook",
            "next_command",
            "medium",
            "local",
        ),
        "customer_automation_webhook_delivery_retry_next_safe_mode": (
            "/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
            "next_runtime_plan",
            "high",
            "real_blocked",
        ),
        "customer_automation_webhook_delivery_retry_due_next_safe_mode": (
            "/api/customers/automation/webhook-deliveries/retry-due",
            "next_runtime_plan",
            "high",
            "real_blocked",
        ),
    }
    for route_id, (route_path, runtime_owner, risk, adapter_mode) in expected.items():
        record = records[route_id]
        assert record["path_pattern"] == route_path
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["runtime_owner"] == runtime_owner
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["external_side_effect_risk"] == risk
        assert record["adapter_mode"] == adapter_mode
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_customer_webhook_manifest_records_are_locked():
    records = {item.get("route_pattern"): item for item in _records(MANIFEST)}

    expected = {
        "/api/customers/automation/activation-webhook": ("next_command", "medium", "local"),
        "/api/customers/automation/webhook-deliveries/{delivery_id}/retry": ("next_runtime_plan", "high", "real_blocked"),
        "/api/customers/automation/webhook-deliveries/retry-due": ("next_runtime_plan", "high", "real_blocked"),
    }
    for route_path, (runtime_owner, risk, adapter_mode) in expected.items():
        record = records[route_path]
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["current_runtime_owner"] == runtime_owner
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["external_side_effect_risk"] == risk
        assert record["adapter_mode"] == adapter_mode
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
