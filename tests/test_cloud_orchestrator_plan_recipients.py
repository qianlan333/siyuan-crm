from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.cloud_orchestrator.repository import _json_dump, build_cloud_plan_repository
from aicrm_next.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "cloud-plan-recipient-test")
    return TestClient(create_app())


def _token_headers() -> dict[str, str]:
    return {
        "X-Admin-Action-Token": ensure_admin_action_token(),
        "X-Admin-Operator": "tester",
    }


def test_cloud_plan_list_does_not_embed_recipients_or_messages(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/cloud-orchestrator/plans?limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["plans"][0]["plan_id"] == "plan_probe"
    assert payload["plans"][0]["target_count"] == 2
    assert "recipients" not in payload["plans"][0]
    assert "messages" not in payload["plans"][0]


def test_plan_list_groups_legacy_campaign_rows(monkeypatch):
    client = _client(monkeypatch)

    payload = client.get("/api/admin/cloud-orchestrator/plans?limit=20&offset=0").json()

    legacy = next(plan for plan in payload["plans"] if plan["plan_id"] == "standard_subscription_20260530_1000_zhaoyanfang_v1")
    assert legacy["display_name"] == "Standard 订阅 v1.6.3 触达 · ZhaoYanFang · 2026-05-30 10:00"
    assert legacy["source_type"] == "legacy_campaign"
    assert legacy["target_count"] == 3
    assert legacy["approved_count"] == 3
    assert "recipients" not in legacy


def test_legacy_campaign_plan_queries_qualify_ambiguous_columns():
    source = (ROOT / "aicrm_next" / "cloud_orchestrator" / "repository.py").read_text(encoding="utf-8")

    assert "SELECT MAX(id) AS id" not in source
    assert "MAX(intent) AS intent" not in source
    assert "STRING_AGG(DISTINCT NULLIF(owner_userid, '')" not in source
    assert source.count("SELECT MAX(c.id) AS id") >= 2
    assert source.count("MAX(c.intent) AS intent") >= 2
    assert source.count("STRING_AGG(DISTINCT NULLIF(c.owner_userid, '')") >= 2


def test_empty_cloud_plan_shell_does_not_hide_legacy_group(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"
    repo.plans.append(
        {
            "id": 99,
            "plan_id": plan_id,
            "display_name": "空的新计划壳",
            "intent": "空的新计划壳",
            "owner_userid": "ZhaoYanFang",
            "candidate_count": 0,
            "review_status": "pending_review",
            "run_status": "draft",
            "status": "draft",
            "selection_json": {},
            "updated_at": "2026-05-31T10:00:00",
        }
    )

    plans = client.get("/api/admin/cloud-orchestrator/plans?limit=20&offset=0").json()["plans"]
    matching = [plan for plan in plans if plan["plan_id"] == plan_id]
    detail = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}").json()["plan"]

    assert len(matching) == 1
    assert matching[0]["source_type"] == "legacy_campaign"
    assert matching[0]["target_count"] == 3
    assert detail["source_type"] == "legacy_campaign"
    assert detail["target_count"] == 3


def test_legacy_campaign_group_detail_recipients_and_messages(monkeypatch):
    client = _client(monkeypatch)
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"

    plan = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}").json()
    recipients = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients?limit=50&offset=0").json()
    detail = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/-11").json()

    assert plan["plan"]["source_type"] == "legacy_campaign"
    assert plan["plan"]["target_count"] == 3
    assert recipients["total"] == 3
    assert recipients["rows"][0]["source_type"] == "legacy_campaign"
    assert recipients["rows"][0]["supports_recipient_approval"] is False
    assert recipients["rows"][0]["recipient_id"] == -11
    assert [message["content_text"] for message in detail["messages"]] == ["老话术 1", "老话术 2"]


