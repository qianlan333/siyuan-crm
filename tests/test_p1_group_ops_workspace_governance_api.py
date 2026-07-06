from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
                "username": "governance-api-admin",
                "display_name": "Governance API Admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def _draft_payload(*, idempotency_key: str = "governance-draft-create", source_plan_id: str = "plan-safe-governance-1") -> dict:
    return {
        "idempotency_key": idempotency_key,
        "source_plan_id": source_plan_id,
        "sanitized_payload": {
            "workspace": "p1_group_ops_workspace",
            "selected_count": 2,
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
                "sanitized_item": {"title": "Governance safe plan", "status": "ready_preview"},
                "guardrail_summary": {"no_direct_send": True},
            }
        ],
    }


def _request_review_payload(*, version: int, snapshot_hash: str, idempotency_key: str = "governance-review-request") -> dict:
    return {
        "version": version,
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": snapshot_hash,
        "review_note": "safe review note",
    }


def _governance_payload(
    *,
    snapshot_hash: str,
    idempotency_key: str = "governance-request-idem",
    allowlist_hash: str = "allowlist-hash-safe-1",
    allowlist_count: int = 2,
    start_at: str | None = None,
    end_at: str | None = None,
) -> dict:
    if start_at is None or end_at is None:
        start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
        end = start + timedelta(hours=1)
        start_at = start_at or start.isoformat()
        end_at = end_at or end.isoformat()
    return {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": snapshot_hash,
        "allowlist_summary": {
            "allowlist_hash": allowlist_hash,
            "allowlist_count": allowlist_count,
            "allowlist_summary": {
                "source": "redacted_governance_allowlist",
                "receiver_summary": "count_only",
            },
            "source_reference": {
                "reference_type": "redacted_internal_record",
                "reference_id": "gov-src-safe-1",
            },
        },
        "gray_window": {
            "start_at": start_at,
            "end_at": end_at,
            "timezone": "UTC",
            "metadata": {"window_label": "safe gray window"},
        },
        "request_note": "safe governance request",
    }


def _count(table: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() or 0)


def _ready_draft(next_client: TestClient, *, create_key: str = "ready-draft") -> dict:
    cookies = _admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key=f"{create_key}-create"),
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()
    reviewed = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{created_payload['draft_id']}/request-review",
        json=_request_review_payload(
            version=created_payload["version"],
            snapshot_hash=created_payload["snapshot_hash"],
            idempotency_key=f"{create_key}-request-review",
        ),
        cookies=cookies,
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def _assert_non_execution_response(payload: dict) -> None:
    assert payload["preview_only"] is True
    assert payload["approved"] is False
    assert payload.get("governance_approved", False) is False
    assert payload["real_external_call"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["push_center_job_created"] is False
    assert payload["external_effect_job_created"] is False
    assert payload["broadcast_job_created"] is False
    assert payload["internal_event_created"] is False
    assert payload["can_claim_pass_90_plus"] is False
    assert payload["execution_status"] == "not_execution"
    assert payload.get("review_status") not in {"governance_approved", "sent", "completed"}


def _assert_step_non_execution_response(payload: dict) -> None:
    assert payload["preview_only"] is True
    assert payload["approved"] is False
    assert payload["execution_status"] == "not_execution"
    assert payload["real_external_call"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["push_center_job_created"] is False
    assert payload["external_effect_job_created"] is False
    assert payload["broadcast_job_created"] is False
    assert payload["internal_event_created"] is False
    assert payload["can_claim_pass_90_plus"] is False
    assert payload.get("review_status") not in {"sent", "completed"}


def _governance_review(next_client: TestClient, *, create_key: str = "step-governance") -> dict:
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key=create_key)
    created = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key=f"{create_key}-governance"),
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    return created.json()


def _step_id(review: dict, step_type: str) -> str:
    for step in review["steps"]:
        if step["step_type"] == step_type:
            return step["step_id"]
    raise AssertionError(f"missing step {step_type}")


