from __future__ import annotations

import subprocess
import sys


def test_channel_entry_next_owner_checker_passes():
    result = subprocess.run([sys.executable, "tools/check_channel_entry_next_owner.py"], text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "channel_entry_next_owner: ok" in result.stdout

