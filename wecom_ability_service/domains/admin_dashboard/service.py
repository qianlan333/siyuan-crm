from __future__ import annotations

from typing import Any

from flask import current_app

from ..admin_auth import admin_role_can_access_module
from ..admin_jobs import build_jobs_dashboard_groups, build_jobs_runtime_snapshot
from . import repo

ADMIN_NAV_ITEMS = (
    {"key": "automation_conversion", "label": "自动化运营", "endpoint": "api.admin_automation_conversion"},
    {"key": "cloud_orchestrator", "label": "AI 助手", "endpoint": "api.admin_cloud_orchestrator_workspace"},
    {"key": "customers", "label": "客户", "endpoint": "api.admin_console_customers"},
    {"key": "user_ops_funnel", "label": "激活漏斗", "endpoint": "api.admin_hxc_dashboard_workspace"},
    {"key": "questionnaires", "label": "问卷", "endpoint": "api.admin_console_questionnaires"},
    {"key": "wechat_pay_transactions", "label": "交易管理", "endpoint": "api.admin_wechat_pay_transactions_page"},
    {"key": "wecom_tags", "label": "企微标签管理", "endpoint": "api.admin_wecom_tags_page"},
    {"key": "image_library", "label": "图片素材库", "endpoint": "api.admin_image_library_workspace"},
    {"key": "miniprogram_library", "label": "小程序素材库", "endpoint": "api.admin_miniprogram_library_workspace"},
    {"key": "jobs", "label": "同步任务", "endpoint": "api.admin_console_jobs"},
    {"key": "config", "label": "配置", "endpoint": "api.admin_config_home"},
    {"key": "api_docs", "label": "API 文档", "endpoint": "api.admin_console_api_docs"},
)


def _current_admin_role_codes() -> list[str]:
    from ...http.internal_auth import current_admin_session_user

    user = current_admin_session_user()
    return list((user or {}).get("roles") or [])


def list_admin_navigation(active_nav: str) -> list[dict[str, Any]]:
    normalized_active_nav = str(active_nav or "").strip() or "automation_conversion"
    role_codes = _current_admin_role_codes()
    items = []
    for item in ADMIN_NAV_ITEMS:
        module_key = str(item["key"] or "").strip()
        if role_codes and not admin_role_can_access_module(role_codes, module_key):
            continue
        items.append({**item, "active": module_key == normalized_active_nav})
    return items


def build_admin_shell_status() -> dict[str, Any]:
    environment = repo.detect_environment(current_app.config)
    health = repo.get_admin_health_snapshot(current_app.config)
    return {
        "environment": environment,
        "release_sha": repo.get_release_sha(current_app.config),
        "health": {
            **health,
            "label": _health_label(health.get("label")),
            "detail": _health_detail(health.get("detail")),
        },
    }


def _bool_label(value: bool) -> str:
    return "已开启" if value else "未开启"


def _empty_value(value: str, *, fallback: str = "Never") -> str:
    text = str(value or "").strip()
    return text or fallback


def _health_label(value: Any) -> str:
    mapping = {
        "HEALTHY": "正常",
        "DEGRADED": "受限",
        "WARN": "需关注",
        "OK": "正常",
        "FAILED": "失败",
        "MISSING": "未配置",
        "UNKNOWN": "未知",
    }
    normalized = str(value or "").strip().upper()
    return mapping.get(normalized, normalized or "未知")


def _health_detail(value: Any) -> str:
    mapping = {
        "service ok": "运行正常",
        "archive sync failed": "最近聊天同步失败",
        "callback not configured": "回调尚未配置",
        "background async disabled": "后台异步处理未开启",
        "status unavailable": "状态暂时无法获取",
    }
    text = str(value or "").strip()
    return mapping.get(text, text or "状态暂时无法获取")


def _status_text(value: Any, *, default: str = "-") -> str:
    mapping = {
        "success": "成功",
        "failed": "失败",
        "pending": "待处理",
        "processing": "处理中",
        "running": "运行中",
        "acked": "已确认",
        "never": "暂无记录",
        "ready": "已就绪",
        "configured": "已配置",
        "missing": "未配置",
    }
    text = str(value or "").strip().lower()
    return mapping.get(text, str(value or "").strip() or default)


