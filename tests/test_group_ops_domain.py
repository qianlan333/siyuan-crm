from __future__ import annotations

import pytest

from tests.group_ops_test_helpers import group_ops_repo


def test_domain_validates_group_owner_match(group_ops_repo):
    from aicrm_next.automation_engine.group_ops.domain import assert_group_owned_by_plan
    from aicrm_next.shared.errors import ContractError

    plan = group_ops_repo.get_plan(1)
    owned_group = group_ops_repo.get_group_asset("wrOgAAA003")
    other_group = group_ops_repo.get_group_asset("wrOgBBB001")

    assert_group_owned_by_plan(group=owned_group, plan=plan)
    with pytest.raises(ContractError, match="owner_userid"):
        assert_group_owned_by_plan(group=other_group, plan=plan)


def test_domain_reuses_unified_attachment_validation():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    normalized = normalize_message_content(
        text="课程入口",
        attachments=[
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "appid": "wx123",
                    "page": "/pages/course/today",
                    "title": "课程入口",
                    "pic_media_id": "MEDIA_ID",
                },
            }
        ],
        sender="owner_001",
    )
    assert normalized["sender"] == "owner_001"
    assert normalized["attachments"][0]["miniprogram"]["pic_media_id"] == "MEDIA_ID"

    with pytest.raises(ContractError, match="pic_media_id"):
        normalize_message_content(
            text="",
            attachments=[
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {"appid": "wx123", "page": "/pages/course/today", "title": "课程入口"},
                }
            ],
        )
    with pytest.raises(ContractError, match="content"):
        normalize_message_content(text="", attachments=[])


def test_group_ops_native_message_content_text_only():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(text="hello", attachments=[])

    assert normalized["text"]["content"] == "hello"
    assert "attachments" not in normalized or normalized["attachments"] == []


def test_group_ops_native_message_content_file_attachment():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(
        text="",
        attachments=[{"msgtype": "file", "file": {"media_id": "file-media-001"}}],
    )

    assert normalized["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-001"}}]


def test_group_ops_native_message_content_miniprogram_aliases():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(
        text="课程入口",
        attachments=[
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "appid": "wx123",
                    "pagepath": "/pages/course/today",
                    "title": "课程入口",
                    "thumb_media_id": "thumb-media-001",
                },
            }
        ],
    )

    assert normalized["attachments"] == [
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx123",
                "page": "/pages/course/today",
                "title": "课程入口",
                "pic_media_id": "thumb-media-001",
            },
        }
    ]


def test_group_ops_native_message_content_missing_miniprogram_fields():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    base = {"appid": "wx123", "page": "/pages/course/today", "title": "课程入口", "pic_media_id": "pic-media-001"}
    for field, expected in (
        ("appid", "appid"),
        ("page", "page"),
        ("title", "title"),
        ("pic_media_id", "pic_media_id"),
    ):
        payload = dict(base)
        payload.pop(field)
        with pytest.raises(ContractError, match=expected):
            normalize_message_content(text="", attachments=[{"msgtype": "miniprogram", "miniprogram": payload}])


def test_group_ops_native_message_content_image_media_ids():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content

    normalized = normalize_message_content(text="", image_media_ids=["img1", "img2", "img3"])

    assert normalized["attachments"] == [
        {"msgtype": "image", "image": {"media_id": "img1"}},
        {"msgtype": "image", "image": {"media_id": "img2"}},
        {"msgtype": "image", "image": {"media_id": "img3"}},
    ]


def test_group_ops_native_message_content_rejects_too_many_images():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    with pytest.raises(ContractError, match="at most 3 images"):
        normalize_message_content(text="", image_media_ids=["img1", "img2", "img3", "img4"])


def test_group_ops_native_message_content_rejects_too_many_total_attachments():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    attachments = [{"msgtype": "file", "file": {"media_id": f"file-{index}"}} for index in range(9)]

    with pytest.raises(ContractError, match="at most 9 attachments"):
        normalize_message_content(text="", attachments=attachments, image_media_ids=["img1"])


def test_group_ops_native_message_content_rejects_unsupported_attachment_msgtype():
    from aicrm_next.automation_engine.group_ops.domain import normalize_message_content
    from aicrm_next.shared.errors import ContractError

    with pytest.raises(ContractError, match="attachments msgtype is not supported"):
        normalize_message_content(text="", attachments=[{"msgtype": "link", "link": {"url": "https://example.invalid"}}])


def test_group_ops_node_payload_draft_allows_empty_content():
    from aicrm_next.automation_engine.group_ops.domain import normalize_node_payload

    normalized = normalize_node_payload(
        {
            "day_index": 1,
            "scheduled_time": "10:00",
            "action_title": "Draft node",
            "status": "draft",
            "text_content": "",
            "attachments": [],
        }
    )

    assert normalized["attachments"] == []
    assert normalized["status"] == "draft"


def test_group_ops_node_payload_active_empty_content_fails():
    from aicrm_next.automation_engine.group_ops.domain import normalize_node_payload
    from aicrm_next.shared.errors import ContractError

    with pytest.raises(ContractError, match="content"):
        normalize_node_payload(
            {
                "day_index": 1,
                "scheduled_time": "10:00",
                "action_title": "Active node",
                "status": "active",
                "text_content": "",
                "attachments": [],
            }
        )


def test_build_node_group_message_content_with_resolved_materials():
    from aicrm_next.automation_engine.group_ops.domain import build_node_group_message_content

    content = build_node_group_message_content(
        node={"text_content": "hello group", "attachments": []},
        sender="owner_001",
        resolved_attachments=[
            {"msgtype": "file", "file": {"media_id": "file-media-001"}},
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "appid": "wx123",
                    "page": "/pages/course/today",
                    "title": "课程入口",
                    "pic_media_id": "pic-media-001",
                },
            },
        ],
        resolved_image_media_ids=["img1"],
    )

    assert content["text"]["content"] == "hello group"
    assert content["sender"] == "owner_001"
    assert content["attachments"] == [
        {"msgtype": "file", "file": {"media_id": "file-media-001"}},
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx123",
                "page": "/pages/course/today",
                "title": "课程入口",
                "pic_media_id": "pic-media-001",
            },
        },
        {"msgtype": "image", "image": {"media_id": "img1"}},
    ]


def test_webhook_token_hash_verification_does_not_require_plaintext_storage():
    from aicrm_next.automation_engine.group_ops.domain import hash_webhook_token, verify_webhook_token

    token_hash = hash_webhook_token("secret-token")

    assert token_hash != "secret-token"
    assert verify_webhook_token(provided_token="secret-token", token_hash=token_hash) is True
    assert verify_webhook_token(provided_token="wrong", token_hash=token_hash) is False


def test_repository_guardrail_uses_sql_repository_in_production_mode(monkeypatch):
    from aicrm_next.automation_engine.group_ops.postgres_repo import PostgresGroupOpsRepository
    from aicrm_next.automation_engine.group_ops.repo import build_group_ops_repository

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://group_ops:group_ops@127.0.0.1:1/aicrm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_GROUP_OPS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    repo = build_group_ops_repository()

    assert isinstance(repo, PostgresGroupOpsRepository)
    assert repo.source_status == "postgres_group_ops_repository"
