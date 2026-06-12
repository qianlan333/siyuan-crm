from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from scripts.script_runtime import REPO_ROOT
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import REPO_ROOT

ROOT = REPO_ROOT
PYTHON_TARGETS = [
    "scripts/run_lint.py",
    "scripts/run_typecheck.py",
    "scripts/script_runtime.py",
]
SCAN_ROOTS = [
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
