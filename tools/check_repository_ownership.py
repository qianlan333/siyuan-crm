from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs" / "architecture" / "repository_ownership.yml"
DEFAULT_MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
REPOSITORY_PATTERNS = ("*repo.py", "*repository.py", "*repositories.py")
SQL_PREFIXES = ("select", "with", "insert", "update", "delete", "truncate")
NON_RELATION_IDENTIFIERS = {
    "__dynamic__",
    "current_timestamp",
    "elem",
    "failed",
    "jsonb_array_element",
    "jsonb_array_elements",
    "jsonb_array_elements_text",
    "lateral",
    "of",
    "set",
    "skip",
    "unnest",
    "value",
    "values",
}
RELATION_PATTERN = r"(?:(?P<schema>[a-zA-Z_][a-zA-Z0-9_]*)\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\b"
READ_RELATION_RE = re.compile(rf"\b(?:FROM|JOIN)\s+{RELATION_PATTERN}", re.IGNORECASE)
WRITE_RELATION_RES = (
    re.compile(rf"\bINSERT\s+INTO\s+{RELATION_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bUPDATE\s+{RELATION_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bDELETE\s+FROM\s+{RELATION_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bTRUNCATE(?:\s+TABLE)?\s+{RELATION_PATTERN}", re.IGNORECASE),
)
CTE_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s+(?:(?:NOT\s+)?MATERIALIZED\s+)?\(",
    re.IGNORECASE,
)
ALLOWED_ACCESS_SCOPES = {"runtime", "test_staging"}


@dataclass(frozen=True)
class RepositoryOwnershipViolation:
    path: str
    rule: str
    detail: str

    def format(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class RepositorySqlAccess:
    table_reads: frozenset[str]
    table_writes: frozenset[str]
    dynamic_relation_literals: frozenset[str]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate repository table ownership declarations.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)

    violations = check_repository_ownership(
        root=Path(args.root).resolve(),
        registry_path=Path(args.registry).resolve(),
        manifest_path=Path(args.manifest).resolve(),
    )
    if violations:
        print("Repository ownership check failed:")
        for violation in violations:
            print(f"- {violation.format()}")
        return 1
    print(f"Repository ownership check OK: {args.registry}")
    return 0