def test_plan_approve_only_changes_plan_review_state(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/approve", headers=_token_headers())

    assert response.status_code == 200
    assert response.json()["plan"]["review_status"] == "approved"
    assert repo.broadcast_jobs == []
    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()["rows"]
    assert [row["approval_status"] for row in recipients] == ["pending", "pending"]


def test_approve_legacy_group_starts_campaign_execution(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"
    repo.legacy_plans[0]["review_status"] = "pending_review"
    repo.legacy_plans[0]["run_status"] = "draft"
    repo.legacy_plans[0]["status"] = "draft"
    for recipient in repo.legacy_recipients:
        recipient["approval_status"] = "pending"
        recipient["send_status"] = "pending"

    response = client.post(f"/api/admin/cloud-orchestrator/plans/{plan_id}/approve", headers=_token_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["review_status"] == "approved"
    assert payload["plan"]["run_status"] == "active"
    recipients = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients").json()["rows"]
    assert {row["approval_status"] for row in recipients} == {"approved"}
    assert {row["send_status"] for row in recipients} == {"queued"}
    assert repo.broadcast_jobs[-1]["source_type"] == "campaign"
    assert repo.broadcast_jobs[-1]["status"] == "queued"
    assert repo.broadcast_jobs[-1]["target_count"] == 3


def test_legacy_approve_postgres_contract_starts_and_prequeues_campaigns():
    source = (ROOT / "aicrm_next" / "cloud_orchestrator" / "repository.py").read_text(encoding="utf-8")

    assert "legacy_campaign_group_approve_and_start_from_cloud_plan" in source
    assert "run_status = CASE" in source
    assert "ELSE 'active'" in source
    assert "campaign_members" in source
    assert "next_due_at = %s::timestamptz" in source
    assert "INSERT INTO broadcast_jobs" in source
    assert "campaign_member_step:" in source


def test_reject_legacy_group_cancels_execution_chain(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"
    repo.legacy_plans[0]["review_status"] = "pending_review"
    repo.legacy_plans[0]["run_status"] = "draft"
    repo.legacy_plans[0]["status"] = "draft"
    for recipient in repo.legacy_recipients:
        recipient["approval_status"] = "pending"
        recipient["send_status"] = "pending"

    approved = client.post(f"/api/admin/cloud-orchestrator/plans/{plan_id}/approve", headers=_token_headers())
    rejected = client.post(
        f"/api/admin/cloud-orchestrator/plans/{plan_id}/reject",
        headers=_token_headers(),
        json={"reason": "重新布置"},
    )

    assert approved.status_code == 200
    assert rejected.status_code == 200
    assert rejected.json()["plan"]["review_status"] == "rejected"
    assert rejected.json()["plan"]["run_status"] == "cancelled"
    recipients = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients").json()["rows"]
    assert {row["approval_status"] for row in recipients} == {"rejected"}
    assert {row["send_status"] for row in recipients} == {"cancelled"}
    assert repo.broadcast_jobs[-1]["status"] == "cancelled"
    assert repo.broadcast_jobs[-1]["cancel_reason"] == "重新布置"


def test_legacy_reject_postgres_contract_cancels_execution_chain():
    source = (ROOT / "aicrm_next" / "cloud_orchestrator" / "repository.py").read_text(encoding="utf-8")

    assert "legacy_campaign_group_reject_from_cloud_plan" in source
    assert "run_status = CASE" in source
    assert "ELSE 'cancelled'" in source
    assert "UPDATE campaign_members" in source
    assert "next_due_at = NULL" in source
    assert "UPDATE broadcast_jobs bj" in source
    assert "bj.source_id LIKE (campaign_id::text || ':%')" in source
    assert "status = ANY(%s)" in source
    assert "WHERE \"\"\" + _LEGACY_GROUP_KEY_SQL + \"\"\" = %s\n                    RETURNING *" not in source


def test_audit_json_dump_serializes_datetime_values():
    payload = json.loads(_json_dump({"updated_at": datetime(2026, 6, 1, 9, 42, 58, tzinfo=timezone.utc)}))

    assert payload["updated_at"] == "2026-06-01T09:42:58+00:00"


def test_recipient_approve_enqueues_single_idempotent_cloud_plan_job(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    client.post("/api/admin/cloud-orchestrator/plans/plan_probe/approve", headers=_token_headers())
    first = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())
    second = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "approved"
    assert second.json()["status"] == "already_approved"
    assert len(repo.broadcast_jobs) == 1
    job = repo.broadcast_jobs[0]
    assert job["source_type"] == "cloud_plan"
    assert job["source_table"] == "cloud_broadcast_plan_recipients"
    assert job["source_id"] == "plan_probe:1"
    assert job["target_external_userids"] == ["wm_a"]
    assert job["target_count"] == 1
    assert job["content_payload"] == {
        "plan_id": "plan_probe",
        "recipient_id": 1,
        "external_userid": "wm_a",
        "message_mode": "recipient_messages",
    }


def test_recipient_approve_requires_plan_level_approval(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())

    assert response.status_code == 409
    assert "plan is not approved" in response.json()["detail"]


def test_recipient_detail_is_the_only_endpoint_returning_messages(monkeypatch):
    client = _client(monkeypatch)

    recipients = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients").json()
    detail = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1").json()

    assert "messages" not in recipients["rows"][0]
    assert detail["messages"][0]["content_text"] == "你好"


def test_cloud_plan_handler_rejects_legacy_bulk_jobs(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    result = execute_job({"id": 99, "source_type": "cloud_plan", "content_payload": {"plan_id": "plan_probe"}})

    assert result["ok"] is False
    assert "bulk job is disabled" in result["error"]


def test_cloud_plan_handler_routes_recipient_jobs(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs import handlers

    called = {}

    def fake_execute_recipient_messages(*, plan_id, recipient_id, broadcast_job_id=None):
        called.update({"plan_id": plan_id, "recipient_id": recipient_id, "broadcast_job_id": broadcast_job_id})
        return {"ok": True, "sent_count": 1, "failed_count": 0}

    monkeypatch.setattr(
        "wecom_ability_service.domains.cloud_orchestrator.broadcast_planner.execute_recipient_messages",
        fake_execute_recipient_messages,
    )

    result = handlers.execute_job(
        {
            "id": 99,
            "source_type": "cloud_plan",
            "content_payload": {"plan_id": "plan_probe", "recipient_id": 1},
        }
    )

    assert result == {"ok": True, "sent_count": 1, "failed_count": 0}
    assert called == {"plan_id": "plan_probe", "recipient_id": 1, "broadcast_job_id": 99}


def test_cloud_plan_recipient_message_payload_resolves_standard_content_package(monkeypatch):
    from wecom_ability_service.domains.cloud_orchestrator import broadcast_planner

    monkeypatch.setattr(
        "wecom_ability_service.domains.image_library.resolve_image_media_id",
        lambda image_id: f"image_media_{image_id}",
    )
    monkeypatch.setattr(
        broadcast_planner.miniprogram_library,
        "materialize_miniprogram_attachment",
        lambda library_id: {"msgtype": "miniprogram", "miniprogram": {"library_id": library_id}},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.attachment_library.materialize_file_attachment",
        lambda library_id: {"msgtype": "file", "file": {"library_id": library_id}},
    )

    request_payload = broadcast_planner._recipient_message_request_payload(
        message={
            "content_text": "标准内容包",
            "content_payload_json": json.dumps(
                {
                    "content_package": {
                        "content_text": "标准内容包",
                        "image_library_ids": [12],
                        "miniprogram_library_ids": [34],
                        "attachment_library_ids": [56],
                    },
                    "image_library_ids": [12],
                    "image_media_ids": [],
                    "miniprogram_library_ids": [34],
                    "attachment_library_ids": [56],
                }
            ),
            "attachments_json": "[]",
        },
        owner_userid="HuangYouCan",
        external_userid="wm_a",
    )

    assert request_payload["text"]["content"] == "标准内容包"
    assert request_payload["image_media_ids"] == ["image_media_12"]
    assert request_payload["attachments"] == [
        {"msgtype": "miniprogram", "miniprogram": {"library_id": 34}},
        {"msgtype": "file", "file": {"library_id": 56}},
    ]


def test_patch_pending_recipient_message_updates_content_package(monkeypatch):
    client = _client(monkeypatch)

    response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/messages/1",
        headers=_token_headers(),
        json={
            "content_package": {
                "content_text": "新版单人话术",
                "image_library_ids": [12, "12", 34],
                "miniprogram_library_ids": ["56"],
                "attachment_library_ids": [78, 90],
            },
            "day_offset": 2,
            "send_time": "14:30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"]["content_text"] == "新版单人话术"
    assert payload["message"]["day_offset"] == 2
    assert payload["message"]["send_time"] == "14:30"
    assert payload["message"]["content_payload"] == {
        "content_package": {
            "content_text": "新版单人话术",
            "image_library_ids": [12, 34],
            "miniprogram_library_ids": [56],
            "attachment_library_ids": [78, 90],
        },
        "image_library_ids": [12, 34],
        "image_media_ids": [],
        "miniprogram_library_ids": [56],
        "attachment_library_ids": [78, 90],
    }
    detail = client.get("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1").json()
    assert detail["messages"][0]["content_text"] == "新版单人话术"
    assert detail["messages"][0]["content_payload"]["content_package"]["image_library_ids"] == [12, 34]


def test_patch_recipient_message_rejects_queued_sent_and_rejected_states(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()

    client.post("/api/admin/cloud-orchestrator/plans/plan_probe/approve", headers=_token_headers())
    queued = client.post("/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/approve", headers=_token_headers())
    assert queued.status_code == 200
    queued_response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/messages/1",
        headers=_token_headers(),
        json={"content_package": {"content_text": "不能改"}},
    )
    assert queued_response.status_code == 409

    repo = build_cloud_plan_repository()
    repo.messages[1]["status"] = "sent"
    sent_response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/2/messages/2",
        headers=_token_headers(),
        json={"content_package": {"content_text": "不能改"}},
    )
    assert sent_response.status_code == 409

    client.post("/api/admin/cloud-orchestrator/plans/plan_probe/reject", headers=_token_headers())
    rejected_response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/2/messages/2",
        headers=_token_headers(),
        json={"content_package": {"content_text": "不能改"}},
    )
    assert rejected_response.status_code == 409


def test_patch_recipient_message_fails_when_message_does_not_belong_to_recipient(monkeypatch):
    client = _client(monkeypatch)

    response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/messages/2",
        headers=_token_headers(),
        json={"content_package": {"content_text": "错人消息"}},
    )

    assert response.status_code == 404


def test_patch_recipient_message_requires_admin_action_token(monkeypatch):
    client = _client(monkeypatch)

    response = client.patch(
        "/api/admin/cloud-orchestrator/plans/plan_probe/recipients/1/messages/1",
        json={"content_package": {"content_text": "缺令牌"}},
    )

    assert response.status_code == 401


def test_patch_pending_legacy_recipient_message_updates_campaign_step(monkeypatch):
    client = _client(monkeypatch)
    repo = build_cloud_plan_repository()
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"
    repo.legacy_recipients[0]["approval_status"] = "pending"
    repo.legacy_recipients[0]["send_status"] = "pending"

    response = client.patch(
        f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/-11/messages/-101",
        headers=_token_headers(),
        json={
            "content_package": {
                "content_text": "旧 Campaign 也能改 pending step",
                "miniprogram_library_ids": [34],
            },
            "day_offset": 3,
            "send_time": "15:30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"]["content_text"] == "旧 Campaign 也能改 pending step"
    assert payload["message"]["day_offset"] == 3
    assert payload["message"]["send_time"] == "15:30"
    assert payload["message"]["content_payload"]["content_package"]["miniprogram_library_ids"] == [34]
    detail = client.get(f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/-11").json()
    assert detail["messages"][0]["content_text"] == "旧 Campaign 也能改 pending step"


def test_patch_non_pending_legacy_recipient_message_is_not_editable(monkeypatch):
    client = _client(monkeypatch)
    plan_id = "standard_subscription_20260530_1000_zhaoyanfang_v1"

    response = client.patch(
        f"/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/-11/messages/-101",
        headers=_token_headers(),
        json={"content_package": {"content_text": "已排队不能改"}},
    )

    assert response.status_code == 409
    assert "recipient is not editable" in response.json()["detail"]
