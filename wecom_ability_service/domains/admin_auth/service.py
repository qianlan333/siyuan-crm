from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from flask import current_app

from ..admin_config import repo as admin_config_repo
from ...infra.settings import get_setting
from ...wecom_client import WeComClient
from . import repo

ROLE_LABELS = {
    "super_admin": "超级管理员",
    "automation_admin": "自动化管理员",
    "questionnaire_admin": "问卷管理员",
    "config_admin": "配置管理员",
    "viewer": "只读查看者",
}

MODULE_LABELS = {
    "automation_conversion": "自动化运营",
    "customers": "客户",
    "questionnaires": "问卷",
    "config": "配置",
    "api_docs": "API 文档",
    "sunset": "已下线模块",
}

ROLE_MODULE_ACCESS = {
    "super_admin": {"automation_conversion", "customers", "questionnaires", "config", "api_docs", "sunset"},
    "automation_admin": {"automation_conversion", "customers", "api_docs", "sunset"},
    "questionnaire_admin": {"questionnaires", "api_docs", "sunset"},
    "config_admin": {"config", "api_docs", "sunset"},
    "viewer": {"automation_conversion", "customers", "questionnaires", "config", "api_docs", "sunset"},
}

READ_ONLY_ROLES = {"viewer"}
ADMIN_LEVEL_LABELS = {
    "super_admin": "超级管理员",
    "admin": "管理员",
}