def build_system_status_payload() -> dict[str, Any]:
    snapshot = repo.get_system_snapshot(current_app.config)
    jobs_snapshot = build_jobs_runtime_snapshot(include_archive_health=False)
    health = snapshot["health"]
    last_sync_run = dict(jobs_snapshot.get("last_sync_run") or {})
    callback_enabled = bool(jobs_snapshot.get("callback_enabled"))
    background_async_enabled = bool(jobs_snapshot.get("background_async_enabled"))
    deferred_counts = dict(jobs_snapshot.get("deferred_counts") or {})
    pending_jobs = int(deferred_counts.get("pending_count") or 0)
    running_jobs = int(deferred_counts.get("running_count") or 0)
    failed_jobs = int(deferred_counts.get("failed_count") or 0)
    total_attention_jobs = pending_jobs + running_jobs + failed_jobs
    last_archive_sync = {
        "run_id": last_sync_run.get("id"),
        "status": str(last_sync_run.get("status") or "").strip() or "never",
        "time": (
            str(last_sync_run.get("finished_at") or "").strip()
            or str(last_sync_run.get("created_at") or "").strip()
            or str(last_sync_run.get("finished_or_created_at") or "").strip()
        ),
        "error_message": str(last_sync_run.get("error_message") or "").strip(),
    }
    snapshot = {
        **snapshot,
        "callback_enabled": callback_enabled,
        "background_async_enabled": background_async_enabled,
        "last_archive_sync": last_archive_sync,
        "deferred_counts": deferred_counts,
    }
    cards = [
        {
            "key": "service_health",
            "label": "服务状态",
            "value": health["label"],
            "description": health["detail"],
            "tone": health["state"],
        },
        {
            "key": "release_sha",
            "label": "当前版本",
            "value": snapshot["release_sha"],
            "description": "当前部署版本",
            "tone": "neutral",
        },
        {
            "key": "database_backend",
            "label": "数据库",
            "value": snapshot["database_backend"],
            "description": "当前运行数据库后端",
            "tone": "neutral",
        },
        {
            "key": "callback_enabled",
            "label": "回调状态",
            "value": _bool_label(callback_enabled),
            "description": "企业微信回调开关状态",
            "tone": "healthy" if callback_enabled else "degraded",
        },
        {
            "key": "background_async_enabled",
            "label": "后台异步处理",
            "value": _bool_label(background_async_enabled),
            "description": "后台异步处理开关",
            "tone": "healthy" if background_async_enabled else "unknown",
        },
        {
            "key": "last_archive_sync",
            "label": "最近聊天同步",
            "value": _status_text(last_archive_sync["status"], default="暂无记录"),
            "description": _empty_value(str(last_archive_sync["time"] or "").strip(), fallback="暂无记录"),
            "tone": "degraded" if last_archive_sync["status"] == "failed" else "neutral",
        },
        {
            "key": "deferred_jobs",
            "label": "待处理作业",
            "value": total_attention_jobs,
            "description": f"待处理 {pending_jobs} · 运行中 {running_jobs} · 失败 {failed_jobs}",
            "tone": "degraded" if failed_jobs else ("unknown" if total_attention_jobs else "healthy"),
        },
        {
            "key": "last_contacts_sync_time",
            "label": "最近联系人同步",
            "value": _empty_value(snapshot["last_contacts_sync_time"], fallback="暂无记录"),
            "description": "联系人数据最近更新时间",
            "tone": "neutral",
        },
    ]
    return {**snapshot, "cards": cards}


def build_dashboard_summary() -> dict[str, Any]:
    counts = repo.get_business_summary_counts()
    cards = [
        {
            "key": "archived_messages_total",
            "label": "聊天消息",
            "value": counts["archived_messages_total"],
            "description": "已归档聊天消息总量",
            "href": "/admin/jobs",
        },
        {
            "key": "contacts_total",
            "label": "联系人",
            "value": counts["contacts_total"],
            "description": "联系人快照总量",
            "href": "/admin/customers",
        },
        {
            "key": "group_chats_total",
            "label": "群聊",
            "value": counts["group_chats_total"],
            "description": "群聊总量",
            "href": "/admin/jobs",
        },
        {
            "key": "customers_total",
            "label": "客户",
            "value": counts["customers_total"],
            "description": "当前客户总量",
            "href": "/admin/customers",
        },
        {
            "key": "questionnaire_total",
            "label": "问卷",
            "value": counts["questionnaire_total"],
            "description": (
                f"最近提交 {_empty_value(counts['questionnaire_latest_submission'], fallback='暂无提交')}"
            ),
            "href": "/admin/questionnaires",
        },
        {
            "key": "user_ops_lead_pool_total",
            "label": "运营名单",
            "value": counts["user_ops_lead_pool_total"],
            "description": "当前运营名单总量",
            "href": "/admin/user-ops",
        },
        {
            "key": "class_user_current_total",
            "label": "班级状态",
            "value": counts["class_user_current_total"],
            "description": "当前班级状态总量",
            "href": "/admin/class-users",
        },
    ]
    return {
        **counts,
        "cards": cards,
    }


