from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "wecom_ability_service"


def test_production_deploy_loads_postgres_env_before_init_db():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    init_db_index = workflow.index("python3 app.py init-db")

    assert env_source_index < database_url_guard_index < init_db_index


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
    init_db_index = workflow.index("python3 app.py init-db")

    assert fetch_index < reset_index < after_sha_index < requirements_guard_index < pip_install_index < init_db_index
    assert "requirements.txt unchanged; skipping pip install" in workflow


def test_production_deploy_polls_health_after_restart_instead_of_fixed_sleep():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    restart_index = workflow.index("sudo systemctl restart openclaw-wecom-postgres.service")
    poll_index = workflow.index("for _ in $(seq 1 20); do")
    health_index = workflow.index("curl -sSf http://127.0.0.1:5001/health")

    assert restart_index < poll_index < health_index
    assert "sleep 3" not in workflow


def test_production_deploy_installs_and_runs_external_push_worker_timer():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    health_index = workflow.index("curl -sSf http://127.0.0.1:5001/health", workflow.index("for _ in $(seq 1 20); do"))
    copy_service_index = workflow.index("sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/openclaw-external-push-worker.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable openclaw-external-push-worker.timer")
    restart_timer_index = workflow.index("sudo systemctl restart openclaw-external-push-worker.timer")
    start_service_index = workflow.index("sudo systemctl start openclaw-external-push-worker.service")

    assert health_index < copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_timer_index < start_service_index


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


def test_pg_only_ops_tools_do_not_expose_sqlite_entrypoints():
    assert not (ROOT / "scripts" / "backup_sqlite.sh").exists()

    seed_demo = (ROOT / "scripts" / "seed_automation_conversion_demo.py").read_text(encoding="utf-8")
    campaign_scheduler = (ROOT / "scripts" / "run_campaign_scheduler.py").read_text(encoding="utf-8")
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(encoding="utf-8")
    ops_runtime = (ROOT / "wecom_ability_service" / "http" / "ops_runtime.py").read_text(encoding="utf-8")
    alembic_env = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "--database-path" not in seed_demo
    assert "INSERT OR " not in seed_demo
    assert "DATABASE_PATH`` / ``DATABASE_URL" not in campaign_scheduler
    assert "DATABASE_PATH`` / ``DATABASE_URL" not in broadcast_worker
    assert "sqlite_path" not in ops_runtime
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
    campaign_scheduler = (ROOT / "scripts" / "run_campaign_scheduler.py").read_text(
        encoding="utf-8"
    )
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(
        encoding="utf-8"
    )

    assert "def read_int_env" in runtime
    assert 'read_int_env("CAMPAIGN_SCHEDULER_BATCH_SIZE", 200)' in campaign_scheduler
    assert 'read_int_env("BROADCAST_QUEUE_BATCH_SIZE", 50)' in broadcast_worker
    assert "int(os.environ.get" not in campaign_scheduler
    assert "int(os.environ.get" not in broadcast_worker


def test_due_runner_scripts_share_int_env_reader():
    due_runner = (ROOT / "scripts" / "run_automation_conversion_due_jobs.py").read_text(
        encoding="utf-8"
    )
    sop_runner = (ROOT / "scripts" / "run_automation_sop.py").read_text(encoding="utf-8")
    external_push_worker = (ROOT / "scripts" / "run_external_push_worker.py").read_text(encoding="utf-8")

    assert 'read_int_env("AUTOMATION_CONVERSION_DUE_RETRY_COUNT"' in due_runner
    assert "AUTOMATION_CONVERSION_DUE_RETRY_INTERVAL_SECONDS" in due_runner
    assert 'read_int_env("AUTOMATION_SOP_RETRY_COUNT"' in sop_runner
    assert "AUTOMATION_SOP_RETRY_INTERVAL_SECONDS" in sop_runner
    assert 'read_int_env("EXTERNAL_PUSH_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE)' in external_push_worker
    assert "int((os.getenv" not in due_runner
    assert "int((os.getenv" not in sop_runner
    assert "int(os.environ.get" not in external_push_worker


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
