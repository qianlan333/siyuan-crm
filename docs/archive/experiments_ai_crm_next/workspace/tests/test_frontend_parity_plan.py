from __future__ import annotations

from pathlib import Path


def test_frontend_parity_plan_exists_and_requires_replication() -> None:
    path = Path("docs/frontend_parity_plan.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "The frontend is not being redesigned" in text
    assert "old AI-CRM frontend is the product baseline" in text
    assert "Do not change navigation information architecture" in text


def test_readme_prefers_local_venv_python_for_tests() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert ".venv/bin/python -m pytest -q" in text
