#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "docs" / "ci" / "test_scope_manifest.yml"
ARCHITECTURE_ORDER = {"none": 0, "fast": 1, "db": 2, "full": 3}


def _load_manifest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(
                f"{path} is not JSON-compatible and PyYAML is not installed. "
                "Keep the CI scope manifest JSON-compatible so selector can run before pip install."
            ) from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a mapping")
    return data


def _normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def _matches(path: str, pattern: str) -> bool:
    path = _normalize_path(path)
    pattern = _normalize_path(pattern)
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(f"{prefix}/")
    return fnmatch.fnmatchcase(path, pattern)


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _exclusive_scope_override_matches(
    manifest: dict,
    scopes_by_name: dict[str, dict],
    path: str,
) -> list[dict] | None:
    overrides = manifest.get("exclusive_scope_overrides", [])
    if not isinstance(overrides, list):
        raise SystemExit("manifest.exclusive_scope_overrides must be a list")
    for override in overrides:
        patterns = override.get("paths", [])
        if not any(_matches(path, pattern) for pattern in patterns):
            continue
        selected_scopes: list[dict] = []
        missing_names: list[str] = []
        for name in override.get("scopes", []):
            scope = scopes_by_name.get(str(name))
            if scope is None:
                missing_names.append(str(name))
                continue
            selected_scopes.append(scope)
        if missing_names:
            raise SystemExit(f"Unknown override scope(s) for {path}: {', '.join(missing_names)}")
        return selected_scopes
    return None


def _git_diff_names(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", *args],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )
    return [_normalize_path(line) for line in completed.stdout.splitlines() if line.strip()]


def _changed_files_from_event() -> list[str]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return _git_diff_names("HEAD^", "HEAD")

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")

    if event_name == "pull_request" and "pull_request" in payload:
        base_sha = payload["pull_request"]["base"]["sha"]
        head_sha = payload["pull_request"]["head"]["sha"]
        return _git_diff_names(f"{base_sha}...{head_sha}")

    if event_name == "push":
        before = payload.get("before")
        after = payload.get("after") or "HEAD"
        if before and set(before) != {"0"}:
            return _git_diff_names(before, after)
        return _git_diff_names("HEAD^", after)

    return []


def _full_ci_requested() -> bool:
    if os.environ.get("AICRM_FORCE_FULL_CI", "").lower() in {"1", "true", "yes"}:
        return True

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return False

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        value = payload.get("inputs", {}).get("full", "")
        return str(value).lower() in {"1", "true", "yes"}

    pull_request = payload.get("pull_request") or {}
    label_names = {
        str(label.get("name", "")).lower()
        for label in pull_request.get("labels", [])
        if isinstance(label, dict)
    }
    body = str(pull_request.get("body") or "").lower()
    title = str(pull_request.get("title") or "").lower()
    return "full-ci" in label_names or "[full-ci]" in body or "[full-ci]" in title


def _select(manifest: dict, changed_files: list[str]) -> dict:
    scopes = manifest.get("scopes", [])
    if not isinstance(scopes, list):
        raise SystemExit("manifest.scopes must be a list")

    changed_files = _unique(_normalize_path(path) for path in changed_files if path.strip())
    high_risk_paths = manifest.get("high_risk_paths", [])
    frontend_build_paths = manifest.get("frontend_build_paths", [])
    scopes_by_name = {str(scope.get("name")): scope for scope in scopes}

    matched_scopes: list[dict] = []
    matched_scope_names: set[str] = set()
    unmatched: list[str] = []

    for path in changed_files:
        override_matches = _exclusive_scope_override_matches(manifest, scopes_by_name, path)
        if override_matches is None:
            path_matches: list[dict] = []
            for scope in scopes:
                patterns = scope.get("paths", [])
                if any(_matches(path, pattern) for pattern in patterns):
                    path_matches.append(scope)
        else:
            path_matches = override_matches
        if not path_matches:
            unmatched.append(path)
            continue
        for scope in path_matches:
            name = str(scope.get("name"))
            if name not in matched_scope_names:
                matched_scope_names.add(name)
                matched_scopes.append(scope)

    high_risk = any(
        _matches(path, pattern)
        for path in changed_files
        for pattern in high_risk_paths
    )
    needs_frontend_build = any(
        _matches(path, pattern)
        for path in changed_files
        for pattern in frontend_build_paths
    )

    python_tests = _unique(
        test
        for scope in matched_scopes
        for test in scope.get("python_tests", [])
    )
    frontend_tests = _unique(
        test
        for scope in matched_scopes
        for test in scope.get("frontend_tests", [])
    )
    needs_postgres = any(bool(scope.get("needs_postgres")) for scope in matched_scopes)

    gate = "none"
    for scope in matched_scopes:
        candidate = str(scope.get("architecture_gate", "none"))
        if candidate not in ARCHITECTURE_ORDER:
            raise SystemExit(f"Unknown architecture_gate={candidate!r} in scope {scope.get('name')!r}")
        if ARCHITECTURE_ORDER[candidate] > ARCHITECTURE_ORDER[gate]:
            gate = candidate
    if high_risk:
        gate = "full" if ARCHITECTURE_ORDER[gate] < ARCHITECTURE_ORDER["full"] else gate

    force_full = _full_ci_requested()
    return {
        "changed_files": changed_files,
        "matched_scopes": [str(scope.get("name")) for scope in matched_scopes],
        "unmatched_files": unmatched,
        "python_tests": python_tests,
        "frontend_tests": frontend_tests,
        "needs_postgres": needs_postgres,
        "needs_frontend_build": needs_frontend_build,
        "needs_full_ci": high_risk or force_full,
        "force_full": force_full,
        "architecture_gate": gate,
    }


def _write_github_output(path: str, result: dict) -> None:
    outputs = {
        "changed_files": " ".join(result["changed_files"]),
        "scopes": ",".join(result["matched_scopes"]),
        "python_tests": " ".join(result["python_tests"]),
        "frontend_tests": " ".join(result["frontend_tests"]),
        "needs_postgres": str(result["needs_postgres"]).lower(),
        "needs_frontend_build": str(result["needs_frontend_build"]).lower(),
        "needs_full_ci": str(result["needs_full_ci"]).lower(),
        "force_full": str(result["force_full"]).lower(),
        "architecture_gate": result["architecture_gate"],
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--changed-files-from", type=Path)
    parser.add_argument("--github-output")
    parser.add_argument("--json", action="store_true", help="Print selected scope as JSON for tests and debugging.")
    args = parser.parse_args(argv)

    changed_files = [_normalize_path(path) for path in args.changed_file]
    if args.changed_files_from:
        changed_files.extend(
            _normalize_path(line)
            for line in args.changed_files_from.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not changed_files:
        changed_files = _changed_files_from_event()

    manifest = _load_manifest(args.manifest)
    result = _select(manifest, changed_files)

    if args.github_output:
        _write_github_output(args.github_output, result)

    if result["unmatched_files"]:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        message = manifest.get("unmapped_path_message", "Unmatched changed files")
        print(message, file=sys.stderr)
        for path in result["unmatched_files"]:
            print(f"- {path}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(
        "Selected CI scopes: "
        f"{','.join(result['matched_scopes']) or 'none'}; "
        f"python_tests={len(result['python_tests'])}; "
        f"frontend_tests={len(result['frontend_tests'])}; "
        f"needs_postgres={str(result['needs_postgres']).lower()}; "
        f"frontend_build={str(result['needs_frontend_build']).lower()}; "
        f"architecture_gate={result['architecture_gate']}; "
        f"needs_full_ci={str(result['needs_full_ci']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
