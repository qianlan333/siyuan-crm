from __future__ import annotations

import json
from typing import Any

from flask import current_app

from ...application.customer_read_model import CustomerDetailQueryDTO, GetCustomerDetailQuery
from ...application.class_user.commands import MigrateClassUserStatusFromContactTagsCommand
from ...application.class_user.dto import (
    ListClassUserManagementRecordsQueryDTO,
    ListClassUserStatusHistoryQueryDTO,
)
from ...application.class_user.queries import (
    ListClassUserManagementRecordsQuery,
    ListClassUserStatusHistoryQuery,
)
from ...application.identity_contact.queries import CountExternalContactIdentityMapsQuery
from ...application.questionnaire.commands import (
    DisableQuestionnaireCommand,
    UpdateQuestionnaireCommand,
)
from ...application.questionnaire.dto import (
    DisableQuestionnaireCommandDTO,
    GetLatestQuestionnaireSubmitDebugQueryDTO,
    GetQuestionnaireDetailQueryDTO,
    ListQuestionnairesQueryDTO,
    UpdateQuestionnaireCommandDTO,
)
from ...application.questionnaire.queries import (
    GetLatestQuestionnaireSubmitDebugQuery,
    GetQuestionnaireDetailQuery,
    ListQuestionnairesQuery,
)
from ...application.routing_config.dto import (
    GetOwnerRoleQueryDTO,
    ResolveContactRoutingContextQueryDTO,
)
from ...application.routing_config.queries import (
    GetOwnerRoleQuery,
    ResolveContactRoutingContextQuery,
)
from ...domains.archive.service import extract_roomid_from_raw_payload, format_message_row
from ...domains.group_chats.repo import get_group_chat_map
from ...domains.tags.service import get_signup_status_definition
from ...infra.json_utils import safe_json_loads as _json_loads
from ...infra.settings import get_setting
from ..questionnaire import build_questionnaire_preflight_payload
from ..questionnaire.preflight_service import runtime_config_value
from ..tags.service import mark_customer_tags, unmark_customer_tags
from ..tasks.service import dispatch_wecom_task
from . import repo
from .customer_profile_service import (
    build_customer_detail_payload as build_customer_profile_page_payload,
    build_customer_list_payload as build_customer_search_payload,
)

def count_external_contact_identity_maps() -> int:
    return CountExternalContactIdentityMapsQuery()()

def get_owner_role(userid: str):
    return GetOwnerRoleQuery()(GetOwnerRoleQueryDTO(userid=str(userid or "").strip()))

def resolve_contact_routing_context(owner_userid: str, owner_role: str, signup_status: str):
    definition = get_signup_status_definition(signup_status)
    return ResolveContactRoutingContextQuery()(
        ResolveContactRoutingContextQueryDTO(
            owner_userid=str(owner_userid or "").strip(),
            owner_role=str(owner_role or "").strip(),
            signup_status=str(signup_status or "").strip(),
            routing_alias=str(definition.get("routing_alias") or "") if definition else "",
        )
    )

def list_class_user_management_records(signup_status: str = ""):
    return ListClassUserManagementRecordsQuery()(
        ListClassUserManagementRecordsQueryDTO(signup_status=str(signup_status or "").strip())
    )

def list_class_user_status_history(limit: int = 100):
    return ListClassUserStatusHistoryQuery()(ListClassUserStatusHistoryQueryDTO(limit=int(limit)))

def migrate_class_user_status_from_contact_tags():
    return MigrateClassUserStatusFromContactTagsCommand()()

def list_questionnaires(*, include_disabled: bool = False, include_stats: bool = True):
    return ListQuestionnairesQuery()(
        ListQuestionnairesQueryDTO(include_disabled=bool(include_disabled), include_stats=bool(include_stats))
    )

def get_questionnaire_detail(questionnaire_id: int):
    return GetQuestionnaireDetailQuery()(GetQuestionnaireDetailQueryDTO(questionnaire_id=int(questionnaire_id)))

def get_latest_questionnaire_submit_debug(questionnaire_id: int):
    return GetLatestQuestionnaireSubmitDebugQuery()(
        GetLatestQuestionnaireSubmitDebugQueryDTO(questionnaire_id=int(questionnaire_id))
    )

def update_questionnaire(questionnaire_id: int, payload: dict):
    return UpdateQuestionnaireCommand()(
        UpdateQuestionnaireCommandDTO(questionnaire_id=int(questionnaire_id), payload=dict(payload or {}))
    )

def disable_questionnaire(questionnaire_id: int, is_disabled: bool = True):
    return DisableQuestionnaireCommand()(
        DisableQuestionnaireCommandDTO(questionnaire_id=int(questionnaire_id), is_disabled=bool(is_disabled))
    )

