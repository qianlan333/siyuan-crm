from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.run_lint as run_lint


def test_run_lint_scope_includes_tools_directory() -> None:
    assert "tools" in run_lint.PYTHON_TARGETS
    assert any(path.name == "tools" for path in run_lint.SCAN_ROOTS)


def test_run_lint_report_only_scope_includes_aicrm_next() -> None:
    assert run_lint.REPORT_ONLY_PYTHON_TARGETS == ["aicrm_next"]
    assert any(path.name == "aicrm_next" for path in run_lint.REPORT_ONLY_SCAN_ROOTS)


def test_custom_text_checks_scan_tools_directory(tmp_path, monkeypatch) -> None:
    tool_file = tmp_path / "tools" / "bad_tool.py"
    tool_file.parent.mkdir()
    tool_file.write_text("value = 1    \n", encoding="utf-8")

    monkeypatch.setattr(run_lint, "ROOT", tmp_path)
    monkeypatch.setattr(run_lint, "SCAN_ROOTS", [tmp_path / "tools"])

    assert run_lint._custom_text_checks() == ["tools/bad_tool.py:1: trailing whitespace"]


def test_run_ruff_passes_tools_target(tmp_path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, cwd, **kwargs):  # noqa: ANN001, ANN003
        calls.append(command)
        assert cwd == tmp_path
        assert kwargs == {}
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_lint, "ROOT", tmp_path)
    monkeypatch.setattr(run_lint.subprocess, "run", fake_run)

    assert run_lint._run_ruff() == 0
    assert calls
    assert calls[0][-1] == "tools"
    assert "scripts/run_lint.py" in calls[0]


def test_run_ruff_report_only_passes_aicrm_next_target(tmp_path, monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    def fake_run(command, cwd, **kwargs):  # noqa: ANN001, ANN003
        calls.append(command)
        assert cwd == tmp_path
        assert kwargs == {"capture_output": True, "text": True}
        return subprocess.CompletedProcess(command, 1, stdout="F401 example\n", stderr="")

    monkeypatch.setattr(run_lint, "ROOT", tmp_path)
    monkeypatch.setattr(run_lint.subprocess, "run", fake_run)

    assert run_lint._run_ruff_report_only() == 1
    assert calls[0][-1] == "aicrm_next"
    assert "report-only ruff findings" in capsys.readouterr().out


def test_main_ignores_report_only_findings(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_lint, "_custom_text_checks", lambda scan_roots=None: ["aicrm_next/example.py:1: trailing whitespace"] if scan_roots else [])
    monkeypatch.setattr(run_lint, "_run_ruff", lambda: 0)
    monkeypatch.setattr(run_lint, "_run_ruff_report_only", lambda: 1)

    assert run_lint.main() == 0
    assert "report-only custom lint findings" in capsys.readouterr().out
