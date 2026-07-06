from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.audit_repo_hygiene import audit_repository, main, render_human_summary, write_report_files


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _issues_by_category(report, category: str):
    return [issue for issue in report.issues if issue.category == category]


def test_audit_reports_missing_markdown_references_from_agent_docs(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "Read [skill](docs/development/ai_crm_next_architecture_skill.md).\n")
    _write(tmp_path / "docs/development/ai_crm_next_architecture_skill.md", "# Skill\n")
    _write(
        tmp_path / "skills/ai-crm-next-architecture/SKILL.md",
        "Read `docs/development/codex_architecture_operating_memory.md` first.\n",
    )

    report = audit_repository(tmp_path, generated_at="2026-06-28T00:00:00Z")

    missing = _issues_by_category(report, "missing_markdown_reference")
    assert len(missing) == 1
    assert missing[0].path == "skills/ai-crm-next-architecture/SKILL.md"
    assert "codex_architecture_operating_memory.md" in missing[0].evidence
    payload = report.as_dict()
    assert set(payload) == {"version", "root", "generated_at", "summary", "issues"}
    assert set(payload["issues"][0]) == {"id", "category", "severity", "path", "line", "message", "evidence"}


def test_audit_resolves_relative_and_repo_root_markdown_references(tmp_path) -> None:
    _write(tmp_path / "README.md", "Root [doc](docs/development/codex_task_template.md).\n")
    _write(tmp_path / "docs/development/codex_task_template.md", "See [local](local.md).\n")
    _write(tmp_path / "docs/development/local.md", "# Local\n")

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "missing_markdown_reference") == []


def test_audit_ignores_generated_hygiene_report_markdown_references(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "docs/cleanup/repo_hygiene_report.md",
        "- stale generated evidence: artifacts/internal_event_coverage_audit.json\n",
    )

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "missing_markdown_reference") == []


def test_audit_ignores_external_links_and_anchor_only_links(tmp_path) -> None:
    _write(
        tmp_path / "README.md",
        "External [site](https://example.com/doc.md), image ![x](https://example.com/a.png), anchor [a](#section), mail [m](mailto:x@y.com).\n",
    )

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "missing_markdown_reference") == []


