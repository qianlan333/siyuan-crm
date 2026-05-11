from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_TARGETS = [
    "wecom_ability_service/db",
    "wecom_ability_service/infra/settings.py",
    "wecom_ability_service/domains/admin_config/service.py",
    "wecom_ability_service/domains/admin_dashboard/service.py",
    "wecom_ability_service/http/admin_console.py",
    "wecom_ability_service/domains/admin_console/customer_profile_service.py",
    "wecom_ability_service/http/admin_customers.py",
    "scripts/run_lint.py",
    "scripts/run_typecheck.py",
    "scripts/run_build.py",
]
SCAN_ROOTS = [
    ROOT / "wecom_ability_service",
    ROOT / "tests",
    ROOT / "scripts",
]
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".sql", ".toml"}
SKIP_DIR_NAMES = {".git", ".venv310", "__pycache__", ".pytest_cache", "node_modules"}


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_dir():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return files


def _custom_text_checks() -> list[str]:
    issues: list[str] = []
    for path in _iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("<<<<<<<") or stripped.startswith("=======") or stripped.startswith(">>>>>>>"):
                issues.append(f"{path.relative_to(ROOT)}:{line_no}: contains merge marker")
            if line.rstrip("\r\n") != line.rstrip():
                issues.append(f"{path.relative_to(ROOT)}:{line_no}: trailing whitespace")
            if "\t" in line and path.suffix.lower() in {".py", ".js", ".html", ".css"}:
                issues.append(f"{path.relative_to(ROOT)}:{line_no}: tab character")
    return issues


def _run_ruff() -> int:
    ruff_path = ROOT / ".venv310" / "bin" / "ruff"
    command = [str(ruff_path if ruff_path.exists() else "ruff"), "check", "--config", str(ROOT / "pyproject.toml"), *PYTHON_TARGETS]
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    text_issues = _custom_text_checks()
    if text_issues:
        print("custom lint failures:")
        for issue in text_issues:
            print(f"  - {issue}")
        return 1
    return _run_ruff()


if __name__ == "__main__":
    sys.exit(main())