def _step_payload(
    *,
    idempotency_key: str,
    allowlist_hash: str | None = None,
    allowlist_count: int | None = None,
    note: str = "safe governance step note",
) -> dict:
    payload = {
        "idempotency_key": idempotency_key,
        "note": note,
    }
    if allowlist_hash is not None:
        payload["allowlist_hash"] = allowlist_hash
    if allowlist_count is not None:
        payload["allowlist_count"] = allowlist_count
    return payload


def _bridge_payload(
    review: dict,
    *,
    idempotency_key: str = "bridge-push-center",
    allowlist_hash: str | None = None,
    allowlist_count: int | None = None,
    snapshot_hash: str | None = None,
) -> dict:
    return {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": snapshot_hash or review["snapshot_hash"],
        "allowlist_hash": allowlist_hash or review["allowlist_summary"]["hash"],
        "allowlist_count": review["allowlist_summary"]["count"] if allowlist_count is None else allowlist_count,
        "bridge_note": "safe bridge note",
    }


def _approve_all_governance_steps(next_client: TestClient, review: dict, *, key_prefix: str = "bridge-approve") -> dict:
    cookies = _admin_cookies()
    operator = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'operator_approval')}/approve",
        json=_step_payload(idempotency_key=f"{key_prefix}-operator"),
        cookies=cookies,
    )
    assert operator.status_code == 200, operator.text
    allowlist = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'receiver_allowlist')}/approve",
        json=_step_payload(
            idempotency_key=f"{key_prefix}-allowlist",
            allowlist_hash=review["allowlist_summary"]["hash"],
            allowlist_count=review["allowlist_summary"]["count"],
        ),
        cookies=cookies,
    )
    assert allowlist.status_code == 200, allowlist.text
    gray = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'gray_window')}/approve",
        json=_step_payload(idempotency_key=f"{key_prefix}-gray-window"),
        cookies=cookies,
    )
    assert gray.status_code == 200, gray.text
    return gray.json()


def _assert_bridge_pending_not_execution(payload: dict) -> None:
    assert payload["preview_only"] is True
    assert payload["approved"] is False
    assert payload["governance_approved"] is True
    assert payload["push_center_job_created"] is True
    assert payload["push_center_job_id"].startswith("p1-gow-push-center:")
    assert payload["push_center_status"] == "pending"
    assert payload["external_effect_job_created"] is False
    assert payload["broadcast_job_created"] is False
    assert payload["internal_event_created"] is False
    assert payload["real_external_call"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["execution_status"] == "push_center_pending_not_sent"
    assert payload["can_claim_pass_90_plus"] is False
    assert payload["push_center_status"] not in {"sent", "completed"}
    assert payload.get("review_status") not in {"sent", "completed"}


def test_group_ops_workspace_governance_apis_fail_closed_without_admin_cookie(next_client: TestClient) -> None:
    request = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts/gowd_missing/governance/request",
        json=_governance_payload(snapshot_hash="safe-snapshot"),
    )
    detail = next_client.get("/api/admin/p1/group-ops-workspace/governance/gowg_missing")
    listed = next_client.get("/api/admin/p1/group-ops-workspace/drafts/gowd_missing/governance")

    for response in [request, detail, listed]:
        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "admin_auth_required"
        assert payload["real_external_call_executed"] is False


def test_ready_for_review_draft_can_request_governance_without_execution(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-create")
    before = {
        "reviews": _count("group_ops_workspace_governance_reviews"),
        "steps": _count("group_ops_workspace_governance_review_steps"),
        "allowlist": _count("group_ops_workspace_allowlist_snapshots"),
        "gray_window": _count("group_ops_workspace_gray_window_approvals"),
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
        "outbound_tasks": _count("outbound_tasks"),
    }

    response = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"]),
        cookies=cookies,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["operation"] == "request_governance"
    assert payload["production_write"] is True
    assert payload["production_write_scope"] == "governance_tables_only"
    assert payload["review_status"] == "approval_pending"
    assert {step["step_type"] for step in payload["steps"]} == {
        "operator_approval",
        "receiver_allowlist",
        "gray_window",
    }
    assert {step["step_status"] for step in payload["steps"]} == {"pending"}
    assert payload["allowlist_summary"]["hash"] == "allowlist-hash-safe-1"
    assert payload["allowlist_summary"]["count"] == 2
    assert payload["gray_window"]["window_status"] == "pending"
    _assert_non_execution_response(payload)

    assert _count("group_ops_workspace_governance_reviews") == before["reviews"] + 1
    assert _count("group_ops_workspace_governance_review_steps") == before["steps"] + 3
    assert _count("group_ops_workspace_allowlist_snapshots") == before["allowlist"] + 1
    assert _count("group_ops_workspace_gray_window_approvals") == before["gray_window"] + 1
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]
    assert _count("outbound_tasks") == before["outbound_tasks"]


