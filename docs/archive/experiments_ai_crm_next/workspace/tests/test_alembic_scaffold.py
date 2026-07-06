from __future__ import annotations

from pathlib import Path


def test_alembic_scaffold_exists() -> None:
    assert Path("alembic.ini").exists()
    assert Path("migrations/env.py").exists()
    assert Path("migrations/versions/.gitkeep").exists()