TARGET_CUSTOMER_TAG_ACTION = "customer_tag_action"
TARGET_CUSTOMER_TASK_ACTION = "customer_task_action"
TARGET_QUESTIONNAIRE_ACTION = "questionnaire_console_action"
TARGET_OPERATIONS_ACTION = "operations_console_action"

OPERATIONS_TABS = (
    {"key": "class-users", "label": "班级状态"},
    {"key": "class-history", "label": "班级状态历史"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()

def _normalized_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))

def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}

def _ui_status_label(value: Any) -> str:
    mapping = {
        "success": "成功",
        "failed": "失败",
        "pending": "待处理",
        "processing": "处理中",
        "running": "运行中",
        "acked": "已确认",
        "disabled": "已停用",
        "enabled": "已启用",
    }
    normalized = _normalized_text(value).lower()
    return mapping.get(normalized, _normalized_text(value) or "-")

def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)

def _operator(value: Any) -> str:
    return _normalized_text(value) or "crm_console"

def _split_csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_normalized_text(item) for item in value if _normalized_text(item)]
    normalized = _normalized_text(value)
    if not normalized:
        return []
    parts = normalized.replace("\n", ",").replace("，", ",").split(",")
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = _normalized_text(part)
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped

def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    # Delegates to the unified entry in admin_audit so all three legacy
    # _audit_log shims share one row format + structured-log emission.
    from ..admin_audit import record_audit

    record_audit(
        operator=_operator(operator),
        action_type=_normalized_text(action_type),
        target_type=_normalized_text(target_type),
        target_id=_normalized_text(target_id),
        before=before or {},
        after=after or {},
    )

def build_customer_list_payload(args: Any) -> dict[str, Any]:
    return build_customer_search_payload(args)

def _load_customer_detail(external_userid: str) -> dict[str, Any] | None:
    return GetCustomerDetailQuery()(CustomerDetailQueryDTO(external_userid=_normalized_text(external_userid)))

def _build_recent_messages(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = repo.list_recent_customer_messages(external_userid, limit=limit)
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        message = format_message_row(row, group_map=group_map)
        items.append(
            {
                "id": int(row["id"]),
                "send_time": _normalized_text(row.get("send_time")) or _normalized_text(row.get("created_at")),
                "chat_type": _normalized_text(row.get("chat_type")),
                "msgtype": _normalized_text(message.get("msgtype") or row.get("msgtype")),
                "sender": _normalized_text(message.get("from") or row.get("sender")),
                "receiver": _normalized_text(row.get("receiver")),
                "content": _normalized_text(message.get("content") or row.get("content")),
                "room_name": _normalized_text(message.get("room_name")),
                "raw_payload": message,
            }
        )
    return items

def _build_customer_questionnaire_rows(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = repo.list_customer_questionnaire_history(external_userid, limit=limit)
    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
                "scrm_apply_status_label": _ui_status_label(row.get("scrm_apply_status")),
            }
        )
    return results

def build_customer_detail_payload(external_userid: str) -> dict[str, Any] | None:
    return build_customer_profile_page_payload(external_userid)

def preview_customer_tag_action(
    *,
    external_userid: str,
    userid: str,
    action: str,
    tag_ids: list[str],
) -> dict[str, Any]:
    detail = _load_customer_detail(external_userid)
    if not detail:
        raise ValueError("未找到客户")
    normalized_action = _normalized_text(action)
    if normalized_action not in {"mark", "unmark"}:
        raise ValueError("标签操作类型不正确")
    normalized_userid = _normalized_text(userid) or _normalized_text(detail.get("owner_userid"))
    if not normalized_userid:
        raise ValueError("负责人账号不能为空")
    normalized_tag_ids = _split_csv(tag_ids)
    if not normalized_tag_ids:
        raise ValueError("请填写标签编号")
    current_tags = [dict(item) for item in (detail.get("tags") or [])]
    return {
        "ok": True,
        "dry_run": True,
        "would_execute": True,
        "action": normalized_action,
        "external_userid": _normalized_text(external_userid),
        "userid": normalized_userid,
        "tag_ids": normalized_tag_ids,
        "current_tags": current_tags,
        "preview_payload": {
            "userid": normalized_userid,
            "external_userid": _normalized_text(external_userid),
            "add_tag": normalized_tag_ids if normalized_action == "mark" else [],
            "remove_tag": normalized_tag_ids if normalized_action == "unmark" else [],
        },
    }

