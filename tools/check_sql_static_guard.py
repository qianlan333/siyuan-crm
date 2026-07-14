from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
SQL_ROOTS = ("aicrm_next", "scripts", "tools", "migrations")
SQL_PREFIXES = (
    "select",
    "with",
    "insert into",
    "update",
    "delete from",
    "truncate",
    "create table",
    "alter table",
    "drop table",
)
RESERVED_TABLE_NAMES = {
    "__expr__",
    "exists",
    "for",
    "from",
    "if",
    "into",
    "not",
    "select",
    "set",
    "table",
    "where",
}
MIGRATION_METADATA_TABLES = {"alembic_version"}
LEGACY_IDENTITY_COLUMNS = {
    "external_userid",
    "external_contact_id",
    "openid",
    "payer_openid",
    "mobile_snapshot",
    "buyer_id",
    "identity_snapshot",
    "userid_snapshot",
    "respondent_key",
    "person_id",
    "target_external_userids",
}
IDENTITY_BOUNDARY_TABLE_PREFIXES = (
    "crm_user_identity",
    "external_contact_bindings",
    "wecom_external_contact_",
)
IDENTITY_BOUNDARY_TABLE_NAMES = {
    "automation_channel_entry_runtime",
}
APPROVED_LEGACY_IDENTITY_MIGRATION_BOUNDARIES = {
    ("0095_service_period_products.py", "upgrade", "service_period_entitlements", "mobile_snapshot"),
    ("0097_service_period_unionid_cleanup.py", "downgrade", "service_period_entitlements", "mobile_snapshot"),
    ("0102_questionnaire_radar_invariants.py", "_radar_click_events", "radar_click_events", "external_userid"),
    ("0102_questionnaire_radar_invariants.py", "_radar_click_events", "radar_click_events", "openid"),
    ("0102_questionnaire_radar_invariants.py", "_radar_click_events", "radar_click_events", "person_id"),
}
_UNQUOTED_SQL_IDENTIFIER = r"[a-zA-Z_][a-zA-Z0-9_]*"
_QUOTED_SQL_IDENTIFIER = r'"[^"]+"'
_SQL_IDENTIFIER_PATTERN = rf"(?:{_QUOTED_SQL_IDENTIFIER}|{_UNQUOTED_SQL_IDENTIFIER})"
_SQL_QUALIFIED_IDENTIFIER_PATTERN = rf"{_SQL_IDENTIFIER_PATTERN}(?:\s*\.\s*{_SQL_IDENTIFIER_PATTERN})*"


@dataclass(frozen=True)
class SqlStaticViolation:
    path: Path
    line: int
    rule: str
    detail: str

    def format(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.line}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class SqlLiteral:
    path: Path
    line: int
    value: str
    function_name: str = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate static SQL guardrails for AI-CRM Next.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    violations = check_sql_static_guard(root=root, manifest_path=Path(args.manifest).resolve())
    if violations:
        print("SQL static guard failed:")
        for violation in violations:
            print(f"- {violation.format(root)}")
        return 1
    print(f"SQL static guard OK: {root}")
    return 0


def check_sql_static_guard(root: Path = ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> list[SqlStaticViolation]:
    manifest = _load_manifest(manifest_path)
    tables = manifest["tables"]
    registered_tables = set(tables)
    retired_tables = {table for table, entry in tables.items() if entry.get("lifecycle") == "retired"}
    baseline_prefix = int((manifest.get("migration_guard") or {}).get("migration_file_prefix_after") or 0)

    violations: list[SqlStaticViolation] = []
    for literal in _iter_sql_literals(root):
        normalized = _normalize_sql(literal.value)
        if not _looks_like_sql(normalized):
            continue
        is_pre_guard_migration = _is_pre_guard_migration(literal.path, root=root, baseline_prefix=baseline_prefix)
        if not is_pre_guard_migration:
            if not (
                _is_migration(literal.path, root=root)
                and (_is_drop_table_statement(normalized) or _is_downgrade_retired_table_restore(literal, normalized, retired_tables, root))
            ):
                violations.extend(_retired_table_violations(literal, normalized, retired_tables))
            violations.extend(_legacy_identity_column_violations(literal, normalized))
        violations.extend(
            _create_table_registration_violations(
                literal,
                normalized,
                registered_tables,
                baseline_prefix,
                root,
            )
        )
    return violations


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("tables"), dict):
        raise ValueError("data table lifecycle manifest must be a mapping with a tables mapping")
    return raw


