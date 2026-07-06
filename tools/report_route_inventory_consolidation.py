from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "architecture" / "route_ownership_manifest.yml"
INVENTORY_DIR = ROOT / "docs" / "architecture"
ARCHIVED_INVENTORY_DIR = ROOT / "docs" / "archive" / "route_inventory"
REPORT_VERSION = "1"

HTTP_METHOD_PREFIX = r"(?:(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+)?"
ROUTE_REF_RE = re.compile(rf"`{HTTP_METHOD_PREFIX}(?P<path>/[^`\s|]+)`")
TEST_REF_RE = re.compile(r"tests/[^`) ,|]+")
FASTAPI_PARAM_CONVERTER_RE = re.compile(r"\{([^}:]+):[^}]+}")


@dataclass(frozen=True)
class RouteInventoryRecord:
    path: str
    location: str
    extracted_route_count: int
    exact_manifest_match_count: int
    wildcard_or_family_count: int
    test_reference_count: int
    classification: str
    reason: str
    manifest_derivable_routes: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "location": self.location,
            "extracted_route_count": self.extracted_route_count,
            "exact_manifest_match_count": self.exact_manifest_match_count,
            "wildcard_or_family_count": self.wildcard_or_family_count,
            "test_reference_count": self.test_reference_count,
            "classification": self.classification,
            "reason": self.reason,
            "manifest_derivable_routes": self.manifest_derivable_routes,
        }


