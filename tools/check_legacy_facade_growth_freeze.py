#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
REMOVED_LEGACY_IMPORT_BOUNDARY = Path("aicrm_next/integration_gateway/legacy_flask_facade.py")
ALLOWED_DIRECT_LEGACY_IMPORTS = {
    (
        "aicrm_next/integration_gateway/wecom_group_adapter.py",
        "wecom_ability_service.domains.broadcast_jobs.service",
    ),
}
REQUIRED_DOCS = [
    Path("docs/development/legacy_facade_freeze_policy.md"),
    Path("docs/development/ai_crm_next_architecture_skill.md"),
    Path("docs/route_ownership/production_route_ownership_manifest.yaml"),
]
FORBIDDEN_IMPORT_ROOTS = ("wecom_ability_service", "openclaw_service")
IMPORTLIB_CONTEXT_KEYWORDS = ("wecom", "ability_service", "openclaw", "legacy_flask")
REQUIRED_MANIFEST_CATEGORIES: dict[str, set[str]] = {}
ALLOWED_SIDE_EFFECT_RISKS = {"none", "guarded", "real_blocked", "low", "medium", "high"}
FORBIDDEN_REAL_ALLOWED_VALUES = {
    "allow_real",
    "allowed",
    "enabled",
    "external_allowed",
    "production_allowed",
    "real",
    "real_allowed",
    "real_enabled",
    "true",
}
FRONTEND_SQL_PATTERNS = [
    re.compile(r"\bSELECT\b.*\bFROM\b", re.I),
    re.compile(r"\bINSERT\s+INTO\b", re.I),
    re.compile(r"\bUPDATE\s+[a-zA-Z_][\w.]*\s+SET\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
    re.compile(r"\bdb\.session\b", re.I),
    re.compile(r"\bengine\.execute\b", re.I),
    re.compile(r"\btext\s*\(", re.I),
]


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _py_files(root: Path, rel_dir: str) -> list[Path]:
    base = root / rel_dir
    if not base.exists():
        return []
    return sorted(base.rglob("*.py"))


def _root_import_name(module: str) -> str:
    return module.split(".", 1)[0]


def _is_importlib_import_module_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "importlib"
        and func.attr == "import_module"
    ) or (isinstance(func, ast.Name) and func.id == "import_module")


def _string_add_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_add_value(node.left)
        right = _string_add_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _line_for(source: str, lineno: int) -> str:
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def _context_for(source: str, lineno: int, radius: int = 2) -> str:
    lines = source.splitlines()
    start = max(1, lineno - radius)
    end = min(len(lines), lineno + radius)
    return "\n".join(lines[start - 1 : end])


