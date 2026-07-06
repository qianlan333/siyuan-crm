from __future__ import annotations

import json
from pathlib import Path
from time import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.shared.db_session import get_engine

from tests.test_p1_group_ops_workspace_governance_api import (
    _admin_cookies,
    _assert_bridge_pending_not_execution,
    _bridge_payload,
    _count,
    _draft_payload,
    _governance_payload,
    _request_review_payload,
    _step_id,
    _step_payload,
)


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_SERVICE = ROOT / "aicrm_next" / "automation_engine" / "group_ops" / "governance_service.py"
GOVERNANCE_API = ROOT / "aicrm_next" / "automation_engine" / "group_ops" / "governance_api.py"
FRONTEND_GOVERNANCE_API = ROOT / "frontend" / "admin" / "p1_group_ops_workspace" / "workspace_governance_api.ts"


def _bridge_admin_cookies() -> dict[str, str]:
    return {
        SESSION_COOKIE: sign_session(
            {
                "auth_source": "pytest",
                "login_type": "pytest",
                "username": "bridge-hardening-admin",
                "display_name": "Bridge Hardening Admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def _table_counts() -> dict[str, int]:
    return {
        "drafts": _count("group_ops_workspace_drafts"),
        "draft_items": _count("group_ops_workspace_draft_items"),
        "draft_audit": _count("group_ops_workspace_draft_audit_logs"),
        "governance_reviews": _count("group_ops_workspace_governance_reviews"),
        "governance_steps": _count("group_ops_workspace_governance_review_steps"),
        "allowlist_snapshots": _count("group_ops_workspace_allowlist_snapshots"),
        "gray_window_approvals": _count("group_ops_workspace_gray_window_approvals"),
        "external_effect_job": _count("external_effect_job"),
        "broadcast_jobs": _count("broadcast_jobs"),
        "internal_event": _count("internal_event"),
        "outbound_tasks": _count("outbound_tasks"),
    }


def _assert_no_execution_table_writes(before: dict[str, int]) -> None:
    after = _table_counts()
    for table in ("external_effect_job", "broadcast_jobs", "internal_event", "outbound_tasks"):
        assert after[table] == before[table], table


def _create_updated_ready_draft(next_client: TestClient, *, marker: str) -> dict:
    cookies = _bridge_admin_cookies()
    created = next_client.post(
        "/api/admin/p1/group-ops-workspace/drafts",
        json=_draft_payload(idempotency_key=f"{marker}-create"),
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()

    updated = next_client.patch(
        f"/api/admin/p1/group-ops-workspace/drafts/{created_payload['draft_id']}",
        json={
            **_draft_payload(idempotency_key=f"{marker}-update", source_plan_id=f"plan-safe-{marker}-updated"),
            "version": created_payload["version"],
        },
        cookies=cookies,
    )
    assert updated.status_code == 200, updated.text
    updated_payload = updated.json()

    reviewed = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{updated_payload['draft_id']}/request-review",
        json=_request_review_payload(
            version=updated_payload["version"],
            snapshot_hash=updated_payload["snapshot_hash"],
            idempotency_key=f"{marker}-request-review",
        ),
        cookies=cookies,
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def _request_and_approve_governance(next_client: TestClient, ready: dict, *, marker: str) -> dict:
    cookies = _bridge_admin_cookies()
    review = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=ready["snapshot_hash"], idempotency_key=f"{marker}-governance"),
        cookies=cookies,
    )
    assert review.status_code == 200, review.text
    review_payload = review.json()

    operator = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review_payload['review_id']}/steps/{_step_id(review_payload, 'operator_approval')}/approve",
        json=_step_payload(idempotency_key=f"{marker}-operator"),
        cookies=cookies,
    )
    assert operator.status_code == 200, operator.text

    allowlist = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review_payload['review_id']}/steps/{_step_id(review_payload, 'receiver_allowlist')}/approve",
        json=_step_payload(
            idempotency_key=f"{marker}-allowlist",
            allowlist_hash=review_payload["allowlist_summary"]["hash"],
            allowlist_count=review_payload["allowlist_summary"]["count"],
        ),
        cookies=cookies,
    )
    assert allowlist.status_code == 200, allowlist.text

    gray = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{review_payload['review_id']}/steps/{_step_id(review_payload, 'gray_window')}/approve",
        json=_step_payload(idempotency_key=f"{marker}-gray-window"),
        cookies=cookies,
    )
    assert gray.status_code == 200, gray.text
    approved = gray.json()
    assert approved["review_status"] == "governance_approved"
    assert {step["step_status"] for step in approved["steps"]} == {"approved"}
    return approved


