from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_identity_reconciliation_outputs_counts_only_and_runs_before_service_stop() -> None:
    script = (ROOT / "scripts/ops/check_unionid_identity_cutover.py").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    for required in (
        "duplicate_alias_group_count",
        "blocked_duplicate_alias_group_count",
        "unregistered_duplicate_alias_group_count",
        "pending_resolution_count",
        "failed_resolution_count",
        "missing_unionid_succeeded_consumer_count",
        "resolver_parity_mismatch_count",
        '"pii_included": False',
        "count_digest",
    ):
        assert required in script
    assert "SELECT unionid, 'external_userid'" in script
    assert "SELECT unionid, 'openid'" in script
    assert "SELECT unionid, 'mobile'" in script
    assert "--phase preflight" in deploy
    assert "--register-existing-conflicts" in deploy
    assert "--phase post-deploy" in deploy
    deploy_execution = deploy[deploy.index("# Identity preflight must fail before any runtime unit is stopped.") :]
    preflight_index = deploy_execution.index("--phase preflight")
    migration_stop_index = deploy_execution.index("--phase stop-for-migration")
    assert preflight_index < migration_stop_index
