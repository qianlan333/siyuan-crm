from __future__ import annotations

import ast
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = ("wecom_ability" + "_service", "openclaw_service")
ACTIVE_DUPLICATE_SOURCE_PATTERNS = (
    "PYTHONPATH=src",
    'pythonpath = ["src"]',
    "from src.aicrm_next",
    'PROJECT_ROOT / "src"',
    "SRC_ROOT",
)


def _python_import_offenders(package_dir: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(package_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_PREFIXES):
                        offenders.append(f"{path.relative_to(REPO_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(FORBIDDEN_PREFIXES):
                    offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module}")
    return offenders


def test_root_aicrm_next_is_default_runtime_source() -> None:
    app_py = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

    assert (REPO_ROOT / "aicrm_next" / "main.py").exists()
    assert not (REPO_ROOT / "legacy_flask_app.py").exists()
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in app_py
    assert "uvicorn.run(NEXT_APP_IMPORT" in app_py
    assert "run-legacy" in app_py


def test_experiments_does_not_keep_duplicate_next_source_package() -> None:
    duplicate_package = REPO_ROOT / "experiments" / "ai_crm_next" / "src" / "aicrm_next"

    assert not duplicate_package.exists()


def test_experiments_workspace_is_retired_stub_only() -> None:
    experiment_root = REPO_ROOT / "experiments" / "ai_crm_next"
    readme = (experiment_root / "README.md").read_text(encoding="utf-8")

    assert "no longer an active test or runtime workspace" in readme
    assert "docs/archive/experiments_ai_crm_next/" in readme
    for retired_child in ("docs", "tests", "tools", "scripts", "migrations"):
        assert not any((experiment_root / retired_child).rglob("*"))
    assert not (experiment_root / "pyproject.toml").exists()
    assert not (experiment_root / "alembic.ini").exists()


def test_duplicate_source_references_are_not_active_import_or_config_paths() -> None:
    allowed_files = {Path("tests/test_next_source_consolidation.py")}
    offenders: list[str] = []
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    for rel_text in tracked:
        rel = Path(rel_text)
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if rel in allowed_files:
            continue
        if path.suffix not in {".py", ".toml", ".sh", ".yml", ".yaml"}:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in ACTIVE_DUPLICATE_SOURCE_PATTERNS:
            if pattern in source:
                offenders.append(f"{rel} contains {pattern}")

    assert offenders == []


def test_shell_guard_blocks_duplicate_next_source_return() -> None:
    script = REPO_ROOT / "scripts" / "check_no_duplicate_next_source.sh"

    source = script.read_text(encoding="utf-8")
    assert "experiments/ai_crm_next/src/aicrm_next" in source
    assert "root aicrm_next/" in source
    subprocess.run(["bash", str(script)], cwd=REPO_ROOT, check=True, capture_output=True, text=True)


def test_root_next_does_not_import_d7_external_fallbacks() -> None:
    assert _python_import_offenders(REPO_ROOT / "aicrm_next") == []


def test_retired_production_compat_package_does_not_return() -> None:
    assert not (REPO_ROOT / "aicrm_next" / "production_compat").exists()
