from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.customer_pulse.access import (
    CUSTOMER_PULSE_ACTION_PERMISSION_MAP,
    CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
    CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK,
    CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE,
    CUSTOMER_PULSE_PERMISSION_VIEW_INBOX,
    CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET,
)
from wecom_ability_service.domains.customer_pulse.service import (
    build_customer_pulse_inbox_payload,
    get_customer_pulse_card_evidence_payload,
    get_customer_pulse_card_payload,
)


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "customer-pulse-quality.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "ai_customer_pulse": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "quality-gates",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
            "AUTOMATION_INTERNAL_API_TOKEN": "internal-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


def _all_permissions() -> list[str]:
    return sorted(
        {
            CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
            CUSTOMER_PULSE_PERMISSION_VIEW_INBOX,
            CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET,
            CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE,
            CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK,
            *CUSTOMER_PULSE_ACTION_PERMISSION_MAP.values(),
        }
    )


def _tenant_context(tenant_key: str) -> dict[str, Any]:
    return {
        "mode": "request_scoped",
        "auth_mode": "request_scoped",
        "valid": True,
        "legacy_mode": False,
        "tenant_key": tenant_key,
        "user_id": "perf-ops",
        "role": "ops",
        "source": "quality_gate_test",
        "tenant_source": "quality_gate_test",
        "user_source": "quality_gate_test",
        "role_source": "quality_gate_test",
        "actor_userid": "perf-ops",
        "actor_role": "ops",
        "operator": "perf-ops",
        "policy": {},
        "allowed_owner_userids": [],
        "member_userids": ["perf-ops"],
        "viewer_roles": ["ops"],
        "operator_roles": ["ops"],
        "internal_roles": ["ops"],
        "permissions_by_role": {},
        "permissions_by_userid": {},
        "granted_permissions": _all_permissions(),
        "can_view_all": True,
        "error_code": "",
        "error_message": "",
        "http_status": 200,
    }


@contextmanager
def _capture_sql_queries() -> Iterator[list[str]]:
    db = get_db()
    statements: list[str] = []

    def _trace(statement: str) -> None:
        normalized = str(statement or "").strip().upper()
        if normalized.startswith(("BEGIN", "COMMIT", "ROLLBACK", "PRAGMA")):
            return
        statements.append(str(statement or "").strip())

    trace_callback = getattr(db, "set_trace_callback", None)
    if not callable(trace_callback):
        yield statements
        return
    trace_callback(_trace)
    try:
        yield statements
    finally:
        trace_callback(None)


def _measure(fn: Callable[[], Any]) -> tuple[Any, int, float]:
    started_at = time.perf_counter()
    with _capture_sql_queries() as statements:
        result = fn()
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    return result, len(statements), elapsed_ms


