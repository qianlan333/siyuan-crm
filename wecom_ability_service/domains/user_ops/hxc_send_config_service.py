"""激活漏斗看板 — 发送人白名单 + 一键群发."""
from __future__ import annotations

import logging
from typing import Any

from ...db import get_db

_logger = logging.getLogger(__name__)


# ── 发送人白名单页面数据 ──────────────────────────────────────────

def build_send_config_page_data() -> dict[str, Any]:
    from ...domains.admin_auth import repo as auth_repo

    from flask import current_app
    corp_id = (current_app.config.get("WECOM_CORP_ID") or "").strip()
    directory_members = auth_repo.list_admin_wecom_directory_members(wecom_corpid=corp_id)

    configs = {c["sender_userid"]: c for c in list_send_configs()}

    members = []
    for m in directory_members:
        uid = (m.get("wecom_userid") or "").strip()
        if not uid:
            continue
        cfg = configs.pop(uid, None)
        members.append({
            "wecom_userid": uid,
            "display_name": (m.get("display_name") or "").strip() or uid,
            "position": (m.get("position") or "").strip(),
            "wecom_status": m.get("wecom_status", 0),
            "is_sender": cfg is not None,
            "priority": cfg["priority"] if cfg else 100,
            "is_active": cfg["is_active"] if cfg else True,
        })

    for uid, cfg in configs.items():
        members.append({
            "wecom_userid": uid,
            "display_name": cfg.get("display_name") or uid,
            "position": "",
            "wecom_status": 0,
            "is_sender": True,
            "priority": cfg["priority"],
            "is_active": cfg["is_active"],
        })

    last_synced = max(
        ((m.get("synced_at") or "") for m in directory_members),
        default="",
    )
    return {
        "members": members,
        "directory_count": len(directory_members),
        "sender_count": sum(1 for m in members if m["is_sender"]),
        "active_sender_count": sum(1 for m in members if m["is_sender"] and m["is_active"]),
        "last_synced_at": last_synced or "尚未同步",
    }


# ── 发送人白名单 CRUD ──────────────────────────────────────────────

