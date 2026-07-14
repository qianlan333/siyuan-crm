from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.ci.check_high_risk_contract_inventory import load_manifest, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "architecture" / "high_risk_contract_inventory.yml"
REQUIRED_DOMAINS = {
    "auth",
    "callback",
    "payment",
    "refund_entitlement",
    "questionnaire",
    "group_ops",
    "broadcast_delivery",
    "delivery",
}


def test_high_risk_contract_inventory_is_complete_and_executable() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert {domain["domain"] for domain in manifest["domains"]} == REQUIRED_DOMAINS
    assert validate_manifest(manifest, root=ROOT) == []


def test_high_risk_contract_inventory_rejects_missing_case() -> None:
    manifest = deepcopy(load_manifest(MANIFEST_PATH))
    manifest["domains"][0]["contracts"].pop("failure")

    errors = validate_manifest(manifest, root=ROOT)

    assert any("failure" in error for error in errors)


def test_high_risk_contract_inventory_rejects_missing_pytest_node() -> None:
    manifest = deepcopy(load_manifest(MANIFEST_PATH))
    manifest["domains"][0]["contracts"]["success"] = "tests/test_missing.py::test_missing"

    errors = validate_manifest(manifest, root=ROOT)

    assert any("does not exist" in error for error in errors)


def test_high_risk_contract_inventory_rejects_unscoped_test() -> None:
    manifest = deepcopy(load_manifest(MANIFEST_PATH))
    manifest["domains"][0]["ci_scope"] = "docs_only"

    errors = validate_manifest(manifest, root=ROOT)

    assert any("not selected" in error for error in errors)


def test_high_risk_contract_inventory_rejects_real_external_calls() -> None:
    manifest = deepcopy(load_manifest(MANIFEST_PATH))
    manifest["domains"][0]["real_external_call_expected"] = True

    errors = validate_manifest(manifest, root=ROOT)

    assert any("real external call" in error for error in errors)
