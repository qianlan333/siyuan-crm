from __future__ import annotations

import ast
from pathlib import Path

import pytest

import app


ROOT = Path(__file__).resolve().parents[1]


def test_app_py_has_no_legacy_startup_imports() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert not any(module.startswith("wecom_ability_service") for module in imported_modules)
    assert "create_app()" not in source


@pytest.mark.parametrize(
    ("argv", "command"),
    (
        (["run-legacy"], "run-legacy"),
        (["init-db-legacy"], "init-db-legacy"),
        (["delete-questionnaire-submissions", "demo"], "delete-questionnaire-submissions"),
        (["delete-questionnaire-submissions-legacy", "demo"], "delete-questionnaire-submissions-legacy"),
    ),
)
def test_removed_legacy_startup_commands_fail_without_flask(argv: list[str], command: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app.main(argv)

    message = str(exc_info.value)
    assert command in message
    assert "Legacy Flask runtime has been removed from startup compatibility" in message
    assert "python3 app.py run" in message


def test_init_db_alias_uses_next_safe_schema(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    called: list[str] = []

    def fake_safe_init() -> None:
        called.append("safe")

    monkeypatch.setattr(app, "init_next_schema_safe", fake_safe_init)

    app.main(["init-db"])

    assert called == ["safe"]
    assert "init-db is deprecated; running init-next-schema-safe" in capsys.readouterr().out