def list_send_configs() -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT id, sender_userid, display_name, priority, is_active,
               created_at, updated_at
        FROM user_ops_hxc_send_config
        ORDER BY priority ASC, sender_userid ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_senders() -> dict[str, dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT sender_userid, display_name, priority
        FROM user_ops_hxc_send_config
        WHERE is_active = TRUE
        ORDER BY priority ASC
        """
    ).fetchall()
    return {r["sender_userid"]: dict(r) for r in rows}


def upsert_send_config(
    sender_userid: str,
    display_name: str = "",
    priority: int = 100,
    is_active: bool = True,
) -> dict[str, Any]:
    db = get_db()
    db.execute(
        """
        INSERT INTO user_ops_hxc_send_config
            (sender_userid, display_name, priority, is_active)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (sender_userid)
        DO UPDATE SET display_name = EXCLUDED.display_name,
                      priority     = EXCLUDED.priority,
                      is_active    = EXCLUDED.is_active,
                      updated_at   = now()
        """,
        (sender_userid, display_name, priority, is_active),
    )
    db.commit()
    return {"ok": True, "sender_userid": sender_userid}


def delete_send_config(sender_userid: str) -> dict[str, Any]:
    db = get_db()
    db.execute(
        "DELETE FROM user_ops_hxc_send_config WHERE sender_userid = ?",
        (sender_userid,),
    )
    db.commit()
    return {"ok": True, "sender_userid": sender_userid}


# ── 一键群发 ──────────────────────────────────────────────────────

def _resolve_broadcast_attachments(
    *,
    image_library_ids: list[int],
    miniprogram_library_id: int | None,
) -> tuple[list[str], list[dict[str, Any]], str | None]:
    image_media_ids: list[str] = []
    attachments: list[dict[str, Any]] = []

    if image_library_ids:
        from ...domains import image_library as _image_library
        for iid in image_library_ids[:3]:
            try:
                mid = _image_library.resolve_image_media_id(iid)
                if mid:
                    image_media_ids.append(mid)
            except Exception as exc:
                _logger.warning("resolve image_library_id=%s failed: %s", iid, exc)
                return [], [], f"image_resolve_failed:id={iid}"

    if miniprogram_library_id:
        from ...domains import miniprogram_library as _miniprogram_library
        try:
            att = _miniprogram_library.materialize_miniprogram_attachment(miniprogram_library_id)
            attachments.append(att)
        except Exception as exc:
            _logger.warning("resolve miniprogram_library_id=%s failed: %s", miniprogram_library_id, exc)
            return [], [], f"miniprogram_resolve_failed:id={miniprogram_library_id}"

    return image_media_ids, attachments, None


def _match_sender_for_targets(
    external_userids: list[str],
    active_senders: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[str]], int]:
    """为每个 external_userid 匹配最优发送人。

    查 wecom_external_contact_follow_users 拿到每个外部联系人的全部好友
    (不只是 owner)，在白名单中找优先级最高的 active sender 作为发送人。
    """
    db = get_db()
    placeholders = ", ".join(["?"] * len(external_userids))
    rows = db.execute(
        f"""
        SELECT external_userid, user_id
        FROM wecom_external_contact_follow_users
        WHERE external_userid IN ({placeholders})
          AND relation_status = 'active'
        """,
        tuple(external_userids),
    ).fetchall()

    euid_friends: dict[str, set[str]] = {}
    for row in rows:
        euid = (row["external_userid"] or "").strip()
        uid = (row["user_id"] or "").strip()
        if euid and uid:
            euid_friends.setdefault(euid, set()).add(uid)

    priority_sorted = sorted(active_senders.keys(), key=lambda u: active_senders[u]["priority"])

    sender_targets: dict[str, list[str]] = {}
    skipped = 0
    seen: set[str] = set()

    for euid in external_userids:
        if euid in seen or not euid:
            continue
        seen.add(euid)
        friends = euid_friends.get(euid, set())
        matched = None
        for sender in priority_sorted:
            if sender in friends:
                matched = sender
                break
        if matched:
            sender_targets.setdefault(matched, []).append(euid)
        else:
            skipped += 1

    return sender_targets, skipped


def broadcast_to_filtered_users(
    *,
    external_userids: list[str],
    content: str,
    image_library_ids: list[int] | None = None,
    miniprogram_library_id: int | None = None,
    operator_id: str = "admin",
) -> dict[str, Any]:
    if not external_userids:
        return {"ok": False, "error": "no_targets"}

    has_text = bool(content.strip())
    has_images = bool(image_library_ids)
    has_miniprogram = bool(miniprogram_library_id)
    if not has_text and not has_images and not has_miniprogram:
        return {"ok": False, "error": "empty_content"}

    image_media_ids, attachments, resolve_err = _resolve_broadcast_attachments(
        image_library_ids=image_library_ids or [],
        miniprogram_library_id=miniprogram_library_id,
    )
    if resolve_err:
        return {"ok": False, "error": resolve_err}

    active_senders = get_active_senders()
    if not active_senders:
        return {"ok": False, "error": "no_active_senders"}

    sender_targets, skipped_no_match = _match_sender_for_targets(
        external_userids, active_senders,
    )

    if not sender_targets:
        return {
            "ok": False,
            "error": "no_eligible_targets",
            "skipped_no_match": skipped_no_match,
        }

    from ...domains.tasks.service import dispatch_wecom_task

    results = []
    total_sent = 0
    total_failed = 0

    for sender_userid, targets in sender_targets.items():
        try:
            payload: dict[str, Any] = {
                "sender": sender_userid,
                "external_userid": targets,
            }
            if has_text:
                payload["text"] = {"content": content}
            if image_media_ids:
                payload["image_media_ids"] = list(image_media_ids)
            if attachments:
                payload["attachments"] = list(attachments)
            result = dispatch_wecom_task(
                "private_message",
                "create_private_message_task",
                payload,
            )
            total_sent += len(targets)
            results.append({
                "sender": sender_userid,
                "display_name": active_senders[sender_userid].get("display_name", ""),
                "target_count": len(targets),
                "ok": True,
                "task_id": result.get("task_id"),
            })
        except Exception as exc:
            _logger.warning(
                "hxc broadcast failed sender=%s targets=%d: %s",
                sender_userid, len(targets), exc,
            )
            total_failed += len(targets)
            results.append({
                "sender": sender_userid,
                "display_name": active_senders[sender_userid].get("display_name", ""),
                "target_count": len(targets),
                "ok": False,
                "error": str(exc),
            })

    return {
        "ok": total_sent > 0,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "skipped_no_match": skipped_no_match,
        "sender_results": results,
    }
