from __future__ import annotations

import json
from math import ceil
from typing import Any
from urllib.parse import urlencode

from . import repo

TARGET_ROUTE_MAP = {
    "customer_tag_action": lambda target_id: f"/admin/customers/{target_id}?tab=tags",
    "customer_task_action": lambda target_id: f"/admin/customers/{target_id}?tab=tasks",
    "questionnaire_console_action": lambda target_id: f"/admin/questionnaires/{target_id}",
    "operations_console_action": lambda target_id: "/admin/user-ops",
    "owner_role_map": lambda target_id: f"/admin/config/routing?edit_owner={target_id}",
    "routing_rule_config": lambda target_id: f"/admin/config/routing?edit_rule={target_id}",
    "signup_tag_rule": lambda target_id: f"/admin/config/signup-tags?edit_tag={target_id}",
    "class_term_tag_mapping": lambda target_id: f"/admin/config/class-term-tags?edit_mapping={target_id}",
    "app_setting": lambda target_id: "/admin/config/app-settings",
    "mcp_tool_setting": lambda target_id: f"/admin/config/mcp-tools?edit_tool={target_id}",
    "mcp_preflight": lambda target_id: "/admin/mcp",
    "mcp_sample_call": lambda target_id: f"/admin/mcp?tool={target_id}",
    "jobs_console_action": lambda target_id: "/admin/jobs",
}

