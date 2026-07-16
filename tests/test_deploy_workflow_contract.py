from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy.yml"
MANIFEST_PATH = ROOT / "deploy" / "production_runtime_units.json"
RUNTIME_UNITS_HELPER = "python3 scripts/ops/manage_production_runtime_units.py"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _phase(phase: str) -> str:
    return f"{RUNTIME_UNITS_HELPER} --phase {phase} --execute"


def test_siyuan_deploy_is_direct_production_after_verified_main_ci() -> None:
    workflow = _workflow()

    assert "name: Deploy to Production" in workflow
    assert "workflow_run:" in workflow
    assert 'workflows: ["CI Fast"]' in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "environment: production" in workflow
    assert "group: siyuan-production-deploy" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "workflow_call:" not in workflow
    assert "push:" not in workflow
    assert "schedule:" not in workflow
    assert "TEST_DEPLOY_" not in workflow


def test_siyuan_deploy_uses_verified_incremental_bundle_without_server_github_access() -> None:
    workflow = _workflow()

    verified = workflow.index('verified_sha="${{ github.event.workflow_run.head_sha }}"')
    base = workflow.index('base_sha="${{ steps.release.outputs.base_sha }}"')
    checksum = workflow.index("sha256sum -c aicrm-release.bundle.sha256", base)
    bundle_verify = workflow.index('git bundle verify "$release_bundle"', checksum)
    fetch = workflow.index(
        'git fetch --no-tags "$release_bundle" "refs/deploy/release:refs/remotes/siyuan/main"',
        bundle_verify,
    )
    reset = workflow.index('git reset --hard "$verified_sha"', fetch)

    assert verified < base < checksum < bundle_verify < fetch < reset
    assert "git@github.com" not in workflow
    assert "GIT_SSH_COMMAND" not in workflow
    assert "secrets.DEPLOY_HOST" in workflow
    assert "secrets.DEPLOY_USER" in workflow
    assert "secrets.DEPLOY_SSH_KEY" in workflow


def test_failed_uncommitted_deploy_restores_exact_sha_dependencies_and_runtime() -> None:
    workflow = _workflow()

    cleanup = workflow.index("cleanup_deploy()")
    mutation_guard = workflow.index('[ "${runtime_mutation_started:-0}" = "1" ]', cleanup)
    rollback_guard = workflow.index('[ "${release_switched:-0}" = "1" ]', mutation_guard)
    reset = workflow.index('git reset --hard "$before_sha"', rollback_guard)
    marker = workflow.index("printf '%s\\n' \"$before_sha\" > .release-sha", reset)
    dependency_guard = workflow.index(
        'git diff --quiet "$before_sha" "$verified_sha" -- requirements.lock', marker
    )
    dependency_restore = workflow.index("--require-hashes -r requirements.lock", dependency_guard)
    restored_health = workflow.index('x-aicrm-release-sha: $restore_expected_sha', dependency_restore)
    restore_runtime = workflow.index("--phase install-enable-after-web-health --execute", restored_health)

    assert cleanup < mutation_guard < rollback_guard < reset < marker
    assert marker < dependency_guard < dependency_restore < restored_health < restore_runtime
    assert "alembic downgrade" not in workflow


