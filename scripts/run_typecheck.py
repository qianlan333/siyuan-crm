from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "wecom_ability_service/domains/customer_pulse/access.py",
    "wecom_ability_service/domains/customer_pulse/ai_recommendation.py",
    "wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py",
    "wecom_ability_service/domains/followup_orchestrator/service.py",
    "wecom_ability_service/domains/followup_orchestrator/repo.py",
    "wecom_ability_service/http/admin_customer_pulse.py",
    "wecom_ability_service/http/admin_followup_orchestrator.py",
    "wecom_ability_service/http/admin_console.py",
    "wecom_ability_service/domains/admin_dashboard/service.py",
    "wecom_ability_service/domains/admin_console/customer_profile_service.py",
    "wecom_ability_service/http/admin_customers.py",
    "wecom_ability_service/domains/admin_config/service.py",
    "wecom_ability_service/infra/settings.py",
    "scripts/run_lint.py",
    "scripts/run_typecheck.py",
    "scripts/run_build.py",
    "scripts/run_customer_pulse_quality_gates.py",
    "scripts/seed_customer_pulse_demo.py",
    "tests/test_customer_pulse_inbox.py",
    "tests/test_customer_pulse_quality_gates.py",
    "tests/test_followup_orchestrator_skeleton.py",
]


def main() -> int:
    command = [sys.executable, "-m", "mypy", "--config-file", str(ROOT / "pyproject.toml"), *TARGETS]
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
