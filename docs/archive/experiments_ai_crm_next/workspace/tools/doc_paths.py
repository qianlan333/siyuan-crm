from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
ACTIVE_DOCS_ROOT = PROJECT_ROOT / "docs"
ARCHIVED_DOCS_ROOT = REPO_ROOT / "docs" / "archive" / "experiments_ai_crm_next" / "docs"


def experiment_doc_path(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute():
        return candidate
    if len(candidate.parts) > 1:
        if candidate.parts[:2] == ("docs", "archive"):
            return REPO_ROOT / candidate
        if candidate.parts[0] == "docs":
            return PROJECT_ROOT / candidate
    archived = ARCHIVED_DOCS_ROOT / name
    if archived.exists():
        return archived
    return ACTIVE_DOCS_ROOT / name


def read_experiment_doc(name: str) -> str:
    return experiment_doc_path(name).read_text(encoding="utf-8")