def test_governance_request_preconditions_reject_non_ready_archived_snapshot_and_invalid_window(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key="governance-not-ready"),
        cookies=cookies,
    ).json()
    not_ready = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{draft['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=draft["snapshot_hash"], idempotency_key="not-ready-governance"),
        cookies=cookies,
    )

    archived_draft = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key="governance-archived"),
        cookies=cookies,
    ).json()
    next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/archive",
        json={"version": archived_draft["version"], "archive_reason": "safe archive"},
        cookies=cookies,
    )
    archived = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{archived_draft['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=archived_draft["snapshot_hash"], idempotency_key="archived-governance"),
        cookies=cookies,
    )

    ready = _ready_draft(next_client, create_key="governance-invalid")
    snapshot_conflict = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash="different-safe-snapshot", idempotency_key="snapshot-conflict"),
        cookies=cookies,
    )
    invalid_start = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).replace(microsecond=0)
    invalid_end = invalid_start - timedelta(hours=1)
    invalid_window = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(
            snapshot_hash=ready["snapshot_hash"],
            idempotency_key="invalid-window",
            start_at=invalid_start.isoformat(),
            end_at=invalid_end.isoformat(),
        ),
        cookies=cookies,
    )
    missing_allowlist_hash = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="missing-allowlist", allowlist_hash=""),
        cookies=cookies,
    )

    assert not_ready.status_code == 400, not_ready.text
    assert archived.status_code in {400, 409}, archived.text
    assert snapshot_conflict.status_code == 409, snapshot_conflict.text
    assert invalid_window.status_code == 400, invalid_window.text
    assert missing_allowlist_hash.status_code == 400, missing_allowlist_hash.text
    assert _count("group_ops_workspace_governance_reviews") == 0
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_governance_request_idempotency_and_active_review_conflicts(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-idempotency")
    payload = _governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="same-governance-key")

    first = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=payload,
        cookies=cookies,
    )
    replay = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=payload,
        cookies=cookies,
    )
    changed_same_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={**payload, "request_note": "changed safe governance note"},
        cookies=cookies,
    )
    different_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="different-governance-key"),
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert changed_same_key.status_code == 409, changed_same_key.text
    assert different_key.status_code == 409, different_key.text
    assert first.json()["review_id"] == replay.json()["review_id"]
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    assert _count("group_ops_workspace_governance_reviews") == 1
    assert _count("group_ops_workspace_governance_review_steps") == 3
    assert _count("group_ops_workspace_allowlist_snapshots") == 1
    assert _count("group_ops_workspace_gray_window_approvals") == 1


def test_governance_request_rejects_sensitive_fields_and_values(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-sensitive")
    sensitive_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={**_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-key"), "raw_external_userid": "wm_unsafe"},
        cookies=cookies,
    )
    sensitive_value = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={
            **_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-value"),
            "allowlist_summary": {
                "allowlist_hash": "allowlist-hash-safe-sensitive",
                "allowlist_count": 1,
                "allowlist_summary": {"summary": "call 13800138000"},
                "source_reference": {"reference_id": "gov-src-safe"},
            },
        },
        cookies=cookies,
    )
    sensitive_note = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json={
            **_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="sensitive-note"),
            "request_note": "contains Authorization: Bearer abc",
        },
        cookies=cookies,
    )

    assert sensitive_key.status_code == 400, sensitive_key.text
    assert sensitive_value.status_code == 400, sensitive_value.text
    assert sensitive_note.status_code == 400, sensitive_note.text
    assert "sensitive" in sensitive_key.json()["detail"]
    assert "sensitive" in sensitive_value.json()["detail"]
    assert "sensitive" in sensitive_note.json()["detail"]
    assert _count("group_ops_workspace_governance_reviews") == 0


