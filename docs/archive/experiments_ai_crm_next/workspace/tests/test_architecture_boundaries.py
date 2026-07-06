from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_PREFIXES = ("wecom_ability_service", "openclaw_service")
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_next_project_does_not_import_old_backend_packages() -> None:
    root = REPO_ROOT / "aicrm_next"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_PREFIXES):
                        offenders.append(f"{path}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(FORBIDDEN_PREFIXES):
                    offenders.append(f"{path}:{module}")
    assert offenders == []
