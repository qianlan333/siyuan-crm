from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ("wecom_ability" + "_service")
SIYUAN_DEPLOY_OVERLAY_REASON = (
    "siyuan-crm keeps its existing production deploy/systemd overlay; "
    "AI-CRM canonical deploy unit contract is not part of this sync PR"
)


def _workflow() -> str:
    return (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")


def _is_siyuan_deploy_overlay() -> bool:
    source = _workflow()
    return "scripts/ensure_channel_multi_staff_schema.py" in source and "workflow_run:" not in source


def test_production_deploy_loads_postgres_env_before_alembic_upgrade():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")

    assert env_source_index < database_url_guard_index < alembic_upgrade_index
    assert "python3 app.py init-db" not in workflow
    assert "python app.py init-db" not in workflow
    assert "init-db-legacy" not in workflow
    assert "alembic stamp head" not in workflow
    assert "legacy_flask_app" not in workflow


def test_production_deploy_stashes_dirty_worktree_before_remote_update():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stash_index = workflow.index("git stash push --include-untracked")
    before_sha_index = workflow.index('before_sha="$(git rev-parse HEAD)"')
    fetch_index = workflow.index("git fetch origin main:refs/remotes/origin/main")
    reset_index = workflow.index("git reset --hard refs/remotes/origin/main")

    assert stash_index < before_sha_index < fetch_index < reset_index


def test_production_deploy_installs_dependencies_only_when_requirements_change():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    fetch_index = workflow.index("git fetch origin main:refs/remotes/origin/main")
    reset_index = workflow.index("git reset --hard refs/remotes/origin/main")
    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    requirements_guard_index = workflow.index('git diff --quiet "$before_sha" "$after_sha" -- requirements.txt')
    pip_install_index = workflow.index("pip install -r requirements.txt")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")

    assert fetch_index < reset_index < after_sha_index < requirements_guard_index < pip_install_index < alembic_upgrade_index
    assert "requirements.txt unchanged; skipping pip install" in workflow


def test_siyuan_deploy_overlay_keeps_existing_release_boundary():
    if not _is_siyuan_deploy_overlay():
        pytest.skip("siyuan deploy overlay not active")

    workflow = _workflow()

    fetch_index = workflow.index("git fetch origin main:refs/remotes/origin/main")
    reset_index = workflow.index("git reset --hard refs/remotes/origin/main")
    health_index = workflow.index("python3 app.py health")
    alembic_index = workflow.index("python3 -m alembic upgrade head")
    schema_guard_index = workflow.index("scripts/ensure_channel_multi_staff_schema.py")
    restart_index = workflow.index("sudo systemctl restart openclaw-wecom-postgres.service")
    smoke_index = workflow.index("admin_channels_status=")
    copy_external_push_index = workflow.index("sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/")

    assert "push:" in workflow
    assert "- main" in workflow
    assert "workflow_run:" not in workflow
    assert fetch_index < reset_index < health_index < alembic_index < schema_guard_index < restart_index
    assert restart_index < smoke_index < copy_external_push_index
    assert '"$admin_channels_status" != "401"' in workflow
    assert '"$admin_channels_status" != "403"' in workflow
    assert "alembic stamp head" not in workflow
    assert "legacy_flask_app" not in workflow
    assert not (ROOT / "deploy" / "aicrm-web.service").exists()
    assert not (ROOT / "deploy" / "openclaw-external-effect-worker.service").exists()


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_refreshes_release_marker_before_restart_and_checks_health_header():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    after_sha_index = workflow.index('after_sha="$(git rev-parse HEAD)"')
    marker_index = workflow.index('printf \'%s\\n\' "$after_sha" > .release-sha')
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    header_curl_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health")
    header_grep_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt')
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then')

    assert after_sha_index < marker_index < start_index < header_curl_index < header_grep_index < ready_guard_index


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_runs_alembic_upgrade_before_service_restart():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    pip_install_index = workflow.index("pip install -r requirements.txt")
    stop_broadcast_timer_index = workflow.index("sudo systemctl stop openclaw-broadcast-queue-worker.timer || true")
    stop_broadcast_service_index = workflow.index("sudo systemctl stop openclaw-broadcast-queue-worker.service || true")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    stop_canonical_web_index = workflow.index("sudo systemctl stop aicrm-web.service || true")
    stop_compatible_web_index = workflow.index("sudo systemctl stop openclaw-wecom-postgres.service || true")
    stale_listener_index = workflow.index('if sudo fuser -s 5001/tcp; then')
    term_kill_index = workflow.index("sudo fuser -k -TERM 5001/tcp || true")
    force_kill_index = workflow.index("sudo fuser -k -KILL 5001/tcp || true")
    wait_for_free_index = workflow.index('echo "waiting for stale 5001 listener to exit"')
    reset_failed_index = workflow.index("sudo systemctl reset-failed openclaw-wecom-postgres.service || true")
    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    alembic_table = "alembic_" + "version"

    assert env_source_index < database_url_guard_index < alembic_upgrade_index
    assert (
        pip_install_index
        < stop_broadcast_timer_index
        < stop_broadcast_service_index
        < alembic_upgrade_index
        < stop_canonical_web_index
        < stop_compatible_web_index
        < stale_listener_index
        < term_kill_index
        < force_kill_index
        < wait_for_free_index
        < reset_failed_index
        < start_index
    )
    assert "sudo fuser -TERM 5001/tcp" not in workflow
    assert "sudo fuser -KILL 5001/tcp" not in workflow
    assert "python3 app.py init-db" not in workflow
    assert "python app.py init-db" not in workflow
    assert "alembic stamp head" not in workflow
    assert f"ALTER TABLE IF EXISTS {alembic_table}" not in workflow
    assert f"ALTER TABLE {alembic_table}" not in workflow


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_polls_health_after_restart_instead_of_fixed_sleep():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    start_index = workflow.index("if ! sudo systemctl start openclaw-wecom-postgres.service; then")
    poll_index = workflow.index("for _ in $(seq 1 60); do", start_index)
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", poll_index)
    header_index = workflow.index('grep -i "x-aicrm-release-sha: $after_sha" /tmp/aicrm_health_headers.txt', health_index)
    ready_guard_index = workflow.index('if [ "$release_ready" != "1" ]; then', header_index)
    status_index = workflow.index("sudo systemctl status openclaw-wecom-postgres.service --no-pager || true", ready_guard_index)

    assert start_index < poll_index < health_index < header_index < status_index
    assert "sleep 3" not in workflow


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_and_runs_external_push_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    copy_service_index = workflow.index("sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-external-push-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-external-push-worker.timer")
    restart_timer_index = workflow.index("sudo systemctl restart openclaw-external-push-worker.timer")
    start_service_index = workflow.index("sudo systemctl start openclaw-external-push-worker.service")

    assert health_index < copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_timer_index < start_service_index


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_external_effect_queue_worker_timer_without_manual_execute():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stop_timer_index = workflow.index("sudo systemctl stop openclaw-external-effect-worker.timer || true")
    stop_service_index = workflow.index("sudo systemctl stop openclaw-external-effect-worker.service || true")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    copy_service_index = workflow.index("sudo cp deploy/openclaw-external-effect-worker.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-external-effect-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-external-effect-worker.timer")
    restart_timer_index = workflow.index("sudo systemctl restart openclaw-external-effect-worker.timer")
    timer_status_index = workflow.index("sudo systemctl status openclaw-external-effect-worker.timer --no-pager")

    assert stop_timer_index < stop_service_index < alembic_upgrade_index
    assert health_index < copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_timer_index < timer_status_index
    assert "sudo systemctl start openclaw-external-effect-worker.service" not in workflow


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_and_runs_broadcast_queue_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    copy_service_index = workflow.index("sudo cp deploy/openclaw-broadcast-queue-worker.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-broadcast-queue-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-broadcast-queue-worker.timer")
    restart_timer_index = workflow.index("sudo systemctl restart openclaw-broadcast-queue-worker.timer")
    start_service_index = workflow.index("if ! sudo systemctl start openclaw-broadcast-queue-worker.service; then")
    service_status_index = workflow.index("sudo systemctl status openclaw-broadcast-queue-worker.service --no-pager || true")
    journal_index = workflow.index("sudo journalctl -u openclaw-broadcast-queue-worker.service -n 80 --no-pager || true")
    timer_status_index = workflow.index("sudo systemctl status openclaw-broadcast-queue-worker.timer --no-pager")

    assert health_index < copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_timer_index < start_service_index
    assert start_service_index < service_status_index < journal_index < timer_status_index


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_and_runs_internal_event_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    copy_service_index = workflow.index("sudo cp deploy/openclaw-internal-event-worker.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-internal-event-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-internal-event-worker.timer")
    restart_timer_index = workflow.index("sudo systemctl restart openclaw-internal-event-worker.timer")
    start_service_index = workflow.index("if ! sudo systemctl start openclaw-internal-event-worker.service; then")
    service_status_index = workflow.index("sudo systemctl status openclaw-internal-event-worker.service --no-pager || true")
    journal_index = workflow.index("sudo journalctl -u openclaw-internal-event-worker.service -n 80 --no-pager || true")
    timer_status_index = workflow.index("sudo systemctl status openclaw-internal-event-worker.timer --no-pager")

    assert health_index < copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_timer_index < start_service_index
    assert start_service_index < service_status_index < journal_index < timer_status_index


def test_external_push_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-external-push-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-external-push-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_external_push_worker.py" in service
    assert "OnCalendar=*-*-* *:*:20" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-external-push-worker.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_external_effect_queue_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-external-effect-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-external-effect-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_external_effect_queue_worker.py --execute" in service
    assert "OnCalendar=*-*-* *:*:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-external-effect-worker.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_payment_reconciliation_and_identity_workers():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    effect_stop_index = workflow.index("sudo systemctl stop openclaw-external-effect-worker.service || true")
    pay_stop_timer_index = workflow.index("sudo systemctl stop openclaw-wechat-pay-order-reconciliation-worker.timer || true")
    pay_stop_service_index = workflow.index("sudo systemctl stop openclaw-wechat-pay-order-reconciliation-worker.service || true")
    identity_stop_timer_index = workflow.index("sudo systemctl stop openclaw-identity-resolution-worker.timer || true")
    identity_stop_service_index = workflow.index("sudo systemctl stop openclaw-identity-resolution-worker.service || true")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    copy_pay_service_index = workflow.index("sudo cp deploy/openclaw-wechat-pay-order-reconciliation-worker.service /etc/systemd/system/")
    copy_pay_timer_index = workflow.index("sudo cp deploy/openclaw-wechat-pay-order-reconciliation-worker.timer /etc/systemd/system/")
    copy_identity_service_index = workflow.index("sudo cp deploy/openclaw-identity-resolution-worker.service /etc/systemd/system/")
    copy_identity_timer_index = workflow.index("sudo cp deploy/openclaw-identity-resolution-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_pay_index = workflow.index("sudo systemctl enable openclaw-wechat-pay-order-reconciliation-worker.timer")
    restart_pay_index = workflow.index("sudo systemctl restart openclaw-wechat-pay-order-reconciliation-worker.timer")
    pay_status_index = workflow.index("sudo systemctl status openclaw-wechat-pay-order-reconciliation-worker.timer --no-pager")
    enable_identity_index = workflow.index("sudo systemctl enable openclaw-identity-resolution-worker.timer")
    restart_identity_index = workflow.index("sudo systemctl restart openclaw-identity-resolution-worker.timer")
    identity_status_index = workflow.index("sudo systemctl status openclaw-identity-resolution-worker.timer --no-pager")

    assert (
        effect_stop_index
        < pay_stop_timer_index
        < pay_stop_service_index
        < identity_stop_timer_index
        < identity_stop_service_index
        < alembic_upgrade_index
    )
    assert (
        copy_pay_service_index
        < copy_pay_timer_index
        < copy_identity_service_index
        < copy_identity_timer_index
        < daemon_reload_index
    )
    assert daemon_reload_index < enable_pay_index < restart_pay_index < pay_status_index
    assert pay_status_index < enable_identity_index < restart_identity_index < identity_status_index


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_payment_reconciliation_and_identity_worker_units_are_deployable():
    payment_service = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.service").read_text(
        encoding="utf-8"
    )
    payment_timer = (ROOT / "deploy" / "openclaw-wechat-pay-order-reconciliation-worker.timer").read_text(
        encoding="utf-8"
    )
    identity_service = (ROOT / "deploy" / "openclaw-identity-resolution-worker.service").read_text(encoding="utf-8")
    identity_timer = (ROOT / "deploy" / "openclaw-identity-resolution-worker.timer").read_text(encoding="utf-8")

    for service in (payment_service, identity_service):
        assert "After=network.target openclaw-wecom-postgres.service" in service
        assert "Requires=openclaw-wecom-postgres.service" in service
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert "wecom_ability_service" not in service
        assert "legacy_flask_app" not in service
        assert "run-legacy" not in service

    assert "python scripts/run_wechat_pay_order_reconciliation_worker.py --execute" in payment_service
    assert "OnCalendar=*-*-* *:0/10:45" in payment_timer
    assert "Persistent=true" in payment_timer
    assert "Unit=openclaw-wechat-pay-order-reconciliation-worker.service" in payment_timer

    assert "python scripts/run_identity_resolution_backfill_worker.py --execute" in identity_service
    assert "OnCalendar=*-*-* *:0/2:20" in identity_timer
    assert "Persistent=true" in identity_timer
    assert "Unit=openclaw-identity-resolution-worker.service" in identity_timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_internal_event_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-internal-event-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-internal-event-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_ENABLED=0" in service
    assert "Environment=AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1" in service
    assert "Environment=AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_internal_event_worker.py" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:*:40" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-internal-event-worker.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_production_deploy_installs_callback_ingress_and_worker_isolated_runtime():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stop_worker_timer_index = workflow.index("sudo systemctl stop openclaw-wecom-callback-inbox-worker.timer || true")
    stop_worker_service_index = workflow.index("sudo systemctl stop openclaw-wecom-callback-inbox-worker.service || true")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    health_index = workflow.index("curl -sSf -D /tmp/aicrm_health_headers.txt http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 60); do"))
    copy_ingress_index = workflow.index("sudo cp deploy/openclaw-wecom-callback-ingress.service /etc/systemd/system/")
    copy_worker_service_index = workflow.index("sudo cp deploy/openclaw-wecom-callback-inbox-worker.service /etc/systemd/system/")
    copy_worker_timer_index = workflow.index("sudo cp deploy/openclaw-wecom-callback-inbox-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_ingress_index = workflow.index("sudo systemctl enable openclaw-wecom-callback-ingress.service")
    restart_ingress_index = workflow.index("sudo systemctl restart openclaw-wecom-callback-ingress.service")
    ingress_poll_index = workflow.index("for _ in $(seq 1 20); do", restart_ingress_index)
    ingress_health_index = workflow.index("curl -sSf http://127.0.0.1:5002/health", ingress_poll_index)
    enable_worker_index = workflow.index("sudo systemctl enable openclaw-wecom-callback-inbox-worker.timer")
    restart_worker_index = workflow.index("sudo systemctl restart openclaw-wecom-callback-inbox-worker.timer")
    ingress_status_index = workflow.index("sudo systemctl status openclaw-wecom-callback-ingress.service --no-pager")
    worker_status_index = workflow.index("sudo systemctl status openclaw-wecom-callback-inbox-worker.timer --no-pager")
    smoke_index = workflow.index("python scripts/ops/check_wecom_callback_deploy_smoke.py")
    smoke_evidence_index = workflow.index("tee /tmp/wecom-callback-deploy-smoke.json")

    assert stop_worker_timer_index < stop_worker_service_index < alembic_upgrade_index
    assert health_index < copy_ingress_index < copy_worker_service_index < copy_worker_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_ingress_index < restart_ingress_index < ingress_poll_index < ingress_health_index
    assert ingress_health_index < enable_worker_index < restart_worker_index < ingress_status_index < worker_status_index < smoke_index < smoke_evidence_index
    assert "python scripts/ops/check_wecom_callback_deploy_smoke.py | tee /tmp/wecom-callback-deploy-smoke.json" in workflow
    assert "nginx-wecom-callback-ingress.conf.example /etc" not in workflow


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_wecom_callback_ingress_systemd_unit_is_deployable():
    service = (ROOT / "deploy" / "openclaw-wecom-callback-ingress.service").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=WECOM_CALLBACK_INGRESS_HOST=127.0.0.1" in service
    assert "Environment=WECOM_CALLBACK_INGRESS_PORT=5002" in service
    assert "Environment=APP_PORT=5002" not in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_wecom_callback_ingress.py" in service
    assert "Restart=always" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_wecom_callback_inbox_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-wecom-callback-inbox-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_EXECUTE=1" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE=20" in service
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_MAX_EXECUTE_BATCH_SIZE=20" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_wecom_callback_inbox_worker.py --execute --limit ${AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE:-20}" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnUnitActiveSec=60s" in timer
    assert "Unit=openclaw-wecom-callback-inbox-worker.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_aicrm_canonical_runtime_isolation_systemd_units_are_deployable():
    web = (ROOT / "deploy" / "aicrm-web.service").read_text(encoding="utf-8")
    ingress = (ROOT / "deploy" / "aicrm-wecom-ingress.service").read_text(encoding="utf-8")
    callback_worker = (ROOT / "deploy" / "aicrm-wecom-callback-worker.service").read_text(encoding="utf-8")
    internal_worker = (ROOT / "deploy" / "aicrm-internal-event-worker.service").read_text(encoding="utf-8")
    external_worker = (ROOT / "deploy" / "aicrm-external-effect-worker.service").read_text(encoding="utf-8")

    for service in (web, ingress, callback_worker, internal_worker, external_worker):
        assert "After=network.target openclaw-wecom-postgres.service" in service
        assert "Requires=openclaw-wecom-postgres.service" in service
        assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
        assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
        assert "wecom_ability_service" not in service
        assert "legacy_flask_app" not in service
        assert "run-legacy" not in service

    assert "Environment=APP_PORT=5001" in web
    assert "python app.py run" in web
    assert "Environment=APP_PORT=5002" in ingress
    assert "python scripts/run_wecom_callback_ingress.py" in ingress
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE=20" in callback_worker
    assert "Environment=AICRM_WECOM_CALLBACK_INBOX_WORKER_MAX_EXECUTE_BATCH_SIZE=20" in callback_worker
    assert "python scripts/run_wecom_callback_inbox_worker.py --limit ${AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE:-20}" in callback_worker
    assert "--execute" not in callback_worker
    assert "python scripts/run_internal_event_worker.py --execute" in internal_worker
    assert "python scripts/run_external_effect_queue_worker.py --execute" in external_worker


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_wechat_shop_order_sync_systemd_units_are_deployable():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "aicrm-wechat-shop-order-sync.timer").read_text(encoding="utf-8")

    copy_service_index = workflow.index("sudo cp deploy/aicrm-wechat-shop-order-sync.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/aicrm-wechat-shop-order-sync.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable aicrm-wechat-shop-order-sync.timer")
    restart_index = workflow.index("sudo systemctl restart aicrm-wechat-shop-order-sync.timer")
    start_index = workflow.index("if ! sudo systemctl start aicrm-wechat-shop-order-sync.service; then")
    status_index = workflow.index("sudo systemctl status aicrm-wechat-shop-order-sync.timer --no-pager")

    assert copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_index < start_index < status_index
    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python -m scripts.run_wechat_shop_order_sync --mode incremental" in service
    assert "OnCalendar=*-*-* *:0/10:30" in timer
    assert "Persistent=true" in timer
    assert "Unit=aicrm-wechat-shop-order-sync.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_broadcast_queue_worker_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "openclaw-broadcast-queue-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-broadcast-queue-worker.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=AICRM_GROUP_OPS_MATERIAL_UPLOAD_MODE=real" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python scripts/run_broadcast_queue_worker.py" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:*:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=openclaw-broadcast-queue-worker.service" in timer


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_archive_sync_systemd_units_are_deployable():
    service = (ROOT / "deploy" / "aicrm-archive-sync.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "aicrm-archive-sync.timer").read_text(encoding="utf-8")

    assert "After=network.target openclaw-wecom-postgres.service" in service
    assert "Requires=openclaw-wecom-postgres.service" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=APP_HOST=127.0.0.1" in service
    assert "Environment=APP_PORT=5001" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service
    assert "python -m scripts.run_incremental_archive_sync" in service
    assert "wecom_ability_service" not in service
    assert "legacy_flask_app" not in service
    assert "run-legacy" not in service
    assert "OnCalendar=*-*-* *:00/5:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=aicrm-archive-sync.service" in timer


def test_pg_only_ops_tools_do_not_expose_sqlite_entrypoints():
    assert not (ROOT / "scripts" / "backup_sqlite.sh").exists()
    retired_seed_demo = ROOT / "scripts" / ("seed_" + "automation_conversion_demo.py")
    assert not retired_seed_demo.exists()
    assert not (ROOT / ("wecom_ability" + "_service") / "http").exists()

    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(encoding="utf-8")
    alembic_env = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "DATABASE_PATH`` / ``DATABASE_URL" not in broadcast_worker
    assert "DATABASE_PATH" not in alembic_env
    assert "data.sqlite3" not in alembic_env
    assert "sqlite:///" not in alembic_env


def test_makefile_check_uses_existing_quality_gate_targets():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "check: lint typecheck build" in makefile
    assert "customer-pulse-quality" not in makefile
    assert "scripts/run_customer_pulse_quality_gates.py" not in makefile
    assert "tests/test_customer_pulse_inbox.py" not in makefile
    assert "tests/test_customer_pulse_quality_gates.py" not in makefile


def test_postgres_backup_restore_share_database_url_guard():
    helper = (ROOT / "scripts" / "_postgres_env.sh").read_text(encoding="utf-8")
    backup = (ROOT / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "restore_postgres.sh").read_text(encoding="utf-8")

    assert "require_database_url()" in helper
    assert 'echo "DATABASE_URL is required" >&2' in helper
    assert 'source "${SCRIPT_DIR}/_postgres_env.sh"' in backup
    assert 'source "${SCRIPT_DIR}/_postgres_env.sh"' in restore
    assert "require_database_url" in backup
    assert "require_database_url" in restore


def test_batch_scripts_share_int_env_reader():
    runtime = (ROOT / "scripts" / "script_runtime.py").read_text(encoding="utf-8")
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(
        encoding="utf-8"
    )

    assert "def read_int_env" in runtime
    assert 'read_int_env("BROADCAST_QUEUE_BATCH_SIZE", 50)' in broadcast_worker
    assert "int(os.environ.get" not in broadcast_worker


def test_due_runner_scripts_share_int_env_reader():
    external_push_worker = (ROOT / "scripts" / "run_external_push_worker.py").read_text(encoding="utf-8")
    internal_event_worker = (ROOT / "scripts" / "run_internal_event_worker.py").read_text(encoding="utf-8")
    ai_audience_scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")

    assert not (ROOT / "scripts" / "run_automation_sop.py").exists()
    assert 'read_int_env("EXTERNAL_PUSH_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE)' in external_push_worker
    assert 'read_int_env("AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE", DEFAULT_WORKER_BATCH_SIZE)' in internal_event_worker
    assert 'read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)' in ai_audience_scheduler
    assert "--execute" in internal_event_worker
    assert "InternalEventWorker().run_due" in internal_event_worker
    assert "int(os.environ.get" not in external_push_worker
    assert "int(os.environ.get" not in internal_event_worker
    assert "int(os.environ.get" not in ai_audience_scheduler


@pytest.mark.skipif(_is_siyuan_deploy_overlay(), reason=SIYUAN_DEPLOY_OVERLAY_REASON)
def test_ai_audience_scheduler_runs_through_internal_event_queue_only():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    scheduler = (ROOT / "scripts" / "run_ai_audience_scheduler.py").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "openclaw-ai-audience-scheduler.timer").read_text(encoding="utf-8")
    stop_timer_index = workflow.index("sudo systemctl stop openclaw-ai-audience-scheduler.timer || true")
    stop_service_index = workflow.index("sudo systemctl stop openclaw-ai-audience-scheduler.service || true")
    alembic_upgrade_index = workflow.index("python3 -m alembic upgrade head")
    copy_service_index = workflow.index("sudo cp deploy/openclaw-ai-audience-scheduler.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-ai-audience-scheduler.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-ai-audience-scheduler.timer")
    restart_index = workflow.index("sudo systemctl restart openclaw-ai-audience-scheduler.timer")
    start_index = workflow.index("if ! sudo systemctl start openclaw-ai-audience-scheduler.service; then")
    status_index = workflow.index("sudo systemctl status openclaw-ai-audience-scheduler.timer --no-pager")

    assert stop_timer_index < stop_service_index < alembic_upgrade_index
    assert copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_index < start_index < status_index
    assert "register_ai_audience_event_consumers()" in scheduler
    assert 'read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)' in scheduler
    assert "run_due_ai_audience_consumers" in scheduler
    assert "--run-consumers --execute" in service
    assert "ExecStart=/bin/bash -c" in service
    assert "AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=" in service
    assert "ai_audience.refresh.incremental_tick,ai_audience.refresh.daily_tick" in service
    assert "AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=" in service
    assert "ai_audience.refresh.incremental_tick:ai_audience_incremental_refresh_consumer" in service
    assert "ai_audience.refresh.daily_tick:ai_audience_daily_refresh_consumer" in service
    assert "ai_audience.run.refreshed:ai_audience_outbound_effect_planner" in service
    assert "ai_audience.member.updated:ai_audience_outbound_effect_planner" not in service
    assert "ai_audience.member.exited:ai_audience_outbound_effect_planner" not in service
    assert "ExternalEffectWorker" not in service
    assert "run_external_effect_queue_worker.py" not in service
    assert "OnCalendar=*-*-* *:0/3:00" in timer


