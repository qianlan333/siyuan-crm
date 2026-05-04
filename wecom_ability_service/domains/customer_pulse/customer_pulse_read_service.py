from __future__ import annotations

from typing import Any

from .customer_pulse_feedback_metrics_service import build_customer_pulse_ops_dashboard_payload
from .service import (
    CUSTOMER_PULSE_FLAG_KEY,
    CUSTOMER_PULSE_RULES_VERSION,
    _action_label,
    _allowed_action_types,
    _build_inbox_filter_options,
    _card_hidden_by_low_confidence,
    _customer_pulse_access_permissions,
    _customer_pulse_evidence_source_allowed,
    _customer_pulse_metrics_summary,
    _filter_match,
    _high_priority_threshold,
    _iso_now,
    _json_loads,
    _message_direction,
    _normalized_text,
    _present_card,
    _present_execution_log,
    _present_signal,
    _present_snapshot,
    _record_metric_event,
    _resolved_tenant_context,
    _resolved_tenant_key,
    _sanitize_evidence_text,
    _show_low_confidence_suggestions,
    assert_customer_pulse_evidence_view,
    customer_pulse_feature_gate_summary,
    customer_pulse_tenant_context_summary,
    repo,
)

__all__ = [
    "build_customer_pulse_customer_detail_payload",
    "build_customer_pulse_dashboard_group",
    "build_customer_pulse_inbox_payload",
    "get_customer_pulse_card_evidence_payload",
    "get_customer_pulse_card_payload",
]


