from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backfill_customer_read_model.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_execute_requires_explicit_allow_execute() -> None:
    result = _run_cli("--source", "fixture", "--execute", "--database-url", "sqlite:////tmp/aicrm_customer_read_model_cli_guard.sqlite")

    assert result.returncode == 2
    assert "--allow-execute" in result.stderr


def test_execute_requires_explicit_database_url() -> None:
    result = _run_cli("--source", "fixture", "--execute", "--allow-execute")

    assert result.returncode == 2
    assert "explicit --database-url" in result.stderr


def test_execute_rejects_production_like_database_url() -> None:
    result = _run_cli(
        "--source",
        "fixture",
        "--execute",
        "--allow-execute",
        "--database-url",
        "postgresql://aicrm:aicrm@prod-db.internal:5432/aicrm",
    )

    assert result.returncode == 2
    assert "test/tmp" in result.stderr


def test_execute_writes_temp_sqlite_and_reconciles_without_sensitive_output(tmp_path: Path) -> None:
    db_path = Path("/tmp") / f"aicrm_customer_read_model_test_{tmp_path.name}.sqlite"
    if db_path.exists():
        db_path.unlink()
    database_url = f"sqlite:///{db_path}"

    result = _run_cli(
        "--source",
        "fixture",
        "--execute",
        "--allow-execute",
        "--database-url",
        database_url,
        "--limit",
        "2",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["source_name"] == "fixture"
    assert payload["source_count"] == 2
    assert payload["written_customers"] == 2
    assert payload["reconciliation"]["diff_count"] == 0
    assert "13800138000" not in result.stdout
    assert "138****00" in result.stdout

    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM customer_list_index_next")).scalar_one()
    assert count == 2