def _iter_sql_literals(root: Path) -> Iterable[SqlLiteral]:
    for base_name in SQL_ROOTS:
        base = root / base_name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                continue
            yield from _iter_sql_literals_from_node(path, tree)


def _iter_sql_literals_from_node(path: Path, node: ast.AST, *, function_name: str = "") -> Iterable[SqlLiteral]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        function_name = node.name
    value = _string_value(node)
    if value is not None:
        yield SqlLiteral(path=path, line=getattr(node, "lineno", 1), value=value, function_name=function_name)
    for child in ast.iter_child_nodes(node):
        yield from _iter_sql_literals_from_node(path, child, function_name=function_name)


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append(" __expr__ ")
        return "".join(parts)
    return None


def _normalize_sql(value: str) -> str:
    return re.sub(r"\s+", " ", _strip_leading_sql_comments(value).strip())


def _strip_leading_sql_comments(value: str) -> str:
    remaining = value.lstrip()
    while remaining:
        if remaining.startswith("--"):
            newline = remaining.find("\n")
            if newline == -1:
                return ""
            remaining = remaining[newline + 1 :].lstrip()
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/", 2)
            if end == -1:
                return ""
            remaining = remaining[end + 2 :].lstrip()
            continue
        break
    return remaining


def _looks_like_sql(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(SQL_PREFIXES)


def _retired_table_violations(
    literal: SqlLiteral,
    normalized: str,
    retired_tables: set[str],
) -> list[SqlStaticViolation]:
    violations: list[SqlStaticViolation] = []
    for table in sorted(retired_tables):
        if _references_table(normalized, table):
            violations.append(
                SqlStaticViolation(
                    path=literal.path,
                    line=literal.line,
                    rule="retired_table_sql_reference",
                    detail=f"SQL references retired table {table}",
                )
            )
    return violations


def _create_table_registration_violations(
    literal: SqlLiteral,
    normalized: str,
    registered_tables: set[str],
    baseline_prefix: int,
    root: Path,
) -> list[SqlStaticViolation]:
    if _is_pre_guard_migration(literal.path, root=root, baseline_prefix=baseline_prefix):
        return []
    created = _created_tables(normalized) - MIGRATION_METADATA_TABLES
    return [
        SqlStaticViolation(
            path=literal.path,
            line=literal.line,
            rule="create_table_without_lifecycle_manifest",
            detail=f"CREATE TABLE for {table} is missing from data_table_lifecycle_manifest.yml",
        )
        for table in sorted(created - registered_tables)
    ]


def _legacy_identity_column_violations(literal: SqlLiteral, normalized: str) -> list[SqlStaticViolation]:
    created_tables = _created_tables(normalized) | _altered_tables(normalized)
    business_tables = {table for table in created_tables if not _is_identity_boundary_table(table)}
    if not business_tables:
        return []
    columns = _declared_columns(normalized) & LEGACY_IDENTITY_COLUMNS
    return [
        SqlStaticViolation(
            path=literal.path,
            line=literal.line,
            rule="legacy_identity_column_in_business_sql",
            detail=f"{table} declares legacy identity column {column}",
        )
        for table in sorted(business_tables)
        for column in sorted(columns)
        if not _approved_legacy_identity_migration_boundary(literal, table, column)
    ]


def _approved_legacy_identity_migration_boundary(literal: SqlLiteral, table: str, column: str) -> bool:
    return (
        literal.path.name,
        literal.function_name,
        table,
        column,
    ) in APPROVED_LEGACY_IDENTITY_MIGRATION_BOUNDARIES


def _references_table(sql_text: str, table: str) -> bool:
    table_pattern = _table_identifier_pattern(table)
    return bool(
        re.search(
            rf"\b(from|join|into|update|table|truncate)\s+(?:if\s+(?:not\s+)?exists\s+)?{table_pattern}(?![a-zA-Z0-9_])",
            sql_text,
            flags=re.IGNORECASE,
        )
    )


def _table_identifier_pattern(table: str) -> str:
    quoted_table = re.escape(f'"{table}"')
    unquoted_table = re.escape(table)
    identifier = rf"(?:{quoted_table}|{unquoted_table})"
    schema_identifier = rf"(?:{_QUOTED_SQL_IDENTIFIER}|{_UNQUOTED_SQL_IDENTIFIER})"
    return rf"(?:(?:{schema_identifier})\s*\.\s*)?{identifier}"


def _unquote_identifier(identifier: str) -> str:
    stripped = identifier.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    return stripped


def _normalize_identifier(identifier: str) -> str:
    return _unquote_identifier(identifier).lower()


def _final_identifier_component(identifier: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*\.\s*", identifier.strip()) if part.strip()]
    if not parts:
        return ""
    return _normalize_identifier(parts[-1])


def _is_drop_table_statement(sql_text: str) -> bool:
    return bool(
        re.match(
            rf"^\s*drop\s+table\s+(?:if\s+exists\s+)?{_SQL_QUALIFIED_IDENTIFIER_PATTERN}(?:\s+cascade|\s+restrict)?\s*;?\s*$",
            sql_text,
            flags=re.IGNORECASE,
        )
    )


def _is_downgrade_retired_table_restore(
    literal: SqlLiteral,
    normalized: str,
    retired_tables: set[str],
    root: Path,
) -> bool:
    if literal.function_name != "downgrade" or not _is_migration(literal.path, root=root):
        return False
    created = _created_tables(normalized)
    return bool(created) and created.issubset(retired_tables)


def _created_tables(sql_text: str) -> set[str]:
    return {
        _final_identifier_component(match.group("table"))
        for match in re.finditer(
            rf"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?P<table>{_SQL_QUALIFIED_IDENTIFIER_PATTERN})",
            sql_text,
            flags=re.IGNORECASE,
        )
        if _is_real_table_name(_final_identifier_component(match.group("table")))
    }


def _altered_tables(sql_text: str) -> set[str]:
    return {
        _final_identifier_component(match.group("table"))
        for match in re.finditer(
            rf"\balter\s+table\s+(?:if\s+exists\s+)?(?P<table>{_SQL_QUALIFIED_IDENTIFIER_PATTERN})",
            sql_text,
            flags=re.IGNORECASE,
        )
        if _is_real_table_name(_final_identifier_component(match.group("table")))
    }


def _declared_columns(sql_text: str) -> set[str]:
    return {
        _normalize_identifier(match.group("column"))
        for match in re.finditer(
            rf"(?<![a-zA-Z0-9_\"])(?P<column>{_SQL_IDENTIFIER_PATTERN})\s+(?:TEXT|VARCHAR|UUID|JSONB|JSON|INTEGER|BIGINT|TIMESTAMPTZ|BOOLEAN)\b",
            sql_text,
            flags=re.IGNORECASE,
        )
    }


def _is_identity_boundary_table(table: str) -> bool:
    return table in IDENTITY_BOUNDARY_TABLE_NAMES or table.startswith(IDENTITY_BOUNDARY_TABLE_PREFIXES)


def _is_pre_guard_migration(path: Path, *, root: Path, baseline_prefix: int) -> bool:
    rel = _rel(path, root)
    if not rel.startswith("migrations/versions/"):
        return False
    match = re.match(r"migrations/versions/(\d{4})_", rel)
    if not match:
        return False
    return int(match.group(1)) <= baseline_prefix


def _is_migration(path: Path, *, root: Path) -> bool:
    return _rel(path, root).startswith("migrations/")


def _is_real_table_name(table: str) -> bool:
    normalized = table.lower()
    return normalized not in RESERVED_TABLE_NAMES and not normalized.startswith("__")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.exit(main())