ADMIN_ROLE_OPTIONS = [{"value": code, "label": label} for code, label in ROLE_LABELS.items()]
ADMIN_ASSIGNABLE_ROLE_OPTIONS = [{"value": code, "label": label} for code, label in ROLE_LABELS.items() if code != "super_admin"]
WECOM_MEMBER_STATUS_LABELS = {
    1: "已激活",
    2: "已禁用",
    4: "未激活",
    5: "已退出",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalized_role_codes(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        candidates = list(value)
    elif value is None:
        candidates = []
    else:
        candidates = [item.strip() for item in str(value).split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        role_code = _normalized_text(candidate)
        if not role_code or role_code in seen:
            continue
        if role_code not in ROLE_LABELS:
            raise ValueError("角色不合法")
        deduped.append(role_code)
        seen.add(role_code)
    if not deduped:
        raise ValueError("至少选择一个角色")
    return deduped


def _normalized_admin_level(value: Any, *, role_codes: list[str] | None = None) -> str:
    admin_level = _normalized_text(value)
    if not admin_level and role_codes and "super_admin" in role_codes:
        return "super_admin"
    if not admin_level:
        return "admin"
    if admin_level not in ADMIN_LEVEL_LABELS:
        raise ValueError("管理员层级不合法")
    return admin_level


def _role_codes_for_admin_level(admin_level: str, role_codes: list[str]) -> list[str]:
    if admin_level == "super_admin":
        return ["super_admin"]
    filtered = [role_code for role_code in role_codes if role_code != "super_admin"]
    if not filtered:
        raise ValueError("普通管理员至少选择一个业务角色")
    return filtered


def _validate_wecom_userid(value: Any) -> str:
    wecom_userid = _normalized_text(value)
    if not wecom_userid:
        raise ValueError("企微成员 UserId 不能为空")
    if len(wecom_userid) > 128:
        raise ValueError("企微成员 UserId 过长")
    return wecom_userid


def _role_labels(role_codes: Iterable[str]) -> list[str]:
    return [ROLE_LABELS.get(role_code, role_code) for role_code in role_codes]


def _setting_or_config(key: str, config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = dict(current_app.config)
    return _normalized_text(get_setting(key)) or _normalized_text(config.get(key, ""))


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalized_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _directory_root_department_id() -> int:
    raw_value = _setting_or_config("WECOM_DIRECTORY_ROOT_DEPARTMENT_ID") or "1"
    return max(1, _normalized_int(raw_value, default=1))


def is_break_glass_login_enabled() -> bool:
    value = _setting_or_config("ADMIN_BREAK_GLASS_LOGIN_ENABLED")
    return value.lower() in {"1", "true", "yes", "on"}


def _present_admin_users(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_rows = repo.list_admin_user_roles([int(row.get("id") or 0) for row in rows if int(row.get("id") or 0) > 0])
    role_map: dict[int, list[str]] = {}
    for role_row in role_rows:
        user_id = int(role_row.get("admin_user_id") or 0)
        if user_id <= 0:
            continue
        role_map.setdefault(user_id, []).append(_normalized_text(role_row.get("role_code")))
    presented: list[dict[str, Any]] = []
    for row in rows:
        user_id = int(row.get("id") or 0)
        role_codes = [role_code for role_code in role_map.get(user_id, []) if role_code]
        presented.append(
            {
                "id": user_id,
                "wecom_userid": _normalized_text(row.get("wecom_userid")),
                "wecom_corpid": _normalized_text(row.get("wecom_corpid")),
                "display_name": _normalized_text(row.get("display_name")) or _normalized_text(row.get("wecom_userid")),
                "roles": role_codes,
                "role_labels": _role_labels(role_codes),
                "roles_display": " / ".join(_role_labels(role_codes)) or "-",
                "is_active": bool(row.get("is_active")),
                "login_enabled": bool(row.get("login_enabled")),
                "admin_level": _normalized_text(row.get("admin_level")) or ("super_admin" if "super_admin" in role_codes else "admin"),
                "admin_level_label": ADMIN_LEVEL_LABELS.get(
                    _normalized_text(row.get("admin_level")) or ("super_admin" if "super_admin" in role_codes else "admin"),
                    "管理员",
                ),
                "auth_source": _normalized_text(row.get("auth_source")) or "wecom_sso",
                "last_login_at": _normalized_text(row.get("last_login_at")),
                "created_by": _normalized_text(row.get("created_by")),
                "updated_by": _normalized_text(row.get("updated_by")),
                "created_at": _normalized_text(row.get("created_at")),
                "updated_at": _normalized_text(row.get("updated_at")),
            }
        )
    return presented


def _present_directory_members(
    rows: list[dict[str, Any]],
    *,
    admin_users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    admin_by_identity = {
        (_normalized_text(user.get("wecom_corpid")), _normalized_text(user.get("wecom_userid"))): user
        for user in admin_users
        if _normalized_text(user.get("wecom_userid"))
    }
    presented: list[dict[str, Any]] = []
    for row in rows:
        department_ids = [_normalized_text(item) for item in _json_list(row.get("department_ids_json")) if _normalized_text(item)]
        status_code = _normalized_int(row.get("wecom_status"), default=0)
        corpid = _normalized_text(row.get("wecom_corpid"))
        userid = _normalized_text(row.get("wecom_userid"))
        authorized_user = admin_by_identity.get((corpid, userid)) or admin_by_identity.get(("", userid))
        is_authorized = bool(authorized_user)
        presented.append(
            {
                "id": int(row.get("id") or 0),
                "wecom_corpid": corpid,
                "wecom_userid": userid,
                "display_name": _normalized_text(row.get("display_name")) or userid,
                "department_ids": department_ids,
                "department_ids_display": " / ".join(department_ids),
                "position": _normalized_text(row.get("position")),
                "wecom_status": status_code,
                "status_label": WECOM_MEMBER_STATUS_LABELS.get(status_code, "未知" if status_code else "-"),
                "is_active": bool(row.get("is_active")),
                "synced_at": _normalized_text(row.get("synced_at")),
                "is_authorized": is_authorized,
                "admin_user_id": int((authorized_user or {}).get("id") or 0),
                "admin_is_active": bool((authorized_user or {}).get("is_active")),
                "admin_login_enabled": bool((authorized_user or {}).get("login_enabled")),
                "admin_level": _normalized_text((authorized_user or {}).get("admin_level")),
                "admin_level_label": _normalized_text((authorized_user or {}).get("admin_level_label")),
                "admin_roles_display": _normalized_text((authorized_user or {}).get("roles_display")) if authorized_user else "",
                "authorization_label": _normalized_text((authorized_user or {}).get("admin_level_label")) if is_authorized else "未授权",
            }
        )
    return presented


def _is_super_admin_user(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return _normalized_text(user.get("admin_level")) == "super_admin" or "super_admin" in list(user.get("roles") or [])


def admin_user_can_login(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return bool(user.get("is_active")) and bool(user.get("login_enabled")) and bool(user.get("roles"))


def count_admin_users() -> int:
    return repo.count_admin_users()


def get_admin_user_by_id(user_id: int | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    row = repo.get_admin_user_by_id(int(user_id))
    rows = _present_admin_users([row] if row else [])
    return rows[0] if rows else None


def get_admin_user_by_wecom_userid(wecom_userid: str, *, wecom_corpid: str = "") -> dict[str, Any] | None:
    row = repo.get_admin_user_by_wecom_userid(wecom_userid, wecom_corpid=wecom_corpid)
    rows = _present_admin_users([row] if row else [])
    return rows[0] if rows else None


def touch_admin_user_login(user_id: int) -> None:
    repo.update_admin_user_last_login(int(user_id))


def record_admin_login(
    *,
    admin_user_id: int | None,
    login_type: str,
    login_result: str,
    ip: str,
    user_agent: str,
) -> None:
    repo.insert_admin_login_audit(
        admin_user_id=admin_user_id,
        login_type=login_type,
        login_result=login_result,
        ip=ip,
        user_agent=user_agent,
    )


def admin_role_can_access_module(role_codes: str | Iterable[str], module_key: str, *, write: bool = False) -> bool:
    if isinstance(role_codes, str):
        normalized_roles = [_normalized_text(role_codes)]
    else:
        normalized_roles = [_normalized_text(role_code) for role_code in role_codes]
    effective_roles = [role_code for role_code in normalized_roles if role_code]
    if "super_admin" in effective_roles:
        return True
    normalized_module = _normalized_text(module_key) or "sunset"
    if write:
        return any(
            normalized_module in ROLE_MODULE_ACCESS.get(role_code, set()) and role_code not in READ_ONLY_ROLES
            for role_code in effective_roles
        )
    return any(normalized_module in ROLE_MODULE_ACCESS.get(role_code, set()) for role_code in effective_roles)


def build_admin_account_page_payload() -> dict[str, Any]:
    rows = _present_admin_users(repo.list_admin_users())
    corp_id = _setting_or_config("WECOM_CORP_ID")
    directory_members = _present_directory_members(
        repo.list_admin_wecom_directory_members(wecom_corpid=corp_id),
        admin_users=rows,
    )
    login_audit_rows = repo.list_admin_login_audit(limit=20)
    return {
        "rows": rows,
        "super_admin_rows": [row for row in rows if row.get("admin_level") == "super_admin"],
        "admin_rows": [row for row in rows if row.get("admin_level") != "super_admin"],
        "directory_members": directory_members,
        "directory_summary": {
            "count": len(directory_members),
            "last_synced_at": max([row["synced_at"] for row in directory_members if row.get("synced_at")] or [""]),
            "active_count": sum(1 for row in directory_members if row.get("is_active")),
            "authorized_count": sum(1 for row in directory_members if row.get("is_authorized")),
        },
        "role_options": list(ADMIN_ROLE_OPTIONS),
        "assignable_role_options": list(ADMIN_ASSIGNABLE_ROLE_OPTIONS),
        "admin_level_labels": dict(ADMIN_LEVEL_LABELS),
        "role_labels": dict(ROLE_LABELS),
        "break_glass_enabled": is_break_glass_login_enabled(),
        "auth_mode": _setting_or_config("ADMIN_AUTH_MODE") or "wecom_sso",
        "corp_id": corp_id,
        "login_audit_rows": [
            {
                "id": int(row.get("id") or 0),
                "admin_user_id": int(row.get("admin_user_id") or 0) if row.get("admin_user_id") else None,
                "wecom_userid": _normalized_text(row.get("wecom_userid")),
                "display_name": _normalized_text(row.get("display_name")),
                "login_type": _normalized_text(row.get("login_type")),
                "login_result": _normalized_text(row.get("login_result")),
                "ip": _normalized_text(row.get("ip")),
                "user_agent": _normalized_text(row.get("user_agent")),
                "created_at": _normalized_text(row.get("created_at")),
            }
            for row in login_audit_rows
        ],
    }


def sync_admin_wecom_directory_members(*, operator: str = "crm_console") -> dict[str, Any]:
    client = WeComClient.from_contact_app()
    department_id = _directory_root_department_id()
    payload = client.list_department_users(department_id=department_id, fetch_child=1)
    userlist = payload.get("userlist") or []
    if not isinstance(userlist, list):
        userlist = []
    synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    members: list[dict[str, Any]] = []
    skipped_count = 0
    for item in userlist:
        if not isinstance(item, dict):
            skipped_count += 1
            continue
        userid = _normalized_text(item.get("userid"))
        if not userid:
            skipped_count += 1
            continue
        status = _normalized_int(item.get("status"), default=1)
        department_ids = item.get("department") if isinstance(item.get("department"), list) else []
        members.append(
            {
                "wecom_userid": userid,
                "display_name": _normalized_text(item.get("name")) or userid,
                "department_ids_json": _json_dumps([_normalized_text(value) for value in department_ids if _normalized_text(value)]),
                "position": _normalized_text(item.get("position")),
                "wecom_status": status,
                "is_active": status in {0, 1},
                "raw_payload_json": _json_dumps(
                    {
                        "userid": userid,
                        "name": _normalized_text(item.get("name")),
                        "department": department_ids,
                        "position": _normalized_text(item.get("position")),
                        "status": status,
                    }
                ),
            }
        )
    synced_count = repo.upsert_admin_wecom_directory_members(
        wecom_corpid=_normalized_text(client.corp_id),
        members=members,
        synced_at=synced_at,
    )
    admin_config_repo.insert_admin_operation_log(
        operator=_normalized_text(operator) or "crm_console",
        action_type="sync_admin_wecom_directory",
        target_type="admin_wecom_directory_members",
        target_id=_normalized_text(client.corp_id),
        before_json={"department_id": department_id},
        after_json={
            "synced_count": synced_count,
            "skipped_count": skipped_count,
            "department_id": department_id,
            "corp_id": _normalized_text(client.corp_id),
        },
    )
    return {
        "corp_id": _normalized_text(client.corp_id),
        "department_id": department_id,
        "synced_count": synced_count,
        "skipped_count": skipped_count,
        "synced_at": synced_at,
    }


def _validate_admin_management_change(
    *,
    existing: dict[str, Any] | None,
    target_user_id: int | None,
    wecom_corpid: str,
    admin_level: str,
    is_active: bool,
    login_enabled: bool,
    actor_user: dict[str, Any] | None,
    confirm_super_admin_transfer: bool,
) -> None:
    actor_is_super_admin = _is_super_admin_user(actor_user) or actor_user is None
    existing_is_super_admin = _normalized_text((existing or {}).get("admin_level")) == "super_admin"
    target_is_super_admin = admin_level == "super_admin"
    if (existing_is_super_admin or target_is_super_admin) and not actor_is_super_admin:
        raise ValueError("只有超级管理员可以创建、转让或修改超级管理员")
    if target_is_super_admin and (not is_active or not login_enabled):
        raise ValueError("超级管理员必须保持启用并允许登录")

    active_super_admins = _present_admin_users(repo.list_active_super_admin_users(wecom_corpid=wecom_corpid))
    active_super_admin_ids = {int(row.get("id") or 0) for row in active_super_admins}
    target_id = int(target_user_id or 0)

    removing_current_super_admin = existing_is_super_admin and (
        not target_is_super_admin or not is_active or not login_enabled
    )
    if removing_current_super_admin and active_super_admin_ids == {target_id}:
        raise ValueError("不能停用或降级唯一超级管理员，请先转让超级管理员身份")

    other_super_admin_ids = {user_id for user_id in active_super_admin_ids if user_id != target_id}
    if target_is_super_admin and other_super_admin_ids and not confirm_super_admin_transfer:
        raise ValueError("当前企业已有超级管理员；如需转让，请勾选确认转让超级管理员")


def _demote_other_super_admins(
    *,
    target_user_id: int,
    wecom_corpid: str,
    operator: str,
) -> list[dict[str, Any]]:
    demoted: list[dict[str, Any]] = []
    for row in _present_admin_users(repo.list_active_super_admin_users(wecom_corpid=wecom_corpid)):
        if int(row.get("id") or 0) == int(target_user_id):
            continue
        demoted.append(row)
        repo.update_admin_user(
            user_id=int(row["id"]),
            wecom_userid=_normalized_text(row.get("wecom_userid")),
            wecom_corpid=_normalized_text(row.get("wecom_corpid")),
            display_name=_normalized_text(row.get("display_name")),
            is_active=bool(row.get("is_active")),
            login_enabled=bool(row.get("login_enabled")),
            admin_level="admin",
            auth_source=_normalized_text(row.get("auth_source")) or "wecom_sso",
            updated_by=operator,
        )
        repo.replace_admin_user_roles(
            admin_user_id=int(row["id"]),
            role_codes=["automation_admin", "questionnaire_admin", "config_admin"],
        )
    return demoted


def save_admin_user(
    payload: dict[str, Any],
    *,
    operator: str = "crm_console",
    actor_user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_id = int(payload.get("id") or 0) or None
    wecom_userid = _validate_wecom_userid(payload.get("wecom_userid"))
    wecom_corpid = _normalized_text(payload.get("wecom_corpid")) or _setting_or_config("WECOM_CORP_ID")
    directory_member = repo.get_admin_wecom_directory_member(wecom_userid, wecom_corpid=wecom_corpid)
    display_name = (
        _normalized_text(payload.get("display_name"))
        or _normalized_text((directory_member or {}).get("display_name"))
        or wecom_userid
    )
    is_active = _normalized_bool(payload.get("is_active"), default=True)
    login_enabled = _normalized_bool(payload.get("login_enabled"), default=True)
    auth_source = _normalized_text(payload.get("auth_source")) or "wecom_sso"
    raw_role_value = payload.get("role_codes") or payload.get("role_code")
    admin_level_hint = _normalized_admin_level(payload.get("admin_level"))
    if admin_level_hint == "super_admin" and not raw_role_value:
        raw_role_codes = ["super_admin"]
    else:
        raw_role_codes = _normalized_role_codes(raw_role_value)
    admin_level = _normalized_admin_level(payload.get("admin_level"), role_codes=raw_role_codes)
    role_codes = _role_codes_for_admin_level(admin_level, raw_role_codes)
    normalized_operator = _normalized_text(operator) or "crm_console"
    confirm_super_admin_transfer = _normalized_bool(payload.get("confirm_super_admin_transfer"), default=False)

    existing_by_userid = repo.get_admin_user_by_wecom_userid(wecom_userid, wecom_corpid=wecom_corpid)
    if existing_by_userid and int(existing_by_userid.get("id") or 0) != int(user_id or 0):
        raise ValueError("该企微成员已经授权")

    existing = get_admin_user_by_id(int(user_id)) if user_id else None
    _validate_admin_management_change(
        existing=existing,
        target_user_id=user_id,
        wecom_corpid=wecom_corpid,
        admin_level=admin_level,
        is_active=is_active,
        login_enabled=login_enabled,
        actor_user=actor_user,
        confirm_super_admin_transfer=confirm_super_admin_transfer,
    )

    if user_id:
        if not existing:
            raise ValueError("授权成员不存在")
        demoted_super_admins = []
        if admin_level == "super_admin":
            demoted_super_admins = _demote_other_super_admins(
                target_user_id=int(user_id),
                wecom_corpid=wecom_corpid,
                operator=normalized_operator,
            )
        repo.update_admin_user(
            user_id=int(user_id),
            wecom_userid=wecom_userid,
            wecom_corpid=wecom_corpid,
            display_name=display_name,
            is_active=is_active,
            login_enabled=login_enabled,
            admin_level=admin_level,
            auth_source=auth_source,
            updated_by=normalized_operator,
        )
        repo.replace_admin_user_roles(admin_user_id=int(user_id), role_codes=role_codes)
        saved = get_admin_user_by_id(int(user_id))
        admin_config_repo.insert_admin_operation_log(
            operator=normalized_operator,
            action_type="update_admin_user",
            target_type="admin_user",
            target_id=wecom_userid,
            before_json={"user": existing or {}, "demoted_super_admins": demoted_super_admins},
            after_json={"user": saved or {}},
        )
        if not saved:
            raise ValueError("保存授权成员失败")
        return saved

    created_id = repo.insert_admin_user(
        wecom_userid=wecom_userid,
        wecom_corpid=wecom_corpid,
        display_name=display_name,
        is_active=is_active,
        login_enabled=login_enabled,
        admin_level=admin_level,
        auth_source=auth_source,
        created_by=normalized_operator,
        updated_by=normalized_operator,
    )
    demoted_super_admins = []
    if admin_level == "super_admin":
        demoted_super_admins = _demote_other_super_admins(
            target_user_id=created_id,
            wecom_corpid=wecom_corpid,
            operator=normalized_operator,
        )
    repo.replace_admin_user_roles(admin_user_id=created_id, role_codes=role_codes)
    saved = get_admin_user_by_id(created_id)
    admin_config_repo.insert_admin_operation_log(
        operator=normalized_operator,
        action_type="create_admin_user",
        target_type="admin_user",
        target_id=wecom_userid,
        before_json={"demoted_super_admins": demoted_super_admins},
        after_json={"user": saved or {}},
    )
    if not saved:
        raise ValueError("创建授权成员失败")
    return saved