def check_aicrm_next_legacy_import_boundary(root: Path = ROOT) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    allowed_dynamic_imports: list[dict[str, Any]] = []
    removed_boundary_path = root / REMOVED_LEGACY_IMPORT_BOUNDARY
    if removed_boundary_path.exists():
        findings.append(
            {
                "path": REMOVED_LEGACY_IMPORT_BOUNDARY.as_posix(),
                "line": 1,
                "reason": "removed_legacy_import_boundary_file_remaining",
            }
        )
    for path in _py_files(root, "aicrm_next"):
        relpath = Path(_rel(path, root))
        source = _read(path)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append({"path": relpath.as_posix(), "line": exc.lineno or 1, "reason": "python_parse_error"})
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _root_import_name(alias.name) in FORBIDDEN_IMPORT_ROOTS:
                        if (relpath.as_posix(), alias.name) in ALLOWED_DIRECT_LEGACY_IMPORTS:
                            continue
                        findings.append(
                            {
                                "path": relpath.as_posix(),
                                "line": node.lineno,
                                "reason": "direct_legacy_import",
                                "match": alias.name,
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _root_import_name(module) in FORBIDDEN_IMPORT_ROOTS:
                    if (relpath.as_posix(), module) in ALLOWED_DIRECT_LEGACY_IMPORTS:
                        continue
                    findings.append(
                        {
                            "path": relpath.as_posix(),
                            "line": node.lineno,
                            "reason": "direct_legacy_import",
                            "match": module,
                        }
                    )
            elif isinstance(node, ast.Call) and _is_importlib_import_module_call(node):
                segment = ast.get_source_segment(source, node) or _line_for(source, node.lineno)
                lower_context = _context_for(source, node.lineno).lower()
                relevant = any(keyword in lower_context for keyword in IMPORTLIB_CONTEXT_KEYWORDS)
                if relevant:
                    findings.append(
                        {
                            "path": relpath.as_posix(),
                            "line": node.lineno,
                            "reason": "dynamic_legacy_import_outside_boundary",
                            "match": segment.strip(),
                        }
                    )
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                value = _string_add_value(node)
                segment = ast.get_source_segment(source, node) or _line_for(source, getattr(node, "lineno", 1))
                lower_segment = segment.lower()
                if value:
                    lower_value = value.lower()
                    looks_like_split_legacy = (
                        "wecom_ability_service" in lower_value
                        or "openclaw_service" in lower_value
                        or ("wecom_" in lower_segment and "ability_service" in lower_segment)
                    )
                    if looks_like_split_legacy:
                        findings.append(
                            {
                                "path": relpath.as_posix(),
                                "line": node.lineno,
                                "reason": "split_string_legacy_import_outside_boundary",
                                "match": segment.strip(),
                            }
                        )

    return {
        "ok": not findings,
        "findings": findings,
        "removed_dynamic_import_boundary": REMOVED_LEGACY_IMPORT_BOUNDARY.as_posix(),
        "allowed_dynamic_imports": allowed_dynamic_imports,
    }


def _is_comment_line(line: str) -> bool:
    return line.lstrip().startswith("#")


def check_frontend_compat_direct_sql(root: Path = ROOT) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in _py_files(root, "aicrm_next/frontend_compat"):
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if _is_comment_line(line):
                continue
            for pattern in FRONTEND_SQL_PATTERNS:
                match = pattern.search(line)
                if match:
                    findings.append(
                        {
                            "path": _rel(path, root),
                            "line": lineno,
                            "reason": "frontend_compat_direct_sql",
                            "match": match.group(0),
                        }
                    )
                    break
    return {"ok": not findings, "findings": findings}


def check_required_docs(root: Path = ROOT) -> dict[str, Any]:
    missing = [path.as_posix() for path in REQUIRED_DOCS if not (root / path).exists()]
    return {"ok": not missing, "missing": missing, "required": [path.as_posix() for path in REQUIRED_DOCS]}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _load_manifest_without_yaml(path: Path) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    in_routes = False
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "routes:":
            in_routes = True
            continue
        if not in_routes:
            continue
        if line.startswith("  - "):
            if current is not None:
                routes.append(current)
            current = {}
            item = line[4:].strip()
            if ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue
        if current is not None and line.startswith("    ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value)
    if current is not None:
        routes.append(current)
    return {"routes": routes}


def _load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        return _load_manifest_without_yaml(path)


def _record_label(record: dict[str, Any], index: int) -> str:
    return str(record.get("route_pattern") or f"routes[{index}]")


def _value_forbids_real_external(value: Any) -> bool:
    if isinstance(value, bool):
        return value is True
    if value is None:
        return False
    normalized = str(value).strip().lower().replace("-", "_")
    return normalized in FORBIDDEN_REAL_ALLOWED_VALUES


def check_manifest_guardrails(root: Path = ROOT, manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or root / "docs/route_ownership/production_route_ownership_manifest.yaml"
    findings: list[dict[str, Any]] = []
    if not path.exists():
        return {"ok": False, "findings": [{"path": _rel(path, root), "reason": "manifest_missing"}], "categories": {}}

    manifest = _load_manifest(path)
    records = manifest.get("routes") or []
    if not isinstance(records, list) or not records:
        findings.append({"path": _rel(path, root), "reason": "manifest_routes_missing"})
        records = []

    categories = {
        "current_runtime_owner": sorted({str(record.get("current_runtime_owner") or "") for record in records}),
        "production_behavior": sorted({str(record.get("production_behavior") or "") for record in records}),
        "external_side_effect_risk": sorted({str(record.get("external_side_effect_risk") or "") for record in records}),
    }
    for field, required_values in REQUIRED_MANIFEST_CATEGORIES.items():
        present = set(categories.get(field) or [])
        missing = sorted(required_values - present)
        if missing:
            findings.append(
                {
                    "path": _rel(path, root),
                    "reason": "manifest_required_categories_missing",
                    "field": field,
                    "missing": missing,
                }
            )

    for index, record in enumerate(records):
        label = _record_label(record, index)
        if record.get("fixture_allowed_in_production") is not False:
            findings.append(
                {
                    "path": _rel(path, root),
                    "reason": "fixture_allowed_in_production_not_false",
                    "route_pattern": label,
                    "value": record.get("fixture_allowed_in_production"),
                }
            )
        side_effect_risk = str(record.get("external_side_effect_risk") or "").strip().lower()
        if side_effect_risk not in ALLOWED_SIDE_EFFECT_RISKS:
            findings.append(
                {
                    "path": _rel(path, root),
                    "reason": "external_side_effect_risk_not_guarded",
                    "route_pattern": label,
                    "value": record.get("external_side_effect_risk"),
                }
            )
        for key, value in record.items():
            key_lower = str(key).lower()
            if (
                ("external_side_effect" in key_lower or "real_external" in key_lower or "real_call" in key_lower)
                and _value_forbids_real_external(value)
            ):
                findings.append(
                    {
                        "path": _rel(path, root),
                        "reason": "real_external_call_marked_allowed",
                        "route_pattern": label,
                        "field": key,
                        "value": value,
                    }
                )
        production_behavior = str(record.get("production_behavior") or "").strip().lower().replace("-", "_")
        if production_behavior in {"real", "real_adapter", "real_external", "production_real"}:
            findings.append(
                {
                    "path": _rel(path, root),
                    "reason": "production_behavior_allows_real_external_call",
                    "route_pattern": label,
                    "value": record.get("production_behavior"),
                }
            )

    return {"ok": not findings, "findings": findings, "categories": categories, "manifest_route_count": len(records)}


def _flatten_findings(checks: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    docs = checks["required_docs"]
    for missing in docs.get("missing") or []:
        blockers.append(f"required doc missing: {missing}")
    for check_name in ("aicrm_next_legacy_import_boundary", "frontend_compat_direct_sql", "manifest_guardrails"):
        for finding in checks[check_name].get("findings") or []:
            blockers.append(f"{check_name}: {finding}")
    return blockers


def build_report(root: Path = ROOT, manifest_path: Path | None = None) -> dict[str, Any]:
    checks = {
        "required_docs": check_required_docs(root),
        "aicrm_next_legacy_import_boundary": check_aicrm_next_legacy_import_boundary(root),
        "frontend_compat_direct_sql": check_frontend_compat_direct_sql(root),
        "manifest_guardrails": check_manifest_guardrails(root, manifest_path),
    }
    blockers = _flatten_findings(checks)
    ok = not blockers
    return {
        "ok": ok,
        "overall": "PASS" if ok else "FAIL",
        "blockers": blockers,
        "checks": checks,
        "recommendation": "READY_FOR_LEGACY_FACADE_REMOVAL_ACCEPTANCE" if ok else "FIX_BLOCKERS",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Legacy Facade Growth Freeze Check",
        "",
        f"- overall: {report['overall']}",
        f"- ok: {str(report['ok']).lower()}",
        f"- recommendation: {report['recommendation']}",
        "",
        "## Blockers",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Checks"])
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {str(check.get('ok')).lower()}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze legacy facade growth and production_compat bypasses.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = build_report()
    if args.output_json:
        write_json(report, Path(args.output_json))
    if args.output_md:
        write_markdown(report, Path(args.output_md))

    print(f"overall: {report['overall']}")
    if report["blockers"]:
        print("blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
