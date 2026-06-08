#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

UNAUTHORIZED_STATUS_MARKERS = ("production_ready", "delete_ready", "production_approved")
FRONTEND_SQL_PATTERNS = [
    re.compile(r"\bSELECT\b.+\bFROM\b", re.I | re.S),
    re.compile(r"\bINSERT\s+INTO\b", re.I),
    re.compile(r"\bUPDATE\s+[a-zA-Z_][\w.]*\s+SET\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
    re.compile(r"\bJOIN\s+[a-zA-Z_][\w.]*\b", re.I),
]
HISTORICAL_OPENCLAW_CONTEXT = (
    "physically removed",
    "deleted",
    "absent",
    "historical",
    "blocked",
    "must not be reintroduced",
    "not a live repo path",
    "forbid",
    "forbidden",
    "blocks",
    "物理删除",
    "已删除",
    "历史",
    "不得重新引入",
    "禁止",
)
FIXTURE_PRODUCTION_ALLOWED_CONTEXT = (
    "not allowed in production",
    "must not",
    "不得",
    "禁止",
    "blocked",
    "risk",
    "unavailable",
    "degraded",
    "failure",
    "失败",
    "不可用",
    "不得返回",
    "not production data",
    "not return",
    "does not return",
    "without fixture",
    "fixture-free",
    "fixture_allowed_in_production: false",
    "fixture_allowed_in_production=false",
    "local_contract_only",
)
UNAUTHORIZED_MARKER_ALLOWED_CONTEXT = (
    "must not",
    "do not",
    "no module",
    "no canary",
    "forbid",
    "forbidden",
    "unauthorized",
    "without approval",
    "unapproved",
    "不得",
    "禁止",
    "未经授权",
)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _iter_files(root: Path) -> list[Path]:
    skip_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _is_archive_or_retirement_path(relpath: str) -> bool:
    lower = relpath.lower()
    return (
        "/archive/" in lower
        or lower.startswith("docs/archive/")
        or lower.startswith("experiments/")
        or "retirement" in lower
    )


def _is_historical_report_doc(relpath: str) -> bool:
    lower = relpath.lower()
    if not lower.startswith("docs/"):
        return False
    name = Path(lower).name
    return (
        lower.startswith("docs/route_ownership/")
        or lower.startswith("docs/development/")
        or lower.startswith("docs/refactor/")
        or lower.startswith("docs/architecture/")
        or name.startswith(("d7_", "d8_", "d9_", "legacy_"))
        or any(token in name for token in ("report", "runbook", "matrix", "plan", "inventory", "evidence", "checklist"))
    )


def _is_checker_or_test_path(relpath: str) -> bool:
    return relpath.startswith("tests/") or "/tests/" in relpath or relpath.startswith("tools/check_") or "/tools/check_" in relpath


def _is_text_path(path: Path) -> bool:
    return path.suffix.lower() in {".py", ".md", ".txt", ".yaml", ".yml", ".sh"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _openclaw_context_ok(text: str, index: int) -> bool:
    start = max(0, index - 180)
    end = min(len(text), index + 220)
    context = text[start:end].lower()
    return any(marker in context for marker in HISTORICAL_OPENCLAW_CONTEXT)


def _fixture_production_context_ok(text: str, index: int) -> bool:
    start = max(0, index - 160)
    end = min(len(text), index + 220)
    context = text[start:end].lower()
    return any(marker in context for marker in FIXTURE_PRODUCTION_ALLOWED_CONTEXT)


def _unauthorized_marker_context_ok(text: str, index: int) -> bool:
    start = max(0, index - 160)
    end = min(len(text), index + 220)
    context = text[start:end].lower()
    return any(marker in context for marker in UNAUTHORIZED_MARKER_ALLOWED_CONTEXT)


def check_openclaw(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if (root / "openclaw_service").exists():
        blockers.append({"path": "openclaw_service/", "reason": "openclaw_service_live_path_exists"})
    for path in _iter_files(root):
        relpath = _rel(path, root)
        if not _is_text_path(path):
            continue
        text = _read_text(path)
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "openclaw_service" or alias.name.startswith("openclaw_service."):
                                blockers.append({"path": relpath, "line": node.lineno, "reason": "imports_openclaw_service"})
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if module == "openclaw_service" or module.startswith("openclaw_service."):
                            blockers.append({"path": relpath, "line": node.lineno, "reason": "imports_openclaw_service"})
        if _is_checker_or_test_path(relpath) or _is_archive_or_retirement_path(relpath) or _is_historical_report_doc(relpath):
            continue
        for match in re.finditer(r"openclaw_service/?", text, flags=re.I):
            if not _openclaw_context_ok(text, match.start()):
                blockers.append({"path": relpath, "line": _line_number(text, match.start()), "reason": "openclaw_live_reference"})
    return blockers


def check_frontend_compat_sql(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    base = root / "aicrm_next/frontend_compat"
    if not base.exists():
        return blockers
    for path in base.rglob("*.py"):
        relpath = _rel(path, root)
        text = _read_text(path)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in {"psycopg", "sqlalchemy"} or alias.name.startswith(("psycopg.", "sqlalchemy.")):
                            blockers.append({"path": relpath, "line": node.lineno, "reason": "frontend_compat_sql_or_driver", "match": alias.name})
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in {"psycopg", "sqlalchemy"} or module.startswith(("psycopg.", "sqlalchemy.")):
                        blockers.append({"path": relpath, "line": node.lineno, "reason": "frontend_compat_sql_or_driver", "match": module})
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for pattern in FRONTEND_SQL_PATTERNS:
                        if pattern.search(node.value):
                            blockers.append({"path": relpath, "line": getattr(node, "lineno", 1), "reason": "frontend_compat_sql_or_driver", "match": pattern.pattern})
                            break
            continue
        for pattern in FRONTEND_SQL_PATTERNS:
            for match in pattern.finditer(text):
                blockers.append({"path": relpath, "line": _line_number(text, match.start()), "reason": "frontend_compat_sql_or_driver", "match": match.group(0)})
    return blockers


def check_api_cross_context_repo_imports(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for path in (root / "aicrm_next").glob("*/api.py"):
        relpath = _rel(path, root)
        context = path.parent.name
        text = _read_text(path)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                parts = module.split(".")
                imported_context = ""
                if len(parts) >= 3 and parts[0] == "aicrm_next":
                    imported_context = parts[1]
                elif module.startswith("."):
                    continue
                if imported_context and imported_context != context and parts[-1] in {"repo", "service"}:
                    blockers.append({"path": relpath, "line": node.lineno, "reason": "api_imports_other_context_repo_or_service", "module": module})
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) >= 3 and parts[0] == "aicrm_next" and parts[1] != context and parts[-1] in {"repo", "service"}:
                        blockers.append({"path": relpath, "line": node.lineno, "reason": "api_imports_other_context_repo_or_service", "module": alias.name})
    return blockers


def check_status_markers(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    allowed_paths = {
        "docs/development/ai_crm_next_architecture_skill.md",
        "docs/development/autonomous_development_loop.md",
        "docs/development/autonomous_stop_conditions.yaml",
        "docs/development/phase_execution_state.yaml",
        "docs/route_ownership/production_route_ownership_manifest.yaml",
        "docs/route_ownership/production_route_ownership_manifest.md",
        "tools/check_architecture_skill_compliance.py",
        "tests/test_architecture_skill_compliance.py",
    }
    for path in _iter_files(root):
        relpath = _rel(path, root)
        if not _is_text_path(path) or relpath in allowed_paths or _is_archive_or_retirement_path(relpath) or _is_checker_or_test_path(relpath):
            continue
        text = _read_text(path)
        for marker in UNAUTHORIZED_STATUS_MARKERS:
            for match in re.finditer(re.escape(marker), text):
                if _unauthorized_marker_context_ok(text, match.start()):
                    continue
                blockers.append({"path": relpath, "line": _line_number(text, match.start()), "reason": "unauthorized_status_marker", "marker": marker})
    return blockers


def check_fixture_production_docs(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for path in (root / "docs").rglob("*.md"):
        relpath = _rel(path, root)
        if _is_archive_or_retirement_path(relpath) or _is_historical_report_doc(relpath):
            continue
        text = _read_text(path)
        for match in re.finditer(r"(fixture|local_contract).{0,120}production|production.{0,120}(fixture|local_contract)", text, flags=re.I | re.S):
            if not _fixture_production_context_ok(text, match.start()):
                blockers.append({"path": relpath, "line": _line_number(text, match.start()), "reason": "fixture_described_as_production_data"})
    return blockers


def check_pr_template(root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    path = root / "docs/development/codex_task_template.md"
    if not path.exists():
        return [{"path": "docs/development/codex_task_template.md", "reason": "missing_codex_task_template"}]
    text = _read_text(path)
    required = ["Summary", "Architecture boundary", "Safety", "Verification", "Rollback"]
    for phrase in required:
        if phrase not in text:
            blockers.append({"path": _rel(path, root), "reason": "template_missing_pr_section", "section": phrase})
    if "check_architecture_skill_compliance" not in text:
        blockers.append({"path": _rel(path, root), "reason": "template_missing_compliance_checker"})
    return blockers


def build_report(root: Path = ROOT) -> dict[str, Any]:
    checks = {
        "openclaw": check_openclaw(root),
        "frontend_compat_sql": check_frontend_compat_sql(root),
        "api_cross_context_repo_imports": check_api_cross_context_repo_imports(root),
        "status_markers": check_status_markers(root),
        "fixture_production_docs": check_fixture_production_docs(root),
        "pr_template": check_pr_template(root),
    }
    blockers = [item for values in checks.values() for item in values]
    return {"ok": not blockers, "blockers": blockers, "checks": checks}


def write_json(path: str, report: dict[str, Any]) -> None:
    if path:
        Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    lines = [
        "# Architecture Skill Compliance",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- blockers: `{len(report['blockers'])}`",
        "",
        "## Checks",
    ]
    for name, values in report["checks"].items():
        lines.append(f"- {name}: `{len(values)}` blocker(s)")
    if report["blockers"]:
        lines.extend(["", "## Blockers"])
        for item in report["blockers"]:
            location = item.get("path", "")
            line = f":{item['line']}" if item.get("line") else ""
            lines.append(f"- `{location}{line}` {item.get('reason')}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-CRM Next architecture skill compliance.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    report = build_report()
    write_markdown(args.output_md, report)
    write_json(args.output_json, report)
    print(json.dumps({"ok": report["ok"], "blocker_count": len(report["blockers"])}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