def build_customer_pulse_inbox_payload(
    *,
    limit: int = 50,
    owner_userid: str = "",
    external_userid: str = "",
    operator: str = "",
    scope: str = "all",
    stage: str = "",
    risk: str = "",
    overdue_only: bool = False,
    draft_only: bool = False,
    high_priority_only: bool = False,
    search: str = "",
    track_metrics: bool = False,
    metric_source: str = "",
    include_ops_dashboard: bool = False,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
            "feature_gate": feature_gate,
            "rules_version": CUSTOMER_PULSE_RULES_VERSION,
            "runtime_config": {
                "high_priority_threshold": _high_priority_threshold(),
                "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
                "allowed_action_types": sorted(_allowed_action_types()),
            },
            "permissions": _customer_pulse_access_permissions(resolved_context),
            "cards": [],
            "filter_options": {"stages": [], "risks": []},
            "filters": {
                "scope": _normalized_text(scope) or "all",
                "stage": _normalized_text(stage),
                "risk": _normalized_text(risk),
                "overdue_only": bool(overdue_only),
                "draft_only": bool(draft_only),
                "high_priority_only": bool(high_priority_only),
                "search": _normalized_text(search),
                "requested_owner_userid": _normalized_text(owner_userid),
                "resolved_owner_userid": _normalized_text(owner_userid) or _normalized_text(operator),
                "external_userid": _normalized_text(external_userid),
                "operator": _normalized_text(operator),
                "scope_fallback_notice": "",
            },
            "visible_count": 0,
            "matched_count": 0,
            "total_active_count": 0,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "metrics_summary": _customer_pulse_metrics_summary(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            ),
            "ops_dashboard": (
                build_customer_pulse_ops_dashboard_payload(
                    tenant_context=resolved_context,
                    tenant_key=resolved_tenant_key,
                    owner_userids=allowed_owner_userids,
                )
                if include_ops_dashboard
                else None
            ),
            "counts": {"open": 0, "draft_ready": 0, "snoozed": 0, "completed": 0, "dismissed": 0},
            "summary_cards": [],
            "channel_notice": "当前租户或角色未进入 Customer Pulse 灰度范围，不展示收件箱数据。",
            "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
            "generated_at": _iso_now(),
        }
    counts = repo.count_customer_pulse_cards_by_status(
        tenant_key=resolved_tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )
    effective_scope = _normalized_text(scope) or "all"
    requested_owner_userid = _normalized_text(owner_userid)
    resolved_owner_userid = requested_owner_userid or _normalized_text(operator)
    scope_fallback_notice = ""
    if effective_scope == "mine" and not resolved_owner_userid:
        effective_scope = "all"
        scope_fallback_notice = "当前后台未注入登录人，`我的客户` 已回退为 `全部客户`。如需锁定负责人，可通过 operator 或 owner_userid 传入。"
    card_rows = repo.list_customer_pulse_cards(
        limit=max(1, min(int(limit or 0), 200)),
        tenant_key=resolved_tenant_key,
        owner_userid=requested_owner_userid,
        external_userid=external_userid,
        allowed_owner_userids=allowed_owner_userids,
    )
    snapshot_rows_by_id = repo.list_customer_pulse_snapshots_by_ids(
        [int(row.get("snapshot_id") or 0) for row in card_rows],
        tenant_key=resolved_tenant_key,
    )
    base_cards = [
        _present_card(
            row,
            snapshot_row=snapshot_rows_by_id.get(int(row.get("snapshot_id") or 0)),
            access_context=resolved_context,
        )
        for row in card_rows
    ]
    base_cards = [card for card in base_cards if not _card_hidden_by_low_confidence(card)]
    filters = {
        "scope": effective_scope,
        "stage": _normalized_text(stage),
        "risk": _normalized_text(risk),
        "overdue_only": bool(overdue_only),
        "draft_only": bool(draft_only),
        "high_priority_only": bool(high_priority_only),
        "search": _normalized_text(search),
        "requested_owner_userid": requested_owner_userid,
        "resolved_owner_userid": resolved_owner_userid,
        "external_userid": _normalized_text(external_userid),
        "operator": _normalized_text(operator),
        "scope_fallback_notice": scope_fallback_notice,
    }
    filtered_cards = [card for card in base_cards if _filter_match(card, filters=filters)]
    cards = filtered_cards[: max(1, min(int(limit or 0), 200))]
    if track_metrics:
        repo.insert_customer_pulse_metric_events_batch(
            tenant_key=resolved_tenant_key,
            events=[
                {
                    "card_id": int(card.get("id") or 0),
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "owner_userid": _normalized_text(card.get("owner_userid")),
                    "action_type": _normalized_text(card.get("suggested_action_type")),
                    "event_type": "card_exposed",
                    "event_source": _normalized_text(metric_source) or "customer_pulse_inbox",
                    "operator": _normalized_text(operator),
                    "payload": {"surface": "inbox"},
                }
                for card in cards
                if int(card.get("id") or 0) > 0
            ],
        )
    filter_options = _build_inbox_filter_options(base_cards)
    high_priority_count = len([card for card in filtered_cards if _normalized_text(card.get("priority")) == "high"])
    draft_ready_count = len(
        [card for card in filtered_cards if bool(_normalized_text(card.get("draft_message"))) or _normalized_text(card.get("card_status")) == "draft_ready"]
    )
    overdue_count = len([card for card in filtered_cards if bool(card.get("is_overdue"))])
    return {
        "enabled": True,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "feature_gate": feature_gate,
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "runtime_config": {
            "high_priority_threshold": _high_priority_threshold(),
            "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
            "allowed_action_types": sorted(_allowed_action_types()),
        },
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "cards": cards,
        "filter_options": filter_options,
        "filters": filters,
        "visible_count": len(cards),
        "matched_count": len(filtered_cards),
        "total_active_count": len(base_cards),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "metrics_summary": _customer_pulse_metrics_summary(
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            owner_userids=allowed_owner_userids,
        ),
        "ops_dashboard": (
            build_customer_pulse_ops_dashboard_payload(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            )
            if include_ops_dashboard
            else None
        ),
        "counts": {
            "open": int(counts.get("open", 0) or 0),
            "draft_ready": int(counts.get("draft_ready", 0) or 0),
            "snoozed": int(counts.get("snoozed", 0) or 0),
            "completed": int(counts.get("completed", 0) or 0),
            "dismissed": int(counts.get("dismissed", 0) or 0),
        },
        "summary_cards": [
            {
                "key": "visible",
                "label": "当前可见卡片",
                "value": len(cards),
                "description": f"当前筛选命中的行动卡，共 {len(filtered_cards)} 条",
            },
            {
                "key": "high_priority",
                "label": "高优先级",
                "value": high_priority_count,
                "description": "priority_score 或风险命中高优先级阈值",
            },
            {
                "key": "draft_ready",
                "label": "已有草稿",
                "value": draft_ready_count,
                "description": "已生成或已保存草稿，等待人工确认",
            },
            {
                "key": "overdue",
                "label": "超期未跟进",
                "value": overdue_count,
                "description": "下次处理时间已过，仍处于待处理状态",
            },
        ],
        "channel_notice": "若仓库中没有企微新链路，当前只复用已有客户沟通通道；不会临时接入新平台。",
        "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "generated_at": _iso_now(),
    }