def build_report(root: Path = ROOT, *, generated_at: str | None = None) -> dict[str, object]:
    root = root.resolve()
    manifest_routes = _manifest_routes(root / "docs" / "architecture" / "route_ownership_manifest.yml")
    manifest_paths = {_canonical_route_path(path) for path in manifest_routes}
    manifest_routes_by_canonical_path = {_canonical_route_path(path): route for path, route in manifest_routes.items()}
    active_paths = sorted((root / "docs" / "architecture").glob("*route_inventory.md"))
    archived_paths = sorted((root / "docs" / "archive" / "route_inventory").glob("*route_inventory.md"))
    records = [
        _inventory_record(
            path,
            root=root,
            manifest_routes=manifest_routes_by_canonical_path,
            manifest_paths=manifest_paths,
        )
        for path in [*active_paths, *archived_paths]
    ]
    derivable_route_count = sum(len(record.manifest_derivable_routes) for record in records if record.classification == "mostly_manifest_derivable")
    summary: dict[str, Any] = {
        "manifest_route_count": len(manifest_paths),
        "inventory_file_count": len(records),
        "active_inventory_file_count": len(active_paths),
        "archived_inventory_file_count": len(archived_paths),
        "manifest_derivable_route_count": derivable_route_count,
        "classifications": {},
    }
    for record in records:
        summary["classifications"][record.classification] = summary["classifications"].get(record.classification, 0) + 1
    return {
        "version": REPORT_VERSION,
        "root": ".",
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "inventories": [record.as_dict() for record in records],
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    records = list(report["inventories"])
    lines = [
        "# Route Inventory Consolidation Inventory",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "This report is generated from `docs/architecture/route_ownership_manifest.yml`,",
        "`docs/architecture/*route_inventory.md`, and",
        "`docs/archive/route_inventory/*route_inventory.md` by",
        "`tools/report_route_inventory_consolidation.py`. It does not delete, move,",
        "or deprecate any route inventory file by itself.",
        "",
        "## Current Sources",
        "",
        "- Canonical manifest: `docs/architecture/route_ownership_manifest.yml`",
        "- Manifest contract: `docs/architecture/route_ownership_manifest.md`",
        "- Manifest checker: `tools/check_route_ownership_manifest.py`",
        "- Manifest regression test: `tests/test_route_ownership_manifest.py`",
        "",
        f"The manifest currently covers {summary['manifest_route_count']} FastAPI routes.",
        f"The active hand-written inventory set currently contains {summary['active_inventory_file_count']} `*_route_inventory.md` files.",
        f"The archived manifest-derivable inventory set currently contains {summary['archived_inventory_file_count']} `*_route_inventory.md` files.",
        f"The total inventory evidence set currently contains {summary['inventory_file_count']} `*_route_inventory.md` files.",
        f"{summary['manifest_derivable_route_count']} exact route rows can currently be regenerated from the manifest for `mostly_manifest_derivable` inventories.",
        "",
        "## Classification Summary",
        "",
    ]
    for classification, count in sorted(summary["classifications"].items()):
        lines.append(f"- `{classification}`: {count}")
    lines.extend(["", "## Inventory Details", ""])
    for classification in ("mostly_manifest_derivable", "retain_closeout_evidence", "needs_manual_review"):
        subset = [record for record in records if record["classification"] == classification]
        if not subset:
            continue
        lines.extend([f"### {classification}", "", "| Inventory | Location | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |", "| --- | --- | ---: | ---: | ---: | ---: | --- |"])
        for record in subset:
            lines.append(
                "| `{path}` | `{location}` | {routes} | {exact} | {wildcard} | {tests} | {reason} |".format(
                    path=record["path"],
                    location=record["location"],
                    routes=record["extracted_route_count"],
                    exact=record["exact_manifest_match_count"],
                    wildcard=record["wildcard_or_family_count"],
                    tests=record["test_reference_count"],
                    reason=record["reason"],
                )
            )
        lines.append("")
    derivable_records = [record for record in records if record["classification"] == "mostly_manifest_derivable" and record["manifest_derivable_routes"]]
    if derivable_records:
        lines.extend(
            [
                "## Manifest-Generated Rows",
                "",
                "These rows are derived from `route_ownership_manifest.yml` for inventories",
                "classified as `mostly_manifest_derivable`. They are intended as parity",
                "evidence before any hand-written route table is archived.",
                "",
                "| Inventory | Route | Methods | Route name | Capability owner | External effects | Data source | Auth |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for record in derivable_records:
            for route in record["manifest_derivable_routes"]:
                lines.append(
                    "| `{inventory}` | `{path}` | `{methods}` | `{route_name}` | `{capability_owner}` | `{external_effects}` | `{data_source}` | `{requires_auth}` |".format(
                        inventory=record["path"],
                        path=route["path"],
                        methods=", ".join(route["methods"]),
                        route_name=route["route_name"],
                        capability_owner=route["capability_owner"],
                        external_effects=route["external_effects"],
                        data_source=route["data_source"],
                        requires_auth=str(route["requires_auth"]).lower(),
                    )
                )
        lines.append("")
    lines.extend(
        [
            "## Recommended Order",
            "",
            "1. Keep all existing route inventory tests in place.",
            "2. Use this report to compare generated route/method/owner rows against the",
            "   active and archived hand-written route inventory files.",
            "3. Keep closeout evidence sections archived under `docs/archive/route_inventory/`",
            "   once exact route rows are proven redundant with manifest-generated rows.",
            "4. Do not remove route inventory tests until their assertions are either",
            "   generated from the manifest or intentionally retained as archive evidence.",
            "",
            "## Non-Goals",
            "",
            "- Do not delete route inventory evidence in this batch.",
            "- Do not delete `tests/test_*_route_inventory.py`.",
            "- Do not change route ownership manifest semantics.",
            "- Do not change FastAPI router registration or route behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report_files(report: dict[str, object], *, summary_output: Path | None = None, json_output: Path | None = None) -> None:
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(render_markdown(report), encoding="utf-8")
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report route inventory consolidation candidates without changing runtime.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-output")
    parser.add_argument("--summary-output")
    parser.add_argument("--generated-at", help="Override generated_at for reproducible reports.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = build_report(root, generated_at=args.generated_at)
    write_report_files(
        report,
        summary_output=(root / args.summary_output) if args.summary_output else None,
        json_output=(root / args.json_output) if args.json_output else None,
    )
    print(render_markdown(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _manifest_routes(path: Path) -> dict[str, dict[str, object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    routes: dict[str, dict[str, object]] = {}
    for route in raw.get("routes", []):
        route_path = str(route.get("path", "")).strip()
        if not route_path:
            continue
        routes[route_path] = {
            "path": route_path,
            "methods": [str(method) for method in route.get("methods", [])],
            "route_name": str(route.get("route_name", "")),
            "capability_owner": str(route.get("capability_owner", "")),
            "runtime_owner": str(route.get("runtime_owner", "")),
            "layer": str(route.get("layer", "")),
            "external_effects": str(route.get("external_effects", "")),
            "data_source": str(route.get("data_source", "")),
            "requires_auth": bool(route.get("requires_auth", False)),
            "rollback": str(route.get("rollback", "")),
        }
    return routes


def _inventory_record(path: Path, *, root: Path, manifest_routes: dict[str, dict[str, object]], manifest_paths: set[str]) -> RouteInventoryRecord:
    text = path.read_text(encoding="utf-8")
    route_refs = sorted(set(_normalize_route_ref(match.group("path")) for match in ROUTE_REF_RE.finditer(text)))
    exact_matches = [route for route in route_refs if _canonical_route_path(route) in manifest_paths]
    wildcard_refs = [route for route in route_refs if "*" in route or "{path:path}" in route or route.endswith("*")]
    test_refs = sorted(set(TEST_REF_RE.findall(text)))
    classification, reason = _classify(route_refs=route_refs, exact_matches=exact_matches, wildcard_refs=wildcard_refs, test_refs=test_refs)
    manifest_derivable_routes = [manifest_routes[_canonical_route_path(route)] for route in exact_matches] if classification == "mostly_manifest_derivable" else []
    return RouteInventoryRecord(
        path=str(path.relative_to(root)),
        location="archived" if "docs/archive/route_inventory" in str(path.relative_to(root)) else "active",
        extracted_route_count=len(route_refs),
        exact_manifest_match_count=len(exact_matches),
        wildcard_or_family_count=len(wildcard_refs),
        test_reference_count=len(test_refs),
        classification=classification,
        reason=reason,
        manifest_derivable_routes=manifest_derivable_routes,
    )


def _classify(*, route_refs: list[str], exact_matches: list[str], wildcard_refs: list[str], test_refs: list[str]) -> tuple[str, str]:
    if not route_refs:
        return "needs_manual_review", "No route-like backtick paths were extracted."
    if wildcard_refs or len(exact_matches) < len(route_refs):
        return "retain_closeout_evidence", "Contains wildcard/family refs or route refs not exactly covered by the manifest."
    if test_refs:
        return "mostly_manifest_derivable", "Exact routes match manifest; preserve linked test evidence until a generated table proves parity."
    return "mostly_manifest_derivable", "Exact routes match manifest and can be compared with generated route rows."


def _canonical_route_path(path: str) -> str:
    return FASTAPI_PARAM_CONVERTER_RE.sub(r"{\1}", path)


def _normalize_route_ref(path: str) -> str:
    return path.split("#", 1)[0].split("?", 1)[0]


if __name__ == "__main__":
    raise SystemExit(main())
