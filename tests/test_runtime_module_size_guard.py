from __future__ import annotations

from pathlib import Path

import yaml

from tools.check_runtime_module_sizes import (
    ROOT,
    check_runtime_module_sizes,
    load_module_size_baseline,
    scan_runtime_module_sizes,
)


BASELINE = ROOT / "docs" / "architecture" / "runtime_module_size_baseline.yml"


def _write_fixture(tmp_path: Path, *, line_count: int, allowed_max: int | None = None) -> Path:
    package = tmp_path / "aicrm_next" / "sample"
    package.mkdir(parents=True)
    (package / "module.py").write_text("\n".join("pass" for _ in range(line_count)) + "\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "package": "aicrm_next",
        "max_lines": 5,
        "allowlisted_modules": [],
    }
    if allowed_max is not None:
        payload["allowlisted_modules"] = [
            {
                "path": "aicrm_next/sample/module.py",
                "max_lines": allowed_max,
                "owner": "architecture",
                "reason": "fixture oversized module",
                "remove_by": "2026-08-31",
            }
        ]
    baseline = tmp_path / "baseline.yml"
    baseline.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return baseline


def test_new_oversized_runtime_module_is_rejected(tmp_path: Path) -> None:
    baseline = _write_fixture(tmp_path, line_count=6)

    _, violations = check_runtime_module_sizes(root=tmp_path, baseline_path=baseline)

    assert [item.rule for item in violations] == ["unregistered_oversized_module"]


def test_allowlisted_module_cannot_grow(tmp_path: Path) -> None:
    baseline = _write_fixture(tmp_path, line_count=8, allowed_max=7)

    _, violations = check_runtime_module_sizes(root=tmp_path, baseline_path=baseline)

    assert [item.rule for item in violations] == ["allowlisted_module_growth"]


def test_allowlist_entry_must_be_removed_after_split(tmp_path: Path) -> None:
    baseline = _write_fixture(tmp_path, line_count=5, allowed_max=7)

    _, violations = check_runtime_module_sizes(root=tmp_path, baseline_path=baseline)

    assert [item.rule for item in violations] == ["stale_oversized_module_allowlist"]


def test_repository_runtime_module_size_baseline_matches_current_tree() -> None:
    baseline = load_module_size_baseline(BASELINE)
    sizes, violations = check_runtime_module_sizes(root=ROOT, baseline_path=BASELINE)
    oversized = {path for path, lines in sizes.items() if lines > baseline.max_lines}

    assert violations == []
    assert oversized == {item.path for item in baseline.allowed}
    assert len(oversized) == 0


def test_runtime_module_size_scan_is_deterministic() -> None:
    assert scan_runtime_module_sizes(ROOT) == scan_runtime_module_sizes(ROOT)