def _seed_bulk_cards(
    *,
    tenant_key: str,
    card_count: int,
    owner_count: int,
    shared_external_userid: str,
    with_evidence: bool,
) -> int:
    db = get_db()
    now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    detail_card_id = 0
    for index in range(card_count):
        external_userid = shared_external_userid if index == 0 else f"{tenant_key}-ext-{index:04d}"
        owner_userid = f"{tenant_key}-owner-{index % max(owner_count, 1):02d}"
        evidence_refs = (
            [{"sourceType": "archived_messages", "sourceId": f"{tenant_key}-msg-0000", "title": "最近询价", "eventTime": now}]
            if with_evidence and index == 0
            else []
        )
        snapshot_cursor = db.execute(
            """
            INSERT INTO customer_pulse_snapshots (
                tenant_key,
                external_userid,
                owner_userid,
                snapshot_status,
                confidence,
                priority_score,
                summary,
                recommended_action_type,
                recommended_action_label,
                evidence_json,
                ai_payload_json,
                signals_json,
                risk_flags_json,
                opportunity_flags_json,
                suggested_action_candidates_json,
                score_breakdown_json,
                source_updated_at,
                created_by
            )
            VALUES (?, ?, ?, 'ready', ?, ?, ?, 'generate_reply_draft', '生成回复草稿', ?, ?, ?, ?, ?, ?, ?, ?, 'quality-gate')
            """,
            (
                tenant_key,
                external_userid,
                owner_userid,
                0.91,
                92.0 - (index % 7),
                f"{tenant_key} 客户 {index} 的推进摘要",
                json.dumps(
                    [{"title": "最近询价", "detail": "客户刚刚追问价格区间", "event_time": now, "source": "archived_messages"}]
                    if with_evidence and index == 0
                    else [],
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "recommendation_status": "accepted",
                        "trace": {
                            "tenant_context": {"tenant_key": tenant_key},
                            "generated_at": now,
                        },
                        "recommendation": {
                            "summary": "适合先发一版可编辑草稿。",
                            "actionType": "generate_reply_draft",
                            "actionTitle": "先跟进价格问题",
                            "whyNow": "最近 24 小时内客户有明显高意向行为。",
                            "evidenceRefs": evidence_refs,
                            "draftText": "我先整理一版价格区间和方案给你确认。",
                            "confidence": 0.91,
                            "safeFieldUpdates": {
                                "followupSegment": "focus",
                                "nextFollowupAt": "",
                                "addTagIds": [],
                                "removeTagIds": [],
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps([], ensure_ascii=False),
                json.dumps([{"key": "unanswered_question", "label": "客户仍有未回复问题"}], ensure_ascii=False),
                json.dumps([{"key": "high_intent_stage", "label": "处于高意向阶段"}], ensure_ascii=False),
                json.dumps(
                    [
                        {
                            "action_type": "generate_reply_draft",
                            "action_label": "生成回复草稿",
                            "title": "先给一版草稿",
                            "candidate_score": 95,
                            "why_now": "客户刚刚追问价格。",
                            "payload": {
                                "draft_message": "我先整理一版价格区间和方案给你确认。",
                                "ai_recommendation": {
                                    "safe_field_updates": {
                                        "followupSegment": "focus",
                                        "nextFollowupAt": "",
                                        "addTagIds": [],
                                        "removeTagIds": [],
                                    }
                                },
                            },
                        }
                    ],
                    ensure_ascii=False,
                ),
                json.dumps([{"key": "priority_score", "value": 92.0}], ensure_ascii=False),
                now,
            ),
        )
        snapshot_id = int(snapshot_cursor.lastrowid or 0)
        card_cursor = db.execute(
            """
            INSERT INTO customer_pulse_cards (
                card_key,
                tenant_key,
                external_userid,
                owner_userid,
                customer_name,
                mobile,
                owner_display_name,
                marketing_main_stage,
                marketing_sub_stage,
                value_segment,
                snapshot_id,
                card_status,
                priority,
                priority_score,
                card_type,
                title,
                summary,
                suggested_action_type,
                suggested_action_payload_json,
                evidence_json,
                risk_flags_json,
                opportunity_flags_json,
                suggested_action_candidates_json,
                score_breakdown_json,
                draft_message,
                need_human_confirmation,
                due_at,
                snooze_until,
                resolved_at,
                resolution_note,
                source_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pool', 'active_focus', 'focus', ?, 'open', 'high', ?, 'followup', ?, ?, 'generate_reply_draft', ?, ?, ?, ?, ?, ?, '', 1, '', '', '', '', ?)
            """,
            (
                f"{tenant_key}:card:{external_userid}",
                tenant_key,
                external_userid,
                owner_userid,
                f"{tenant_key} 客户 {index}",
                f"1380013{index:04d}"[-11:],
                owner_userid,
                snapshot_id,
                92.0 - (index % 7),
                f"{tenant_key} 行动卡 {index}",
                f"{tenant_key} 客户 {index} 需要跟进。",
                json.dumps(
                    {
                        "draft_message": "我先整理一版价格区间和方案给你确认。",
                        "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
                        "ai_recommendation": {
                            "confidence": 0.91,
                            "safe_field_updates": {
                                "followupSegment": "focus",
                                "nextFollowupAt": "",
                                "addTagIds": [],
                                "removeTagIds": [],
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    [{"title": "最近询价", "detail": "客户刚刚追问价格区间", "event_time": now, "source": "archived_messages"}]
                    if with_evidence and index == 0
                    else [],
                    ensure_ascii=False,
                ),
                json.dumps([{"key": "unanswered_question", "label": "客户仍有未回复问题"}], ensure_ascii=False),
                json.dumps([{"key": "high_intent_stage", "label": "处于高意向阶段"}], ensure_ascii=False),
                json.dumps(
                    [
                        {
                            "action_type": "generate_reply_draft",
                            "action_label": "生成回复草稿",
                            "title": "先给一版草稿",
                            "candidate_score": 95,
                            "why_now": "客户刚刚追问价格。",
                            "payload": {"draft_message": "我先整理一版价格区间和方案给你确认。"},
                        }
                    ],
                    ensure_ascii=False,
                ),
                json.dumps([{"key": "priority_score", "value": 92.0}], ensure_ascii=False),
                now,
            ),
        )
        if with_evidence and index == 0:
            detail_card_id = int(card_cursor.lastrowid or 0)
    if with_evidence:
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (1, ?, 'private', ?, ?, ?, ?, 'text', ?, ?, '{}', ?)
            """,
            (
                f"{tenant_key}-msg-0000",
                shared_external_userid,
                f"{tenant_key}-owner-00",
                shared_external_userid,
                f"{tenant_key}-owner-00",
                "客户手机号 13800138111，想先了解价格区间。",
                now,
                now,
            ),
        )
        db.execute(
            """
            INSERT INTO customer_pulse_signal_events (
                signal_key,
                tenant_key,
                external_userid,
                owner_userid,
                signal_type,
                signal_source,
                signal_status,
                priority,
                evidence_json,
                source_ref_type,
                source_ref_id,
                source_updated_at,
                score,
                summary,
                payload_json,
                first_seen_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, 'unanswered_question', 'archived_messages', 'open', 'high', ?, 'archived_messages', ?, ?, 28, ?, '{}', ?, ?)
            """,
            (
                f"{tenant_key}:{shared_external_userid}:unanswered_question",
                tenant_key,
                shared_external_userid,
                f"{tenant_key}-owner-00",
                json.dumps(
                    [
                        {
                            "title": "客户手机号 13800138111，想了解价格",
                            "detail": "客户手机号 13800138111，想先了解价格区间。",
                            "event_time": now,
                            "source": "archived_messages",
                        }
                    ],
                    ensure_ascii=False,
                ),
                f"{tenant_key}-msg-0000",
                now,
                "客户仍在等待价格问题回复。",
                now,
                now,
            ),
        )
    db.commit()
    return detail_card_id


def _seed_quality_gate_dataset() -> dict[str, Any]:
    primary_tenant = "tenant-load-a"
    secondary_tenant = "tenant-load-b"
    primary_card_id = _seed_bulk_cards(
        tenant_key=primary_tenant,
        card_count=1000,
        owner_count=24,
        shared_external_userid="shared-external-user",
        with_evidence=True,
    )
    _seed_bulk_cards(
        tenant_key=secondary_tenant,
        card_count=260,
        owner_count=12,
        shared_external_userid="shared-external-user",
        with_evidence=False,
    )
    return {
        "primary_tenant": primary_tenant,
        "secondary_tenant": secondary_tenant,
        "detail_card_id": primary_card_id,
    }


def test_customer_pulse_quality_gates_handle_bulk_multi_tenant_workloads(app):
    with app.app_context():
        dataset = _seed_quality_gate_dataset()
        tenant_a_context = _tenant_context(dataset["primary_tenant"])
        tenant_b_context = _tenant_context(dataset["secondary_tenant"])

        inbox_payload, inbox_query_count, inbox_elapsed_ms = _measure(
            lambda: build_customer_pulse_inbox_payload(
                limit=100,
                operator="perf-ops",
                track_metrics=True,
                metric_source="quality_gate_perf",
                tenant_context=tenant_a_context,
            )
        )
        detail_payload, detail_query_count, detail_elapsed_ms = _measure(
            lambda: get_customer_pulse_card_payload(
                int(dataset["detail_card_id"]),
                tenant_context=tenant_a_context,
            )
        )
        evidence_payload, evidence_query_count, evidence_elapsed_ms = _measure(
            lambda: get_customer_pulse_card_evidence_payload(
                int(dataset["detail_card_id"]),
                tenant_context=tenant_a_context,
            )
        )
        tenant_b_inbox_payload, tenant_b_query_count, tenant_b_elapsed_ms = _measure(
            lambda: build_customer_pulse_inbox_payload(
                limit=50,
                operator="perf-ops",
                track_metrics=False,
                tenant_context=tenant_b_context,
            )
        )

        db = get_db()
        exposure_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total_count
                FROM customer_pulse_metric_events
                WHERE tenant_key = ? AND event_type = 'card_exposed'
                """,
                (dataset["primary_tenant"],),
            ).fetchone()["total_count"]
        )

    assert inbox_payload["counts"]["open"] == 1000
    assert inbox_payload["visible_count"] == 100
    assert all(card["tenant_key"] == dataset["primary_tenant"] for card in inbox_payload["cards"])
    assert inbox_query_count <= 12
    assert inbox_elapsed_ms < 2500
    assert exposure_count == 100

    assert detail_payload["card"]["id"] == int(dataset["detail_card_id"])
    assert detail_payload["card"]["tenant_key"] == dataset["primary_tenant"]
    assert detail_query_count <= 8
    assert detail_elapsed_ms < 1200

    assert evidence_payload["card_id"] == int(dataset["detail_card_id"])
    assert evidence_payload["tenant_context"]["tenant_key"] == dataset["primary_tenant"]
    assert evidence_payload["evidence"]
    assert all("13800138111" not in item["title"] for item in evidence_payload["evidence"])
    assert all("13800138111" not in item["detail"] for item in evidence_payload["evidence"])
    assert evidence_query_count <= 6
    assert evidence_elapsed_ms < 1200

    assert tenant_b_inbox_payload["counts"]["open"] == 260
    assert tenant_b_inbox_payload["visible_count"] == 50
    assert all(card["tenant_key"] == dataset["secondary_tenant"] for card in tenant_b_inbox_payload["cards"])
    assert tenant_b_query_count <= 6
    assert tenant_b_elapsed_ms < 1200
