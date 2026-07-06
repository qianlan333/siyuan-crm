from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs" / "architecture" / "repository_ownership.yml"
DEFAULT_MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
REPOSITORY_PATTERNS = ("*repo.py", "*repository.py", "*repositories.py")


@dataclass(frozen=True)
class RepositoryOwnershipViolation:
    path: str
    rule: str
    detail: str

    def format(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


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
