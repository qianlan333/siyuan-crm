from pathlib import Path

from scripts.ci.check_auth_credential_boundaries import _active_contract_files, check_auth_credential_boundaries


def test_siyuan_historical_evidence_is_not_treated_as_active_auth_contract() -> None:
    active = {path.relative_to(Path(__file__).resolve().parents[1]) for path in _active_contract_files()}

    assert Path("docs/siyuan_aicrm_next_migration.md") not in active
    assert not any(path.parts[:2] == ("docs", "reports") and "siyuan" in path.name.lower() for path in active)


def test_auth_credential_boundary_checker_passes_current_overlay() -> None:
    report = check_auth_credential_boundaries()

    assert report["ok"], report["violations"]
