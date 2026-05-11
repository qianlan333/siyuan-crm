from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "wecom_ability_service/http/admin_console.py",
    "wecom_ability_service/domains/admin_dashboard/service.py",
    "wecom_ability_service/domains/admin_console/customer_profile_service.py",
    "wecom_ability_service/http/admin_customers.py",
    "wecom_ability_service/domains/admin_config/service.py",
    "wecom_ability_service/infra/settings.py",
    "scripts/run_lint.py",
    "scripts/run_typecheck.py",
    "scripts/run_build.py",
]


def main() -> int:
    command = [sys.executable, "-m", "mypy", "--config-file", str(ROOT / "pyproject.toml"), *TARGETS]
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