def execute_customer_tag_action(
    *,
    external_userid: str,
    userid: str,
    action: str,
    tag_ids: list[str],
    operator: str,
) -> dict[str, Any]:
    preview = preview_customer_tag_action(
        external_userid=external_userid,
        userid=userid,
        action=action,
        tag_ids=tag_ids,
    )
    payload = dict(preview["preview_payload"])
    if preview["action"] == "mark":
        result = mark_customer_tags(payload)
    else:
        result = unmark_customer_tags(payload)
    after_detail = _load_customer_detail(external_userid) or {}
    _audit_log(
        operator=operator,
        action_type=f"execute_{preview['action']}",
        target_type=TARGET_CUSTOMER_TAG_ACTION,
        target_id=_normalized_text(external_userid),
        before={"tags": preview["current_tags"], "userid": preview["userid"]},
        after={
            "tags": after_detail.get("tags") or [],
            "payload": payload,
            "result": result,
        },
    )
    return {
        **preview,
        "dry_run": False,
        "executed": True,
        "result": result,
        "current_tags": after_detail.get("tags") or [],
    }

def preview_customer_task_action(
    *,
    external_userid: str,
    task_type: str,
    userid: str,
    content: str,
) -> dict[str, Any]:
    detail = _load_customer_detail(external_userid)
    if not detail:
        raise ValueError("未找到客户")
    normalized_task_type = _normalized_text(task_type)
    if normalized_task_type not in {"private_message", "group_message", "moment"}:
        raise ValueError("任务类型不正确")
    normalized_userid = _normalized_text(userid) or _normalized_text(detail.get("owner_userid"))
    normalized_content = _normalized_text(content)
    if not normalized_content:
        raise ValueError("请输入触达内容")
    if not normalized_userid:
        raise ValueError("负责人账号不能为空")
    if normalized_task_type == "private_message":
        payload = {
            "chat_type": "single",
            "external_userid": [_normalized_text(external_userid)],
            "sender": normalized_userid,
            "text": {"content": normalized_content},
        }
    elif normalized_task_type == "group_message":
        payload = {
            "chat_type": "group",
            "external_userid": [_normalized_text(external_userid)],
            "sender": normalized_userid,
            "text": {"content": normalized_content},
        }
    else:
        payload = {
            "visible_range": {"sender_list": {"userid": [normalized_userid]}},
            "text": {"content": normalized_content},
        }
    return {
        "ok": True,
        "dry_run": True,
        "would_execute": True,
        "external_userid": _normalized_text(external_userid),
        "task_type": normalized_task_type,
        "userid": normalized_userid,
        "content": normalized_content,
        "preview_payload": payload,
    }

def execute_customer_task_action(
    *,
    external_userid: str,
    task_type: str,
    userid: str,
    content: str,
    operator: str,
) -> dict[str, Any]:
    preview = preview_customer_task_action(
        external_userid=external_userid,
        task_type=task_type,
        userid=userid,
        content=content,
    )
    mapping = {
        "private_message": "create_private_message_task",
        "group_message": "create_group_message_task",
        "moment": "create_moment_task",
    }
    result = dispatch_wecom_task(preview["task_type"], mapping[preview["task_type"]], dict(preview["preview_payload"]))
    _audit_log(
        operator=operator,
        action_type=f"execute_{preview['task_type']}",
        target_type=TARGET_CUSTOMER_TASK_ACTION,
        target_id=_normalized_text(external_userid),
        before={"preview_payload": preview["preview_payload"]},
        after=result,
    )
    return {
        **preview,
        "dry_run": False,
        "executed": True,
        "result": result,
    }

def _questionnaire_paths(slug: str) -> dict[str, str]:
    normalized_slug = _normalized_text(slug)
    return {
        "public_path": f"/s/{normalized_slug}" if normalized_slug else "",
        "submitted_path": f"/s/{normalized_slug}/submitted" if normalized_slug else "",
    }

def build_questionnaire_index_payload() -> dict[str, Any]:
    questionnaires = []
    for item in list_questionnaires():
        questionnaires.append({**item, **_questionnaire_paths(_normalized_text(item.get("slug")))})
    preflight_error = ""
    try:
        def _lightweight_tag_probe() -> list[dict[str, Any]]:
            required_keys = ["WECOM_CORP_ID", "WECOM_SECRET", "WECOM_API_BASE"]
            missing = [key for key in required_keys if not runtime_config_value(current_app.config, key)]
            if missing:
                raise RuntimeError(f"缺少配置：{', '.join(missing)}")
            return [{"tag_id": "config-ok", "tag_name": "config-ok"}]

        preflight = build_questionnaire_preflight_payload(
            config=current_app.config,
            list_available_wecom_tags_fn=_lightweight_tag_probe,
            count_external_contact_identity_maps_fn=count_external_contact_identity_maps,
        )
    except Exception as exc:
        preflight = {
            "ok": False,
            "wechat_oauth_configured": False,
            "wecom_contact_configured": False,
            "debug_session_api_enabled": False,
            "questionnaire_admin_ui_enabled": True,
            "wecom_tags_api_available": False,
            "identity_map_available": False,
        }
        preflight_error = str(exc)
    return {
        "questionnaires": questionnaires,
        "preflight": preflight,
        "preflight_error": preflight_error,
    }

