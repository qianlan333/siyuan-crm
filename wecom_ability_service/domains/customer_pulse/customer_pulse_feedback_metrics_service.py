from __future__ import annotations

from typing import Any

from .service import (
    CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
    CUSTOMER_PULSE_FLAG_KEY,
    CUSTOMER_PULSE_FLAG_POLICY_KEY,
    _customer_pulse_dependency_status,
    _customer_pulse_review_data_source_summary,
    _feature_override_map,
    _feature_policy_map,
    _iso_now,
    _next_followup_time,
    _normalized_bool,
    _normalized_text,
    _present_card,
    _record_action_feedback,
    _record_metric_event,
    _resolved_tenant_context,
    _resolved_tenant_key,
    _safe_rate,
    _setting_enabled,
    _stats_since,
    _tenant_review_status,
    _trend_direction,
    assert_customer_pulse_feedback_permission,
    customer_pulse_external_request_scoped_enforced,
    customer_pulse_feature_gate_summary,
    customer_pulse_tenant_context_summary,
    customer_pulse_tenant_mode,
    repo,
)

__all__ = [
    "build_customer_pulse_first_wave_review_report",
    "build_customer_pulse_ops_dashboard_payload",
    "build_customer_pulse_tenant_rollout_report",
    "customer_pulse_rollout_whitelist_summary",
    "submit_customer_pulse_feedback",
]


def customer_pulse_rollout_whitelist_summary() -> dict[str, Any]:
    """Internal owner for customer-pulse rollout and metrics reporting reads."""

    feature_policy = _feature_policy_map()
    tenant_map = feature_policy.get("tenants") if isinstance(feature_policy.get("tenants"), dict) else {}
    default_enabled = bool(feature_policy.get("default_enabled"))
    enabled_tenants: list[str] = []
    disabled_tenants: list[str] = []
    tenant_entries: list[dict[str, Any]] = []
    for tenant_key in sorted(_normalized_text(key) for key in tenant_map.keys() if _normalized_text(key)):
        section = tenant_map.get(tenant_key) if isinstance(tenant_map.get(tenant_key), dict) else {}
        tenant_enabled = _normalized_bool(section.get("enabled")) if "enabled" in section else default_enabled
        role_overrides = _feature_override_map(section, "roles")
        user_overrides = _feature_override_map(section, "userids", "users")
        if tenant_enabled:
            enabled_tenants.append(tenant_key)
        else:
            disabled_tenants.append(tenant_key)
        tenant_entries.append(
            {
                "tenant_key": tenant_key,
                "enabled": bool(tenant_enabled),
                "role_override_count": len(role_overrides),
                "user_override_count": len(user_overrides),
            }
        )
    return {
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": _setting_enabled(),
        "default_enabled": default_enabled,
        "tenant_mode": customer_pulse_tenant_mode(),
        "external_request_scoped_enforced": customer_pulse_external_request_scoped_enforced(),
        "enabled_tenants": enabled_tenants,
        "disabled_tenants": disabled_tenants,
        "tenants": tenant_entries,
        "whitelist_ready": bool(_setting_enabled()) and not default_enabled and bool(enabled_tenants),
    }


