from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MIGRATION_TEMPLATE = ROOT / "docs" / "development" / "schema_migration_template.md"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"

MIGRATION_REQUIRED_TOKENS = (
    "Lifecycle manifest entry",
    "Capability owner",
    "Business key",
    "PII level",
    "Read path",
    "Write path",
    "Repository ownership",
    "Rollback note",
    "Fresh DB test",
    "docs/architecture/data_table_lifecycle_manifest.yml",
    "docs/architecture/repository_ownership.yml",
    "tools/check_data_table_lifecycle.py",
    "tools/check_sql_static_guard.py",
    "tools/check_repository_ownership.py",
    "bash scripts/ci/run_architecture_gates.sh",
)

PR_REQUIRED_TOKENS = (
    "## schema_change_checklist",
    "是否新增表",
    "是否删除表",
    "是否变更业务主键",
    "是否影响 unionid",
    "是否影响 external effect",
    "是否影响 payment / notification",
    "是否影响 material assets",
    "docs/development/schema_migration_template.md",
)


@dataclass(frozen=True)
class TemplateViolation:
    path: Path
    missing_token: str

    def format(self) -> str:
        return f"{self.path}: missing required schema-change template token: {self.missing_token}"


def check_schema_change_templates(
    *,
    migration_template: Path = MIGRATION_TEMPLATE,
    pr_template: Path = PR_TEMPLATE,
) -> list[TemplateViolation]:
    violations: list[TemplateViolation] = []
    violations.extend(_missing_tokens(migration_template, MIGRATION_REQUIRED_TOKENS))
    violations.extend(_missing_tokens(pr_template, PR_REQUIRED_TOKENS))
    return violations


def _missing_tokens(path: Path, tokens: tuple[str, ...]) -> list[TemplateViolation]:
    if not path.exists():
        return [TemplateViolation(path=path, missing_token="<file missing>")]

    content = path.read_text(encoding="utf-8")
    return [
        TemplateViolation(path=path, missing_token=token)
        for token in tokens
        if token not in content
    ]


def main() -> int:
    violations = check_schema_change_templates()
    if not violations:
        print("schema change templates: ok")
        return 0

    for violation in violations:
        print(violation.format())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