def _calls_utcnow(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "utcnow":
            return True
        if isinstance(node.func, ast.Name) and node.func.id == "utcnow":
            return True
    return False


def test_runtime_code_does_not_use_deprecated_utcnow():
    offenders = sorted(
        path.relative_to(ROOT).as_posix()
        for path in RUNTIME_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and _calls_utcnow(path)
    )

    assert not offenders, (
        "Runtime code must use explicit timezone-aware UTC helpers instead of datetime.utcnow(). "
        f"Offenders: {offenders}"
    )


def test_alembic_0002_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0002_perf_indexes_and_trace.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0003_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0003_member_segment_columns.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "information_schema.columns" in migration
    assert "DROP COLUMN IF EXISTS" in migration


def test_alembic_0004_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0004_cloud_orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "datetime('now'" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "workflow_id BIGINT NOT NULL" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP" in migration
    assert "next_node_id BIGINT" in migration
    assert "DROP COLUMN IF EXISTS" in migration


def test_alembic_0005_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0005_segments_and_campaigns.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "sql_dialect TEXT NOT NULL DEFAULT 'postgres'" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "ADD COLUMN IF NOT EXISTS segment_id BIGINT" in migration


def test_alembic_0006_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0006_miniprogram_library.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT TRUE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration


def test_alembic_0007_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0007_image_library.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "thumb_image_id BIGINT" in migration
    assert "TIMESTAMPTZ" in migration


def test_alembic_0008_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0008_broadcast_jobs.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "AUTOINCREMENT" not in migration
    assert "BIGSERIAL PRIMARY KEY" in migration
    assert "BOOLEAN NOT NULL DEFAULT FALSE" in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "WHERE source_id <> ''" in migration


def test_alembic_0009_is_pg_only():
    migration = (
        ROOT / "migrations" / "versions" / "0009_image_library_semantic.py"
    ).read_text(encoding="utf-8")

    assert "_is_postgres" not in migration
    assert "PRAGMA" not in migration
    assert "TEXT NOT NULL DEFAULT '[]'" not in migration
    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in migration
    assert "USING GIN (tags)" in migration
