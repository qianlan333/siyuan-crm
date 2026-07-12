#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "architecture" / "high_risk_contract_inventory.yml"
SCOPE_MANIFEST = ROOT / "docs" / "ci" / "test_scope_manifest.yml"
REQUIRED_DOMAINS = {
    "auth",
    "callback",
    "payment",
    "refund_entitlement",
    "questionnaire",
    "group_ops",
    "delivery",
}
REQUIRED_CASES = {"success", "failure", "replay_or_concurrency"}


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        import yaml

        value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _test_functions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def _node_parts(node_id: str) -> tuple[str, str]:
    parts = str(node_id or "").split("::")
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def validate_manifest(
    manifest: dict[str, Any],
    *,
    root: Path = ROOT,
    scope_manifest_path: Path = SCOPE_MANIFEST,
) -> list[str]:
    errors: list[str] = []
    domains = manifest.get("domains", [])
    if not isinstance(domains, list):
        return ["domains must be a list"]
    domain_names = {str(item.get("domain") or "") for item in domains if isinstance(item, dict)}
    for missing in sorted(REQUIRED_DOMAINS - domain_names):
        errors.append(f"missing required domain: {missing}")
    for extra in sorted(domain_names - REQUIRED_DOMAINS):
        errors.append(f"unknown high-risk domain: {extra}")

    scopes_document = load_manifest(scope_manifest_path)
    scopes = {
        str(item.get("name") or ""): item
        for item in scopes_document.get("scopes", []) or []
        if isinstance(item, dict)
    }
    used_nodes: set[str] = set()
    for domain in domains:
        if not isinstance(domain, dict):
            errors.append("domain entry must be a mapping")
            continue
        name = str(domain.get("domain") or "<missing>")
        owner = str(domain.get("owner") or "")
        scope_name = str(domain.get("ci_scope") or "")
        contracts = domain.get("contracts", {})
        if not owner:
            errors.append(f"{name}: owner is required")
        if bool(domain.get("real_external_call_expected", False)):
            errors.append(f"{name}: real external call must not be expected in contract tests")
        if not isinstance(contracts, dict):
            errors.append(f"{name}: contracts must be a mapping")
            continue
        for case in sorted(REQUIRED_CASES - set(contracts)):
            errors.append(f"{name}: missing {case} contract")
        scope = scopes.get(scope_name)
        if scope is None:
            errors.append(f"{name}: unknown CI scope {scope_name!r}")
            selected_files: set[str] = set()
        else:
            selected_files = {str(item) for item in scope.get("python_tests", []) or []}
        for case in sorted(REQUIRED_CASES & set(contracts)):
            node_id = str(contracts.get(case) or "")
            test_file, test_name = _node_parts(node_id)
            if not test_file or not test_name:
                errors.append(f"{name}.{case}: invalid pytest node id {node_id!r}")
                continue
            if node_id in used_nodes:
                errors.append(f"{name}.{case}: duplicate pytest node id {node_id}")
            used_nodes.add(node_id)
            functions = _test_functions(root / test_file)
            if test_name not in functions:
                errors.append(f"{name}.{case}: pytest node does not exist: {node_id}")
            if test_file not in selected_files:
                errors.append(f"{name}.{case}: {test_file} is not selected by CI scope {scope_name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Issue #67 high-risk golden contract coverage.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    validation_messages = validate_manifest(load_manifest(args.manifest), root=ROOT)
    if validation_messages:
        for validation_message in validation_messages:
            print(validation_message)
        return 1
    print("high-risk contract inventory: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