def build_questionnaire_detail_payload(questionnaire_id: int) -> dict[str, Any] | None:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        return None
    detail = {
        **questionnaire,
        **_questionnaire_paths(_normalized_text(questionnaire.get("slug"))),
    }
    return {
        "questionnaire": detail,
        "latest_submit_debug": get_latest_questionnaire_submit_debug(int(questionnaire_id)),
        "submissions": [
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
            }
            for row in repo.list_questionnaire_submissions(int(questionnaire_id), limit=50)
        ],
        "apply_logs": [
            {
                **row,
                "final_tags": _json_loads(row.get("final_tags"), default=[]),
                "status_label": _ui_status_label(row.get("status")),
            }
            for row in repo.list_questionnaire_apply_logs(int(questionnaire_id), limit=50)
        ],
    }

def parse_questionnaire_editor_form(form: Any) -> dict[str, Any]:
    questions_json = _normalized_text(form.get("questions_json"))
    score_rules_json = _normalized_text(form.get("score_rules_json"))
    questions = _json_loads(questions_json, default=[])
    score_rules = _json_loads(score_rules_json, default=[])
    if questions_json and not isinstance(questions, list):
        raise ValueError("题目内容必须是 JSON 数组")
    if score_rules_json and not isinstance(score_rules, list):
        raise ValueError("评分规则必须是 JSON 数组")
    return {
        "name": _normalized_text(form.get("name")),
        "slug": _normalized_text(form.get("slug")),
        "title": _normalized_text(form.get("title")),
        "description": _normalized_text(form.get("description")),
        "redirect_url": _normalized_text(form.get("redirect_url")),
        "external_push_enabled": _normalize_bool(form.get("external_push_enabled")),
        "external_push_url": _normalized_text(form.get("external_push_url")),
        "is_disabled": _normalize_bool(form.get("is_disabled")),
        "questions": questions,
        "score_rules": score_rules,
    }

def save_questionnaire_editor(
    questionnaire_id: int,
    *,
    form: Any,
    operator: str,
) -> dict[str, Any]:
    before = get_questionnaire_detail(int(questionnaire_id))
    if not before:
        raise ValueError("未找到问卷")
    payload = parse_questionnaire_editor_form(form)
    updated = update_questionnaire(int(questionnaire_id), payload)
    if not updated:
        raise ValueError("未找到问卷")
    _audit_log(
        operator=operator,
        action_type="save_questionnaire",
        target_type=TARGET_QUESTIONNAIRE_ACTION,
        target_id=str(int(questionnaire_id)),
        before=before,
        after=updated,
    )
    return updated

def toggle_questionnaire_disabled(questionnaire_id: int, *, is_disabled: bool, operator: str) -> dict[str, Any]:
    before = get_questionnaire_detail(int(questionnaire_id))
    if not before:
        raise ValueError("未找到问卷")
    updated = disable_questionnaire(int(questionnaire_id), is_disabled)
    if not updated:
        raise ValueError("未找到问卷")
    _audit_log(
        operator=operator,
        action_type="disable_questionnaire" if is_disabled else "enable_questionnaire",
        target_type=TARGET_QUESTIONNAIRE_ACTION,
        target_id=str(int(questionnaire_id)),
        before=before,
        after=updated,
    )
    return updated

def operations_tabs(active_key: str) -> list[dict[str, Any]]:
    normalized = _normalized_text(active_key) or "class-users"
    return [
        {
            **item,
            "active": item["key"] == normalized,
            "href": f"/admin/class-users?tab={item['key']}",
        }
        for item in OPERATIONS_TABS
    ]

def build_operations_payload(args: Any) -> dict[str, Any]:
    active_tab = _normalized_text(args.get("tab")) or "class-users"
    if active_tab not in {item["key"] for item in OPERATIONS_TABS}:
        active_tab = "class-users"
    class_status_filter = _normalized_text(args.get("signup_status"))
    history_limit = _normalized_int(args.get("limit"), default=100, minimum=1, maximum=200)
    class_user_payload = list_class_user_management_records(signup_status=class_status_filter) if active_tab == "class-users" else {}
    class_history_payload = list_class_user_status_history(limit=history_limit) if active_tab == "class-history" else {}
    return {
        "active_tab": active_tab,
        "tabs": operations_tabs(active_tab),
        "class_status_filter": class_status_filter,
        "class_user_list": class_user_payload,
        "class_user_history": class_history_payload,
        "mcp_auth_configured": bool(_normalized_text(get_setting("MCP_BEARER_TOKEN"))),
    }
