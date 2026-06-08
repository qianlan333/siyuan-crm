from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "tools/generate_legacy_replacement_backlog.py"
MANIFEST_PATH = REPO_ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_legacy_replacement_backlog", GENERATOR_PATH)
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
  - route_pattern: /api/admin/example
    methods: [GET, POST]
    capability_owner: aicrm_next.integration_gateway
    current_runtime_owner: production_compat
    production_behavior: legacy_forward
    legacy_fallback_allowed: true
    fixture_allowed_in_production: {str(fixture_allowed).lower()}
    external_side_effect_risk: {side_effect_risk}
    delete_ready: false
    checker: tools/check_legacy_facade_growth_freeze.py
    notes: example guarded route
"""


def _manifest_and_backlog():
    generator = _load_generator()
    manifest = generator.load_manifest(MANIFEST_PATH)
    routes = manifest["routes"]
    backlog = generator.build_backlog(routes)
    return generator, routes, backlog


def test_generator_builds_backlog_from_manifest() -> None:
    _generator, routes, backlog = _manifest_and_backlog()

    assert routes
    assert backlog["status"] == "current_progress_snapshot_no_runtime_change"
    assert len(backlog["entries"]) == len(routes)


def test_every_manifest_route_maps_to_one_backlog_entry() -> None:
    _generator, routes, backlog = _manifest_and_backlog()

    manifest_patterns = [route["route_pattern"] for route in routes]
    backlog_patterns = [entry["route_pattern"] for entry in backlog["entries"]]

    assert backlog_patterns == manifest_patterns


def test_backlog_entries_include_required_fields_and_allowed_enums() -> None:
    generator, _routes, backlog = _manifest_and_backlog()

    for entry in backlog["entries"]:
        assert generator.BACKLOG_REQUIRED_FIELDS <= set(entry)
        assert entry["replacement_category"] in generator.ALLOWED_CATEGORIES
        assert entry["replacement_phase"] in generator.ALLOWED_PHASES
        assert entry["priority"] in generator.ALLOWED_PRIORITIES


def test_readonly_no_external_side_effect_enters_phase_3_readonly() -> None:
    generator = _load_generator()
    route = {
        "route_pattern": "/api/example-readonly",
        "methods": ["GET"],
        "capability_owner": "aicrm_next.customer_read_model",
        "current_runtime_owner": "next",
        "production_behavior": "readonly_facade",
        "legacy_fallback_allowed": True,
        "fixture_allowed_in_production": False,
        "external_side_effect_risk": "none",
        "checker": "tools/check_next_production_runtime_gaps.py",
        "notes": "readonly example",
    }

    assert generator.classify_replacement_category(route) == "readonly"
    assert generator.classify_replacement_phase(route) == "phase_3_readonly"
    assert generator.classify_priority(route) == "P0"


def test_scheduled_safe_mode_timer_routes_are_phase_6_and_not_high_priority() -> None:
    generator, _routes, backlog = _manifest_and_backlog()
    timer_entries = [
        entry
        for entry in backlog["entries"]
        if entry["production_behavior"] == "scheduled_safe_mode" or "run-due" in entry["route_pattern"]
    ]

    assert timer_entries
    for entry in timer_entries:
        assert entry["replacement_phase"] in {"phase_6_timer_automation", "keep_guarded_until_adapter_ready"}
        assert entry["priority"] in {"P2", "P3"}
        assert entry["replacement_category"] == "timer_or_automation_execution"


def test_external_adapter_related_routes_do_not_enter_phase_3_readonly() -> None:
    _generator, _routes, backlog = _manifest_and_backlog()
    risky_tokens = ("wechat-pay", "alipay", "oauth", "wecom", "mcp", "openclaw", "upload")

    risky_entries = [
        entry
        for entry in backlog["entries"]
        if entry["production_behavior"] == "fake_adapter"
        or entry["external_side_effect_risk"] == "real_blocked"
        or any(token in f"{entry['route_pattern']} {entry['notes']}".lower() for token in risky_tokens)
    ]

    assert risky_entries
    assert all(entry["replacement_phase"] != "phase_3_readonly" for entry in risky_entries)


def test_daily_business_critical_routes_have_business_continuity_requirement() -> None:
    _generator, _routes, backlog = _manifest_and_backlog()

    critical_entries = [entry for entry in backlog["entries"] if entry["daily_business_critical"] is True]

    assert critical_entries
    assert all(entry["business_continuity_requirement"] for entry in critical_entries)
    assert all("does not regress" in entry["business_continuity_requirement"].lower() for entry in critical_entries)


def test_no_fallback_entries_do_not_keep_legacy_fallback_until() -> None:
    _generator, _routes, backlog = _manifest_and_backlog()
    checked_fields = (
        "business_continuity_requirement",
        "replacement_strategy",
        "fallback_required_until",
        "delete_condition",
    )

    no_fallback_entries = [entry for entry in backlog["entries"] if entry["legacy_fallback_allowed"] is False]

    assert no_fallback_entries
    for entry in no_fallback_entries:
        for field in checked_fields:
            assert "Keep legacy fallback until" not in entry[field], (entry["route_pattern"], field)


def test_current_generated_backlog_files_are_fresh() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_fixture_allowed_in_production_true_fails_checker(tmp_path: Path) -> None:
    generator = _load_generator()
    manifest = tmp_path / "manifest.yaml"
    _write(manifest, _minimal_manifest(fixture_allowed=True))

    report = generator.build_report(manifest, tmp_path / "backlog.yaml", tmp_path / "backlog.md")

    assert report["overall"] == "FAIL"
    assert any("fixture_allowed_in_production" in blocker for blocker in report["blockers"])


def test_real_external_side_effect_allowed_or_enabled_fails_checker(tmp_path: Path) -> None:
    generator = _load_generator()
    for value in ("real_allowed", "enabled"):
        manifest = tmp_path / f"manifest-{value}.yaml"
        _write(manifest, _minimal_manifest(side_effect_risk=value))

        report = generator.build_report(manifest, tmp_path / f"{value}.yaml", tmp_path / f"{value}.md")

        assert report["overall"] == "FAIL"
        assert any("external_side_effect_risk" in blocker for blocker in report["blockers"])


def test_check_mode_passes_when_generated_files_match_and_fails_when_they_differ(tmp_path: Path) -> None:
    output_yaml = tmp_path / "legacy_replacement_backlog.yaml"
    output_md = tmp_path / "legacy_replacement_backlog.md"
    output_json = tmp_path / "report.json"

    subprocess.run(
        [
            sys.executable,
            str(GENERATOR_PATH),
            "--manifest",
            str(MANIFEST_PATH),
            "--output-yaml",
            str(output_yaml),
            "--output-md",
            str(output_md),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR_PATH),
            "--manifest",
            str(MANIFEST_PATH),
            "--output-yaml",
            str(output_yaml),
            "--output-md",
            str(output_md),
            "--check",
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output_yaml.write_text(output_yaml.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
    failed = subprocess.run(
        [
            sys.executable,
            str(GENERATOR_PATH),
            "--manifest",
            str(MANIFEST_PATH),
            "--output-yaml",
            str(output_yaml),
            "--output-md",
            str(output_md),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert failed.returncode == 1
    assert "differs from generated backlog" in failed.stdout
