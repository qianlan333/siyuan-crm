from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "docs" / "development" / "module_boundaries.yml"


@dataclass(frozen=True)
class BoundaryViolation:
    path: Path
    line: int
    rule: str
    reason: str
    suggestion: str

    def format(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.line}: {self.rule}: {self.reason} Suggestion: {self.suggestion}"


def load_config(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("module boundary config must be a mapping")
    api_rules = raw.get("api_import_rules") or {}
    _validate_allowed_imports_shape(api_rules.get("allowed_imports") or [])
    _validate_allowlist_shape(raw.get("legacy_allowlist") or [])
    return raw


def check_boundaries(root: Path = ROOT, config_path: Path = DEFAULT_CONFIG) -> list[BoundaryViolation]:
    config = load_config(config_path)
    violations: list[BoundaryViolation] = []
    violations.extend(_check_api_import_boundaries(root, config))
    violations.extend(_check_forbidden_legacy_markers(root, config))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AI-CRM Next architecture boundaries.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    violations = check_boundaries(root=root, config_path=Path(args.config).resolve())
    if violations:
        print("Architecture boundary check failed:")
        for violation in violations:
            print(f"- {violation.format(root)}")
        return 1
    print(f"Architecture boundary check OK: {args.config}")
    return 0


def _check_api_import_boundaries(root: Path, config: dict[str, Any]) -> list[BoundaryViolation]:
    rule_config = config.get("api_import_rules") or {}
    globs = rule_config.get("api_file_globs") or []
    semantic_imports = set(rule_config.get("api_semantic_imports") or ["fastapi.APIRouter"])
    forbidden_modules = set(rule_config.get("forbidden_cross_context_modules") or [])
    allowed_imports = rule_config.get("allowed_imports") or []
    violations: list[BoundaryViolation] = []

    for path in _iter_python_files(root / "aicrm_next"):
        rel = path.relative_to(root).as_posix()
        context = _context_for_path(path, root)
        if not context:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(
                BoundaryViolation(
                    path=path,
                    line=exc.lineno or 1,
                    rule="python_parse_error",
                    reason=str(exc),
                    suggestion="Fix syntax before running architecture boundary checks.",
                )
            )
            continue

        if not _is_api_boundary_file(rel, tree, globs, semantic_imports):
            continue
        for node in ast.walk(tree):
            for imported_module in _imported_modules(path, root, node, forbidden_modules=forbidden_modules):
                imported_context, imported_leaf = _context_and_leaf(imported_module)
                if not imported_context or not imported_leaf:
                    continue
                if imported_context == context:
                    continue
                if imported_leaf not in forbidden_modules:
                    continue
                if _is_allowed_import(allowed_imports, rel, imported_module):
                    continue
                violations.append(
                    BoundaryViolation(
                        path=path,
                        line=getattr(node, "lineno", 1),
                        rule="api_cross_context_repo_service_import",
                        reason=f"{rel} imports {imported_module} across context boundary.",
                        suggestion="Move the dependency behind this context's application/query/command layer or an integration_gateway adapter.",
                    )
                )
    return violations


def _check_forbidden_legacy_markers(root: Path, config: dict[str, Any]) -> list[BoundaryViolation]:
    markers = config.get("forbidden_legacy_markers") or []
    allowlist = config.get("legacy_allowlist") or []
    violations: list[BoundaryViolation] = []
    for path in _iter_python_files(root / "aicrm_next"):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            for marker in markers:
                if marker not in line:
                    continue
                if _is_allowed_legacy_marker(allowlist, rel, marker, line.strip()):
                    continue
                violations.append(
                    BoundaryViolation(
                        path=path,
                        line=line_number,
                        rule="forbidden_legacy_marker",
                        reason=f"`{marker}` appears in AI-CRM Next runtime code.",
                        suggestion="Remove the legacy runtime reference or add a precise allowlist entry with path, rule, reason, owner, marker, and match.",
                    )
                )
    return violations


def _iter_python_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return (path for path in sorted(base.rglob("*.py")) if "__pycache__" not in path.parts)


def _is_api_boundary_file(rel: str, tree: ast.AST, globs: list[str], semantic_imports: set[str]) -> bool:
    if any(fnmatch.fnmatch(rel, pattern) for pattern in globs):
        return True
    imported_symbols = set(_semantic_imported_symbols(tree))
    return bool(imported_symbols & semantic_imports)


def _semantic_imported_symbols(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                yield f"{module}.{alias.name}" if module else alias.name


def _imported_modules(path: Path, root: Path, node: ast.AST, *, forbidden_modules: set[str]) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        base = _resolve_import_from_module(path, root, node)
        if not base:
            return []
        modules = [base]
        for alias in node.names:
            if alias.name in forbidden_modules:
                modules.append(f"{base}.{alias.name}")
        return modules
    return []


def _resolve_import_from_module(path: Path, root: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    current = _module_for_path(path, root).split(".")
    package = current[:-1]
    if node.level > 1:
        package = package[: -(node.level - 1)]
    parts = [part for part in package + ([module] if module else []) if part]
    return ".".join(parts)


def _module_for_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _context_for_path(path: Path, root: Path) -> str | None:
    rel = path.relative_to(root)
    if len(rel.parts) < 3 or rel.parts[0] != "aicrm_next":
        return None
    return rel.parts[1]


def _context_and_leaf(module: str) -> tuple[str | None, str | None]:
    parts = module.split(".")
    if len(parts) < 3 or parts[0] != "aicrm_next":
        return None, None
    return parts[1], parts[-1]


def _is_allowed_import(allowed_imports: list[dict[str, Any]], path: str, imported_module: str) -> bool:
    for entry in allowed_imports:
        if entry.get("path") == path and entry.get("module") == imported_module:
            return True
    return False


def _is_allowed_legacy_marker(allowlist: list[dict[str, Any]], path: str, marker: str, stripped_line: str) -> bool:
    for entry in allowlist:
        if entry.get("path") != path:
            continue
        if entry.get("rule") != "forbidden_legacy_marker":
            continue
        if entry.get("marker") != marker:
            continue
        if stripped_line in set(entry.get("matches") or []):
            return True
    return False


def _validate_allowlist_shape(allowlist: list[dict[str, Any]]) -> None:
    required = {"path", "rule", "reason", "owner"}
    for index, entry in enumerate(allowlist, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"legacy_allowlist entry #{index} must be a mapping")
        missing = sorted(field for field in required if not entry.get(field))
        if missing:
            raise ValueError(f"legacy_allowlist entry #{index} missing required fields: {', '.join(missing)}")


def _validate_allowed_imports_shape(allowed_imports: list[dict[str, Any]]) -> None:
    required = {"path", "module", "owner", "reason", "migration_target"}
    for index, entry in enumerate(allowed_imports, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"allowed_imports entry #{index} must be a mapping")
        missing = sorted(field for field in required if not entry.get(field))
        if missing:
            raise ValueError(f"allowed_imports entry #{index} missing required fields: {', '.join(missing)}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