def test_runtime_transaction_wraps_migration_and_all_mainline_units() -> None:
    workflow = _workflow()

    reset = workflow.index('git reset --hard "$verified_sha"')
    retire = workflow.index(_phase("retire-legacy-overlays"), reset)
    begin = workflow.index("--phase begin-transaction --execute", retire)
    stop = workflow.index("--phase stop-for-migration --execute", begin)
    migration = workflow.index("python3 -m alembic upgrade head", stop)
    web_install = workflow.index(_phase("install-primary-web"), migration)
    web_start = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then", web_install)
    runtime_install = workflow.index(_phase("install-enable-after-web-health"), web_start)
    runtime_verify = workflow.index(_phase("verify-staged-runtime"), runtime_install)
    guard_release = workflow.index(_phase("release-runtime-guard"), runtime_verify)

    assert reset < retire < begin < stop < migration < web_install < web_start
    assert web_start < runtime_install < runtime_verify < guard_release

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    active = {item["service"] for item in manifest["active_services"]}
    active.update(item["timer"] for item in manifest["active_autostart"])
    assert "openclaw-wecom-callback-ingress.service" in active
    assert "openclaw-wecom-callback-inbox-worker.service" in active
    assert "openclaw-external-effect-worker.timer" in active
    assert "openclaw-internal-event-worker.timer" in active
    assert "openclaw-broadcast-queue-worker.timer" in active
    assert "openclaw-identity-resolution-worker.timer" in active
    assert "openclaw-wechat-pay-order-reconciliation-worker.timer" in active
    assert "openclaw-customer-read-model-refresh.timer" in active
    assert "openclaw-ai-audience-scheduler.timer" in active
    assert "openclaw-automation-ops-scheduler.timer" in active
    assert "aicrm-wechat-shop-order-sync.timer" not in active
    approval_required = {item["timer"] for item in manifest["approval_required"]}
    assert "aicrm-wechat-shop-order-sync.timer" in approval_required


def test_siyuan_runtime_environment_is_migrated_before_workers_start() -> None:
    workflow = _workflow()

    env_migration = workflow.index("scripts/ops/ensure_siyuan_production_runtime_env.py")
    migration = workflow.index("python3 -m alembic upgrade head", env_migration)
    web_start = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then", migration)
    runtime_install = workflow.index(_phase("install-enable-after-web-health"), web_start)

    assert env_migration < migration < web_start < runtime_install
    assert "AICRM_NEXT_WECOM_REAL_CALLS_ENABLED=true" not in workflow


def test_siyuan_release_control_archive_contains_validated_entrypoints() -> None:
    workflow = _workflow()

    archive = workflow.index('git archive "$verified_sha"')
    app_entrypoint = workflow.index("app.py", archive)
    script_entrypoints = workflow.index("scripts", app_entrypoint)
    deploy_units = workflow.index("deploy", script_entrypoints)
    extract = workflow.index('tar -x -C "$release_control_dir"', deploy_units)
    readiness = workflow.index("scripts/ops/check_runtime_secret_readiness.py")

    assert archive < app_entrypoint < script_entrypoints < deploy_units < extract < readiness
    assert "--allow-missing-wechat-shop-callback-token" in workflow


def test_deploy_does_not_reject_historical_queue_backlog_before_workers_start() -> None:
    workflow = _workflow()

    smoke = workflow.index("scripts/ops/check_admin_read_pages_smoke.py")
    runtime_install = workflow.index(_phase("install-enable-after-web-health"), smoke)

    assert "--include-all-sidebar" in workflow
    assert "--require-all-data-health-green" not in workflow
    assert smoke < runtime_install


def test_callback_ingress_is_verified_and_public_nginx_cutover_is_last_commit_gate() -> None:
    workflow = _workflow()

    runtime_install = workflow.index(_phase("install-enable-after-web-health"))
    callback_smoke = workflow.index("scripts/ops/check_wecom_callback_deploy_smoke.py", runtime_install)
    runtime_verify = workflow.index(_phase("verify-staged-runtime"), callback_smoke)
    public_release = workflow.index("scripts/ops/ensure_production_public_release_route.py", runtime_verify)
    guard_release = workflow.index(_phase("release-runtime-guard"), public_release)
    nginx_cutover = workflow.index("scripts/ops/ensure_siyuan_wecom_callback_nginx.py --execute", guard_release)
    runtime_committed = workflow.index("runtime_committed=1", nginx_cutover)
    release_committed = workflow.index("release_committed=1", runtime_committed)

    assert runtime_install < callback_smoke < runtime_verify < public_release
    assert public_release < guard_release < nginx_cutover < runtime_committed < release_committed
    assert "--server-name www.xinliushangye.com" in workflow
    assert "--nginx-config /etc/nginx/sites-enabled/siyuan-crm" in workflow
    assert "--zone-config /etc/nginx/conf.d/aicrm-wecom-callback-zones.conf" in workflow