def _build_failed_apply_group() -> dict[str, Any]:
    rows = repo.list_recent_failed_questionnaire_apply_logs(limit=5)
    items = [
        {
            "title": f"提交 #{row['submission_id']}",
            "meta": _empty_value(str(row.get("created_at") or "").strip()),
            "detail": str(row.get("error_message") or "").strip() or "问卷结果处理失败",
        }
        for row in rows
    ]
    return {
        "key": "failed_questionnaire_apply",
        "title": "问卷处理失败",
        "count": len(rows),
        "description": "最近失败的问卷处理记录。",
        "tone": "danger" if rows else "ok",
        "items": items,
        "empty_title": "最近没有问卷处理失败",
        "href": "/admin/questionnaires",
    }


def _build_questionnaire_preflight_group() -> dict[str, Any]:
    snapshot = repo.get_questionnaire_preflight_snapshot(current_app.config)
    anomaly_items: list[dict[str, Any]] = []

    if not snapshot.get("wechat_oauth_configured"):
        anomaly_items.append(
            {
                "title": "WeChat OAuth 未配置",
                "meta": "微信授权尚未完整配置",
                "detail": "问卷身份识别功能暂时不完整。",
            }
        )
    if not snapshot.get("wecom_contact_configured"):
        anomaly_items.append(
            {
                "title": "WeCom Contact 凭证缺失",
                "meta": "企业微信联系人能力尚未完整配置",
                "detail": "问卷同步到客户侧的能力可能受限。",
            }
        )
    if not snapshot.get("wecom_tags_api_available"):
        anomaly_items.append(
            {
                "title": "Tag Probe 未通过",
                "meta": "企业微信标签检查未通过",
                "detail": str(snapshot.get("wecom_tags_api_error") or "").strip() or "当前无法确认标签接口是否正常",
            }
        )
    if not snapshot.get("identity_map_available"):
        anomaly_items.append(
            {
                "title": "Identity Map 不可用",
                "meta": "身份映射暂时不可用",
                "detail": str(snapshot.get("identity_map_error") or "").strip() or "当前无法读取身份映射数据",
            }
        )

    return {
        "key": "questionnaire_preflight",
        "title": "问卷环境检查",
        "count": len(anomaly_items),
        "description": "这里提示问卷环境是否存在明显异常。",
        "tone": "warn" if anomaly_items else "ok",
        "items": anomaly_items,
        "empty_title": "问卷环境检查正常",
        "href": "/admin/questionnaires",
    }


def _build_mcp_runtime_group() -> dict[str, Any]:
    snapshot = repo.get_mcp_runtime_snapshot(current_app.config)
    items: list[dict[str, Any]] = []
    if not snapshot["bearer_token_configured"]:
        items.append(
            {
                "title": "AI 工具访问令牌未配置",
                "meta": "AI 工具暂时无法完整使用",
                "detail": "请先在系统设置中补齐访问令牌。",
            }
        )
    return {
        "key": "mcp_runtime",
        "title": "AI 工具状态",
        "count": len(items),
        "description": "这里提示 AI 工具的连接和配置异常。",
        "tone": "warn" if items else "ok",
        "items": items,
        "empty_title": "AI 工具配置正常",
        "href": "/admin/api-docs",
    }


def build_dashboard_todos() -> dict[str, Any]:
    groups = [
        *build_jobs_dashboard_groups(),
        _build_failed_apply_group(),
        _build_questionnaire_preflight_group(),
        _build_mcp_runtime_group(),
    ]
    return {
        "groups": groups,
        "total_pending": sum(int(group["count"]) for group in groups),
    }


def build_dashboard_cards() -> list[dict[str, Any]]:
    return build_dashboard_summary()["cards"]