def test_audit_reports_artifact_directory_candidates_without_git(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(tmp_path / "artifacts/internal_event_coverage_audit.json", "{}\n")
    _write(tmp_path / ".codex_artifacts/screenshot.png", "not really an image\n")

    report = audit_repository(tmp_path)

    artifacts = _issues_by_category(report, "tracked_artifact_candidate")
    assert {issue.path for issue in artifacts} == {
        ".codex_artifacts/screenshot.png",
        "artifacts/internal_event_coverage_audit.json",
    }


def test_audit_ignores_untracked_artifacts_inside_git_worktree(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(tmp_path / ".gitignore", ".codex_artifacts/\n")
    _write(tmp_path / ".codex_artifacts/full_repo_file_inventory.txt", "AGENTS.md\n")

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "tracked_artifact_candidate") == []


def test_audit_reports_agent_entry_drift_and_ops_details(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(tmp_path / "CLAUDE.md", "Use scripts/prod.sh and crm-prod.\n")
    _write(
        tmp_path / "docs/development/ai_crm_next_architecture_skill.md",
        "real external adapter 仍 blocked / fake / staging-disabled\n"
        "legacy Flask 只作为显式 fallback 和生产兼容 facade。\n",
    )

    report = audit_repository(tmp_path)

    categories = {issue.category for issue in report.issues}
    assert "agent_entry_missing_canonical_preflight" in categories
    assert "agent_entry_ops_detail" in categories
    assert "agent_entry_external_effect_drift" in categories
    assert "agent_entry_legacy_fallback_drift" in categories


def test_audit_reports_production_ops_entry_details(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "scripts/prod.sh",
        "HOST=${SSH_HOST:-crm-prod}\nexec ssh \"$HOST\" psql-stdin\n",
    )

    report = audit_repository(tmp_path)

    findings = _issues_by_category(report, "production_ops_stub_detail")
    assert len(findings) == 2
    assert findings[0].path == "scripts/prod.sh"


def test_audit_reports_active_legacy_source_path_references(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "docs/queue/broadcast-jobs.md",
        "Register a handler in `wecom_ability_service.domains.broadcast_jobs.handlers`.\n",
    )
    _write(
        tmp_path / "skills/image-library-curator/README.md",
        "[mcp_tools.py](https://github.com/qianlan333/AI-CRM/blob/main/wecom_ability_service/domains/image_library/mcp_tools.py)\n",
    )
    _write(
        tmp_path / "docs/archive/old.md",
        "Historical link: `wecom_ability_service/domains/old.py`.\n",
    )

    report = audit_repository(tmp_path)

    findings = _issues_by_category(report, "active_legacy_path_reference")
    assert [finding.path for finding in findings] == [
        "docs/queue/broadcast-jobs.md",
        "skills/image-library-curator/README.md",
    ]


def test_audit_allows_retired_legacy_boundary_text(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "docs/development/ai_crm_next_architecture_skill.md",
        "`wecom_ability_service/domains/foo.py` is retired and must not be restored.\n"
        "不得恢复 `openclaw_service/foo.py`。\n",
    )

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "active_legacy_path_reference") == []


def test_audit_allows_production_ops_safe_stub(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "scripts/prod.sh",
        "echo 'Use the private ops handoff; no host aliases or command cookbooks are exposed.' >&2\nexit 2\n",
    )

    report = audit_repository(tmp_path)

    assert _issues_by_category(report, "production_ops_stub_detail") == []


def test_audit_reports_aicrm_next_debug_and_legacy_markers(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "aicrm_next/example/service.py",
        "print('debug')\n# TODO: retire production_compat marker\n",
    )

    report = audit_repository(tmp_path)

    categories = {issue.category for issue in report.issues}
    assert "aicrm_next_print_marker" in categories
    assert "aicrm_next_todo_marker" in categories
    assert "aicrm_next_legacy_marker" in categories


def test_audit_ignores_console_paths_and_fingerprint_names(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "aicrm_next/example/template.html",
        "<script src=\"admin_console/admin_console.js\"></script>\n",
    )
    _write(
        tmp_path / "aicrm_next/example/service.py",
        "def _content_fingerprint(content):\n    return {'content': content}\n",
    )

    report = audit_repository(tmp_path)

    categories = {issue.category for issue in report.issues}
    assert "aicrm_next_console_marker" not in categories
    assert "aicrm_next_print_marker" not in categories


def test_write_report_files_outputs_markdown_and_json(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    report = audit_repository(tmp_path, generated_at="2026-06-28T00:00:00Z")

    summary_output = tmp_path / "docs/cleanup/repo_hygiene_report.md"
    json_output = tmp_path / "docs/cleanup/repo_hygiene_report.json"
    write_report_files(report, summary_output=summary_output, json_output=json_output)

    assert "# Repo Hygiene Audit" in summary_output.read_text(encoding="utf-8")
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["version"] == "1"
    assert payload["root"] == "."
    assert "summary" in payload
    assert "issues" in payload
    assert "Issues" in render_human_summary(report)


def test_cli_outputs_json_and_keeps_success_exit_with_findings(tmp_path, capsys) -> None:
    _write(tmp_path / "AGENTS.md", "Read `missing/file.md`.\n")
    json_output = tmp_path / "out/report.json"
    summary_output = tmp_path / "out/report.md"

    assert main(["--root", str(tmp_path), "--json-output", str(json_output), "--summary-output", str(summary_output)]) == 0

    stdout = capsys.readouterr().out
    assert "# Repo Hygiene Audit" in stdout
    assert '"version": "1"' in stdout
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["summary"]["issue_count"] >= 1
    assert summary_output.exists()


def test_cli_accepts_generated_at_for_reproducible_reports(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    json_output = tmp_path / "out/report.json"
    summary_output = tmp_path / "out/report.md"

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--json-output",
                str(json_output),
                "--summary-output",
                str(summary_output),
                "--generated-at",
                "2026-06-29T00:00:00Z",
            ]
        )
        == 0
    )

    assert json.loads(json_output.read_text(encoding="utf-8"))["generated_at"] == "2026-06-29T00:00:00Z"
    assert "Generated at: `2026-06-29T00:00:00Z`" in summary_output.read_text(encoding="utf-8")
