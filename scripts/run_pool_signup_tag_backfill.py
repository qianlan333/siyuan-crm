#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from wecom_ability_service import create_app
from wecom_ability_service.domains.automation_conversion import repo as automation_repo
from wecom_ability_service.domains.automation_conversion.local_projection import POOL_TO_STAGE_DEF
from wecom_ability_service.domains.class_user.service import (
    apply_class_user_status_change,
    get_class_user_status_current,
    update_class_user_status_sync_result,
)
from wecom_ability_service.domains.questionnaire.service import list_available_wecom_tags
from wecom_ability_service.domains.tags.repo import (
    list_contact_tag_ids_for_user,
    list_signup_tag_rules,
    remove_tag_snapshot,
    save_tag_snapshot,
)
from wecom_ability_service.infra.wecom_runtime import get_app_runtime_client
from wecom_ability_service.wecom_client import WeComClientError


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool_flag(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _allowed_pool_keys() -> list[str]:
    return sorted(POOL_TO_STAGE_DEF.keys())


def _resolve_target_tag(*, signup_status: str, tag_name: str, tag_group_name: str) -> dict[str, Any]:
    normalized_signup_status = _text(signup_status)
    normalized_tag_name = _text(tag_name)
    normalized_group_name = _text(tag_group_name)
    rules = [dict(item) for item in list_signup_tag_rules(active_only=True)]

    if normalized_signup_status:
        matched_rule = next((item for item in rules if _text(item.get("signup_status")) == normalized_signup_status), None)
        if matched_rule:
            return {
                "signup_status": normalized_signup_status,
                "tag_id": _text(matched_rule.get("tag_id")),
                "tag_name": _text(matched_rule.get("tag_name")) or normalized_tag_name,
                "group_name": normalized_group_name,
                "source": "signup_tag_rules",
            }

    if normalized_tag_name:
        matched_rule = next((item for item in rules if _text(item.get("tag_name")) == normalized_tag_name), None)
        if matched_rule:
            return {
                "signup_status": _text(matched_rule.get("signup_status")) or normalized_signup_status,
                "tag_id": _text(matched_rule.get("tag_id")),
                "tag_name": _text(matched_rule.get("tag_name")),
                "group_name": normalized_group_name,
                "source": "signup_tag_rules",
            }

    live_tags = list_available_wecom_tags()
    matched_live_tags = [
        item
        for item in live_tags
        if _text(item.get("tag_name")) == normalized_tag_name
        and (not normalized_group_name or _text(item.get("group_name")) == normalized_group_name)
    ]
    if not matched_live_tags:
        raise ValueError(f"未找到目标标签：group={normalized_group_name or '*'} tag={normalized_tag_name}")
    if len(matched_live_tags) > 1:
        raise ValueError(f"找到多个同名标签，请指定 tag_group_name：{normalized_tag_name}")
    matched = matched_live_tags[0]
    return {
        "signup_status": normalized_signup_status,
        "tag_id": _text(matched.get("tag_id")),
        "tag_name": _text(matched.get("tag_name")),
        "group_name": _text(matched.get("group_name")),
        "source": "live_wecom_tags",
    }


def _load_pool_members(*, pool_key: str, batch_size: int, max_members: int | None) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    offset = 0
    normalized_max = int(max_members) if max_members is not None else None
    while True:
        remaining = None if normalized_max is None else max(normalized_max - len(members), 0)
        if remaining == 0:
            break
        limit = batch_size if remaining is None else min(batch_size, remaining)
        rows = automation_repo.list_stage_members(current_pool=pool_key, limit=limit, offset=offset)
        if not rows:
            break
        members.extend(dict(row) for row in rows)
        offset += len(rows)
        if len(rows) < limit:
            break
    return members


def _normalize_external_userids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        for token in re.split(r"[\s,]+", _text(raw)):
            normalized = _text(token)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return result


def _read_input_file_rows(*, path: str, owner_column_index: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        columns = [item for item in re.split(r"\t+|\s{2,}", line) if _text(item)]
        if not columns:
            continue
        external_userid = _text(columns[0])
        owner_userid = ""
        if len(columns) >= 2:
            try:
                owner_userid = _text(columns[owner_column_index])
            except IndexError:
                owner_userid = ""
        rows.append({"external_userid": external_userid, "owner_userid": owner_userid})
    return rows


def _load_explicit_members(*, external_userids: list[str], explicit_owner_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    owner_map = {key: _text(value) for key, value in (explicit_owner_map or {}).items() if _text(key)}
    for external_userid in external_userids:
        row = automation_repo.get_member_by_external_contact_id(external_userid)
        if row:
            payload = dict(row)
            if owner_map.get(external_userid):
                payload["owner_staff_id"] = owner_map[external_userid]
            rows.append(payload)
            continue
        rows.append(
            {
                "external_contact_id": external_userid,
                "phone": "",
                "owner_staff_id": owner_map.get(external_userid, ""),
            }
        )
    return rows


def _current_tag_ids_for_member(*, external_userid: str, owner_userid: str) -> set[str]:
    return set(list_contact_tag_ids_for_user(external_userid, owner_userid))


def _build_member_snapshot(member: dict[str, Any]) -> dict[str, str]:
    external_userid = _text(member.get("external_contact_id"))
    owner_userid = _text(member.get("owner_staff_id"))
    phone = _text(member.get("phone"))
    current_status = get_class_user_status_current(external_userid) or {}
    return {
        "external_userid": external_userid,
        "customer_name_snapshot": _text(current_status.get("customer_name_snapshot")) or external_userid,
        "owner_userid_snapshot": _text(current_status.get("owner_userid_snapshot")) or owner_userid,
        "mobile_snapshot": _text(current_status.get("mobile_snapshot")) or phone,
    }


def _apply_member_signup_tag(
    *,
    member: dict[str, Any],
    operator: str,
    signup_status: str,
    target_tag: dict[str, Any],
    remove_tag_ids: list[str],
) -> dict[str, Any]:
    external_userid = _text(member.get("external_contact_id"))
    owner_userid = _text(member.get("owner_staff_id"))
    snapshot = _build_member_snapshot(member)

    apply_class_user_status_change(
        external_userid=external_userid,
        signup_status=signup_status,
        set_by_userid=operator or owner_userid,
        customer_name_snapshot=snapshot["customer_name_snapshot"],
        owner_userid_snapshot=snapshot["owner_userid_snapshot"] or owner_userid,
        mobile_snapshot=snapshot["mobile_snapshot"],
    )

    sync_status = "success"
    sync_error = ""
    result: dict[str, Any]
    try:
        result = get_app_runtime_client().mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=owner_userid,
            add_tags=[_text(target_tag.get("tag_id"))],
            remove_tags=remove_tag_ids,
        )
        save_tag_snapshot(
            owner_userid,
            external_userid,
            [_text(target_tag.get("tag_id"))],
            {_text(target_tag.get("tag_id")): _text(target_tag.get("tag_name"))},
        )
        if remove_tag_ids:
            remove_tag_snapshot(owner_userid, external_userid, remove_tag_ids)
    except WeComClientError as exc:
        sync_status = "failed"
        sync_error = str(exc)
        result = {
            "ok": False,
            "error": str(exc),
            "error_category": exc.category or "",
            "error_stage": exc.stage or "",
        }

    update_class_user_status_sync_result(
        external_userid,
        wecom_tag_sync_status=sync_status,
        wecom_tag_sync_error=sync_error,
    )
    return {
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "sync_status": sync_status,
        "sync_error": sync_error,
        "result": result,
    }


def run(
    *,
    pool_key: str,
    external_userids: list[str],
    explicit_owner_map: dict[str, str],
    signup_status: str,
    tag_name: str,
    tag_group_name: str,
    dry_run: bool,
    only_missing: bool,
    batch_size: int,
    max_members: int | None,
    operator: str,
) -> dict[str, Any]:
    normalized_pool_key = _text(pool_key)
    normalized_external_userids = _normalize_external_userids(external_userids)
    if not normalized_external_userids and normalized_pool_key not in POOL_TO_STAGE_DEF:
        raise ValueError(f"pool_key 无效，可选值：{', '.join(_allowed_pool_keys())}")

    target_tag = _resolve_target_tag(
        signup_status=signup_status,
        tag_name=tag_name,
        tag_group_name=tag_group_name,
    )
    if not _text(target_tag.get("signup_status")):
        raise ValueError("未解析到 signup_status，请显式传入 --signup-status")
    target_tag_id = _text(target_tag.get("tag_id"))
    if not target_tag_id:
        raise ValueError("未解析到 tag_id")

    signup_rules = [dict(item) for item in list_signup_tag_rules(active_only=True)]
    remove_tag_ids = sorted(
        {
            _text(item.get("tag_id"))
            for item in signup_rules
            if _text(item.get("tag_id")) and _text(item.get("tag_id")) != target_tag_id
        }
    )

    if normalized_external_userids:
        members = _load_explicit_members(external_userids=normalized_external_userids, explicit_owner_map=explicit_owner_map)
    else:
        members = _load_pool_members(pool_key=normalized_pool_key, batch_size=batch_size, max_members=max_members)
    summary: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "pool_key": normalized_pool_key,
        "pool_label": _text((POOL_TO_STAGE_DEF.get(normalized_pool_key) or {}).get("label")),
        "explicit_external_userids": normalized_external_userids,
        "target_tag": target_tag,
        "remove_tag_ids": remove_tag_ids,
        "total_in_pool": len(members),
        "only_missing": only_missing,
        "operator": operator,
        "considered_count": 0,
        "skipped_missing_owner": 0,
        "skipped_existing": 0,
        "ready_count": 0,
        "applied_count": 0,
        "failed_count": 0,
        "items": [],
        "failures": [],
    }

    for member in members:
        external_userid = _text(member.get("external_contact_id"))
        owner_userid = _text(member.get("owner_staff_id"))
        if not external_userid:
            continue
        if not owner_userid:
            summary["skipped_missing_owner"] += 1
            summary["failures"].append(
                {
                    "external_userid": external_userid,
                    "owner_userid": owner_userid,
                    "error": "owner_staff_id 为空，无法打标签",
                }
            )
            continue

        summary["considered_count"] += 1
        existing_tag_ids = _current_tag_ids_for_member(external_userid=external_userid, owner_userid=owner_userid)
        already_has_target = target_tag_id in existing_tag_ids
        item = {
            "external_userid": external_userid,
            "owner_userid": owner_userid,
            "phone": _text(member.get("phone")),
            "already_has_target": already_has_target,
            "existing_tag_ids": sorted(existing_tag_ids),
        }
        if only_missing and already_has_target:
            summary["skipped_existing"] += 1
            item["status"] = "skipped_existing"
            summary["items"].append(item)
            continue

        summary["ready_count"] += 1
        if dry_run:
            item["status"] = "dry_run_ready"
            summary["items"].append(item)
            continue

        applied = _apply_member_signup_tag(
            member=member,
            operator=operator or owner_userid,
            signup_status=_text(target_tag.get("signup_status")),
            target_tag=target_tag,
            remove_tag_ids=remove_tag_ids,
        )
        item["status"] = applied["sync_status"]
        item["sync_error"] = _text(applied.get("sync_error"))
        item["result"] = applied.get("result") or {}
        summary["items"].append(item)
        if applied["sync_status"] == "success":
            summary["applied_count"] += 1
        else:
            summary["failed_count"] += 1
            summary["failures"].append(
                {
                    "external_userid": external_userid,
                    "owner_userid": owner_userid,
                    "error": _text(applied.get("sync_error")) or _text((applied.get("result") or {}).get("error")),
                }
            )

    summary["ok"] = summary["failed_count"] == 0
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill one signup tag to every current member in one automation pool")
    parser.add_argument("--pool-key", choices=_allowed_pool_keys(), default="")
    parser.add_argument("--external-userid", action="append", default=[])
    parser.add_argument("--input-file", default="")
    parser.add_argument("--owner-column-index", type=int, default=-2)
    parser.add_argument("--signup-status", default="lead")
    parser.add_argument("--tag-name", default="报名引流品")
    parser.add_argument("--tag-group-name", default="AI 产品报名情况")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--max-members", type=int, default=None)
    parser.add_argument("--only-missing", default="true")
    parser.add_argument("--operator", default="pool_signup_tag_backfill_script")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args()
    file_rows = _read_input_file_rows(path=args.input_file, owner_column_index=args.owner_column_index) if _text(args.input_file) else []
    explicit_userids = list(args.external_userid or []) + [item["external_userid"] for item in file_rows]
    explicit_owner_map = {
        item["external_userid"]: item["owner_userid"]
        for item in file_rows
        if _text(item.get("external_userid")) and _text(item.get("owner_userid"))
    }
    if not args.pool_key and not explicit_userids:
        parser.error("需要提供 --pool-key、--input-file 或至少一个 --external-userid")

    dry_run = True
    if args.apply:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    app = create_app()
    try:
        with app.app_context():
            payload = run(
                pool_key=args.pool_key,
                external_userids=explicit_userids,
                explicit_owner_map=explicit_owner_map,
                signup_status=args.signup_status,
                tag_name=args.tag_name,
                tag_group_name=args.tag_group_name,
                dry_run=dry_run,
                only_missing=_bool_flag(args.only_missing),
                batch_size=max(1, int(args.batch_size)),
                max_members=args.max_members,
                operator=_text(args.operator),
            )
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)}, indent=2)
        return 1

    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
