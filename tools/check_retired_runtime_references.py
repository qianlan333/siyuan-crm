#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs/architecture/retired_runtime_registry.yml"
TEXT_SUFFIXES = {".json", ".py", ".sh", ".toml", ".yaml", ".yml"}


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version") or 0) != 1:
        raise ValueError("retired runtime registry version must be 1")
    if not payload.get("scan_roots") or not payload.get("artifacts"):
        raise ValueError("retired runtime registry requires scan_roots and artifacts")
    return payload


def _allowed(relative_path: str, allowed_paths: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in allowed_paths)


def scan_references(root: Path, registry: dict[str, Any]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    scanned_files: set[str] = set()
    for relative_root in registry["scan_roots"]:
        scan_root = root / str(relative_root)
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative_path = path.relative_to(root).as_posix()
            scanned_files.add(relative_path)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for artifact in registry["artifacts"]:
                allowed_paths = [str(item) for item in artifact.get("allowed_paths") or []]
                if _allowed(relative_path, allowed_paths):
                    continue
                for pattern in artifact.get("patterns") or []:
                    text = str(pattern)
                    for line_number, line in enumerate(lines, start=1):
                        if text not in line:
                            continue
                        violations.append(
                            {
                                "artifact_id": str(artifact.get("id") or ""),
                                "kind": str(artifact.get("kind") or ""),
                                "pattern": text,
                                "path": relative_path,
                                "line": line_number,
                            }
                        )
    return {
        "ok": not violations,
        "registry_version": registry["version"],
        "scanned_file_count": len(scanned_files),
        "artifact_count": len(registry["artifacts"]),
        "violation_count": len(violations),
        "violations": violations,
    }


def run_check(root: Path = ROOT, registry_path: Path | None = None) -> dict[str, Any]:
    path = registry_path or root / "docs/architecture/retired_runtime_registry.yml"
    return scan_references(root, load_registry(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when retired runtime artifacts return to active source or ops paths.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    result = run_check(args.root.resolve(), args.registry.resolve() if args.registry else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