def get_customer_pulse_card_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        raise ValueError("当前租户或角色未启用 AI推进")
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    snapshot = (
        repo.get_customer_pulse_snapshot(int(card.get("snapshot_id") or 0), tenant_key=resolved_tenant_key)
        if card.get("snapshot_id")
        else {}
    )
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "card": _present_card(card, snapshot_row=snapshot, access_context=resolved_context),
        "snapshot": _present_snapshot(snapshot, access_context=resolved_context) if snapshot else None,
        "latest_execution": _present_execution_log(
            repo.get_latest_customer_pulse_execution_log(int(card.get("id") or 0), tenant_key=resolved_tenant_key)
        ),
        "recent_action_feedback": [
            {
                "id": int(row.get("id") or 0),
                "execution_log_id": int(row.get("execution_log_id") or 0) if row.get("execution_log_id") not in (None, "") else 0,
                "action_type": _normalized_text(row.get("action_type")),
                "feedback_type": _normalized_text(row.get("feedback_type")),
                "feedback_source": _normalized_text(row.get("feedback_source")),
                "operator": _normalized_text(row.get("operator")),
                "note": _normalized_text(row.get("note")),
                "payload": _json_loads(row.get("payload_json"), default={}),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in repo.list_customer_pulse_action_feedback(
                card_id=int(card.get("id") or 0),
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "metrics_summary": _customer_pulse_metrics_summary(
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        ),
        "recent_activities": [
            {
                "id": int(row.get("id") or 0),
                "activity_type": _normalized_text(row.get("activity_type")),
                "activity_status": _normalized_text(row.get("activity_status")),
                "title": _normalized_text(row.get("title")),
                "summary": _normalized_text(row.get("summary")),
                "due_at": _normalized_text(row.get("due_at")),
                "operator": _normalized_text(row.get("operator")),
                "created_at": _normalized_text(row.get("created_at")),
                "undone_at": _normalized_text(row.get("undone_at")),
                "payload": _json_loads(row.get("payload_json"), default={}),
            }
            for row in repo.list_customer_pulse_activity_logs(
                _normalized_text(card.get("external_userid")),
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
    }


def get_customer_pulse_card_evidence_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        raise ValueError("当前租户或角色未启用 AI推进")
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    assert_customer_pulse_evidence_view(resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    snapshot = (
        repo.get_customer_pulse_snapshot(int(card.get("snapshot_id") or 0), tenant_key=resolved_tenant_key)
        if card.get("snapshot_id")
        else {}
    )
    presented_card = _present_card(card, snapshot_row=snapshot, access_context=resolved_context)
    evidence_refs = list(presented_card.get("evidence_refs") or [])
    ref_keys = {
        (_normalized_text(item.get("sourceType")), _normalized_text(item.get("sourceId")))
        for item in evidence_refs
        if _normalized_text(item.get("sourceType")) and _normalized_text(item.get("sourceId"))
    }
    evidence_items: list[dict[str, Any]] = []
    inaccessible_refs: list[dict[str, Any]] = []
    seen_item_keys: set[tuple[str, str, str, str]] = set()
    signals = repo.list_customer_pulse_signal_events(
        _normalized_text(card.get("external_userid")),
        tenant_key=resolved_tenant_key,
        statuses=("open", "resolved"),
        limit=50,
    )
    for signal_row in signals:
        presented_signal = _present_signal(signal_row, access_context=resolved_context)
        source_type = _normalized_text(presented_signal.get("source_ref_type") or presented_signal.get("signal_source"))
        source_id = _normalized_text(presented_signal.get("source_ref_id"))
        ref_key = (source_type, source_id)
        if ref_key not in ref_keys:
            continue
        if not _customer_pulse_evidence_source_allowed(
            source_type=source_type,
            source_id=source_id,
            external_userid=_normalized_text(card.get("external_userid")),
            owner_userid=_normalized_text(card.get("owner_userid")),
        ):
            inaccessible_refs.append({"sourceType": source_type, "sourceId": source_id})
            continue
        signal_evidence = presented_signal.get("evidence") if isinstance(presented_signal.get("evidence"), list) else []
        candidate_items = signal_evidence or [
            {
                "title": _normalized_text(presented_signal.get("summary")) or "证据",
                "detail": _normalized_text(presented_signal.get("summary")) or "暂无详情",
                "event_time": _normalized_text(presented_signal.get("source_updated_at")),
                "source": source_type,
            }
        ]
        for item in candidate_items:
            if not isinstance(item, dict):
                continue
            dedupe_key = (
                source_type,
                source_id,
                _normalized_text(item.get("title")),
                _normalized_text(item.get("event_time") or item.get("detail")),
            )
            if dedupe_key in seen_item_keys:
                continue
            seen_item_keys.add(dedupe_key)
            evidence_items.append(
                {
                    "sourceType": source_type,
                    "sourceId": source_id,
                    "title": _sanitize_evidence_text(item.get("title"), max_length=48) or "证据",
                    "detail": _sanitize_evidence_text(
                        item.get("detail") or presented_signal.get("summary"),
                        max_length=160,
                    )
                    or "暂无详情",
                    "event_time": _normalized_text(item.get("event_time")) or _normalized_text(presented_signal.get("source_updated_at")),
                    "source": _normalized_text(item.get("source")) or source_type,
                }
            )
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "card_id": int(card_id),
        "external_userid": _normalized_text(card.get("external_userid")),
        "evidence_refs": evidence_refs,
        "evidence": evidence_items[: max(1, min(int(limit or 0), 100))],
        "inaccessible_refs": inaccessible_refs,
    }


def build_customer_pulse_customer_detail_payload(
    external_userid: str,
    *,
    track_metrics: bool = False,
    metric_source: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
            "feature_gate": feature_gate,
            "rules_version": CUSTOMER_PULSE_RULES_VERSION,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "runtime_config": {
                "high_priority_threshold": _high_priority_threshold(),
                "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
                "allowed_action_types": sorted(_allowed_action_types()),
            },
            "permissions": _customer_pulse_access_permissions(resolved_context),
            "customer": {
                "external_userid": normalized_external_userid,
                "customer_name": normalized_external_userid,
                "owner_userid": "",
                "mobile": "",
            },
            "card": None,
            "has_card": False,
            "latest_snapshot": None,
            "signals": [],
            "recent_messages": [],
            "metrics_summary": _customer_pulse_metrics_summary(
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                owner_userids=allowed_owner_userids,
            ),
        }
    latest_snapshot = repo.get_latest_customer_pulse_snapshot_for_external_userid(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    card = repo.get_latest_customer_pulse_card_for_external_userid(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    owner_anchor_userid = _normalized_text(card.get("owner_userid") or latest_snapshot.get("owner_userid"))
    if allowed_owner_userids:
        normalized_allowed_owner_userids = {
            _normalized_text(item) for item in allowed_owner_userids if _normalized_text(item)
        }
        if owner_anchor_userid and owner_anchor_userid not in normalized_allowed_owner_userids:
            raise LookupError("customer not found")
    signals = repo.list_customer_pulse_signal_events(
        normalized_external_userid,
        tenant_key=resolved_tenant_key,
        statuses=("open", "resolved"),
        limit=20,
    )
    presented_card = (
        _present_card(
            repo.get_customer_pulse_card(int(card.get("id") or 0), tenant_key=resolved_tenant_key) or card,
            snapshot_row=latest_snapshot,
            access_context=resolved_context,
        )
        if card
        else None
    )
    if presented_card and _card_hidden_by_low_confidence(presented_card):
        presented_card = None
    if presented_card and track_metrics:
        _record_metric_event(
            event_type="card_exposed",
            event_source=_normalized_text(metric_source) or "customer_pulse_customer_detail",
            card=presented_card,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "customer_detail"},
        )
    summary = (
        repo.get_customer_pulse_customer_summary(normalized_external_userid)
        if bool(resolved_context.get("legacy_mode")) and not presented_card
        else {}
    )
    recent_messages = (
        repo.list_recent_archived_message_rows(normalized_external_userid, limit=5)
        if bool(resolved_context.get("legacy_mode"))
        else []
    )
    return {
        "enabled": True,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "feature_gate": feature_gate,
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "runtime_config": {
            "high_priority_threshold": _high_priority_threshold(),
            "show_low_confidence_suggestions": _show_low_confidence_suggestions(),
            "allowed_action_types": sorted(_allowed_action_types()),
        },
        "permissions": _customer_pulse_access_permissions(resolved_context),
        "customer": {
            "external_userid": normalized_external_userid,
            "customer_name": _normalized_text((presented_card or {}).get("customer_name")) or _normalized_text(summary.get("customer_name")) or normalized_external_userid,
            "owner_userid": _normalized_text((presented_card or {}).get("owner_userid")) or owner_anchor_userid,
            "mobile": _normalized_text((presented_card or {}).get("mobile")) or _normalized_text(summary.get("mobile")),
        },
        "card": presented_card,
        "has_card": bool(presented_card),
        "latest_snapshot": _present_snapshot(latest_snapshot, access_context=resolved_context) if latest_snapshot else None,
        "signals": [_present_signal(row, access_context=resolved_context) for row in signals],
        "recent_messages": [
            {
                "id": int(row.get("id") or 0),
                "sender": _normalized_text(row.get("sender")),
                "content": _normalized_text(row.get("content")),
                "send_time": _normalized_text(row.get("send_time")),
                "direction": _message_direction(row, external_userid=normalized_external_userid),
            }
            for row in recent_messages
        ],
        "recent_activities": [
            {
                "id": int(row.get("id") or 0),
                "activity_type": _normalized_text(row.get("activity_type")),
                "activity_status": _normalized_text(row.get("activity_status")),
                "title": _normalized_text(row.get("title")),
                "summary": _normalized_text(row.get("summary")),
                "due_at": _normalized_text(row.get("due_at")),
                "operator": _normalized_text(row.get("operator")),
                "created_at": _normalized_text(row.get("created_at")),
                "undone_at": _normalized_text(row.get("undone_at")),
                "payload": _json_loads(row.get("payload_json"), default={}),
            }
            for row in repo.list_customer_pulse_activity_logs(
                normalized_external_userid,
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "latest_execution": _present_execution_log(
            repo.get_latest_customer_pulse_execution_log(int(card.get("id") or 0), tenant_key=resolved_tenant_key)
        )
        if card
        else None,
        "recent_action_feedback": [
            {
                "id": int(row.get("id") or 0),
                "execution_log_id": int(row.get("execution_log_id") or 0) if row.get("execution_log_id") not in (None, "") else 0,
                "action_type": _normalized_text(row.get("action_type")),
                "feedback_type": _normalized_text(row.get("feedback_type")),
                "feedback_source": _normalized_text(row.get("feedback_source")),
                "operator": _normalized_text(row.get("operator")),
                "note": _normalized_text(row.get("note")),
                "payload": _json_loads(row.get("payload_json"), default={}),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in repo.list_customer_pulse_action_feedback(
                external_userid=normalized_external_userid,
                tenant_key=resolved_tenant_key,
                limit=10,
            )
        ],
        "generated_at": _iso_now(),
    }


def build_customer_pulse_dashboard_group(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    rows = repo.list_recent_customer_pulse_cards_for_dashboard(limit=5, tenant_key=resolved_tenant_key)
    items = [
        {
            "title": _normalized_text(row.get("customer_name")) or _normalized_text(row.get("external_userid")),
            "meta": _action_label(row.get("suggested_action_type")),
            "detail": _normalized_text(row.get("summary")) or _normalized_text(row.get("title")) or "待处理客户推进卡",
        }
        for row in rows
    ]
    counts = repo.count_customer_pulse_cards_by_status(tenant_key=resolved_tenant_key)
    count = int(counts.get("open", 0) or 0) + int(counts.get("draft_ready", 0) or 0)
    return {
        "key": "customer_pulse",
        "title": "AI推进收件箱",
        "count": count,
        "description": "今天该处理的客户推进动作卡。",
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "tone": "warn" if count else "ok",
        "items": items,
        "empty_title": "当前没有待处理推进卡",
        "href": "/admin/customer-pulse",
    }
