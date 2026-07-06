from __future__ import annotations

from scripts.ops import check_wecom_callback_rollback_evidence as rollback


def _payload(*, ok: bool = True) -> dict:
    return {
        "ok": ok,
        "production_rollback_drill": ok,
        "rollback_ready": ok,
        "backup_path": "/etc/nginx/sites-enabled/youcangogogo.conf.bak-codex-callback-cutover-20260627T120000",
        "backup_exists": ok,
        "nginx_test_after_restore_ok": ok,
        "nginx_reload_after_restore_ok": ok,
        "web_health_after_restore": {"ok": ok, "status_code": 200 if ok else 503},
        "quick_ack_after_restore": {"ok": ok, "emergency_quick_ack_enabled": ok},
        "cutover_reapplied_after_drill": ok,
    }


def test_rollback_evidence_accepts_complete_production_drill_payload() -> None:
    payload = rollback.evaluate_rollback_evidence(_payload())

    assert payload["ok"] is True
    assert payload["production_rollback_drill"] is True
    assert payload["rollback_ready"] is True
    assert payload["backup_exists"] is True
    assert payload["quick_ack_after_restore"]["emergency_quick_ack_enabled"] is True
    assert payload["cutover_reapplied_after_drill"] is True


def test_rollback_evidence_rejects_missing_drill_or_restore_proof() -> None:
    bad = _payload()
    bad["production_rollback_drill"] = False
    bad["quick_ack_after_restore"] = {"ok": True, "emergency_quick_ack_enabled": False}
    bad["cutover_reapplied_after_drill"] = False

    payload = rollback.evaluate_rollback_evidence(bad)

    assert payload["ok"] is False
    assert "production_rollback_drill is not true" in payload["violations"]
    assert "quick_ack_after_restore.emergency_quick_ack_enabled is not true" in payload["violations"]
    assert "cutover_reapplied_after_drill is not true" in payload["violations"]


def test_rollback_evidence_template_is_marked_as_production_drill_shape() -> None:
    payload = rollback.run(["--print-template"])

    assert payload["ok"] is True
    assert payload["production_rollback_drill"] is True
    assert payload["quick_ack_after_restore"]["emergency_quick_ack_enabled"] is True