def test_get_governance_returns_sanitized_summary_only(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    ready = _ready_draft(next_client, create_key="governance-read")
    created = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key="read-governance-key"),
        cookies=cookies,
    ).json()

    detail = next_client.get(
        f"/api/admin/p1/group-ops-workspace/governance/{created['review_id']}",
        cookies=cookies,
    )
    listed = next_client.get(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance",
        cookies=cookies,
    )

    assert detail.status_code == 200, detail.text
    assert listed.status_code == 200, listed.text
    detail_payload = detail.json()
    listed_payload = listed.json()
    assert detail_payload["operation"] == "get_governance"
    assert listed_payload["total"] == 1
    assert listed_payload["items"][0]["review_id"] == created["review_id"]
    _assert_non_execution_response(detail_payload)
    _assert_non_execution_response(listed_payload["items"][0])

    rendered = json.dumps({"detail": detail_payload, "listed": listed_payload}, ensure_ascii=False).lower()
    for forbidden in [
        "raw_external_userid",
        "13800138000",
        "authorization",
        "bearer",
        "secret",
        "openid",
        "unionid",
        "raw message",
        "raw callback",
    ]:
        assert forbidden not in rendered


def test_governance_step_apis_fail_closed_without_admin_cookie(next_client: TestClient) -> None:
    approve = next_client.post(
        "/api/admin/p1/group-ops-workspace/governance/gowg_missing/steps/gowgs_missing/approve",
        json=_step_payload(idempotency_key="unauth-approve"),
    )
    reject = next_client.post(
        "/api/admin/p1/group-ops-workspace/governance/gowg_missing/steps/gowgs_missing/reject",
        json=_step_payload(idempotency_key="unauth-reject"),
    )
    expire = next_client.post(
        "/api/admin/p1/group-ops-workspace/governance/gowg_missing/expire",
        json=_step_payload(idempotency_key="unauth-expire"),
    )

    for response in [approve, reject, expire]:
        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "admin_auth_required"
        assert payload["real_external_call_executed"] is False


def test_approve_governance_steps_to_governance_approved_without_execution(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="step-approve-all")
    before = {
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
        "outbound_tasks": _count("outbound_tasks"),
    }

    operator = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'operator_approval')}/approve",
        json=_step_payload(idempotency_key="approve-operator"),
        cookies=cookies,
    )
    allowlist = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'receiver_allowlist')}/approve",
        json=_step_payload(
            idempotency_key="approve-allowlist",
            allowlist_hash=review["allowlist_summary"]["hash"],
            allowlist_count=review["allowlist_summary"]["count"],
        ),
        cookies=cookies,
    )
    gray = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'gray_window')}/approve",
        json=_step_payload(idempotency_key="approve-gray-window"),
        cookies=cookies,
    )

    assert operator.status_code == 200, operator.text
    assert allowlist.status_code == 200, allowlist.text
    assert gray.status_code == 200, gray.text
    assert operator.json()["step_status"] == "approved"
    assert allowlist.json()["step_status"] == "approved"
    final_payload = gray.json()
    assert final_payload["step_status"] == "approved"
    assert final_payload["review_status"] == "governance_approved"
    assert final_payload["governance_approved"] is True
    assert {step["step_status"] for step in final_payload["steps"]} == {"approved"}
    _assert_step_non_execution_response(final_payload)
    assert final_payload["execution_status"] == "not_execution"
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]
    assert _count("outbound_tasks") == before["outbound_tasks"]


