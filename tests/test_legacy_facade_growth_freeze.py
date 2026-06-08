from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools/check_legacy_facade_growth_freeze.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_legacy_facade_growth_freeze", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_manifest(*, fixture_allowed: bool = False, side_effect_risk: str = "guarded") -> str:
    return f"""
version: 1
routes:
  - route_pattern: /api/compat
    methods: [GET]
    capability_owner: aicrm_next.integration_gateway
    current_runtime_owner: production_compat
    production_behavior: legacy_forward
    legacy_fallback_allowed: true
    fixture_allowed_in_production: {str(fixture_allowed).lower()}
    external_side_effect_risk: {side_effect_risk}
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: compatibility route
  - route_pattern: /admin/customers
    methods: [GET]
    capability_owner: aicrm_next.customer_read_model
    current_runtime_owner: frontend_compat
    production_behavior: readonly_facade
    legacy_fallback_allowed: true
    fixture_allowed_in_production: false
    external_side_effect_risk: none
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: readonly facade
  - route_pattern: /api/admin/questionnaires*
    methods: [GET, POST]
    capability_owner: aicrm_next.questionnaire
    current_runtime_owner: next
    production_behavior: guarded_preview
    legacy_fallback_allowed: true
    fixture_allowed_in_production: false
    external_side_effect_risk: guarded
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: guarded preview
  - route_pattern: /api/admin/image-library*
    methods: [GET, POST]
    capability_owner: aicrm_next.media_library
    current_runtime_owner: next
    production_behavior: fake_adapter
    legacy_fallback_allowed: true
    fixture_allowed_in_production: false
    external_side_effect_risk: real_blocked
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: fake adapter
  - route_pattern: /api/admin/automation-conversion/jobs/run-due*
    methods: [POST]
    capability_owner: aicrm_next.automation_engine
    current_runtime_owner: production_compat
    production_behavior: scheduled_safe_mode
    legacy_fallback_allowed: true
    fixture_allowed_in_production: false
    external_side_effect_risk: real_blocked
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: timer safe mode
"""


def test_legacy_facade_growth_freeze_checker_passes_current_repo() -> None:
    checker = _load_checker()

    report = checker.build_report()

    assert report["ok"], report["blockers"]
    assert report["overall"] == "PASS"


def test_legacy_flask_facade_is_only_dynamic_legacy_import_boundary(tmp_path: Path) -> None:
    checker = _load_checker()
    _write(
        tmp_path / "aicrm_next/integration_gateway/legacy_flask_facade.py",
        "import importlib\nmodule_name = 'wecom_' + 'ability_service'\nimportlib.import_module(module_name)\n",
    )
    _write(
        tmp_path / "aicrm_next/integration_gateway/other_facade.py",
        "import importlib\nmodule_name = 'wecom_' + 'ability_service'\nimportlib.import_module(module_name)\n",
    )

    result = checker.check_aicrm_next_legacy_import_boundary(tmp_path)

    assert result["ok"] is False
    reasons = {finding["reason"] for finding in result["findings"]}
    assert "split_string_legacy_import_outside_boundary" in reasons


def test_aicrm_next_cannot_directly_import_wecom_or_openclaw(tmp_path: Path) -> None:
    checker = _load_checker()
    _write(tmp_path / "aicrm_next/integration_gateway/legacy_flask_facade.py", "import importlib\n")
    _write(
        tmp_path / "aicrm_next/bad.py",
        "from wecom_ability_service.domains.questionnaire import service\nimport openclaw_service\n",
    )

    result = checker.check_aicrm_next_legacy_import_boundary(tmp_path)

    assert result["ok"] is False
    assert [finding["reason"] for finding in result["findings"]].count("direct_legacy_import") == 2


def test_frontend_compat_cannot_add_direct_sql(tmp_path: Path) -> None:
    checker = _load_checker()
    _write(
        tmp_path / "aicrm_next/frontend_compat/legacy_routes.py",
        "# SELECT in a comment is not a direct SQL path\n"
        "def route():\n"
        "    db.session.execute('SELECT * FROM customers')\n",
    )

    result = checker.check_frontend_compat_direct_sql(tmp_path)

    assert result["ok"] is False
    assert result["findings"][0]["reason"] == "frontend_compat_direct_sql"


def test_manifest_does_not_allow_fixture_allowed_in_production(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    _write(manifest, _minimal_manifest(fixture_allowed=True))

    result = checker.check_manifest_guardrails(tmp_path, manifest)

    assert result["ok"] is False
    assert any(finding["reason"] == "fixture_allowed_in_production_not_false" for finding in result["findings"])


def test_manifest_does_not_allow_real_external_calls(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    _write(manifest, _minimal_manifest(side_effect_risk="real_allowed"))

    result = checker.check_manifest_guardrails(tmp_path, manifest)

    assert result["ok"] is False
    assert any(finding["reason"] == "external_side_effect_risk_not_guarded" for finding in result["findings"])
