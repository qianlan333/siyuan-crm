from __future__ import annotations

import json
from time import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.shared.db_session import get_engine


def _admin_cookies() -> dict[str, str]:
    return {
        SESSION_COOKIE: sign_session(
            {
                "auth_source": "pytest",
                "login_type": "pytest",
                "username": "draft-api-admin",
                "display_name": "Draft API Admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def _payload(*, idempotency_key: str = "draft-api-idem-1", source_plan_id: str = "plan-safe-1") -> dict:
    return {
        "idempotency_key": idempotency_key,
        "source_plan_id": source_plan_id,
        "sanitized_payload": {
            "workspace": "p1_group_ops_workspace",
            "selected_count": 1,
            "preview_only": True,
        },
        "guardrail_summary": {
            "requires_approval": True,
            "requires_allowlist": True,
            "requires_gray_window": True,
            "no_direct_send": True,
            "no_external_call": True,
        },
        "approval_requirements": {
            "approval_required": True,
            "allowlist_required": True,
            "gray_window_required": True,
        },
        "items": [
            {
                "item_type": "plan",
                "item_ref_id": source_plan_id,
                "item_order": 0,
                "sanitized_item": {"title": "Safe plan reference", "status": "draft_preview"},
                "guardrail_summary": {"no_direct_send": True},
            }
        ],
    }


def _request_review_payload(
    *,
    version: int,
    idempotency_key: str = "request-review-idem-1",
    client_snapshot_hash: str = "",
    review_note: str = "safe review note",
) -> dict:
    payload = {
        "version": version,
        "idempotency_key": idempotency_key,
        "review_note": review_note,
    }
    if client_snapshot_hash:
        payload["client_snapshot_hash"] = client_snapshot_hash
    return payload


def _count(table: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() or 0)


def _audit_rows(draft_id: str) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT action, actor_id, version, snapshot_hash,
                       before_metadata_json, after_metadata_json
                FROM group_ops_workspace_draft_audit_logs
                WHERE draft_id = :draft_id
                ORDER BY id ASC
                """
            ),
            {"draft_id": draft_id},
        ).fetchall()
        return [dict(row._mapping) for row in rows]


def _assert_non_execution_response(payload: dict) -> None:
    assert payload["preview_only"] is True
    assert payload["real_external_call"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["push_center_job_created"] is False
    assert payload["external_effect_job_created"] is False
    assert payload["broadcast_job_created"] is False
    assert payload["internal_event_created"] is False
    assert payload["can_claim_pass_90_plus"] is False
    assert payload["execution_status"] == "not_execution"
    assert payload.get("approved") is False
    assert payload.get("draft_status") not in {"sent", "completed"}


def test_group_ops_workspace_draft_write_apis_fail_closed_without_admin_cookie(
    next_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    create = next_client.post("/api/admin/p1/group-ops-workspace/drafts", json=_payload())
    update = next_client.patch("/api/admin/p1/group-ops-workspace/drafts/gowd_missing", json={**_payload(), "version": 1})
    archive = next_client.post("/api/admin/p1/group-ops-workspace/drafts/gowd_missing/archive", json={"version": 1})
    request_review = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts/gowd_missing/request-review",
        json=_request_review_payload(version=1),
    )

    for response in [create, update, archive, request_review]:
        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "admin_auth_required"
        assert payload["real_external_call_executed"] is False


def test_group_ops_workspace_draft_request_review_route_requires_admin_cookie(
    next_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    response = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts/gowd_safe/request-review",
        json=_request_review_payload(version=1),
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"] == "admin_auth_required"
    assert payload["real_external_call_executed"] is False


def test_group_ops_workspace_create_draft_writes_only_draft_tables_and_audit(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    before = {
        "drafts": _count("group_ops_workspace_drafts"),
        "items": _count("group_ops_workspace_draft_items"),
        "audit": _count("group_ops_workspace_draft_audit_logs"),
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
    }

    response = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="create-safe"),
        cookies=_admin_cookies(),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["operation"] == "create"
    assert payload["production_write"] is True
    assert payload["production_write_scope"] == "draft_tables_only"
    assert payload["draft_status"] == "draft"
    assert payload["version"] == 1
    assert payload["items"][0]["item_type"] == "plan"
    _assert_non_execution_response(payload)

    assert _count("group_ops_workspace_drafts") == before["drafts"] + 1
    assert _count("group_ops_workspace_draft_items") == before["items"] + 1
    assert _count("group_ops_workspace_draft_audit_logs") == before["audit"] + 1
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]

    audit = _audit_rows(payload["draft_id"])
    assert len(audit) == 1
    assert audit[0]["action"] == "create"
    assert audit[0]["actor_id"] == "draft-api-admin"
    assert audit[0]["snapshot_hash"]
    assert "Safe plan reference" not in json.dumps(audit, ensure_ascii=False)


def test_group_ops_workspace_create_draft_idempotency_replays_same_payload_and_conflicts_on_changed_payload(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    payload = _payload(idempotency_key="same-key")

    first = next_client.post("/api/admin/p1/group-ops-workspace/drafts", json=payload, cookies=cookies)
    second = next_client.post("/api/admin/p1/group-ops-workspace/drafts", json=payload, cookies=cookies)
    changed = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json={**payload, "source_plan_id": "plan-safe-changed"},
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert changed.status_code == 409, changed.text
    assert first.json()["draft_id"] == second.json()["draft_id"]
    assert second.json()["idempotent_replay"] is True
    assert second.json()["production_write"] is False
    assert _count("group_ops_workspace_drafts") == 1
    assert _count("group_ops_workspace_draft_audit_logs") == 1


def test_group_ops_workspace_update_requires_current_version_and_writes_audit(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="update-key"),
        cookies=cookies,
    ).json()

    update_payload = {
        **_payload(idempotency_key="update-key-v2", source_plan_id="plan-safe-2"),
        "version": created["version"],
    }
    updated = next_client.patch(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}",
        json=update_payload,
        cookies=cookies,
    )
    stale = next_client.patch(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}",
        json={**update_payload, "source_plan_id": "plan-safe-3"},
        cookies=cookies,
    )

    assert updated.status_code == 200, updated.text
    assert stale.status_code == 409, stale.text
    payload = updated.json()
    assert payload["version"] == 2
    assert payload["source_plan_id"] == "plan-safe-2"
    assert payload["production_write"] is True
    _assert_non_execution_response(payload)
    assert [row["action"] for row in _audit_rows(created["draft_id"])] == ["create", "update"]


def test_group_ops_workspace_archive_marks_archived_and_writes_audit(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="archive-key"),
        cookies=cookies,
    ).json()

    archived = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}/archive",
        json={"version": created["version"], "archive_reason": "safe test archive"},
        cookies=cookies,
    )

    assert archived.status_code == 200, archived.text
    payload = archived.json()
    assert payload["draft_status"] == "archived"
    assert payload["archived_at"]
    assert payload["production_write"] is True
    _assert_non_execution_response(payload)
    assert [row["action"] for row in _audit_rows(created["draft_id"])] == ["create", "archive"]


def test_group_ops_workspace_draft_api_rejects_sensitive_fields_and_values(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    sensitive_key = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json={**_payload(idempotency_key="sensitive-key"), "sanitized_payload": {"raw_external_userid": "wm_unsafe"}},
        cookies=cookies,
    )
    sensitive_value = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json={
            **_payload(idempotency_key="sensitive-value"),
            "items": [
                {
                    "item_type": "group",
                    "item_ref_id": "group-safe",
                    "sanitized_item": {"summary": "call 13800138000"},
                }
            ],
        },
        cookies=cookies,
    )

    assert sensitive_key.status_code == 400
    assert sensitive_value.status_code == 400
    assert "sensitive" in sensitive_key.json()["detail"]
    assert "sensitive" in sensitive_value.json()["detail"]
    assert _count("group_ops_workspace_drafts") == 0


def test_group_ops_workspace_draft_api_does_not_implement_review_or_execution_routes(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="no-review-key"),
        cookies=cookies,
    ).json()

    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_group_ops_workspace_draft_api_does_not_break_legacy_group_ops_read_routes(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    response = next_client.get("/api/admin/automation-conversion/group-ops/plans?limit=1")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_group_ops_workspace_request_review_marks_ready_and_writes_audit_without_execution(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="review-key"),
        cookies=cookies,
    ).json()
    before = {
        "audit": _count("group_ops_workspace_draft_audit_logs"),
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
    }

    reviewed = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}/request-review",
        json=_request_review_payload(
            version=created["version"],
            idempotency_key="review-ready-key",
            client_snapshot_hash=created["snapshot_hash"],
        ),
        cookies=cookies,
    )

    assert reviewed.status_code == 200, reviewed.text
    payload = reviewed.json()
    assert payload["operation"] == "request_review"
    assert payload["draft_status"] == "ready_for_review"
    assert payload["ready_for_review"] is True
    assert payload["approved"] is False
    assert payload["version"] == 2
    assert payload["production_write"] is True
    _assert_non_execution_response(payload)
    assert _count("group_ops_workspace_draft_audit_logs") == before["audit"] + 1
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]

    audit = _audit_rows(created["draft_id"])
    assert [row["action"] for row in audit] == ["create", "request_review"]
    assert audit[-1]["actor_id"] == "draft-api-admin"
    assert audit[-1]["version"] == 2
    after = audit[-1]["after_metadata_json"]
    assert after["request_review_idempotency_key"] == "review-ready-key"
    assert after["approved"] is False
    assert after["push_center_job_created"] is False
    assert "safe review note" not in json.dumps(audit, ensure_ascii=False)


def test_group_ops_workspace_request_review_idempotency_replays_same_payload_and_conflicts_changed_payload(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="review-idem-create"),
        cookies=cookies,
    ).json()
    request_payload = _request_review_payload(
        version=created["version"],
        idempotency_key="request-review-same-key",
        client_snapshot_hash=created["snapshot_hash"],
    )

    first = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}/request-review",
        json=request_payload,
        cookies=cookies,
    )
    replay = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}/request-review",
        json=request_payload,
        cookies=cookies,
    )
    changed = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created['draft_id']}/request-review",
        json={**request_payload, "review_note": "changed safe review note"},
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert changed.status_code == 409, changed.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    assert replay.json()["draft_status"] == "ready_for_review"
    assert _count("group_ops_workspace_draft_audit_logs") == 2


def test_group_ops_workspace_request_review_rejects_stale_archived_and_sensitive_payloads(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    cookies = _admin_cookies()
    stale_draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="review-stale-create"),
        cookies=cookies,
    ).json()
    stale = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{stale_draft['draft_id']}/request-review",
        json=_request_review_payload(version=stale_draft["version"] + 1, idempotency_key="review-stale"),
        cookies=cookies,
    )
    snapshot_conflict = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{stale_draft['draft_id']}/request-review",
        json=_request_review_payload(version=stale_draft["version"], idempotency_key="review-snapshot", client_snapshot_hash="not-the-current-snapshot"),
        cookies=cookies,
    )
    sensitive = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{stale_draft['draft_id']}/request-review",
        json={**_request_review_payload(version=stale_draft["version"], idempotency_key="review-sensitive"), "raw_external_userid": "wm_unsafe"},
        cookies=cookies,
    )
    sensitive_note = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{stale_draft['draft_id']}/request-review",
        json=_request_review_payload(version=stale_draft["version"], idempotency_key="review-sensitive-note", review_note="contains token marker"),
        cookies=cookies,
    )

    archived_draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_payload(idempotency_key="review-archived-create"),
        cookies=cookies,
    ).json()
    next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/archive",
        json={"version": archived_draft["version"], "archive_reason": "safe archive"},
        cookies=cookies,
    )
    archived = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/request-review",
        json=_request_review_payload(version=archived_draft["version"], idempotency_key="review-archived"),
        cookies=cookies,
    )

    assert stale.status_code == 409, stale.text
    assert snapshot_conflict.status_code == 409, snapshot_conflict.text
    assert sensitive.status_code == 400, sensitive.text
    assert sensitive_note.status_code == 400, sensitive_note.text
    assert archived.status_code in {400, 409}, archived.text
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0