def _stored_bridge_metadata(review_id: str) -> dict:
    with get_engine().connect() as conn:
        raw = conn.execute(
            text(
                """
                SELECT audit_metadata_json
                FROM group_ops_workspace_governance_reviews
                WHERE review_id = :review_id
                """
            ),
            {"review_id": review_id},
        ).scalar_one()
    metadata = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
    return metadata.get("push_center_bridge") or {}


def test_full_draft_governance_bridge_flow_writes_only_expected_tables(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    before = _table_counts()
    cookies = _bridge_admin_cookies()

    ready = _create_updated_ready_draft(next_client, marker="hardening-e2e")
    approved = _request_and_approve_governance(next_client, ready, marker="hardening-e2e")
    bridged = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=_bridge_payload(approved, idempotency_key="hardening-e2e-bridge"),
        cookies=cookies,
    )
    assert bridged.status_code == 200, bridged.text
    bridge_payload = bridged.json()
    _assert_bridge_pending_not_execution(bridge_payload)

    detail = next_client.get(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/push-center-bridge",
        cookies=cookies,
    )
    assert detail.status_code == 200, detail.text
    _assert_bridge_pending_not_execution(detail.json())
    assert detail.json()["push_center_job_id"] == bridge_payload["push_center_job_id"]

    after = _table_counts()
    assert after["drafts"] == before["drafts"] + 1
    assert after["draft_items"] == before["draft_items"] + 1
    assert after["draft_audit"] == before["draft_audit"] + 3
    assert after["governance_reviews"] == before["governance_reviews"] + 1
    assert after["governance_steps"] == before["governance_steps"] + 3
    assert after["allowlist_snapshots"] == before["allowlist_snapshots"] + 1
    assert after["gray_window_approvals"] == before["gray_window_approvals"] + 1
    _assert_no_execution_table_writes(before)

    bridge_metadata = _stored_bridge_metadata(approved["review_id"])
    assert bridge_metadata["push_center_status"] == "pending"
    assert bridge_metadata["execution_status"] == "push_center_pending_not_sent"
    assert bridge_metadata["external_effect_job_created"] is False
    assert bridge_metadata["broadcast_job_created"] is False
    assert bridge_metadata["internal_event_created"] is False
    assert bridge_metadata["real_external_call"] is False
    rendered = json.dumps(bridge_metadata, ensure_ascii=False).lower()
    for forbidden in ("raw_external_userid", "13800138000", "authorization", "secret", "openid", "unionid", "raw_target", "raw_message", "raw_callback"):
        assert forbidden not in rendered


