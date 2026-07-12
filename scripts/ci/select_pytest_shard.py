#!/usr/bin/env python3
"""Select one deterministic, file-preserving pytest shard for CI."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DURATION_BASELINE = ROOT / "docs" / "ci" / "pytest_duration_baseline.json"


@dataclass(frozen=True)
class FileDuration:
    items: int
    duration_seconds: float


@dataclass(frozen=True)
class DurationBaseline:
    fallback_seconds_per_item: float
    files: dict[str, FileDuration]


@dataclass(frozen=True)
class ShardSelection:
    index: int
    files: tuple[str, ...]
    item_count: int
    estimated_seconds: float


def parse_collected_nodeids(output: str) -> list[str]:
    """Return pytest node IDs from quiet collection output."""

    nodeids: list[str] = []
    for raw_line in output.splitlines():
        nodeid = raw_line.strip()
        if not nodeid.startswith("tests/") or "::" not in nodeid:
            continue
        file_path = nodeid.split("::", 1)[0]
        if not file_path.endswith(".py"):
            continue
        nodeids.append(nodeid)
    return nodeids


def _validated_nodeids(nodeids: Iterable[str]) -> list[str]:
    normalized = sorted(str(nodeid).strip() for nodeid in nodeids if str(nodeid).strip())
    if not normalized:
        raise ValueError("no pytest node IDs were collected")
    duplicates = [nodeid for nodeid, count in Counter(normalized).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate pytest node ID: {duplicates[0]}")
    for nodeid in normalized:
        file_path, separator, _ = nodeid.partition("::")
        if not separator or not file_path.startswith("tests/") or not file_path.endswith(".py"):
            raise ValueError(f"invalid pytest node ID: {nodeid}")
    return normalized


def load_duration_baseline(path: Path) -> DurationBaseline:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("duration baseline must use version 1")
    source_run_id = data.get("source_run_id")
    if not isinstance(source_run_id, int) or isinstance(source_run_id, bool) or source_run_id <= 0:
        raise ValueError("duration baseline source_run_id must be a positive integer")
    source_sha = data.get("source_sha")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("duration baseline source_sha must be a lowercase 40-character Git SHA")
    try:
        fallback = float(data.get("fallback_seconds_per_item") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration baseline fallback_seconds_per_item must be numeric") from exc
    if not math.isfinite(fallback) or fallback <= 0:
        raise ValueError("duration baseline fallback_seconds_per_item must be positive")
    raw_files = data.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise ValueError("duration baseline files must be a non-empty mapping")

    files: dict[str, FileDuration] = {}
    for file_path, raw_entry in raw_files.items():
        if not isinstance(file_path, str) or not file_path.startswith("tests/") or not file_path.endswith(".py"):
            raise ValueError("duration baseline contains an invalid test file path")
        if not isinstance(raw_entry, dict):
            raise ValueError("duration baseline file entry must be a mapping")
        items = raw_entry.get("items")
        try:
            duration = float(raw_entry.get("duration_seconds") or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("duration baseline file duration_seconds must be numeric") from exc
        if not isinstance(items, int) or isinstance(items, bool) or items <= 0:
            raise ValueError("duration baseline file items must be positive integers")
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("duration baseline file duration_seconds must be non-negative")
        files[file_path] = FileDuration(items=items, duration_seconds=duration)

    total_items = data.get("total_items")
    if not isinstance(total_items, int) or isinstance(total_items, bool) or total_items != sum(entry.items for entry in files.values()):
        raise ValueError("duration baseline total_items does not match file entries")
    try:
        total_duration = float(data.get("total_duration_seconds") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration baseline total_duration_seconds must be numeric") from exc
    file_duration_total = sum(entry.duration_seconds for entry in files.values())
    if not math.isfinite(total_duration) or not math.isclose(
        total_duration,
        file_duration_total,
        rel_tol=1e-6,
        abs_tol=0.01,
    ):
        raise ValueError("duration baseline total_duration_seconds does not match file entries")
    return DurationBaseline(fallback_seconds_per_item=fallback, files=files)


def _estimated_file_seconds(
    file_path: str,
    item_count: int,
    duration_baseline: DurationBaseline | None,
) -> float:
    if duration_baseline is None:
        return float(item_count)
    baseline = duration_baseline.files.get(file_path)
    if baseline is None:
        return duration_baseline.fallback_seconds_per_item * item_count
    return baseline.duration_seconds * item_count / baseline.items


def partition_nodeids_by_file(
    nodeids: Iterable[str],
    *,
    shard_total: int,
    duration_baseline: DurationBaseline | None = None,
) -> tuple[ShardSelection, ...]:
    """Greedily balance estimated duration without splitting test files."""

    if shard_total <= 0:
        raise ValueError("shard_total must be positive")
    normalized = _validated_nodeids(nodeids)
    file_counts = Counter(nodeid.split("::", 1)[0] for nodeid in normalized)
    if len(file_counts) < shard_total:
        raise ValueError("shard_total exceeds the number of collected test files")

    shard_files: list[list[str]] = [[] for _ in range(shard_total)]
    shard_item_counts = [0 for _ in range(shard_total)]
    file_estimates = {
        file_path: _estimated_file_seconds(file_path, item_count, duration_baseline)
        for file_path, item_count in file_counts.items()
    }
    shard_estimated_seconds = [0.0 for _ in range(shard_total)]
    for file_path, item_count in sorted(
        file_counts.items(),
        key=lambda item: (-file_estimates[item[0]], -item[1], item[0]),
    ):
        shard_index = min(
            range(shard_total),
            key=lambda index: (
                shard_estimated_seconds[index],
                shard_item_counts[index],
                len(shard_files[index]),
                index,
            ),
        )
        shard_files[shard_index].append(file_path)
        shard_item_counts[shard_index] += item_count
        shard_estimated_seconds[shard_index] += file_estimates[file_path]

    return tuple(
        ShardSelection(
            index=index,
            files=tuple(sorted(shard_files[index])),
            item_count=shard_item_counts[index],
            estimated_seconds=round(shard_estimated_seconds[index], 3),
        )
        for index in range(shard_total)
    )


def select_shard(
    nodeids: Iterable[str],
    *,
    shard_index: int,
    shard_total: int,
    duration_baseline: DurationBaseline | None = None,
) -> tuple[ShardSelection, ...]:
    if shard_total <= 0:
        raise ValueError("shard_total must be positive")
    if shard_index < 0 or shard_index >= shard_total:
        raise ValueError("shard_index must be within [0, shard_total)")
    shards = partition_nodeids_by_file(
        nodeids,
        shard_total=shard_total,
        duration_baseline=duration_baseline,
    )
    if not shards[shard_index].files:
        raise ValueError(f"pytest shard {shard_index} is empty")
    return shards


def collect_pytest_nodeids() -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--collect-only",
        "-q",
        "--disable-warnings",
        "--color=no",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        diagnostic = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines()[-40:])
        raise RuntimeError(f"pytest collection failed with exit code {completed.returncode}:\n{diagnostic}")
    nodeids = parse_collected_nodeids(completed.stdout)
    if not nodeids:
        raise RuntimeError("pytest collection succeeded but returned no test node IDs")
    return nodeids


def _write_selected_files(path: Path, files: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        handle.write("\n".join(files))
        handle.write("\n")
    os.replace(temporary_path, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-total", type=int, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--duration-baseline", type=Path, default=DEFAULT_DURATION_BASELINE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        nodeids = collect_pytest_nodeids()
        duration_baseline = load_duration_baseline(args.duration_baseline)
        shards = select_shard(
            nodeids,
            shard_index=args.shard_index,
            shard_total=args.shard_total,
            duration_baseline=duration_baseline,
        )
        selected = shards[args.shard_index]
        _write_selected_files(args.output_file, selected.files)
    except (OSError, RuntimeError, ValueError):
        print(json.dumps({"error": "pytest shard selection failed", "ok": False}, sort_keys=True), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "selected_files": len(selected.files),
                "selected_items": selected.item_count,
                "shard_index": selected.index,
                "shard_estimated_seconds": [shard.estimated_seconds for shard in shards],
                "shard_item_counts": [shard.item_count for shard in shards],
                "shard_total": len(shards),
                "total_files": sum(len(shard.files) for shard in shards),
                "total_items": len(nodeids),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