SORTABLE_COLUMNS = (
    {"key": "created_at", "label": "时间"},
    {"key": "operator", "label": "操作人"},
    {"key": "action_type", "label": "操作"},
    {"key": "target_type", "label": "模块"},
    {"key": "target_id", "label": "对象"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _sort_dir(value: Any) -> str:
    return "asc" if _normalized_text(value).lower() == "asc" else "desc"


def _build_href(base_path: str, params: dict[str, Any]) -> str:
    filtered = {key: value for key, value in params.items() if value not in ("", None, False)}
    if not filtered:
        return base_path
    return f"{base_path}?{urlencode(filtered, doseq=True)}"


def _target_href(target_type: str, target_id: str) -> str:
    builder = TARGET_ROUTE_MAP.get(_normalized_text(target_type))
    if builder:
        return builder(_normalized_text(target_id))
    return _build_href("/admin/audit", {"target_type": target_type, "target_id": target_id})


def _target_type_label(value: Any) -> str:
    mapping = {
        "customer_tag_action": "客户标签",
        "customer_task_action": "客户触达任务",
        "questionnaire_console_action": "问卷中心",
        "operations_console_action": "运营管理",
        "owner_role_map": "负责人配置",
        "routing_rule_config": "分配规则",
        "signup_tag_rule": "报名标签规则",
        "class_term_tag_mapping": "班期标签规则",
        "app_setting": "系统设置",
        "mcp_tool_setting": "AI 工具设置",
        "mcp_preflight": "AI 工具环境检查",
        "mcp_sample_call": "AI 工具试运行",
        "jobs_console_action": "同步任务",
    }
    normalized = _normalized_text(value)
    return mapping.get(normalized, normalized or "-")


def _action_type_label(value: Any) -> str:
    normalized = _normalized_text(value)
    mapping = {
        "ack_message_batch": "确认消息批次",
        "apply_backfill_owner_class_terms": "执行班期回填",
        "preview_backfill_owner_class_terms": "预览班期回填",
        "disable_questionnaire": "停用问卷",
        "enable_questionnaire": "启用问卷",
        "save_questionnaire": "保存问卷",
        "execute_mcp_sample_call": "正式试运行",
        "preview_mcp_sample_call": "试运行预览",
        "preview_archive_sync": "预览聊天同步",
        "run_archive_sync": "执行聊天同步",
        "run_deferred_jobs": "执行待处理作业",
        "run_mcp_preflight": "执行环境检查",
        "migrate_class_user_status": "同步班级状态",
        "import_mobile_class_terms": "导入班期",
        "import_activation_status": "导入激活状态",
        "update": "更新",
    }
    if normalized in mapping:
        return mapping[normalized]
    if normalized == "execute_mark":
        return "执行添加标签"
    if normalized == "execute_unmark":
        return "执行移除标签"
    if normalized == "execute_private_message":
        return "发送单聊任务"
    if normalized == "execute_group_message":
        return "发送群发任务"
    if normalized == "execute_moment":
        return "发送朋友圈任务"
    return normalized or "-"


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _log_preview_text(value: Any) -> str:
    text = _pretty_json(value)
    if len(text) <= 200:
        return text
    return text[:200] + "..."


def build_admin_audit_payload(args: Any) -> dict[str, Any]:
    filters = {
        "q": _normalized_text(args.get("q")),
        "target_type": _normalized_text(args.get("target_type")),
        "action_type": _normalized_text(args.get("action_type")),
        "operator": _normalized_text(args.get("operator")),
        "target_id": _normalized_text(args.get("target_id")),
        "page": _normalized_int(args.get("page"), default=1, minimum=1, maximum=100000),
        "page_size": _normalized_int(args.get("page_size"), default=20, minimum=10, maximum=100),
        "sort_by": _normalized_text(args.get("sort_by")) or "created_at",
        "sort_dir": _sort_dir(args.get("sort_dir")),
    }
    query_result = repo.list_admin_operation_logs(
        q=filters["q"],
        target_type=filters["target_type"],
        action_type=filters["action_type"],
        operator=filters["operator"],
        target_id=filters["target_id"],
        page=filters["page"],
        page_size=filters["page_size"],
        sort_by=filters["sort_by"],
        sort_dir=filters["sort_dir"],
    )
    total = int(query_result["total"] or 0)
    total_pages = max(1, ceil(total / filters["page_size"])) if filters["page_size"] else 1
    if filters["page"] > total_pages:
        filters["page"] = total_pages
        query_result = repo.list_admin_operation_logs(
            q=filters["q"],
            target_type=filters["target_type"],
            action_type=filters["action_type"],
            operator=filters["operator"],
            target_id=filters["target_id"],
            page=filters["page"],
            page_size=filters["page_size"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
    items = []
    for row in query_result["items"]:
        items.append(
            {
                **row,
                "target_type_label": _target_type_label(row.get("target_type")),
                "action_type_label": _action_type_label(row.get("action_type")),
                "target_href": _target_href(_normalized_text(row.get("target_type")), _normalized_text(row.get("target_id"))),
                "detail_href": _build_href("/admin/audit", {**filters, "log_id": row["id"]}),
                "before_preview": _log_preview_text(row.get("before_json") or {}),
                "after_preview": _log_preview_text(row.get("after_json") or {}),
                "before_pretty": _pretty_json(row.get("before_json") or {}),
                "after_pretty": _pretty_json(row.get("after_json") or {}),
            }
        )
    selected_log_id = _normalized_int(args.get("log_id"), default=0, minimum=0, maximum=10**9)
    selected_entry = next((item for item in items if int(item["id"]) == selected_log_id), None) if selected_log_id else None
    if not selected_entry and selected_log_id:
        row = repo.get_admin_operation_log(selected_log_id)
        if row:
            selected_entry = {
                **row,
                "target_type_label": _target_type_label(row.get("target_type")),
                "action_type_label": _action_type_label(row.get("action_type")),
                "target_href": _target_href(_normalized_text(row.get("target_type")), _normalized_text(row.get("target_id"))),
                "before_pretty": _pretty_json(row.get("before_json") or {}),
                "after_pretty": _pretty_json(row.get("after_json") or {}),
            }
    base_params = {key: value for key, value in filters.items() if key != "page"}
    page_numbers = []
    window_start = max(1, filters["page"] - 2)
    window_end = min(total_pages, filters["page"] + 2)
    for page_number in range(window_start, window_end + 1):
        page_numbers.append(
            {
                "label": str(page_number),
                "href": _build_href("/admin/audit", {**base_params, "page": page_number}),
                "active": page_number == filters["page"],
            }
        )
    sort_links = {
        item["key"]: _build_href(
            "/admin/audit",
            {
                **filters,
                "sort_by": item["key"],
                "sort_dir": "asc" if filters["sort_by"] == item["key"] and filters["sort_dir"] == "desc" else "desc",
                "page": 1,
            },
        )
        for item in SORTABLE_COLUMNS
    }
    return {
        "filters": filters,
        "items": items,
        "selected_entry": selected_entry or {},
        "summary_cards": [
            {"label": "操作记录", "value": total, "description": "当前筛选结果总数"},
            {"label": "操作人", "value": len({item["operator"] for item in items if _normalized_text(item.get("operator"))}), "description": "当前页涉及的操作人数"},
            {"label": "模块", "value": len({item["target_type"] for item in items if _normalized_text(item.get("target_type"))}), "description": "当前页涉及的模块数量"},
            {
                "label": "高风险操作",
                "value": sum(
                    1
                    for item in items
                    if any(token in _normalized_text(item.get("action_type")) for token in ("execute_", "run_", "save_", "disable_", "enable_", "import_", "apply_"))
                ),
                "description": "当前页高风险操作数量",
            },
        ],
        "pagination": {
            "page": filters["page"],
            "page_size": filters["page_size"],
            "total": total,
            "total_pages": total_pages,
            "prev_href": _build_href("/admin/audit", {**base_params, "page": filters["page"] - 1}) if filters["page"] > 1 else "",
            "next_href": _build_href("/admin/audit", {**base_params, "page": filters["page"] + 1}) if filters["page"] < total_pages else "",
            "page_links": page_numbers,
        },
        "sort_columns": SORTABLE_COLUMNS,
        "sort_links": sort_links,
        "operator_options": repo.list_distinct_values("operator"),
        "action_type_options": [{"value": item, "label": _action_type_label(item)} for item in repo.list_distinct_values("action_type")],
        "target_type_options": [{"value": item, "label": _target_type_label(item)} for item in repo.list_distinct_values("target_type")],
        "shareable_href": _build_href("/admin/audit", filters),
    }


