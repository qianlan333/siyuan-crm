from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.report_route_inventory_consolidation import build_report, main, render_markdown, write_report_files


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_route_inventory_consolidation_report_classifies_inventory_files(tmp_path) -> None:
    _write(
        tmp_path / "docs/architecture/route_ownership_manifest.yml",
        yaml.safe_dump(
            {
                "routes": [
                    {"path": "/health"},
                    {"path": "/api/items"},
                    {"path": "/api/items/{item_id:int}"},
                ]
            },
            sort_keys=False,
        ),
    )
    _write(
        tmp_path / "docs/architecture/health_route_inventory.md",
        "| route | test |\n| --- | --- |\n| `GET /health?probe=1` | `tests/test_health.py` |\n",
    )
    _write(
        tmp_path / "docs/architecture/items_route_inventory.md",
        "| route | note |\n| --- | --- |\n| `GET /api/items/{item_id}` | method-prefixed exact |\n| `/api/items/*` | family closeout |\n",
    )
    _write(tmp_path / "docs/architecture/narrative_route_inventory.md", "Narrative closeout evidence only.\n")
    _write(
        tmp_path / "docs/archive/route_inventory/archived_route_inventory.md",
        "| route |\n| --- |\n| `/health` |\n",
    )

    report = build_report(tmp_path, generated_at="2026-06-29T00:00:00Z")

    records = {record["path"]: record for record in report["inventories"]}
    assert records["docs/architecture/health_route_inventory.md"]["classification"] == "mostly_manifest_derivable"
    assert records["docs/architecture/health_route_inventory.md"]["location"] == "active"
    assert records["docs/architecture/health_route_inventory.md"]["manifest_derivable_routes"] == [
        {
            "path": "/health",
            "methods": [],
            "route_name": "",
            "capability_owner": "",
            "runtime_owner": "",
            "layer": "",
            "external_effects": "",
            "data_source": "",
            "requires_auth": False,
            "rollback": "",
        }
    ]
    assert records["docs/archive/route_inventory/archived_route_inventory.md"]["classification"] == "mostly_manifest_derivable"
    assert records["docs/archive/route_inventory/archived_route_inventory.md"]["location"] == "archived"
    assert records["docs/architecture/items_route_inventory.md"]["classification"] == "retain_closeout_evidence"
    assert records["docs/architecture/items_route_inventory.md"]["manifest_derivable_routes"] == []
    assert records["docs/architecture/narrative_route_inventory.md"]["classification"] == "needs_manual_review"
    assert report["summary"]["manifest_route_count"] == 3
    assert report["summary"]["inventory_file_count"] == 4
    assert report["summary"]["active_inventory_file_count"] == 3
    assert report["summary"]["archived_inventory_file_count"] == 1
    assert report["summary"]["manifest_derivable_route_count"] == 2


def test_route_inventory_consolidation_report_writes_markdown_and_json(tmp_path) -> None:
    _write(tmp_path / "docs/architecture/route_ownership_manifest.yml", yaml.safe_dump({"routes": [{"path": "/health"}]}))
    _write(tmp_path / "docs/architecture/health_route_inventory.md", "| route |\n| --- |\n| `/health` |\n")
    report = build_report(tmp_path, generated_at="2026-06-29T00:00:00Z")

    summary_output = tmp_path / "docs/cleanup/route_inventory_consolidation_inventory.md"
    json_output = tmp_path / "docs/cleanup/route_inventory_consolidation_inventory.json"
    write_report_files(report, summary_output=summary_output, json_output=json_output)

    summary = summary_output.read_text(encoding="utf-8")
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert "Route Inventory Consolidation Inventory" in summary
    assert "health_route_inventory.md" in summary
    assert "Manifest-Generated Rows" in summary
    assert payload["summary"]["inventory_file_count"] == 1
    assert payload["summary"]["manifest_derivable_route_count"] == 1
    assert "mostly_manifest_derivable" in render_markdown(report)


def test_route_inventory_consolidation_cli_returns_zero_and_outputs_files(tmp_path) -> None:
    _write(tmp_path / "docs/architecture/route_ownership_manifest.yml", yaml.safe_dump({"routes": [{"path": "/health"}]}))
    _write(tmp_path / "docs/architecture/health_route_inventory.md", "| route |\n| --- |\n| `/health` |\n")

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