def check_repository_ownership(
    *,
    root: Path = ROOT,
    registry_path: Path = DEFAULT_REGISTRY,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> list[RepositoryOwnershipViolation]:
    registry = _load_registry(registry_path)
    manifest = _load_manifest(manifest_path)
    entries = registry["repositories"]
    repo_paths = _repository_paths(root)
    violations: list[RepositoryOwnershipViolation] = []

    missing = sorted(repo_paths - set(entries))
    for path in missing:
        violations.append(
            RepositoryOwnershipViolation(
                path=path,
                rule="repository_missing_ownership_declaration",
                detail="repository file must declare capability_owner, table_reads, and table_writes",
            )
        )

    stale = sorted(set(entries) - repo_paths)
    for path in stale:
        violations.append(
            RepositoryOwnershipViolation(
                path=path,
                rule="repository_ownership_stale_path",
                detail="declared repository path does not exist",
            )
        )

    tables = manifest["tables"]
    for path, entry in sorted(entries.items()):
        capability_owner = str(entry.get("capability_owner") or "").strip()
        if not capability_owner:
            violations.append(
                RepositoryOwnershipViolation(
                    path=path,
                    rule="repository_missing_capability_owner",
                    detail="capability_owner is required",
                )
            )
        for field in ("table_reads", "table_writes"):
            if not isinstance(entry.get(field), list):
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_invalid_table_declaration",
                        detail=f"{field} must be a list",
                    )
                )
                continue
            if sorted(entry[field]) != entry[field]:
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_unsorted_table_declaration",
                        detail=f"{field} must be sorted for reviewable diffs",
                    )
                )
        access_scope = str(entry.get("access_scope") or "runtime").strip()
        if access_scope not in ALLOWED_ACCESS_SCOPES:
            violations.append(
                RepositoryOwnershipViolation(
                    path=path,
                    rule="repository_invalid_access_scope",
                    detail=f"access_scope must be one of {sorted(ALLOWED_ACCESS_SCOPES)}",
                )
            )
        declared_exceptions: dict[str, list[str]] = {}
        for field in ("non_table_relations", "optional_relations"):
            values = entry.get(field) or []
            if (
                not isinstance(values, list)
                or sorted(values) != values
                or not all(isinstance(item, str) and item.strip() for item in values)
            ):
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule=f"repository_invalid_{field}",
                        detail=f"{field} must be a sorted list of non-empty names",
                    )
                )
                values = []
            declared_exceptions[field] = values

        non_literal_access: dict[str, list[str]] = {}
        for field in ("non_literal_table_reads", "non_literal_table_writes"):
            values = entry.get(field) or []
            if (
                not isinstance(values, list)
                or sorted(values) != values
                or not all(isinstance(item, str) and item.strip() for item in values)
            ):
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule=f"repository_invalid_{field}",
                        detail=f"{field} must be a sorted list of non-empty declared table names",
                    )
                )
                values = []
            non_literal_access[field] = values

        if isinstance(entry.get("table_reads"), list) and isinstance(entry.get("table_writes"), list):
            access = extract_repository_sql_access(root / path)
            declared_reads = set(entry["table_reads"])
            declared_writes = set(entry["table_writes"])
            missing_reads = sorted(access.table_reads - declared_reads)
            missing_writes = sorted(access.table_writes - declared_writes)
            for field, missing_values in (
                ("table_reads", missing_reads),
                ("table_writes", missing_writes),
            ):
                if missing_values:
                    violations.append(
                        RepositoryOwnershipViolation(
                            path=path,
                            rule="repository_sql_access_missing_declaration",
                            detail=f"{field} is missing AST/SQL accesses: {missing_values}",
                        )
                    )
            for field, declared_values, actual_values, exception_field in (
                (
                    "table_reads",
                    declared_reads,
                    set(access.table_reads),
                    "non_literal_table_reads",
                ),
                (
                    "table_writes",
                    declared_writes,
                    set(access.table_writes),
                    "non_literal_table_writes",
                ),
            ):
                exceptions = set(non_literal_access[exception_field])
                exception_without_declaration = sorted(exceptions - declared_values)
                if exception_without_declaration:
                    violations.append(
                        RepositoryOwnershipViolation(
                            path=path,
                            rule="repository_non_literal_access_without_declaration",
                            detail=f"{exception_field} is not present in {field}: {exception_without_declaration}",
                        )
                    )
                direct_exception_overlap = sorted(exceptions & actual_values)
                if direct_exception_overlap:
                    violations.append(
                        RepositoryOwnershipViolation(
                            path=path,
                            rule="repository_stale_non_literal_access_exception",
                            detail=f"{exception_field} is now visible as literal SQL: {direct_exception_overlap}",
                        )
                    )
                declarations_without_source = sorted(declared_values - actual_values - exceptions)
                if declarations_without_source:
                    violations.append(
                        RepositoryOwnershipViolation(
                            path=path,
                            rule="repository_sql_declaration_without_access",
                            detail=(
                                f"{field} has no literal SQL access or explicit {exception_field}: "
                                f"{declarations_without_source}"
                            ),
                        )
                    )
            allowed_non_tables = set(declared_exceptions["non_table_relations"])
            allowed_optional = set(declared_exceptions["optional_relations"])
            undeclared_exceptions = sorted(
                (allowed_non_tables | allowed_optional) - declared_reads - declared_writes
            )
            if undeclared_exceptions:
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_relation_exception_without_declaration",
                        detail=f"relation exceptions are not present in table reads/writes: {undeclared_exceptions}",
                    )
                )
            for relation in sorted(declared_reads | declared_writes):
                if (
                    relation in tables
                    or relation in allowed_non_tables
                    or relation in allowed_optional
                    or access_scope == "test_staging"
                ):
                    continue
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_relation_missing_lifecycle",
                        detail=(
                            f"{relation} is not in the table lifecycle manifest; declare a governed "
                            "view/CTE in non_table_relations or a fail-closed optional legacy relation "
                            "in optional_relations"
                        ),
                    )
                )
        for table in entry.get("table_reads") or []:
            manifest_entry = tables.get(table)
            if manifest_entry and manifest_entry.get("lifecycle") == "retired":
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_reads_retired_table",
                        detail=f"declared read of retired table {table}",
                    )
                )
            if manifest_entry and manifest_entry.get("pii_level") and not capability_owner:
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_reads_pii_without_owner",
                        detail=f"declared read of PII table {table} requires capability_owner",
                    )
                )
        for table in entry.get("table_writes") or []:
            manifest_entry = tables.get(table)
            if not manifest_entry:
                continue
            write_owners = _write_owners(manifest_entry)
            if not write_owners:
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_writes_manifest_table_without_owner",
                        detail=f"{table} has no write_owner in lifecycle manifest",
                    )
                )
                continue
            if not any(_owner_matches(capability_owner, write_owner) for write_owner in write_owners):
                violations.append(
                    RepositoryOwnershipViolation(
                        path=path,
                        rule="repository_write_owner_mismatch",
                        detail=f"{table} write_owners={write_owners} does not match capability_owner={capability_owner}",
                    )
                )
    return violations