def test_governance_step_specific_validation_and_rejection_paths(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="step-validation")

    allowlist_missing = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'receiver_allowlist')}/approve",
        json=_step_payload(idempotency_key="allowlist-missing"),
        cookies=cookies,
    )
    allowlist_mismatch = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'receiver_allowlist')}/approve",
        json=_step_payload(idempotency_key="allowlist-mismatch", allowlist_hash="different-safe-hash", allowlist_count=review["allowlist_summary"]["count"]),
        cookies=cookies,
    )

    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE group_ops_workspace_gray_window_approvals
                SET start_at = CURRENT_TIMESTAMP - INTERVAL '2 hours',
                    end_at = CURRENT_TIMESTAMP - INTERVAL '1 hour'
                WHERE review_id = :review_id
                """
            ),
            {"review_id": review["review_id"]},
        )
    expired_gray = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'gray_window')}/approve",
        json=_step_payload(idempotency_key="gray-expired"),
        cookies=cookies,
    )
    rejected = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'operator_approval')}/reject",
        json=_step_payload(idempotency_key="operator-reject", note="safe reject reason"),
        cookies=cookies,
    )

    assert allowlist_missing.status_code == 400, allowlist_missing.text
    assert allowlist_mismatch.status_code in {400, 409}, allowlist_mismatch.text
    assert expired_gray.status_code in {400, 409}, expired_gray.text
    assert rejected.status_code == 200, rejected.text
    rejected_payload = rejected.json()
    assert rejected_payload["step_status"] == "rejected"
    assert rejected_payload["review_status"] == "governance_rejected"
    assert rejected_payload["governance_approved"] is False
    _assert_step_non_execution_response(rejected_payload)


def test_expire_governance_review_marks_pending_steps_and_window_expired(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="step-expire")

    expired = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/expire",
        json=_step_payload(idempotency_key="expire-review", note="safe expire reason"),
        cookies=cookies,
    )

    assert expired.status_code == 200, expired.text
    payload = expired.json()
    assert payload["review_status"] == "governance_expired"
    assert payload["step_status"] == "expired"
    assert payload["governance_approved"] is False
    assert payload["gray_window"]["window_status"] == "expired"
    assert {step["step_status"] for step in payload["steps"]} == {"expired"}
    _assert_step_non_execution_response(payload)


def test_governance_step_idempotency_conflicts_and_sensitive_fields(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="step-idempotency")
    operator_step = _step_id(review, "operator_approval")

    first = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{operator_step}/approve",
        json=_step_payload(idempotency_key="same-step-key", note="safe same note"),
        cookies=cookies,
    )
    replay = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{operator_step}/approve",
        json=_step_payload(idempotency_key="same-step-key", note="safe same note"),
        cookies=cookies,
    )
    conflict = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{operator_step}/approve",
        json=_step_payload(idempotency_key="same-step-key", note="changed safe note"),
        cookies=cookies,
    )
    transitioned = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{operator_step}/approve",
        json=_step_payload(idempotency_key="different-step-key", note="safe different key"),
        cookies=cookies,
    )
    sensitive = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/steps/{_step_id(review, 'receiver_allowlist')}/approve",
        json={
            **_step_payload(idempotency_key="sensitive-step", allowlist_hash=review["allowlist_summary"]["hash"], allowlist_count=review["allowlist_summary"]["count"]),
            "raw_external_userid": "unsafe",
        },
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    assert conflict.status_code == 409, conflict.text
    assert transitioned.status_code == 409, transitioned.text
    assert sensitive.status_code == 400, sensitive.text
    _assert_step_non_execution_response(first.json())
    _assert_step_non_execution_response(replay.json())


def test_governance_api_does_not_break_legacy_group_ops_read_routes(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    response = next_client.get("/api/admin/automation-conversion/group-ops/plans?limit=1")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_push_center_bridge_apis_fail_closed_without_admin_cookie(next_client: TestClient) -> None:
    bridged = next_client.post(
        "/api/admin/p1/group-ops-workspace/governance/gowg_missing/bridge-push-center",
        json={
            "idempotency_key": "unauth-bridge",
            "client_snapshot_hash": "safe-snapshot",
            "allowlist_hash": "safe-allowlist",
            "allowlist_count": 1,
        },
    )
    detail = next_client.get("/api/admin/p1/group-ops-workspace/governance/gowg_missing/push-center-bridge")

    for response in [bridged, detail]:
        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "admin_auth_required"
        assert payload["real_external_call_executed"] is False


def test_push_center_bridge_preconditions_reject_non_approved_reviews(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="bridge-precondition-pending")
    pending = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review['review_id']}/bridge-push-center",
        json=_bridge_payload(review, idempotency_key="bridge-pending"),
        cookies=cookies,
    )

    operator_only_review = _governance_review(next_client, create_key="bridge-precondition-operator")
    operator = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{operator_only_review['review_id']}/steps/{_step_id(operator_only_review, 'operator_approval')}/approve",
        json=_step_payload(idempotency_key="bridge-precondition-operator-approve"),
        cookies=cookies,
    )
    assert operator.status_code == 200, operator.text
    missing_allowlist = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{operator_only_review['review_id']}/bridge-push-center",
        json=_bridge_payload(operator_only_review, idempotency_key="bridge-missing-allowlist"),
        cookies=cookies,
    )

    two_step_review = _governance_review(next_client, create_key="bridge-precondition-gray")
    next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{two_step_review['review_id']}/steps/{_step_id(two_step_review, 'operator_approval')}/approve",
        json=_step_payload(idempotency_key="bridge-precondition-gray-operator"),
        cookies=cookies,
    )
    next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{two_step_review['review_id']}/steps/{_step_id(two_step_review, 'receiver_allowlist')}/approve",
        json=_step_payload(
            idempotency_key="bridge-precondition-gray-allowlist",
            allowlist_hash=two_step_review["allowlist_summary"]["hash"],
            allowlist_count=two_step_review["allowlist_summary"]["count"],
        ),
        cookies=cookies,
    )
    missing_gray = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{two_step_review['review_id']}/bridge-push-center",
        json=_bridge_payload(two_step_review, idempotency_key="bridge-missing-gray"),
        cookies=cookies,
    )

    assert pending.status_code == 400, pending.text
    assert missing_allowlist.status_code == 400, missing_allowlist.text
    assert missing_gray.status_code == 400, missing_gray.text
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_governance_approved_review_can_bridge_to_push_center_pending_without_execution(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    review = _governance_review(next_client, create_key="bridge-success")
    approved = _approve_all_governance_steps(next_client, review, key_prefix="bridge-success-approve")
    before = {
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
        "outbound_tasks": _count("outbound_tasks"),
    }

    response = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=_bridge_payload(approved, idempotency_key="bridge-success-key"),
        cookies=cookies,
    )
    detail = next_client.get(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/push-center-bridge",
        cookies=cookies,
    )

    assert response.status_code == 200, response.text
    assert detail.status_code == 200, detail.text
    payload = response.json()
    detail_payload = detail.json()
    assert payload["operation"] == "bridge_push_center"
    assert payload["production_write"] is True
    assert payload["production_write_scope"] == "governance_bridge_metadata_only"
    _assert_bridge_pending_not_execution(payload)
    _assert_bridge_pending_not_execution(detail_payload)
    assert payload["push_center_job_id"] == detail_payload["push_center_job_id"]
    assert payload["push_center_metadata"]["source"] == "p1_group_ops_workspace"
    assert payload["push_center_metadata"]["allowlist_hash"] == approved["allowlist_summary"]["hash"]
    assert payload["push_center_metadata"]["allowlist_count"] == approved["allowlist_summary"]["count"]
    assert payload["push_center_metadata"]["no_external_call"] is True
    assert _count("external_effect_job") == before["external_effect_job"]
    assert _count("broadcast_jobs") == before["broadcast_jobs"]
    assert _count("internal_event") == before["internal_event"]
    assert _count("outbound_tasks") == before["outbound_tasks"]


def test_push_center_bridge_rejects_snapshot_allowlist_and_expired_window_conflicts(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()

    snapshot_review = _approve_all_governance_steps(
        next_client,
        _governance_review(next_client, create_key="bridge-snapshot-mismatch"),
        key_prefix="bridge-snapshot-mismatch-approve",
    )
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE group_ops_workspace_drafts SET snapshot_hash = :snapshot_hash WHERE draft_id = :draft_id"),
            {"snapshot_hash": "different-safe-snapshot", "draft_id": snapshot_review["draft_id"]},
        )
    snapshot_mismatch = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{snapshot_review['review_id']}/bridge-push-center",
        json=_bridge_payload(snapshot_review, idempotency_key="bridge-snapshot-mismatch"),
        cookies=cookies,
    )

    allowlist_review = _approve_all_governance_steps(
        next_client,
        _governance_review(next_client, create_key="bridge-allowlist-mismatch"),
        key_prefix="bridge-allowlist-mismatch-approve",
    )
    allowlist_mismatch = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{allowlist_review['review_id']}/bridge-push-center",
        json=_bridge_payload(allowlist_review, idempotency_key="bridge-allowlist-mismatch", allowlist_hash="different-safe-allowlist"),
        cookies=cookies,
    )

    expired_review = _approve_all_governance_steps(
        next_client,
        _governance_review(next_client, create_key="bridge-expired-window"),
        key_prefix="bridge-expired-window-approve",
    )
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE group_ops_workspace_gray_window_approvals
                SET start_at = CURRENT_TIMESTAMP - INTERVAL '2 hours',
                    end_at = CURRENT_TIMESTAMP - INTERVAL '1 hour'
                WHERE review_id = :review_id
                """
            ),
            {"review_id": expired_review["review_id"]},
        )
    expired_window = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{expired_review['review_id']}/bridge-push-center",
        json=_bridge_payload(expired_review, idempotency_key="bridge-expired-window"),
        cookies=cookies,
    )

    assert snapshot_mismatch.status_code == 409, snapshot_mismatch.text
    assert allowlist_mismatch.status_code == 409, allowlist_mismatch.text
    assert expired_window.status_code in {400, 409}, expired_window.text
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_push_center_bridge_idempotency_replay_conflict_and_already_bridged(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    approved = _approve_all_governance_steps(
        next_client,
        _governance_review(next_client, create_key="bridge-idempotency"),
        key_prefix="bridge-idempotency-approve",
    )
    payload = _bridge_payload(approved, idempotency_key="same-bridge-key")

    first = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=payload,
        cookies=cookies,
    )
    replay = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=payload,
        cookies=cookies,
    )
    conflict = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json={**payload, "bridge_note": "changed safe bridge note"},
        cookies=cookies,
    )
    already_bridged = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=_bridge_payload(approved, idempotency_key="different-bridge-key"),
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert conflict.status_code == 409, conflict.text
    assert already_bridged.status_code == 409, already_bridged.text
    assert first.json()["push_center_job_id"] == replay.json()["push_center_job_id"]
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    _assert_bridge_pending_not_execution(first.json())
    _assert_bridge_pending_not_execution(replay.json())
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_push_center_bridge_rejects_sensitive_fields_and_values(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()
    approved = _approve_all_governance_steps(
        next_client,
        _governance_review(next_client, create_key="bridge-sensitive"),
        key_prefix="bridge-sensitive-approve",
    )

    sensitive_key = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json={**_bridge_payload(approved, idempotency_key="bridge-sensitive-key"), "raw_external_userid": "unsafe"},
        cookies=cookies,
    )
    sensitive_value = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json={**_bridge_payload(approved, idempotency_key="bridge-sensitive-value"), "bridge_note": "call 13800138000"},
        cookies=cookies,
    )
    sensitive_auth = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json={**_bridge_payload(approved, idempotency_key="bridge-sensitive-auth"), "bridge_note": "Authorization: Bearer unsafe"},
        cookies=cookies,
    )

    assert sensitive_key.status_code == 400, sensitive_key.text
    assert sensitive_value.status_code == 400, sensitive_value.text
    assert sensitive_auth.status_code == 400, sensitive_auth.text
    assert "sensitive" in sensitive_key.json()["detail"]
    assert "sensitive" in sensitive_value.json()["detail"]
    assert "sensitive" in sensitive_auth.json()["detail"]
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0
