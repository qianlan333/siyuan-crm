from __future__ import annotations

from pathlib import Path

from tools.check_schema_change_templates import check_schema_change_templates


ROOT = Path(__file__).resolve().parents[1]


def test_schema_change_templates_current_repository_passes() -> None:
    assert check_schema_change_templates(
        migration_template=ROOT / "docs" / "development" / "schema_migration_template.md",
        pr_template=ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
    ) == []


def test_schema_change_templates_report_missing_required_fields(tmp_path: Path) -> None:
    migration_template = tmp_path / "schema_migration_template.md"
    pr_template = tmp_path / "PULL_REQUEST_TEMPLATE.md"
    migration_template.write_text("# incomplete\n", encoding="utf-8")
    pr_template.write_text("# incomplete\n", encoding="utf-8")

    violations = check_schema_change_templates(
        migration_template=migration_template,
        pr_template=pr_template,
    )

    missing = {violation.missing_token for violation in violations}
    assert "Lifecycle manifest entry" in missing
    assert "是否新增表" in missing
    assert "是否影响 material assets" in missing
