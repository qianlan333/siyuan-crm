from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.build_pytest_duration_baseline import build_duration_baseline


def _write_junit(path: Path, body: str) -> None:
    path.write_text(f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>', encoding="utf-8")


def test_builder_aggregates_testcase_time_by_repository_file(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (tests_dir / "test_beta.py").write_text("def test_two(): pass\n", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    _write_junit(
        junit,
        """
        <testcase classname="tests.test_alpha" name="test_one" time="1.25" />
        <testcase classname="tests.test_alpha.TestThing" name="test_two" time="2.75" />
        <testcase classname="tests.test_beta" name="test_three" time="6.00" />
        """,
    )

    baseline = build_duration_baseline(
        [junit],
        root=tmp_path,
        source_run_id=123,
        source_sha="a" * 40,
    )

    assert baseline["total_items"] == 3
    assert baseline["total_duration_seconds"] == 10.0
    assert baseline["fallback_seconds_per_item"] == pytest.approx(10 / 3, abs=1e-6)
    assert baseline["files"] == {
        "tests/test_alpha.py": {"duration_seconds": 4.0, "items": 2},
        "tests/test_beta.py": {"duration_seconds": 6.0, "items": 1},
    }


def test_builder_rejects_unknown_or_duplicate_testcases(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text("def test_one(): pass\n", encoding="utf-8")
    unknown = tmp_path / "unknown.xml"
    _write_junit(unknown, '<testcase classname="tests.test_missing" name="test_one" time="1.0" />')

    with pytest.raises(ValueError, match="unknown test module"):
        build_duration_baseline([unknown], root=tmp_path, source_run_id=123, source_sha="a" * 40)

    duplicate = tmp_path / "duplicate.xml"
    _write_junit(
        duplicate,
        """
        <testcase classname="tests.test_alpha" name="test_one" time="1.0" />
        <testcase classname="tests.test_alpha" name="test_one" time="1.0" />
        """,
    )
    with pytest.raises(ValueError, match="duplicate JUnit testcase"):
        build_duration_baseline([duplicate], root=tmp_path, source_run_id=123, source_sha="a" * 40)