def build_customer_pulse_tenant_rollout_report(
    *,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    whitelist = customer_pulse_rollout_whitelist_summary()
    requested_tenant_keys = [_normalized_text(item) for item in (tenant_keys or []) if _normalized_text(item)]
    report_tenant_keys = requested_tenant_keys or list(whitelist.get("enabled_tenants") or [])
    tenant_reports: list[dict[str, Any]] = []
    for tenant_key in report_tenant_keys:
        stats = build_customer_pulse_ops_dashboard_payload(tenant_key=tenant_key, days=days)
        tenant_reports.append(
            {
                "tenant_key": tenant_key,
                "feature_gate": dict(stats.get("feature_gate") or {}),
                "counts": {
                    key: int((stats.get("counts") or {}).get(key, 0) or 0)
                    for key in (
                        "ai_success",
                        "ai_error",
                        "fallback_count",
                        "draft_preview_started",
                        "draft_confirmed",
                        "writeback_success",
                        "unauthorized_denied",
                        "cross_tenant_denied",
                    )
                },
                "rates": {
                    key: float((stats.get("rates") or {}).get(key, 0.0) or 0.0)
                    for key in (
                        "draft_confirm_rate",
                        "fallback_rate",
                        "writeback_success_rate",
                        "ai_error_rate",
                    )
                },
                "window": dict(stats.get("window") or {}),
            }
        )
    return {
        "generated_at": _iso_now(),
        "window_days": max(1, int(days or CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS)),
        "whitelist": whitelist,
        "tenants": tenant_reports,
    }


def build_customer_pulse_first_wave_review_report(
    *,
    days: int = 7,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_days = max(1, int(days or 7))
    rollout = build_customer_pulse_tenant_rollout_report(days=resolved_days, tenant_keys=tenant_keys)
    data_source = _customer_pulse_review_data_source_summary()
    since = _stats_since(resolved_days)
    tenant_reviews: list[dict[str, Any]] = []
    decision_rank = {"expand": 0, "hold": 1, "rollback": 2}
    overall_decision = "expand"
    for tenant_report in rollout.get("tenants") or []:
        item = dict(tenant_report or {})
        tenant_key = _normalized_text(item.get("tenant_key"))
        daily_rows = repo.count_customer_pulse_metric_events_by_day(
            tenant_key=tenant_key,
            since=since,
            event_types=(
                "ai_success",
                "ai_error",
                "fallback_count",
                "draft_preview_started",
                "draft_confirmed",
                "writeback_success",
                "writeback_failed",
                "unauthorized_denied",
                "cross_tenant_denied",
            ),
        )
        daily_map: dict[str, dict[str, int]] = {}
        for row in daily_rows:
            metric_date = _normalized_text(row.get("metric_date"))
            if not metric_date:
                continue
            bucket = daily_map.setdefault(metric_date, {})
            bucket[_normalized_text(row.get("event_type"))] = int(row.get("total_count") or 0)
        ordered_dates = sorted(daily_map.keys())
        counts = dict(item.get("counts") or {})
        ai_success = int(counts.get("ai_success", 0) or 0)
        ai_error = int(counts.get("ai_error", 0) or 0)
        fallback_count = int(counts.get("fallback_count", 0) or 0)
        draft_preview_started = int(counts.get("draft_preview_started", 0) or 0)
        draft_confirmed = int(counts.get("draft_confirmed", 0) or 0)
        writeback_success = int(counts.get("writeback_success", 0) or 0)
        unauthorized_denied = int(counts.get("unauthorized_denied", 0) or 0)
        cross_tenant_denied = int(counts.get("cross_tenant_denied", 0) or 0)
        writeback_failed = sum(int(daily_map.get(day, {}).get("writeback_failed", 0) or 0) for day in ordered_dates)
        ai_error_rate = _safe_rate(ai_error, ai_success + ai_error)
        fallback_rate = _safe_rate(fallback_count, ai_success + fallback_count)
        draft_confirm_rate = _safe_rate(draft_confirmed, draft_preview_started)
        writeback_success_rate = _safe_rate(writeback_success, writeback_success + writeback_failed)
        review_status = _tenant_review_status(
            ai_error_rate=ai_error_rate,
            fallback_rate=fallback_rate,
            draft_confirm_rate=draft_confirm_rate,
            writeback_success_rate=writeback_success_rate,
            unauthorized_denied=unauthorized_denied,
            cross_tenant_denied=cross_tenant_denied,
            production_evidence_verified=bool(data_source.get("production_evidence_verified")),
            observed_days=len(ordered_dates),
        )
        overall_decision = (
            review_status["decision"]
            if decision_rank[review_status["decision"]] > decision_rank[overall_decision]
            else overall_decision
        )
        tenant_reviews.append(
            {
                "tenant_key": tenant_key,
                "seven_day_totals": {
                    "ai_success": ai_success,
                    "ai_error": ai_error,
                    "fallback_count": fallback_count,
                    "draft_preview_started": draft_preview_started,
                    "draft_confirmed": draft_confirmed,
                    "writeback_success": writeback_success,
                    "writeback_failed": writeback_failed,
                    "unauthorized_denied": unauthorized_denied,
                    "cross_tenant_denied": cross_tenant_denied,
                },
                "daily_average": {
                    "ai_success": round(ai_success / resolved_days, 4),
                    "ai_error": round(ai_error / resolved_days, 4),
                    "fallback_count": round(fallback_count / resolved_days, 4),
                    "draft_preview_started": round(draft_preview_started / resolved_days, 4),
                    "draft_confirmed": round(draft_confirmed / resolved_days, 4),
                    "writeback_success": round(writeback_success / resolved_days, 4),
                },
                "rates": {
                    "ai_error_rate": ai_error_rate,
                    "fallback_rate": fallback_rate,
                    "draft_confirm_rate": draft_confirm_rate,
                    "writeback_success_rate": writeback_success_rate,
                },
                "trend": {
                    "observed_days": len(ordered_dates),
                    "active_dates": ordered_dates,
                    "draft_preview_started": _trend_direction(
                        [int(daily_map.get(day, {}).get("draft_preview_started", 0) or 0) for day in ordered_dates]
                    ),
                    "draft_confirmed": _trend_direction(
                        [int(daily_map.get(day, {}).get("draft_confirmed", 0) or 0) for day in ordered_dates]
                    ),
                    "fallback_count": _trend_direction(
                        [int(daily_map.get(day, {}).get("fallback_count", 0) or 0) for day in ordered_dates]
                    ),
                },
                "meets_expansion_gate": review_status["decision"] == "expand",
                "status": review_status["label"],
                "decision": review_status["decision"],
            }
        )
    final_decision = overall_decision
    if not bool(data_source.get("production_evidence_verified")):
        final_decision = "hold"
    return {
        "generated_at": _iso_now(),
        "window_days": resolved_days,
        "data_source": data_source,
        "rollout": rollout,
        "tenants": tenant_reviews,
        "final_decision": final_decision,
    }


def build_customer_pulse_ops_dashboard_payload(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    owner_userids: list[str] | tuple[str, ...] | None = None,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    resolved_days = max(1, min(int(days or CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS), 90))
    since = _stats_since(resolved_days)
    counts = repo.count_customer_pulse_metric_events(
        tenant_key=resolved_tenant_key,
        owner_userids=owner_userids,
        since=since,
        event_types=(
            "action_executed",
            "ai_error",
            "ai_success",
            "ai_recommendation_completed",
            "card_clicked",
            "card_exposed",
            "draft_preview_started",
            "draft_confirmed",
            "fallback_count",
            "followup_segment_updated",
            "followup_task_created",
            "writeback_failed",
            "writeback_success",
        ),
    )
    security_counts = repo.count_customer_pulse_metric_events(
        tenant_key=resolved_tenant_key,
        since=since,
        event_types=("access_denied", "cross_tenant_denied", "unauthorized_denied"),
    )
    exposures = int(counts.get("card_exposed", 0) or 0)
    executions = int(counts.get("action_executed", 0) or 0)
    ai_success = int(counts.get("ai_success", 0) or 0)
    card_clicks = int(counts.get("card_clicked", 0) or 0)
    draft_preview_started = int(counts.get("draft_preview_started", 0) or 0)
    draft_confirms = int(counts.get("draft_confirmed", 0) or 0)
    fallback_count = int(counts.get("fallback_count", 0) or 0)
    writeback_success = int(counts.get("writeback_success", 0) or 0)
    writeback_failed = int(counts.get("writeback_failed", 0) or 0)
    ai_errors = int(counts.get("ai_error", 0) or 0)
    ai_completed = int(counts.get("ai_recommendation_completed", 0) or 0)
    unauthorized_denied = int(security_counts.get("unauthorized_denied", 0) or 0)
    cross_tenant_denied = int(security_counts.get("cross_tenant_denied", 0) or 0)
    execution_rate = _safe_rate(executions, exposures)
    draft_confirm_rate = _safe_rate(draft_confirms, draft_preview_started or card_clicks)
    fallback_rate = _safe_rate(fallback_count, ai_completed)
    writeback_success_rate = _safe_rate(writeback_success, writeback_success + writeback_failed)
    ai_error_rate = _safe_rate(ai_errors, ai_completed)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    dependencies = _customer_pulse_dependency_status(resolved_context)
    return {
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "feature_gate": feature_gate,
        "dependencies": dependencies,
        "window": {
            "days": resolved_days,
            "since": since,
        },
        "counts": {
            "card_exposed": exposures,
            "action_executed": executions,
            "ai_success": ai_success,
            "draft_confirmed": draft_confirms,
            "draft_preview_started": draft_preview_started,
            "fallback_count": fallback_count,
            "writeback_success": writeback_success,
            "writeback_failed": writeback_failed,
            "ai_error": ai_errors,
            "ai_recommendation_completed": ai_completed,
            "unauthorized_denied": int(security_counts.get("unauthorized_denied", 0) or 0),
            "cross_tenant_denied": int(security_counts.get("cross_tenant_denied", 0) or 0),
            "followup_task_created": int(counts.get("followup_task_created", 0) or 0),
            "followup_segment_updated": int(counts.get("followup_segment_updated", 0) or 0),
            "card_clicked": card_clicks,
            "access_denied": int(security_counts.get("access_denied", 0) or 0),
        },
        "rates": {
            "execution_rate": execution_rate,
            "draft_confirm_rate": draft_confirm_rate,
            "fallback_rate": fallback_rate,
            "writeback_success_rate": writeback_success_rate,
            "ai_error_rate": ai_error_rate,
        },
        "summary_cards": [
            {
                "key": "card_exposed",
                "label": f"最近 {resolved_days} 天曝光",
                "value": exposures,
                "description": "行动卡被展示的总次数。",
            },
            {
                "key": "execution_rate",
                "label": "执行率",
                "value": f"{round(execution_rate * 100, 1)}%",
                "description": f"{executions} 次执行 / {exposures} 次曝光",
            },
            {
                "key": "draft_confirm_rate",
                "label": "草稿确认率",
                "value": f"{round(draft_confirm_rate * 100, 1)}%",
                "description": f"{draft_confirms} 次确认 / {card_clicks} 次点击",
            },
            {
                "key": "writeback_success_rate",
                "label": "写回成功率",
                "value": f"{round(writeback_success_rate * 100, 1)}%",
                "description": f"{writeback_success} 成功 / {writeback_success + writeback_failed} 次写回",
            },
            {
                "key": "ai_error_rate",
                "label": "AI 错误率",
                "value": f"{round(ai_error_rate * 100, 1)}%",
                "description": f"{ai_errors} 次错误 / {ai_completed} 次 AI 推荐",
            },
            {
                "key": "unauthorized_denied",
                "label": "越权拒绝",
                "value": unauthorized_denied,
                "description": "权限不足导致的拒绝次数。",
            },
            {
                "key": "cross_tenant_denied",
                "label": "跨租户拒绝",
                "value": cross_tenant_denied,
                "description": "跨租户读取或探测被拦截的次数。",
            },
        ],
        "rollout_cards": [
            {
                "key": "feature_gate",
                "label": "灰度状态",
                "value": "已开启" if feature_gate["enabled"] else "未开启",
                "description": f"reason={feature_gate['reason']} · tenant={feature_gate['tenant_key']}",
            },
            {
                "key": "tenant_mode",
                "label": "Tenant Mode",
                "value": dependencies["tenant_mode"]["value"],
                "description": "legacy internal 与 request-scoped 显式区分。",
            },
            {
                "key": "rbac",
                "label": "RBAC",
                "value": "已就绪" if dependencies["rbac"]["ready"] else "未就绪",
                "description": str(dependencies["rbac"]["value"]),
            },
            {
                "key": "audit_metrics",
                "label": "审计 / 指标",
                "value": "已就绪",
                "description": "execution log、audit log、metric events 已贯通。",
            },
        ],
    }


def submit_customer_pulse_feedback(
    card_id: int,
    *,
    feedback_type: str,
    note: str = "",
    operator: str = "",
    payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    assert_customer_pulse_feedback_permission(resolved_context)
    presented = _present_card(card, access_context=resolved_context)
    normalized_feedback_type = _normalized_text(feedback_type).lower()
    normalized_operator = _normalized_text(operator) or "crm_console"
    payload = dict(payload or {})
    if normalized_feedback_type in {"adopted", "edited_then_sent", "misjudged", "unhelpful", "ignored"}:
        feedback_row = _record_action_feedback(
            card=presented,
            feedback_type=normalized_feedback_type,
            feedback_source=_normalized_text(payload.get("feedback_source")) or "manual_feedback",
            operator=normalized_operator,
            action_type=_normalized_text(payload.get("action_type")) or _normalized_text(presented.get("suggested_action_type")),
            execution_log_id=int(payload.get("execution_id") or 0) or None,
            note=note,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload=payload,
        )
        if normalized_feedback_type == "ignored":
            _record_metric_event(
                event_type="card_ignored",
                event_source=_normalized_text(payload.get("feedback_source")) or "manual_feedback",
                card=presented,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
            )
        return {
            "ok": True,
            "card": presented,
            "feedback": feedback_row,
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        }
    update_fields: dict[str, Any]
    feedback_value = ""
    action_feedback_type = ""
    if normalized_feedback_type == "complete":
        update_fields = {
            "card_status": "completed",
            "resolved_at": _iso_now(),
            "resolution_note": _normalized_text(note) or "marked_complete",
            "snooze_until": "",
        }
    elif normalized_feedback_type == "dismiss":
        update_fields = {
            "card_status": "dismissed",
            "resolved_at": _iso_now(),
            "resolution_note": _normalized_text(note) or "dismissed",
            "snooze_until": "",
        }
        action_feedback_type = "ignored"
    elif normalized_feedback_type == "reopen":
        update_fields = {
            "card_status": "open",
            "resolved_at": "",
            "resolution_note": _normalized_text(note),
            "snooze_until": "",
        }
    elif normalized_feedback_type == "snooze":
        snooze_until = _normalized_text(payload.get("snooze_until")) or _next_followup_time()
        feedback_value = snooze_until
        update_fields = {
            "card_status": "snoozed",
            "due_at": snooze_until,
            "snooze_until": snooze_until,
            "resolution_note": _normalized_text(note) or "snoozed",
        }
    else:
        raise ValueError("unsupported feedback_type")
    updated_row = repo.update_customer_pulse_card(card_id, tenant_key=resolved_tenant_key, **update_fields)
    feedback_row = repo.insert_customer_pulse_feedback(
        card_id=card_id,
        tenant_key=resolved_tenant_key,
        external_userid=presented["external_userid"],
        feedback_type=normalized_feedback_type,
        feedback_value=feedback_value,
        note=note,
        operator=normalized_operator,
        payload=payload,
    )
    action_feedback_row = {}
    if action_feedback_type:
        action_feedback_row = _record_action_feedback(
            card=_present_card(updated_row, access_context=resolved_context),
            feedback_type=action_feedback_type,
            feedback_source=_normalized_text(payload.get("feedback_source")) or "card_feedback",
            operator=normalized_operator,
            action_type=_normalized_text(payload.get("action_type")) or _normalized_text(presented.get("suggested_action_type")),
            execution_log_id=int(payload.get("execution_id") or 0) or None,
            note=note,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload=payload,
        )
        _record_metric_event(
            event_type="card_ignored",
            event_source=_normalized_text(payload.get("feedback_source")) or "card_feedback",
            card=_present_card(updated_row, access_context=resolved_context),
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
    return {
        "ok": True,
        "card": _present_card(updated_row, access_context=resolved_context),
        "feedback": feedback_row,
        "action_feedback": action_feedback_row,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
    }
