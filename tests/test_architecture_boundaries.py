from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from tools.check_architecture_boundaries import check_boundaries, load_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(path: Path, *, allowlist: list[dict] | None = None) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "api_import_rules": {
                    "api_file_globs": ["aicrm_next/*/api.py"],
                    "api_semantic_imports": ["fastapi.APIRouter"],
                    "forbidden_cross_context_modules": ["repo", "service"],
                    "allowed_imports": [],
                },
                "forbidden_legacy_markers": [
                    "legacy_flask",
                    "openclaw_service",
                    "forward_to_legacy_flask",
                    "production_compat",
                ],
                "legacy_allowlist": allowlist or [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_architecture_boundary_allows_same_context_application_import(tmp_path) -> None:
    _write_config(tmp_path / "module_boundaries.yml")
    _write(tmp_path / "aicrm_next" / "alpha" / "api.py", "from aicrm_next.alpha.application import Query\n")

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert violations == []


def test_architecture_boundary_blocks_cross_context_repo_import(tmp_path) -> None:
    _write_config(tmp_path / "module_boundaries.yml")
    _write(tmp_path / "aicrm_next" / "alpha" / "api.py", "from aicrm_next.beta.repo import BetaRepo\n")

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert len(violations) == 1
    assert violations[0].rule == "api_cross_context_repo_service_import"
    assert "aicrm_next.beta.repo" in violations[0].reason
    assert violations[0].line == 1


def test_architecture_boundary_blocks_cross_context_repo_alias_import(tmp_path) -> None:
    _write_config(tmp_path / "module_boundaries.yml")
    _write(tmp_path / "aicrm_next" / "alpha" / "api.py", "from aicrm_next.beta import repo\n")

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert len(violations) == 1
    assert "aicrm_next.beta.repo" in violations[0].reason


def test_architecture_boundary_detects_semantic_api_router_files(tmp_path) -> None:
    _write_config(tmp_path / "module_boundaries.yml")
    _write(
        tmp_path / "aicrm_next" / "alpha" / "http.py",
        "from fastapi import APIRouter\nfrom aicrm_next.beta.repo import BetaRepo\nrouter = APIRouter()\n",
    )

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert len(violations) == 1
    assert violations[0].rule == "api_cross_context_repo_service_import"
    assert "aicrm_next.beta.repo" in violations[0].reason


def test_architecture_boundary_blocks_legacy_marker(tmp_path) -> None:
    _write_config(tmp_path / "module_boundaries.yml")
    _write(tmp_path / "aicrm_next" / "alpha" / "service.py", "RUNTIME = 'legacy_flask'\n")

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert len(violations) == 1
    assert violations[0].rule == "forbidden_legacy_marker"
    assert "legacy_flask" in violations[0].reason


def test_architecture_boundary_allows_precise_legacy_marker_allowlist(tmp_path) -> None:
    _write_config(
        tmp_path / "module_boundaries.yml",
        allowlist=[
            {
                "path": "aicrm_next/alpha/service.py",
                "rule": "forbidden_legacy_marker",
                "marker": "production_compat",
                "owner": "alpha",
                "reason": "Historical audit field only.",
                "matches": ['"production_compat_changed": False,'],
            }
        ],
    )
    _write(tmp_path / "aicrm_next" / "alpha" / "service.py", 'PAYLOAD = {\n        "production_compat_changed": False,\n}\n')

    violations = check_boundaries(root=tmp_path, config_path=tmp_path / "module_boundaries.yml")

    assert violations == []


def test_architecture_boundary_rejects_unowned_allowed_import(tmp_path) -> None:
    (tmp_path / "module_boundaries.yml").write_text(
        yaml.safe_dump(
            {
                "api_import_rules": {
                    "api_file_globs": ["aicrm_next/*/api.py"],
                    "forbidden_cross_context_modules": ["repo", "service"],
                    "allowed_imports": [
                        {
                            "path": "aicrm_next/alpha/api.py",
                            "module": "aicrm_next.beta.repo",
                        }
                    ],
                },
                "forbidden_legacy_markers": [],
                "legacy_allowlist": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="owner"):
        load_config(tmp_path / "module_boundaries.yml")
