from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import select_pytest_shard


def _nodeids() -> list[str]:
    weights = {
        "tests/test_alpha.py": 5,
        "tests/test_beta.py": 4,
        "tests/test_gamma.py": 3,
        "tests/test_delta.py": 2,
        "tests/test_epsilon.py": 1,
        "tests/test_zeta.py": 1,
    }
    return [f"{path}::test_case_{index}" for path, count in weights.items() for index in range(count)]


def _write_baseline(path: Path) -> None:
    weights = {
        "tests/test_alpha.py": 5,
        "tests/test_beta.py": 4,
        "tests/test_gamma.py": 3,
        "tests/test_delta.py": 2,
        "tests/test_epsilon.py": 1,
        "tests/test_zeta.py": 1,
    }
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_run_id": 123,
                "source_sha": "a" * 40,
                "fallback_seconds_per_item": 1.0,
                "total_items": sum(weights.values()),
                "total_duration_seconds": float(sum(weights.values())),
                "files": {
                    file_path: {"duration_seconds": float(items), "items": items}
                    for file_path, items in weights.items()
                },
            }
        ),
        encoding="utf-8",
    )


def test_parse_collected_nodeids_keeps_only_test_nodes() -> None:
    output = """
tests/test_alpha.py::test_one
tests/nested/test_beta.py::TestThing::test_two[param]

2 tests collected in 0.42s
"""

    assert select_pytest_shard.parse_collected_nodeids(output) == [
        "tests/test_alpha.py::test_one",
        "tests/nested/test_beta.py::TestThing::test_two[param]",
    ]


def test_partition_is_deterministic_exhaustive_disjoint_and_file_preserving() -> None:
    nodeids = _nodeids()

    forward = select_pytest_shard.partition_nodeids_by_file(nodeids, shard_total=3)
    reverse = select_pytest_shard.partition_nodeids_by_file(list(reversed(nodeids)), shard_total=3)

    assert forward == reverse
    assert [shard.item_count for shard in forward] == [6, 5, 5]
    all_files = [path for shard in forward for path in shard.files]
    assert len(all_files) == len(set(all_files))
    assert set(all_files) == {nodeid.split("::", 1)[0] for nodeid in nodeids}
    assert sum(shard.item_count for shard in forward) == len(nodeids)


def test_partition_balance_is_bounded_by_largest_file() -> None:
    shards = select_pytest_shard.partition_nodeids_by_file(_nodeids(), shard_total=3)
    counts = [shard.item_count for shard in shards]

    assert max(counts) - min(counts) <= 5


def test_duration_weighting_separates_slow_files_and_reports_estimates() -> None:
    nodeids = [
        "tests/test_alpha.py::test_one",
        "tests/test_beta.py::test_one",
        "tests/test_gamma.py::test_one",
        "tests/test_delta.py::test_one",
    ]
    baseline = select_pytest_shard.DurationBaseline(
        fallback_seconds_per_item=1.0,
        files={
            "tests/test_alpha.py": select_pytest_shard.FileDuration(items=1, duration_seconds=100.0),
            "tests/test_beta.py": select_pytest_shard.FileDuration(items=1, duration_seconds=90.0),
            "tests/test_gamma.py": select_pytest_shard.FileDuration(items=1, duration_seconds=10.0),
            "tests/test_delta.py": select_pytest_shard.FileDuration(items=1, duration_seconds=10.0),
        },
    )

    shards = select_pytest_shard.partition_nodeids_by_file(
        nodeids,
        shard_total=2,
        duration_baseline=baseline,
    )

    file_locations = {file_path: shard.index for shard in shards for file_path in shard.files}
    assert file_locations["tests/test_alpha.py"] != file_locations["tests/test_beta.py"]
    assert [shard.estimated_seconds for shard in shards] == [110.0, 100.0]


def test_duration_baseline_loader_rejects_inconsistent_totals(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    _write_baseline(baseline_path)
    baseline = select_pytest_shard.load_duration_baseline(baseline_path)

    assert baseline.fallback_seconds_per_item == 1.0
    assert baseline.files["tests/test_alpha.py"].items == 5

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    payload["total_items"] += 1
    baseline_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="total_items"):
        select_pytest_shard.load_duration_baseline(baseline_path)


def test_checked_in_duration_baseline_is_valid() -> None:
    baseline_path = select_pytest_shard.ROOT / "docs" / "ci" / "pytest_duration_baseline.json"

    baseline = select_pytest_shard.load_duration_baseline(baseline_path)

    assert baseline.fallback_seconds_per_item > 0
    assert len(baseline.files) >= 400


@pytest.mark.parametrize(
    ("shard_index", "shard_total"),
    [(-1, 3), (3, 3), (0, 0), (0, -1)],
)
def test_select_shard_rejects_invalid_bounds(shard_index: int, shard_total: int) -> None:
    with pytest.raises(ValueError):
        select_pytest_shard.select_shard(_nodeids(), shard_index=shard_index, shard_total=shard_total)


def test_partition_rejects_empty_or_duplicate_collection() -> None:
    with pytest.raises(ValueError, match="no pytest node IDs"):
        select_pytest_shard.partition_nodeids_by_file([], shard_total=3)

    with pytest.raises(ValueError, match="duplicate pytest node ID"):
        select_pytest_shard.partition_nodeids_by_file(
            ["tests/test_alpha.py::test_one", "tests/test_alpha.py::test_one"],
            shard_total=3,
        )


def test_cli_writes_selected_files_and_machine_readable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "selected-files.txt"
    baseline_path = tmp_path / "baseline.json"
    _write_baseline(baseline_path)
    monkeypatch.setattr(select_pytest_shard, "collect_pytest_nodeids", lambda: _nodeids())

    exit_code = select_pytest_shard.main(
        [
            "--shard-index",
            "1",
            "--shard-total",
            "3",
            "--output-file",
            str(output_path),
            "--duration-baseline",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "ok": True,
        "selected_files": 2,
        "selected_items": 5,
        "shard_index": 1,
        "shard_estimated_seconds": [6.0, 5.0, 5.0],
        "shard_item_counts": [6, 5, 5],
        "shard_total": 3,
        "total_files": 6,
        "total_items": 16,
    }
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "tests/test_beta.py",
        "tests/test_epsilon.py",
    ]


def test_cli_failure_is_fixed_and_does_not_echo_collection_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "selected-files.txt"
    baseline_path = tmp_path / "baseline.json"
    _write_baseline(baseline_path)
    monkeypatch.setattr(
        select_pytest_shard,
        "collect_pytest_nodeids",
        lambda: (_ for _ in ()).throw(RuntimeError("unsafe node detail")),
    )

    exit_code = select_pytest_shard.main(
        [
            "--shard-index",
            "0",
            "--shard-total",
            "3",
            "--output-file",
            str(output_path),
            "--duration-baseline",
            str(baseline_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {"error": "pytest shard selection failed", "ok": False}
    assert "unsafe node detail" not in captured.err
    assert not output_path.exists()