def test_siyuan_deploy_has_no_other_project_domain_or_environment() -> None:
    workflow = _workflow()

    assert "https://www.xinliushangye.com/health" in workflow
    assert "https://www.xinliushangye.com" in workflow
    assert "youcangogogo.com" not in workflow
    assert "id-dev" not in workflow
    assert 'deploy_target="production"' in workflow
    assert "target_environment" not in workflow


def test_retired_external_push_and_legacy_callback_units_are_absent() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    retired = set(manifest["retired_forbidden"])

    assert "openclaw-external-push-worker.service" in retired
    assert "openclaw-external-push-worker.timer" in retired
    assert "openclaw-wecom-callback-inbox-worker.timer" in retired
    assert not (ROOT / "deploy" / "openclaw-external-push-worker.service").exists()
    assert not (ROOT / "deploy" / "openclaw-external-push-worker.timer").exists()


def test_wecom_callback_inbox_worker_systemd_units_are_deployable() -> None:
    service = (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.service").read_text(
        encoding="utf-8"
    )

    assert "Type=simple" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "scripts/run_wecom_callback_inbox_worker.py --execute --loop" in service
    assert "Restart=always" in service
    assert "WantedBy=multi-user.target" in service
    assert not (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.timer").exists()


def test_production_deploy_installs_callback_ingress_and_worker_isolated_runtime() -> None:
    workflow = _workflow()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    services = {item["service"] for item in manifest["active_services"]}

    install = workflow.index(_phase("install-enable-after-web-health"))
    smoke = workflow.index("scripts/ops/check_wecom_callback_deploy_smoke.py", install)
    verify = workflow.index(_phase("verify-staged-runtime"), smoke)

    assert "openclaw-wecom-callback-ingress.service" in services
    assert "openclaw-wecom-callback-inbox-worker.service" in services
    assert install < smoke < verify
    assert "tee /tmp/wecom-callback-deploy-smoke.json" in workflow


def test_aicrm_canonical_runtime_isolation_systemd_units_are_deployable() -> None:
    expectations = {
        "aicrm-wecom-ingress.service": "scripts/run_wecom_callback_ingress.py",
        "aicrm-wecom-callback-worker.service": "scripts/run_wecom_callback_inbox_worker.py --execute --loop",
        "aicrm-internal-event-worker.service": "scripts/run_internal_event_worker.py --execute",
        "aicrm-external-effect-worker.service": "scripts/run_external_effect_queue_worker.py --execute",
    }

    for filename, command in expectations.items():
        service = (ROOT / "deploy" / filename).read_text(encoding="utf-8")
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert command in service


def test_internal_event_runtime_declares_exactly_one_relay_owner() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    declared = {
        item["service"]: item["internal_event_relay_role"]
        for item in manifest["active_autostart"]
        if item.get("internal_event_relay_role")
    }

    assert declared == {
        "openclaw-ai-audience-scheduler.service": "consumer_only",
        "openclaw-internal-event-worker.service": "owner",
    }
    assert list(declared.values()).count("owner") == 1

    internal_worker = (ROOT / "scripts" / "run_internal_event_worker.py").read_text(encoding="utf-8")
    audience_runtime = (ROOT / "aicrm_next" / "ai_audience_ops" / "scheduler.py").read_text(encoding="utf-8")
    internal_service = (ROOT / "deploy" / "openclaw-internal-event-worker.service").read_text(encoding="utf-8")
    audience_service = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.service").read_text(encoding="utf-8")

    assert 'relay_role="owner"' in internal_worker
    assert 'relay_role="consumer_only"' in audience_runtime
    assert "Environment=AICRM_INTERNAL_EVENT_RELAY_ROLE=owner" in internal_service
    assert "Environment=AICRM_INTERNAL_EVENT_RELAY_ROLE=consumer_only" in audience_service
