from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _run_app_command(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "app.py", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_app_py_has_no_legacy_startup_imports() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert not any(module.startswith("wecom_ability" + "_service") for module in imported_modules)
    assert "create_app()" not in source
    assert "wecom_ability" + "_service" not in source


def test_app_health_uses_next_runtime_without_legacy_import() -> None:
    result = _run_app_command("health")

    assert result.returncode == 0, result.stderr
    assert "'ok': True" in result.stdout
    assert "'default_runtime': 'ai_crm_next'" in result.stdout
    assert "wecom_ability" + "_service" not in result.stdout + result.stderr


def test_app_routes_prints_next_routes_without_legacy_import() -> None:
    result = _run_app_command("routes")

    assert result.returncode == 0, result.stderr
    assert "/health" in result.stdout
    assert "wecom_ability" + "_service" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("argv", "command"),
    (
        (("run-legacy",), "run-legacy"),
        (("init-db",), "init-db"),
        (("init-db-legacy",), "init-db-legacy"),
        (("delete-questionnaire-submissions", "demo"), "delete-questionnaire-submissions"),
        (("delete-questionnaire-submissions-legacy", "demo"), "delete-questionnaire-submissions-legacy"),
    ),
)
def test_removed_legacy_startup_commands_hard_error_without_legacy_import(argv: tuple[str, ...], command: str) -> None:
    result = _run_app_command(*argv)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert command in output
    assert "has been removed. AI-CRM now starts with Next runtime only." in output
    assert "For database schema changes use Alembic migrations." in output
    assert "wecom_ability" + "_service" not in output