def extract_repository_sql_access(path: Path) -> RepositorySqlAccess:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    sql_literals = _sql_literals(tree)
    table_reads: set[str] = set()
    table_writes: set[str] = set()
    for sql_source in sql_literals:
        cte_names = {
            match.group(1).lower()
            for match in CTE_RE.finditer(sql_source)
        }
        table_reads.update(
            _relations_from_matches(
                sql_source,
                READ_RELATION_RE,
                cte_names=cte_names,
                read_context=True,
            )
        )
        for pattern in WRITE_RELATION_RES:
            table_writes.update(
                _relations_from_matches(
                    sql_source,
                    pattern,
                    cte_names=cte_names,
                    read_context=False,
                )
            )
    dynamic_relation_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", node.value)
    }
    return RepositorySqlAccess(
        table_reads=frozenset(table_reads),
        table_writes=frozenset(table_writes),
        dynamic_relation_literals=frozenset(dynamic_relation_literals),
    )


def _sql_literals(tree: ast.AST) -> list[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        value = _static_string(node)
        if value is not None and value.lstrip().lower().startswith(SQL_PREFIXES):
            values.add(value)
    return sorted(values)


def _static_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(" __dynamic__ ")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left)
        right = _static_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _relations_from_matches(
    sql_source: str,
    pattern: re.Pattern[str],
    *,
    cte_names: set[str],
    read_context: bool,
) -> set[str]:
    relations: set[str] = set()
    for match in pattern.finditer(sql_source):
        schema = (match.group("schema") or "").lower()
        table = match.group("table").lower()
        if schema not in {"", "public"}:
            continue
        if table in NON_RELATION_IDENTIFIERS or table in cte_names:
            continue
        if read_context:
            prefix = sql_source[max(0, match.start() - 16) : match.start()]
            if re.search(r"DELETE\s*$", prefix, flags=re.IGNORECASE):
                continue
            if sql_source[match.end() :].lstrip().startswith("("):
                continue
        relations.add(table)
    return relations


def _load_registry(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("repositories"), dict):
        raise ValueError("repository ownership registry must contain a repositories mapping")
    return raw


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("tables"), dict):
        raise ValueError("data table lifecycle manifest must contain a tables mapping")
    return raw


def _repository_paths(root: Path) -> set[str]:
    base = root / "aicrm_next"
    paths: set[str] = set()
    for pattern in REPOSITORY_PATTERNS:
        paths.update(path.relative_to(root).as_posix() for path in base.rglob(pattern))
    return {path for path in paths if "__pycache__" not in path}


def _owner_matches(capability_owner: str, write_owner: str) -> bool:
    return write_owner == capability_owner or write_owner.startswith(f"{capability_owner}.")


def _write_owners(manifest_entry: dict[str, Any]) -> list[str]:
    owners: list[str] = []
    write_owner = str(manifest_entry.get("write_owner") or "").strip()
    if write_owner:
        owners.append(write_owner)
    extra_owners = manifest_entry.get("write_owners")
    if isinstance(extra_owners, list):
        owners.extend(str(owner or "").strip() for owner in extra_owners)
    return sorted({owner for owner in owners if owner})


if __name__ == "__main__":
    sys.exit(main())