def test_bridge_hardening_rejects_terminal_pending_and_missing_step_states(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _admin_cookies()

    pending = _create_updated_ready_draft(next_client, marker="hardening-pending")
    pending_review = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{pending['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=pending["snapshot_hash"], idempotency_key="hardening-pending-governance"),
        cookies=cookies,
    ).json()
    pending_bridge = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{pending_review['review_id']}/bridge-push-center",
        json=_bridge_payload(pending_review, idempotency_key="hardening-pending-bridge"),
        cookies=cookies,
    )

    rejected_ready = _create_updated_ready_draft(next_client, marker="hardening-rejected-clean")
    rejected_created = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{rejected_ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=rejected_ready["snapshot_hash"], idempotency_key="hardening-rejected-governance"),
        cookies=cookies,
    ).json()
    rejected = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{rejected_created['review_id']}/steps/{_step_id(rejected_created, 'operator_approval')}/reject",
        json=_step_payload(idempotency_key="hardening-reject-step"),
        cookies=cookies,
    )
    assert rejected.status_code == 200, rejected.text
    rejected_bridge = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{rejected_created['review_id']}/bridge-push-center",
        json=_bridge_payload(rejected_created, idempotency_key="hardening-rejected-bridge"),
        cookies=cookies,
    )

    expired_ready = _create_updated_ready_draft(next_client, marker="hardening-expired")
    expired_created = next_client.post(
        f"/api/admin/p1/group-ops-workspace/drafts/{expired_ready['draft_id']}/governance/request",
        json=_governance_payload(snapshot_hash=expired_ready["snapshot_hash"], idempotency_key="hardening-expired-governance"),
        cookies=cookies,
    ).json()
    expired = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{expired_created['review_id']}/expire",
        json=_step_payload(idempotency_key="hardening-expire-review"),
        cookies=cookies,
    )
    assert expired.status_code == 200, expired.text
    expired_bridge = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{expired_created['review_id']}/bridge-push-center",
        json=_bridge_payload(expired_created, idempotency_key="hardening-expired-bridge"),
        cookies=cookies,
    )

    assert pending_bridge.status_code == 400, pending_bridge.text
    assert rejected_bridge.status_code == 400, rejected_bridge.text
    assert expired_bridge.status_code == 400, expired_bridge.text
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_bridge_idempotency_and_conflict_are_enforced_in_pg(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _bridge_admin_cookies()
    approved = _request_and_approve_governance(
        next_client,
        _create_updated_ready_draft(next_client, marker="hardening-idempotency"),
        marker="hardening-idempotency",
    )
    payload = _bridge_payload(approved, idempotency_key="hardening-same-bridge")
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
        json={**payload, "bridge_note": "changed safe note"},
        cookies=cookies,
    )
    already_bridged = next_client.post(
        f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
        json=_bridge_payload(approved, idempotency_key="hardening-different-bridge"),
        cookies=cookies,
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["production_write"] is False
    assert first.json()["push_center_job_id"] == replay.json()["push_center_job_id"]
    assert conflict.status_code == 409, conflict.text
    assert already_bridged.status_code == 409, already_bridged.text


def test_bridge_rejects_sensitive_bait_and_never_stores_it(
    next_client: TestClient,
    next_pg_schema,
) -> None:
    del next_pg_schema
    cookies = _bridge_admin_cookies()
    approved = _request_and_approve_governance(
        next_client,
        _create_updated_ready_draft(next_client, marker="hardening-sensitive"),
        marker="hardening-sensitive",
    )
    baits = [
        {"raw_receiver": "unsafe"},
        {"raw_external_userid": "wm_unsafe"},
        {"phone": "13800138000"},
        {"mobile": "13800138000"},
        {"raw_chat_member_id": "member_unsafe"},
        {"openid": "openid_unsafe"},
        {"unionid": "unionid_unsafe"},
        {"token": "unsafe"},
        {"secret": "unsafe"},
        {"authorization": "Bearer unsafe"},
        {"raw_target_list": ["unsafe"]},
        {"raw_message_body": "unsafe"},
        {"raw_callback_body": "unsafe"},
        {"bridge_note": "call 13800138000"},
    ]
    for index, bait in enumerate(baits):
        response = next_client.post(
            f"/api/admin/p1/group-ops-workspace/governance/{approved['review_id']}/bridge-push-center",
            json={**_bridge_payload(approved, idempotency_key=f"hardening-sensitive-{index}"), **bait},
            cookies=cookies,
        )
        assert response.status_code == 400, response.text
        assert "sensitive" in response.json()["detail"].lower()

    assert _stored_bridge_metadata(approved["review_id"]) == {}
    assert _count("external_effect_job") == 0
    assert _count("broadcast_jobs") == 0
    assert _count("internal_event") == 0


def test_bridge_inventory_has_no_execution_clients_or_route_calls() -> None:
    service_source = GOVERNANCE_SERVICE.read_text(encoding="utf-8")
    api_source = GOVERNANCE_API.read_text(encoding="utf-8")
    frontend_source = FRONTEND_GOVERNANCE_API.read_text(encoding="utf-8")

    forbidden_runtime_tokens = [
        "ExternalEffect",
        "external_effect_service",
        "create_external_effect",
        "create_broadcast_job",
        "InternalEventService",
        "WeCom",
        "webhook.send",
        "message_send",
        "execute_external",
    ]
    bridge_slice = service_source[service_source.index("def bridge_push_center") :]
    for token in forbidden_runtime_tokens:
        assert token not in bridge_slice
        assert token not in api_source

    assert "bridgeGovernanceToPushCenter" in frontend_source
    assert "getGovernancePushCenterBridge" in frontend_source
    for token in ("executeGovernance", "sendGovernance", "runGovernance", "externalEffect", "broadcastClient", "internalEventClient"):
        assert token not in frontend_source
