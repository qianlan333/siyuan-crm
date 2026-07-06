from __future__ import annotations

import json
from pathlib import Path

from tools.report_experiments_inventory import build_report, main, render_markdown, write_report_files


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_experiments_inventory_report_classifies_files_and_root_references(tmp_path) -> None:
    _write(tmp_path / "README.md", "Run `cd experiments/ai_crm_next` for frozen evidence tests.\n")
    _write(
        tmp_path / "scripts/check_no_duplicate_next_source.sh",
        "DUPLICATE_DIR=\"$ROOT_DIR/experiments/ai_crm_next/src/aicrm_next\"\n",
    )
    _write(
        tmp_path / "tests/test_next_source_consolidation.py",
        'assert "experiments/ai_crm_next/src/aicrm_next" in source\n',
    )
    _write(tmp_path / "experiments/ai_crm_next/README.md", "# Frozen\n")
    _write(tmp_path / "experiments/ai_crm_next/docs/architecture.md", "# Architecture\n")
    _write(tmp_path / "experiments/ai_crm_next/tools/check_canary_readiness.py", "def main(): return 0\n")
    _write(tmp_path / "experiments/ai_crm_next/tools/doc_paths.py", "ARCHIVE = 'docs/archive'\n")
    _write(tmp_path / "experiments/ai_crm_next/tests/test_contract.py", "def test_contract(): pass\n")
    _write(tmp_path / "experiments/ai_crm_next/tests/fixtures/sample.json", "{}\n")
    _write(tmp_path / "experiments/ai_crm_next/migrations/versions/0001_initial.py", "# migration\n")
    _write(tmp_path / "docs/archive/experiments_ai_crm_next/docs/canary_execution_report.md", "# Report\n")
    _write(tmp_path / "docs/cleanup/experiments_ai_crm_next_inventory.md", "generated reference should be ignored\n")

    report = build_report(tmp_path, generated_at="2026-06-29T00:00:00Z")

    assert report["summary"]["experiment_tracked_file_count"] == 7
    assert report["summary"]["archived_experiment_file_count"] == 1
    assert report["summary"]["root_reference_count"] == 3
    assert report["summary"]["areas"] == {
        "docs": 1,
        "migrations": 1,
        "root_config": 1,
        "test_fixtures": 1,
        "tests": 1,
        "tools": 2,
    }
    records = {record["path"]: record for record in report["experiment_files"]}
    assert records["experiments/ai_crm_next/README.md"]["classification"] == "retired_stub"
    assert records["experiments/ai_crm_next/tools/check_canary_readiness.py"]["classification"] == "active_readiness_checker"
    assert records["experiments/ai_crm_next/tools/doc_paths.py"]["classification"] == "active_archive_path_helper"
    assert records["experiments/ai_crm_next/tests/fixtures/sample.json"]["classification"] == "active_fixture_data"
    assert {reference["classification"] for reference in report["root_references"]} == {
        "active_doc_pointer",
        "active_duplicate_source_guard",
        "active_guard_test",
    }


def test_experiments_inventory_report_ignores_its_own_fixtures(tmp_path) -> None:
    _write(tmp_path / "README.md", "Run `cd experiments/ai_crm_next` for frozen evidence tests.\n")
    _write(
        tmp_path / "tools/report_experiments_inventory.py",
        'EXPERIMENT_PREFIX = "experiments/ai_crm_next/"\n',
    )
    _write(
        tmp_path / "tests/test_experiments_inventory_report.py",
        '_write(tmp_path / "experiments/ai_crm_next/README.md", "# Frozen\\n")\n',
    )
    _write(tmp_path / "experiments/ai_crm_next/README.md", "# Frozen\n")

    report = build_report(tmp_path, generated_at="2026-06-29T00:00:00Z")

    assert report["summary"]["root_reference_count"] == 1
    assert report["root_references"] == [
        {
            "path": "README.md",
            "line": 1,
            "classification": "active_doc_pointer",
            "evidence": "Run `cd experiments/ai_crm_next` for frozen evidence tests.",
        }
    ]


def test_experiments_inventory_report_writes_markdown_and_json(tmp_path) -> None:
    _write(tmp_path / "experiments/ai_crm_next/README.md", "# Frozen\n")
    _write(tmp_path / "docs/archive/experiments_ai_crm_next/retired_tools.md", "# Retired\n")
    report = build_report(tmp_path, generated_at="2026-06-29T00:00:00Z")

    summary_output = tmp_path / "docs/cleanup/experiments_ai_crm_next_inventory.md"
    json_output = tmp_path / "docs/cleanup/experiments_ai_crm_next_inventory.json"
    write_report_files(report, summary_output=summary_output, json_output=json_output)

    summary = summary_output.read_text(encoding="utf-8")
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert "experiments/ai_crm_next Cleanup Inventory" in summary
    assert "Retention rule" in summary
    assert "experiments/ai_crm_next/README.md" in summary
    assert payload["version"] == "1"
    assert payload["summary"]["experiment_tracked_file_count"] == 1
    assert "retired_stub" in render_markdown(report)


def test_experiments_inventory_cli_returns_zero_and_outputs_files(tmp_path) -> None:
    _write(tmp_path / "experiments/ai_crm_next/README.md", "# Frozen\n")

    status = main(
        [
            "--root",
            str(tmp_path),
            "--summary-output",
            "docs/cleanup/report.md",
            "--json-output",
            "docs/cleanup/report.json",
            "--generated-at",
            "2026-06-29T00:00:00Z",
        ]
    )

    assert status == 0
    assert "Generated: 2026-06-29T00:00:00Z" in (tmp_path / "docs/cleanup/report.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "docs/cleanup/report.json").read_text(encoding="utf-8"))["generated_at"] == "2026-06-29T00:00:00Z"
