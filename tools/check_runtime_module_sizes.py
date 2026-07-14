#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "docs" / "architecture" / "runtime_module_size_baseline.yml"


@dataclass(frozen=True)
class AllowedOversizedModule:
    path: str
    max_lines: int
    owner: str
    reason: str
    remove_by: str


@dataclass(frozen=True)
class ModuleSizeBaseline:
    package: str
    max_lines: int
    allowed: tuple[AllowedOversizedModule, ...]


@dataclass(frozen=True)
class ModuleSizeViolation:
    rule: str
    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "path": self.path, "reason": self.reason}

    def format(self) -> str:
        return f"{self.rule}: {self.path}: {self.reason}"


def scan_runtime_module_sizes(root: Path = ROOT, *, package: str = "aicrm_next") -> dict[str, int]:
    root = Path(root).resolve()
    package_dir = root / package
    if not package_dir.is_dir():
        raise ValueError(f"runtime package directory does not exist: {package_dir}")
    return {
        path.relative_to(root).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
        for path in sorted(package_dir.rglob("*.py"))
        if path.is_file()
    }


def load_module_size_baseline(path: Path) -> ModuleSizeBaseline:
    path = Path(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"module size baseline must be a mapping: {path}")
    package = str(payload.get("package") or "").strip()
    max_lines = int(payload.get("max_lines") or 0)
    if not package or max_lines <= 0:
        raise ValueError("module size baseline requires package and positive max_lines")
    allowed: list[AllowedOversizedModule] = []
    seen: set[str] = set()
    for raw in payload.get("allowlisted_modules") or []:
        if not isinstance(raw, dict):
            raise ValueError("allowlisted_modules entries must be mappings")
        item = AllowedOversizedModule(
            path=str(raw.get("path") or "").strip(),
            max_lines=int(raw.get("max_lines") or 0),
            owner=str(raw.get("owner") or "").strip(),
            reason=str(raw.get("reason") or "").strip(),
            remove_by=str(raw.get("remove_by") or "").strip(),
        )
        if not all((item.path, item.owner, item.reason, item.remove_by)) or item.max_lines <= max_lines:
            raise ValueError(f"invalid oversized module allowlist entry: {item.path or '<missing>'}")
        if item.path in seen:
            raise ValueError(f"duplicate oversized module allowlist path: {item.path}")
        if not item.path.startswith(f"{package}/") or not item.path.endswith(".py"):
            raise ValueError(f"allowlisted module must be a Python file under {package}: {item.path}")
        seen.add(item.path)
        allowed.append(item)
    return ModuleSizeBaseline(package=package, max_lines=max_lines, allowed=tuple(allowed))


def check_runtime_module_sizes(
    *,
    root: Path = ROOT,
    baseline_path: Path = DEFAULT_BASELINE,
) -> tuple[dict[str, int], list[ModuleSizeViolation]]:
    baseline = load_module_size_baseline(baseline_path)
    sizes = scan_runtime_module_sizes(root, package=baseline.package)
    allowed = {item.path: item for item in baseline.allowed}
    violations: list[ModuleSizeViolation] = []

    for path, line_count in sizes.items():
        if line_count <= baseline.max_lines:
            continue
        item = allowed.get(path)
        if item is None:
            violations.append(
                ModuleSizeViolation(
                    rule="unregistered_oversized_module",
                    path=path,
                    reason=f"{line_count} lines exceeds the {baseline.max_lines}-line runtime limit",
                )
            )
        elif line_count > item.max_lines:
            violations.append(
                ModuleSizeViolation(
                    rule="allowlisted_module_growth",
                    path=path,
                    reason=f"{line_count} lines exceeds its frozen {item.max_lines}-line budget",
                )
            )

    for path, item in allowed.items():
        line_count = sizes.get(path)
        if line_count is None:
            violations.append(ModuleSizeViolation("missing_allowlisted_module", path, "allowlisted runtime module does not exist"))
        elif line_count <= baseline.max_lines:
            violations.append(
                ModuleSizeViolation(
                    rule="stale_oversized_module_allowlist",
                    path=path,
                    reason=f"module is now {line_count} lines; remove it from the oversized allowlist",
                )
            )

    return sizes, sorted(violations, key=lambda item: (item.rule, item.path))


def _payload(sizes: dict[str, int], violations: list[ModuleSizeViolation], baseline: ModuleSizeBaseline) -> dict[str, Any]:
    oversized = {path: lines for path, lines in sizes.items() if lines > baseline.max_lines}
    return {
        "ok": not violations,
        "max_lines": baseline.max_lines,
        "runtime_python_file_count": len(sizes),
        "oversized_module_count": len(oversized),
        "oversized_modules": oversized,
        "violations": [item.to_dict() for item in violations],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce shrinking line-count budgets for oversized runtime Python modules.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    baseline = load_module_size_baseline(args.baseline)
    sizes, violations = check_runtime_module_sizes(root=args.root, baseline_path=args.baseline)
    payload = _payload(sizes, violations, baseline)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Runtime module sizes: "
            f"files={payload['runtime_python_file_count']} oversized={payload['oversized_module_count']} "
            f"limit={payload['max_lines']}"
        )
        for violation in violations:
            print(violation.format())
        if not violations:
            print("Runtime module size check OK")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
