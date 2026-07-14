from __future__ import annotations

from pathlib import Path

from scripts.ops import recover_identity_resolution_worker_deadlock as recovery


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.queries: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.queries.append((query, tuple(params)))
        return _Cursor(self.rows.pop(0))


def _evidence(count: int, age: int = 0) -> dict[str, int]:
    return {"matching_deadlock_count": count, "oldest_blocker_age_seconds": age}


def test_deadlock_detector_is_limited_to_the_legacy_polling_claim_signature() -> None:
    conn = _Connection([_evidence(0)])

    result = recovery.collect_deadlock_evidence(conn, minimum_age_seconds=120)

    query, params = conn.queries[0]
    normalized = " ".join(query.lower().split())
    assert result == _evidence(0)
    assert "insert into crm_user_identity_resolution_queue" in normalized
    assert "update crm_user_identity_resolution_queue q" in normalized
    assert "set status = ''polling''" in normalized
    assert "idle in transaction" in normalized
    assert "for update skip locked" in normalized
    assert params == (120,)


def test_deadlock_recovery_is_noop_without_exact_match(tmp_path: Path) -> None:
    conn = _Connection([_evidence(0)])
    commands: list[list[str]] = []

    def runner(command: list[str]) -> str:
        commands.append(command)
        return "ActiveState=inactive\nSubState=dead\nMainPID=0\n"

    result = recovery.recover_deadlock(
        conn,
        execute=True,
        guard_file=tmp_path / "missing-guard",
        runner=runner,
    )

    assert result["ok"] is True
    assert result["recovery_required"] is False
    assert result["recovered"] is False
    assert not any(command[:3] == ["sudo", "systemctl", "stop"] for command in commands)


def test_deadlock_recovery_requires_deploy_guard_before_stopping_worker(tmp_path: Path) -> None:
    conn = _Connection([_evidence(1, 600)])
    commands: list[list[str]] = []

    def runner(command: list[str]) -> str:
        commands.append(command)
        return "ActiveState=activating\nSubState=start\nMainPID=1234\n"

    result = recovery.recover_deadlock(
        conn,
        execute=True,
        guard_file=tmp_path / "missing-guard",
        runner=runner,
    )

    assert result["ok"] is False
    assert result["reason"] == "deploy_transaction_guard_missing"
    assert not any(command[:3] == ["sudo", "systemctl", "stop"] for command in commands)


def test_deadlock_recovery_stops_only_active_worker_and_verifies_lock_release(tmp_path: Path) -> None:
    conn = _Connection([_evidence(1, 600), _evidence(0)])
    guard = tmp_path / "deploy-guard"
    guard.write_text("guarded", encoding="utf-8")
    commands: list[list[str]] = []
    stopped = False

    def runner(command: list[str]) -> str:
        nonlocal stopped
        commands.append(command)
        if command[:3] == ["sudo", "systemctl", "stop"]:
            stopped = True
            return ""
        if command[:3] == ["sudo", "systemctl", "reset-failed"]:
            return ""
        if stopped:
            return "ActiveState=inactive\nSubState=dead\nMainPID=0\n"
        return "ActiveState=activating\nSubState=start\nMainPID=1234\n"

    result = recovery.recover_deadlock(conn, execute=True, guard_file=guard, runner=runner)

    assert result["ok"] is True
    assert result["recovery_required"] is True
    assert result["recovered"] is True
    assert result["matching_deadlock_count_after"] == 0
    assert ["sudo", "systemctl", "stop", recovery.SERVICE] in commands
    assert ["sudo", "systemctl", "reset-failed", recovery.SERVICE] in commands
    assert result["pii_included"] is False
