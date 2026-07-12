#!/usr/bin/env python3
"""Build a validated pytest file-duration baseline from JUnit artifacts."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "docs" / "ci" / "pytest_duration_baseline.json"


def _test_modules(root: Path) -> dict[str, str]:
    return {
        path.with_suffix("").relative_to(root).as_posix().replace("/", "."): path.relative_to(root).as_posix()
        for path in root.glob("tests/**/test_*.py")
    }


def _resolve_test_file(classname: str, modules: dict[str, str]) -> str:
    candidates = [
        (len(module), file_path)
        for module, file_path in modules.items()
        if classname == module or classname.startswith(f"{module}.")
    ]
    if not candidates:
        raise ValueError("JUnit testcase references an unknown test module")
    return max(candidates)[1]


def build_duration_baseline(
    junit_paths: Sequence[Path],
    *,
    root: Path,
    source_run_id: int,
    source_sha: str,
) -> dict:
    if source_run_id <= 0:
        raise ValueError("source_run_id must be positive")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source_sha must be a lowercase 40-character Git SHA")
    if not junit_paths:
        raise ValueError("at least one JUnit XML file is required")

    modules = _test_modules(root)
    if not modules:
        raise ValueError("repository contains no pytest test files")
    item_counts: defaultdict[str, int] = defaultdict(int)
    duration_totals: defaultdict[str, float] = defaultdict(float)
    seen_testcases: set[tuple[str, str]] = set()
    for junit_path in junit_paths:
        for testcase in ET.parse(junit_path).iter("testcase"):
            classname = str(testcase.attrib.get("classname") or "")
            name = str(testcase.attrib.get("name") or "")
            testcase_key = (classname, name)
            if testcase_key in seen_testcases:
                raise ValueError("duplicate JUnit testcase across input artifacts")
            seen_testcases.add(testcase_key)
            file_path = _resolve_test_file(classname, modules)
            duration = float(testcase.attrib.get("time") or 0.0)
            if not math.isfinite(duration) or duration < 0:
                raise ValueError("JUnit testcase duration must be non-negative")
            item_counts[file_path] += 1
            duration_totals[file_path] += duration

    total_items = sum(item_counts.values())
    total_duration = sum(duration_totals.values())
    if total_items <= 0 or total_duration <= 0:
        raise ValueError("JUnit artifacts contain no positive timing evidence")
    files = {
        file_path: {
            "duration_seconds": round(duration_totals[file_path], 6),
            "items": item_counts[file_path],
        }
        for file_path in sorted(item_counts)
    }
    return {
        "version": 1,
        "source_run_id": source_run_id,
        "source_sha": source_sha,
        "fallback_seconds_per_item": round(total_duration / total_items, 6),
        "total_items": total_items,
        "total_duration_seconds": round(sum(entry["duration_seconds"] for entry in files.values()), 6),
        "files": files,
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary_path, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit-xml", type=Path, action="append", required=True)
    parser.add_argument("--source-run-id", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        baseline = build_duration_baseline(
            args.junit_xml,
            root=ROOT,
            source_run_id=args.source_run_id,
            source_sha=args.source_sha,
        )
        _write_json_atomic(args.output, baseline)
    except (ET.ParseError, OSError, ValueError):
        print(json.dumps({"error": "pytest duration baseline build failed", "ok": False}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "files": len(baseline["files"]),
                "items": baseline["total_items"],
                "ok": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
