from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COMMANDS = [
    ("lint", [sys.executable, "scripts/run_lint.py"]),
    ("typecheck", [sys.executable, "scripts/run_typecheck.py"]),
    ("build", [sys.executable, "scripts/run_build.py"]),
    ("customer_pulse_e2e", [sys.executable, "-m", "pytest", "-q", "tests/test_customer_pulse_inbox.py"]),
    ("customer_pulse_perf", [sys.executable, "-m", "pytest", "-q", "tests/test_customer_pulse_quality_gates.py"]),
]


def _run_step(label: str, command: list[str]) -> int:
    print(f"[customer-pulse-quality] running {label}: {' '.join(command)}")
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    for label, command in COMMANDS:
        exit_code = _run_step(label, command)
        if exit_code != 0:
            print(f"[customer-pulse-quality] step failed: {label}")
            return exit_code
    print("[customer-pulse-quality] all gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
