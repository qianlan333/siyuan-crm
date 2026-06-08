from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools/check_production_route_ownership_manifest.py"
MANIFEST_PATH = REPO_ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
MANIFEST_DOC = REPO_ROOT / "docs/route_ownership/production_route_ownership_manifest.md"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_production_route_ownership_manifest", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_documents_required_route_families() -> None:
    checker = _load_checker()
    manifest = checker.load_manifest()
    patterns = {record["route_pattern"] for record in manifest["routes"]}
    for route_family in checker.REQUIRED_ROUTE_FAMILIES:
        assert route_family in patterns


def test_manifest_checker_passes_current_app_routes() -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["ok"], report["blockers"]
    assert report["production_compat_catch_all_count"] >= 1
    assert "/api/messages/{path:path}" not in report["production_compat_catch_alls"]


def test_mcp_owner_is_next_integration_gateway() -> None:
    checker = _load_checker()
    manifest = checker.load_manifest()
    mcp = next(record for record in manifest["routes"] if record["route_pattern"] == "/mcp")
    assert mcp["capability_owner"] == "aicrm_next.integration_gateway"
    assert "openclaw_service is not an owner" in mcp["notes"]


def test_customer_and_questionnaire_admin_routes_are_readonly_facades() -> None:
    checker = _load_checker()
    manifest = checker.load_manifest()
    records = {record["route_pattern"]: record for record in manifest["routes"]}
    for route in ["/admin/customers", "/admin/questionnaires"]:
        assert records[route]["production_behavior"] == "readonly_facade"
        assert records[route]["fixture_allowed_in_production"] is False


def test_checker_detects_real_external_behavior_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    drifted = manifest_text.replace("route_pattern: /mcp\n", "route_pattern: /mcp\n", 1).replace(
        "production_behavior: fake_adapter",
        "production_behavior: real",
        1,
    )
    target_manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(drifted, encoding="utf-8")
    original = checker.MANIFEST
    checker.MANIFEST = target_manifest
    try:
        report = checker.build_report()
    finally:
        checker.MANIFEST = original
    assert report["ok"] is False
    assert any("production_behavior=real" in blocker for blocker in report["blockers"])


def test_manifest_docs_and_checker_cli() -> None:
    assert MANIFEST_PATH.exists()
    assert MANIFEST_DOC.exists()
    completed = subprocess.run(
        [
            sys.executable,
            "tools/check_production_route_ownership_manifest.py",
            "--output-md",
            "/tmp/production_route_ownership_manifest.md",
            "--output-json",
            "/tmp/production_route_ownership_manifest.json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"ok": true' in completed.stdout
