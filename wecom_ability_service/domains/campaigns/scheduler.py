"""Campaign 调度引擎 — 把 due 的 campaign_member 同步到 broadcast_jobs。

每个 ``campaign_member`` 是一条独立的旅程。Cron 调用 ``process_due_campaign_members``
扫所有 ``status=pending`` 且 ``next_due_at <= now`` 的成员，对没有队列任务的成员：

1. claim — 改 status='running'（乐观锁防并发重复处理）
2. 取下一步 step → 拼内容 → 走频次预算 → 写入 ``broadcast_jobs``

已有队列任务时，由 broadcast queue worker 到点 claim、发送、写
``automation_touch_delivery_log`` 并推进 ``current_step_index``。

回复处理：``register_member_reply`` 在 reply_monitor 收到 inbound 时被调，
对应 campaign_member 走 ``stop_on_reply`` 逻辑。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ...db import get_db
from .payload_helpers import normalize_int_list, normalize_str_list, parse_step_payload
from .time_helpers import DEFAULT_TIMEZONE, campaign_step_due_iso


logger = logging.getLogger(__name__)
CAMPAIGN_QUEUE_SOURCE_TYPE = "campaign"
CAMPAIGN_QUEUE_SOURCE_TABLE = "campaign_members"
CAMPAIGN_QUEUE_CONTENT_TYPE = "private_message"
_OPEN_JOB_STATUSES = ["waiting_approval", "queued", "claimed"]


def _now_iso() -> str:
    # 必须输出 timezone-aware ISO（含 +00:00 后缀），否则 PG TIMESTAMPTZ 字段会按
    # server timezone（Asia/Shanghai）解读 naive 字符串 → 倒推 8 小时，cron
    # ``WHERE next_due_at <= ?`` 永远不命中下一步 due。
    return datetime.now(timezone.utc).isoformat()


def _empty_ts() -> None:
    """``campaign_members.next_due_at / last_step_sent_at`` 的"未设置"占位值。

    PG-only 后统一返回 ``None`` (PG NULL)。保留函数名让 N 处 caller 不用改。
    """
    return None


def _due_at_for_step(
    *,
    anchor_date: str,
    day_offset: int,
    send_time: str,
    step_timezone: str = "Asia/Shanghai",
) -> str:
    """算 step 的 due ISO — 必须输出 tz-aware，防止 PG 二次套时区。"""
    return campaign_step_due_iso(
        anchor_date=anchor_date,
        day_offset=day_offset,
        send_time=send_time,
        step_timezone=step_timezone or DEFAULT_TIMEZONE,
        fallback_to_timezone_today=True,
    )


def _has_inbound_since(
    *,
    external_userid: str,
    since_iso: str,
    owner_userid: str = "",
) -> bool:
    """看 archived_messages 里 since_iso 之后这个 external_userid 有没有真实回复。

    判定与 reply_monitor._reply_monitor_candidate_message 一致：private 单聊 +
    sender == external_userid（用户作为发送方就是 inbound）+ msgtype 不在系统消息列表。
    owner_userid 非空时必须匹配同一个会话归属，避免 A 账号的 campaign 被 B 账号
    会话存档里的回复误停。
    """
    if not external_userid or not since_iso:
        return False
    db = get_db()
    cur = db.cursor()
    owner_filter = ""
    params: list[Any] = [str(external_userid), str(external_userid), str(since_iso)]
    normalized_owner = str(owner_userid or "").strip()
    if normalized_owner:
        owner_filter = " AND owner_userid = ?"
        params.append(normalized_owner)
    cur.execute(
        f"""
        SELECT 1 FROM archived_messages
        WHERE external_userid = ?
          AND chat_type = 'private'
          AND sender = ?
          AND send_time > ?
          {owner_filter}
          AND msgtype NOT IN ('event', 'revoke', 'calendar', 'vote')
        LIMIT 1
        """,
        tuple(params),
    )
    return cur.fetchone() is not None


def _campaign_job_source_id(*, campaign_id: int, campaign_segment_id: int, step_index: int) -> str:
    return f"{int(campaign_id)}:{int(campaign_segment_id)}:{int(step_index)}"


def _legacy_campaign_job_source_id(*, campaign_id: int, step_index: int) -> str:
    return f"{int(campaign_id)}:{int(step_index)}"


def _campaign_job_source_ids(*, campaign_id: int, campaign_segment_id: int, step_index: int) -> tuple[str, str]:
    return (
        _campaign_job_source_id(
            campaign_id=campaign_id,
            campaign_segment_id=campaign_segment_id,
            step_index=step_index,
        ),
        _legacy_campaign_job_source_id(campaign_id=campaign_id, step_index=step_index),
    )


def _open_campaign_job_exists(*, queue_repo: Any, source_ids: tuple[str, ...]) -> bool:
    return any(
        queue_repo.fetch_job_by_source(
            source_type=CAMPAIGN_QUEUE_SOURCE_TYPE,
            source_table=CAMPAIGN_QUEUE_SOURCE_TABLE,
            source_id=str(source_id or ""),
            statuses=_OPEN_JOB_STATUSES,
        )
        for source_id in source_ids
    )


def _campaign_queue_target_summary(*, campaign: dict[str, Any], step: dict[str, Any]) -> str:
    return f"campaign={campaign.get('campaign_code')} step={step.get('step_index')}"


def _resolve_automation_member_id(
    *,
    candidate_member_id: int | None,
    external_contact_id: str,
) -> int | None:
    """Return a real ``automation_member.id`` for campaign-side member data.

    Campaign segments may come from non-automation_member pools where
    ``member_id`` is only the source table row id. FK-backed touch tables must
    never use that id directly.
    """
    candidate = int(candidate_member_id or 0)
    external = str(external_contact_id or "").strip()
    db = get_db()
    cur = db.cursor()
    try:
        if candidate > 0:
            cur.execute("SELECT id FROM automation_member WHERE id = ? LIMIT 1", (candidate,))
            row = cur.fetchone()
            if row:
                return int(row["id"])
        if external:
            cur.execute(
                "SELECT id FROM automation_member WHERE external_contact_id = ? ORDER BY id DESC LIMIT 1",
                (external,),
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
    except Exception as exc:  # pragma: no cover - defensive against partial schemas
        logger.warning(
            "resolve automation member failed (candidate=%s external=%s): %s",
            candidate,
            external,
            exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
    return None


def _mark_member_replied_inline(*, member_row_id: int) -> None:
    """同步路径：发前现查命中时，立刻把 member 标 replied。reply_monitor 异步路径也会做这件事，互为兜底。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE campaign_members SET
            status = 'replied',
            stop_reason = 'user_replied_inline',
            next_due_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (_empty_ts(), _now_iso(), int(member_row_id)),
    )
    db.commit()


def _datetime_from_db(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_pending_member_context(*, member_row_id: int) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, status, member_id, external_contact_id, next_due_at,
               last_step_sent_at, trace_id, campaign_segment_id
        FROM campaign_members
        WHERE id = ?
        """,
        (int(member_row_id),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_live_campaign_context(campaign: dict[str, Any]) -> dict[str, Any] | None:
    campaign_id = int(campaign.get("id") or 0)
    campaign_code = str(campaign.get("campaign_code") or "").strip()
    if not campaign_id and not campaign_code:
        return None
    db = get_db()
    cur = db.cursor()
    if campaign_id:
        cur.execute(
            "SELECT id, campaign_code, run_status, owner_userid, trace_id FROM campaigns WHERE id = ?",
            (campaign_id,),
        )
    else:
        cur.execute(
            "SELECT id, campaign_code, run_status, owner_userid, trace_id FROM campaigns WHERE campaign_code = ?",
            (campaign_code,),
        )
    row = cur.fetchone()
    return dict(row) if row else None


def _restore_running_members_for_skipped_campaign(members: list[dict[str, Any]]) -> int:
    member_ids: list[int] = []
    for item in members:
        try:
            cm_id = int(item.get("cm_id") or 0)
        except (TypeError, ValueError):
            cm_id = 0
        if cm_id:
            member_ids.append(cm_id)
    if not member_ids:
        return 0
    placeholders = ", ".join("?" for _ in member_ids)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"""
        UPDATE campaign_members
        SET status = 'pending',
            last_error_text = ?,
            updated_at = ?
        WHERE id IN ({placeholders})
          AND status = 'running'
        """,
        tuple(["campaign_not_active"] + [_now_iso()] + member_ids),
    )
    db.commit()
    return int(cur.rowcount or 0)


def _claim_due_member(*, member_row_id: int) -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaign_members SET status = 'running', updated_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (_now_iso(), int(member_row_id)),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def _all_step_ids_for_campaign(campaign_id: int) -> list[str]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM campaign_steps WHERE campaign_id = ?",
        (int(campaign_id),),
    )
    return [str(row["id"]) for row in (cur.fetchall() or [])]


def _next_step(
    *, campaign_segment_id: int, after_step_index: int
) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, step_index, day_offset, send_time, content_text,
               timezone, content_payload_json, stop_on_reply, skip_if_recently_touched_days
        FROM campaign_steps
        WHERE campaign_segment_id = ? AND step_index > ?
        ORDER BY step_index ASC LIMIT 1
        """,
        (int(campaign_segment_id), int(after_step_index)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _resolve_step_payload(*, campaign: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """把一个 step 解析成"准备好发送的素材"：text + image_media_ids + miniprogram attachments。

    与 member 无关，所以可以一次解析后批量复用给 N 个 member —— 这是聚合发送的前提。
    返回的 dict 含 ``base_request``（缺 external_userid）+ ``trace_id`` + ``error``。
    error 非空表示解析失败（图片/小程序素材库 resolve 失败之类），整批不应发送。
    """
    from ..marketing_automation.service import DEFAULT_AUTOMATION_OWNER_USERID

    owner_userid = str(campaign.get("owner_userid") or "") or DEFAULT_AUTOMATION_OWNER_USERID

    step_payload = parse_step_payload(step.get("content_payload_json"))

    # 老格式：image_media_ids 直接是企微 media_id（兼容老 step）
    image_media_ids = normalize_str_list(step_payload.get("image_media_ids"), limit=9)
    # 新格式：image_library_ids 引用图片素材库；发送前 resolve 成有效 media_id
    image_library_ids = normalize_int_list(step_payload.get("image_library_ids"), limit=9)
    if image_library_ids:
        from .. import image_library as _image_library

        for iid in image_library_ids:
            try:
                resolved = _image_library.resolve_image_media_id(iid)
            except Exception as exc:
                logger.exception("resolve image_library_id=%s failed: %s", iid, exc)
                return {"error": f"image_library_resolve_failed:id={iid}:{exc}"}
            if resolved:
                image_media_ids.append(resolved)
    image_media_ids = image_media_ids[:9]  # 企微单消息最多 9 张

    miniprogram_library_ids = normalize_int_list(step_payload.get("miniprogram_library_ids"))
    attachments: list[dict[str, Any]] = []
    if miniprogram_library_ids:
        from .. import miniprogram_library as _miniprogram_library

        for lid in miniprogram_library_ids:
            try:
                attachments.append(_miniprogram_library.materialize_miniprogram_attachment(lid))
            except Exception as exc:
                logger.exception("resolve miniprogram_library_id=%s failed: %s", lid, exc)
                return {"error": f"miniprogram_resolve_failed:id={lid}:{exc}"}

    attachment_library_ids = normalize_int_list(step_payload.get("attachment_library_ids"), limit=9)
    if attachment_library_ids:
        from .. import attachment_library as _attachment_library

        for aid in attachment_library_ids:
            try:
                attachments.append(_attachment_library.materialize_file_attachment(aid))
            except Exception as exc:
                logger.exception("resolve attachment_library_id=%s failed: %s", aid, exc)
                return {"error": f"attachment_resolve_failed:id={aid}:{exc}"}

    return {
        "base_request": {
            "sender": owner_userid,
            "text": {"content": str(step.get("content_text") or "")},
            "image_media_ids": image_media_ids,
            "attachments": attachments,
        },
    }


def _dispatch_step_batch(
    *,
    campaign: dict[str, Any],
    members: list[dict[str, Any]],
    step: dict[str, Any],
) -> dict[str, Any]:
    """**一次** dispatch 把同一 step 的素材发给 N 个 external_userid。

    企微的 ``add_msg_template`` 原生支持 ``external_userid`` 数组 — 一次调用就在
    每个员工的"客户群发"列表里产生 1 个 task（包含 N 个客户），运营点 1 次确认即可。
    之前每个 member 单独调一次，导致运营要点 N 次确认 — 严重的产品体验 bug。

    所有 ``members`` 必须是同一 ``(campaign_id, campaign_segment_id, step_index)``，
    调用方负责分组。"""
    if not members:
        return {"ok": False, "reason": "empty_batch"}

    resolved = _resolve_step_payload(campaign=campaign, step=step)
    if resolved.get("error"):
        return {"ok": False, "reason": resolved["error"]}

    externals = [m["external_contact_id"] for m in members if m.get("external_contact_id")]
    if not externals:
        return {"ok": False, "reason": "no_external_userid"}

    request_payload = dict(resolved["base_request"])
    request_payload["external_userid"] = externals

    return _dispatch_private_message_payload(request_payload=request_payload, recipient_count=len(externals))


def _dispatch_private_message_payload(
    *,
    request_payload: dict[str, Any],
    recipient_count: int,
    broadcast_job_id: int | None = None,
    resume_outbound_task_id: int | None = None,
    trace_id: str = "",
) -> dict[str, Any]:
    if resume_outbound_task_id:
        return {
            "ok": True,
            "task_id": int(resume_outbound_task_id),
            "recipient_count": int(recipient_count),
            "resumed": True,
        }
    from ..marketing_automation.service import dispatch_wecom_task
    from ..tasks.service import dispatch_wecom_task_with_intent

    try:
        if broadcast_job_id:
            wecom_result = dispatch_wecom_task_with_intent(
                "private_message",
                "create_private_message_task",
                request_payload,
                broadcast_job_id=int(broadcast_job_id),
                trace_id=trace_id,
            )
        else:
            wecom_result = dispatch_wecom_task(
                "private_message",
                "create_private_message_task",
                request_payload,
            )
        task_id = int(wecom_result.get("task_id") or 0)
        return {"ok": True, "task_id": task_id, "recipient_count": int(recipient_count)}
    except Exception as exc:
        logger.exception("campaign batch dispatch failed (%d recipients): %s", int(recipient_count), exc)
        return {"ok": False, "reason": f"dispatch_error:{exc}"}


def run_campaign_batch(*, batch_data: dict[str, Any]) -> dict[str, Any]:
    """broadcast_jobs handler 调用 — 执行一个 campaign batch 的真发 + side effects。"""
    campaign = batch_data.get("campaign") or {}
    step = batch_data.get("step") or {}
    members = batch_data.get("members") or []
    request_payload = batch_data.get("request_payload") or {}
    broadcast_job_id = int(batch_data.get("broadcast_job_id") or 0) or None
    resume_outbound_task_id = int(batch_data.get("resume_outbound_task_id") or 0) or None
    if not members:
        return {"ok": False, "error": "empty batch"}
    live_campaign = _load_live_campaign_context(campaign)
    if not live_campaign:
        return {"ok": False, "error": "campaign_not_found"}
    if str(live_campaign.get("run_status") or "") != "active":
        restored = _restore_running_members_for_skipped_campaign(members)
        logger.info(
            "skip campaign batch because campaign is not active: campaign=%s run_status=%s restored_members=%s",
            live_campaign.get("campaign_code") or campaign.get("campaign_code"),
            live_campaign.get("run_status"),
            restored,
        )
        return {
            "ok": False,
            "error": f"campaign_not_active:{live_campaign.get('run_status')}",
            "failure_type": "campaign_not_active",
        }
    # 预排期的 job 没有 request_payload，执行时现场 resolve + claim
    is_pre_scheduled = not request_payload
    if is_pre_scheduled:
        from ..marketing_automation import frequency_budget_service

        now = datetime.now(timezone.utc)
        campaign_id = int(campaign.get("id") or 0)
        exclude_step_ids = _all_step_ids_for_campaign(campaign_id) if campaign_id else []
        # 到点执行时重新做 per-member 判定；预排期只解决"何时发送"，不提前消耗预算。
        eligible = []
        for m in members:
            cm_id = int(m["cm_id"])
            context = _load_pending_member_context(member_row_id=cm_id)
            if not context:
                continue
            current_status = str(context.get("status") or "")
            if resume_outbound_task_id and current_status in {"pending", "running"}:
                external = str(context.get("external_contact_id") or m.get("external_contact_id") or "")
                if not external:
                    continue
                member_payload = dict(m)
                member_payload.update({
                    "member_id": int(context.get("member_id") or 0),
                    "external_contact_id": external,
                    "trace_id": str(context.get("trace_id") or m.get("trace_id") or ""),
                    "campaign_segment_id": int(context.get("campaign_segment_id") or m.get("campaign_segment_id") or 0),
                })
                eligible.append(member_payload)
                continue
            if current_status != "pending":
                continue
            due_at = _datetime_from_db(context.get("next_due_at"))
            if due_at and due_at > now:
                continue
            if not _claim_due_member(member_row_id=cm_id):
                continue
            external = str(context.get("external_contact_id") or m.get("external_contact_id") or "")
            last_sent_dt = _datetime_from_db(context.get("last_step_sent_at"))
            if last_sent_dt and external and _has_inbound_since(
                external_userid=external,
                since_iso=last_sent_dt.isoformat(),
                owner_userid=str(campaign.get("owner_userid") or ""),
            ):
                _mark_member_replied_inline(member_row_id=cm_id)
                continue
            if not external:
                db = get_db()
                db.execute(
                    "UPDATE campaign_members SET status = 'failed', last_error_text = ?, updated_at = ? WHERE id = ?",
                    ("missing_external_contact_id", _now_iso(), cm_id),
                )
                db.commit()
                continue
            automation_member_id = _resolve_automation_member_id(
                candidate_member_id=int(context.get("member_id") or 0) or None,
                external_contact_id=external,
            )
            verdict = frequency_budget_service.check_member_budget(
                member_id=automation_member_id,
                external_contact_id=external,
                channels=("wecom_private", "ai_initiated"),
                program_codes=("campaign",),
                exclude_source_kind="campaign_step",
                exclude_source_ids=exclude_step_ids,
            )
            if not verdict.allowed:
                retry_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                db = get_db()
                db.execute(
                    "UPDATE campaign_members SET status = 'pending', next_due_at = ?, "
                    "last_error_text = ?, updated_at = ? WHERE id = ?",
                    (retry_at, str(verdict.skip_reason or "")[:300], _now_iso(), cm_id),
                )
                db.commit()
                continue
            member_payload = dict(m)
            member_payload.update({
                "member_id": int(context.get("member_id") or 0),
                "external_contact_id": external,
                "trace_id": str(context.get("trace_id") or m.get("trace_id") or ""),
                "campaign_segment_id": int(context.get("campaign_segment_id") or m.get("campaign_segment_id") or 0),
            })
            eligible.append(member_payload)
        if not eligible:
            return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "all_members_already_claimed"}
        members = eligible
        if not resume_outbound_task_id:
            resolved = _resolve_step_payload(campaign=campaign, step=step)
            if resolved.get("error"):
                return {"ok": False, "error": resolved["error"]}
            externals = [m["external_contact_id"] for m in members if m.get("external_contact_id")]
            if not externals:
                return {"ok": False, "error": "no_external_userid"}
            request_payload = dict(resolved["base_request"])
            request_payload["external_userid"] = externals

    send_res = _dispatch_private_message_payload(
        request_payload=request_payload,
        recipient_count=len(members),
        broadcast_job_id=broadcast_job_id,
        resume_outbound_task_id=resume_outbound_task_id,
        trace_id=str(campaign.get("trace_id") or ""),
    )

    sent_count = 0
    failed_count = 0
    for m in members:
        if send_res.get("ok"):
            sent_count += 1
            _record_member_after_dispatch(
                campaign=campaign, member=m, step=step, send_result=send_res,
            )
        else:
            failed_count += 1
        progress_member_after_send(
            member_row_id=int(m["cm_id"]), step=step, send_result=send_res,
        )

    # 提前排期：当前 step 发完后，查下一步并立刻入队 broadcast_jobs
    if send_res.get("ok"):
        _pre_enqueue_next_step(campaign=campaign, step=step, members=members)

    return {
        "ok": send_res.get("ok", False),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "outbound_task_id": int(send_res.get("task_id") or 0) or None,
    }


def recover_requeued_campaign_job_members(job: dict[str, Any]) -> int:
    """Reset campaign members claimed by a stale job before any outbound intent.

    This is intentionally limited to jobs that the broadcast queue already proved
    had no outbound_task_id. Once an outbound intent exists, recovery must either
    resume local side effects or require manual reconciliation.
    """
    if str(job.get("source_type") or "") != CAMPAIGN_QUEUE_SOURCE_TYPE:
        return 0
    if int(job.get("outbound_task_id") or 0):
        return 0
    payload = job.get("content_payload") or {}
    members = payload.get("members") or []
    member_row_ids_set: set[int] = set()
    for item in members:
        if not isinstance(item, dict):
            continue
        try:
            cm_id = int(item.get("cm_id") or 0)
        except (TypeError, ValueError):
            continue
        if cm_id:
            member_row_ids_set.add(cm_id)
    member_row_ids = sorted(member_row_ids_set)
    if not member_row_ids:
        return 0
    placeholders = ", ".join("?" * len(member_row_ids))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"""
        UPDATE campaign_members
        SET status = 'pending',
            last_error_text = 'recovered stale broadcast job before outbound dispatch',
            updated_at = ?
        WHERE id IN ({placeholders})
          AND status = 'running'
        """,
        (_now_iso(), *member_row_ids),
    )
    db.commit()
    return int(cur.rowcount or 0)


def _pre_enqueue_next_step(
    *,
    campaign: dict[str, Any],
    step: dict[str, Any],
    members: list[dict[str, Any]],
) -> None:
    """当前 step 成功后，把下一步提前写入 broadcast_jobs 以便队列页展示排期。

    此处只做"排期占位"——写入一条 scheduled_for=下一步due 的 job。
    到时间后 worker claim → handler 走 process_due_campaign_members 正常流程
    （频次预算、inline reply 等在执行时才检查，排期阶段不做）。
    """
    if not members:
        return
    # 取第一个 member 的 campaign_segment_id 查下一步
    first = members[0]
    campaign_segment_id = int(first.get("campaign_segment_id") or 0)
    if not campaign_segment_id:
        return
    next_step = _next_step(
        campaign_segment_id=campaign_segment_id,
        after_step_index=int(step.get("step_index") or 0),
    )
    if not next_step:
        return
    # 取 anchor_date 算 due 时间（同 batch 的 anchor_date 一致）
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT anchor_date FROM campaign_members WHERE id = ?",
        (int(first["cm_id"]),),
    )
    row = cur.fetchone()
    if not row:
        return
    next_due = _due_at_for_step(
        anchor_date=str(row["anchor_date"] or ""),
        day_offset=int(next_step["day_offset"] or 0),
        send_time=str(next_step["send_time"] or "09:00"),
        step_timezone=str(next_step.get("timezone") or "Asia/Shanghai"),
    )
    externals = [m["external_contact_id"] for m in members if m.get("external_contact_id")]
    if not externals:
        return
    from ..broadcast_jobs import service as queue_service
    from ..broadcast_jobs import repo as queue_repo

    source_ids = _campaign_job_source_ids(
        campaign_id=int(campaign.get("id") or 0),
        campaign_segment_id=campaign_segment_id,
        step_index=int(next_step.get("step_index") or 0),
    )
    if _open_campaign_job_exists(queue_repo=queue_repo, source_ids=source_ids):
        return

    queue_service.enqueue_job(
        source_type=CAMPAIGN_QUEUE_SOURCE_TYPE,
        source_id=source_ids[0],
        source_table=CAMPAIGN_QUEUE_SOURCE_TABLE,
        scheduled_for=next_due,
        target_external_userids=externals,
        target_summary=_campaign_queue_target_summary(campaign=campaign, step=next_step),
        content_type=CAMPAIGN_QUEUE_CONTENT_TYPE,
        content_payload={
            "campaign": campaign,
            "step": next_step,
            "members": members,
        },
        content_summary=str(next_step.get("content_text") or "")[:200],
        trace_id=str(campaign.get("trace_id") or ""),
    )


def _record_member_after_dispatch(
    *,
    campaign: dict[str, Any],
    member: dict[str, Any],
    step: dict[str, Any],
    send_result: dict[str, Any],
) -> None:
    """成功 dispatch 后，per-member 写 ``automation_touch_delivery_log`` + 频次预算消耗。

    跟 dispatch 解耦，所以同一 task_id 的 N 个 member 可以分别记账，每条独立带 trace_id。
    """
    from ..marketing_automation import frequency_budget_service

    if not send_result.get("ok"):
        return  # 没真发出去就不记
    task_id = int(send_result.get("task_id") or 0)
    external = str(member.get("external_contact_id") or "")
    member_id = int(member.get("member_id") or 0)
    automation_member_id = _resolve_automation_member_id(
        candidate_member_id=member_id or None,
        external_contact_id=external,
    )
    trace_id = str(member.get("trace_id") or campaign.get("trace_id") or "")

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO automation_touch_delivery_log
                (program_code, touch_surface, rule_key, member_id,
                 external_contact_id, status, detail, metadata_json, trace_id, sent_at)
            VALUES (?, 'campaign_step', ?, ?, ?, 'sent', ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                f"campaign:{campaign.get('campaign_code')}",
                f"step:{step.get('step_index')}",
                automation_member_id,
                external,
                f"campaign_step task_id={task_id}",
                json.dumps(
                    {
                        "campaign_id": campaign.get("id"),
                        "campaign_segment_id": member.get("campaign_segment_id"),
                        "step_index": step.get("step_index"),
                        "wecom_task_id": task_id,
                        "batch_recipient_count": send_result.get("recipient_count") or 1,
                    },
                    ensure_ascii=False,
                ),
                trace_id,
                _now_iso(),
            ),
        )
        db.commit()
    except Exception as exc:
        logger.warning(
            "delivery_log insert failed (campaign_member_id=%s automation_member_id=%s): %s",
            member_id,
            automation_member_id,
            exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
    try:
        frequency_budget_service.record_consumption(
            member_id=automation_member_id,
            external_contact_id=external,
            channels=("wecom_private", "ai_initiated"),
            program_codes=("campaign",),
            source_kind="campaign_step",
            source_id=str(step.get("id") or ""),
            trace_id=trace_id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("record_consumption failed: %s", exc)


def progress_member_after_send(
    *,
    member_row_id: int,
    step: dict[str, Any],
    send_result: dict[str, Any],
) -> None:
    """发完后推进 — 计算下一步 due，或者标记成员完成 / 失败。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cm.id, cm.campaign_id, cm.campaign_segment_id, cm.anchor_date,
               c.run_status
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.id = ?
        """,
        (int(member_row_id),),
    )
    row = cur.fetchone()
    if not row:
        return
    if str(row["run_status"] or "") != "active":
        cur.execute(
            "UPDATE campaign_members SET status = 'paused', updated_at = ? WHERE id = ?",
            (_now_iso(), int(member_row_id)),
        )
        db.commit()
        return
    next_step = _next_step(
        campaign_segment_id=int(row["campaign_segment_id"]),
        after_step_index=int(step.get("step_index") or 0),
    )
    if not next_step:
        # 走完最后一步 → 完成
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'completed',
                current_step_index = ?,
                last_step_sent_at = ?,
                next_due_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(step.get("step_index") or 0),
                _now_iso() if send_result.get("ok") else _empty_ts(),
                _empty_ts(),
                _now_iso(),
                int(member_row_id),
            ),
        )
    else:
        # 算下一步 due
        next_due = _due_at_for_step(
            anchor_date=str(row["anchor_date"] or ""),
            day_offset=int(next_step["day_offset"] or 0),
            send_time=str(next_step["send_time"] or "09:00"),
            step_timezone=str(next_step.get("timezone") or "Asia/Shanghai"),
        )
        cur.execute(
            """
            UPDATE campaign_members SET
                status = 'pending',
                current_step_index = ?,
                last_step_sent_at = ?,
                next_due_at = ?,
                last_error_text = ?,
                retry_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(step.get("step_index") or 0),
                _now_iso() if send_result.get("ok") else _empty_ts(),
                next_due,
                "" if send_result.get("ok") else str(send_result.get("reason") or "")[:300],
                0 if send_result.get("ok") else 1,
                _now_iso(),
                int(member_row_id),
            ),
        )
    db.commit()


def process_due_campaign_members(*, batch_size: int = 200) -> dict[str, Any]:
    """Cron 入口：扫一批 due 的 member、按 (segment, step) 聚合后入 broadcast_jobs。

    两阶段：
    1. **per-member 决策** — claim 乐观锁、stop_on_reply 同步检查、频次预算检查；
       通过的 member 加入分组 buffer ``(campaign_segment_id, step_index) → [members]``
    2. **per-group 批量入队** — worker 每组**一次** ``dispatch_wecom_task``，企微侧
       产生 1 个含 N 个客户的群发任务。运营点 1 次确认 = N 个客户都收到。

    之前每 member 一个 dispatch 让运营要点 N 次确认（用户实测：64 人 = 64 个待确认任务）。
    """
    from ..marketing_automation import frequency_budget_service
    from ..broadcast_jobs import service as queue_service
    from ..broadcast_jobs import repo as queue_repo

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cm.id AS cm_id, cm.member_id, cm.external_contact_id,
               cm.campaign_id, cm.campaign_segment_id, cm.current_step_index,
               cm.anchor_date, cm.trace_id, cm.last_step_sent_at,
               c.campaign_code, c.run_status, c.owner_userid
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.status = 'pending'
          AND cm.next_due_at IS NOT NULL
          AND cm.next_due_at <= ?
          AND c.run_status = 'active'
        ORDER BY cm.next_due_at ASC, cm.id ASC
        LIMIT ?
        """,
        (_now_iso(), int(batch_size)),
    )
    due = cur.fetchall() or []

    # group key = (campaign_segment_id, step_index) → step + campaign_dict + members[]
    groups: dict[tuple[int, int], dict[str, Any]] = {}
    skipped_budget = 0
    skipped_inline_reply = 0
    completed_no_step = 0
    # 同 campaign 续推不重复消耗 daily budget — 缓存 campaign_id → step_ids
    _step_ids_cache: dict[int, list[str]] = {}

    for r in due:
        cm_id = int(r["cm_id"])
        # 取下一个待发的 step（current_step_index 之后的第一个）
        step = _next_step(
            campaign_segment_id=int(r["campaign_segment_id"]),
            after_step_index=int(r["current_step_index"]) if r["current_step_index"] is not None else -1,
        )
        if not step:
            if not _claim_due_member(member_row_id=cm_id):
                continue
            cur.execute(
                "UPDATE campaign_members SET status = 'completed', next_due_at = ?, updated_at = ? "
                "WHERE id = ?",
                (_empty_ts(), _now_iso(), cm_id),
            )
            db.commit()
            completed_no_step += 1
            continue
        source_ids = _campaign_job_source_ids(
            campaign_id=int(r["campaign_id"]),
            campaign_segment_id=int(r["campaign_segment_id"]),
            step_index=int(step.get("step_index") or 0),
        )
        # 若已经有预排期/已领取的 broadcast_job，让 queue worker 负责 claim member。
        # 这里不能先把 member 改 running，否则 worker 到点后会看到 "already claimed"
        # 而跳过真发，形成“不推送”的卡死状态。
        if _open_campaign_job_exists(queue_repo=queue_repo, source_ids=source_ids):
            continue
        if not _claim_due_member(member_row_id=cm_id):
            continue
        # 同步路径：第二条及之后的 step 发送前，先现查会话存档看用户有没有回复。命中
        # 直接停，不再发，也不走频次预算扣减。第一条 step 不查（last_step_sent_at 为空）。
        last_sent = str(r["last_step_sent_at"] or "").strip()
        external = str(r["external_contact_id"] or "")
        if last_sent and external and _has_inbound_since(
            external_userid=external,
            since_iso=last_sent,
            owner_userid=str(r["owner_userid"] or ""),
        ):
            _mark_member_replied_inline(member_row_id=cm_id)
            skipped_inline_reply += 1
            continue
        if not external:
            # 没 external_userid 的 member 直接标失败，避免整批 dispatch 时被拒绝
            cur.execute(
                "UPDATE campaign_members SET status = 'failed', last_error_text = ?, updated_at = ? "
                "WHERE id = ?",
                ("missing_external_contact_id", _now_iso(), cm_id),
            )
            db.commit()
            continue
        # 频次预算 per-member（如果该 member 跨方案累计触达超预算就跳过）
        # 同 campaign 续推排除：同一 campaign 先前 step 的消耗不计入 daily 限额
        campaign_id = int(r["campaign_id"])
        member_id = int(r["member_id"] or 0)
        automation_member_id = _resolve_automation_member_id(
            candidate_member_id=member_id or None,
            external_contact_id=external,
        )
        if campaign_id not in _step_ids_cache:
            _step_ids_cache[campaign_id] = _all_step_ids_for_campaign(campaign_id)
        verdict = frequency_budget_service.check_member_budget(
            member_id=automation_member_id,
            external_contact_id=external,
            channels=("wecom_private", "ai_initiated"),
            program_codes=("campaign",),
            exclude_source_kind="campaign_step",
            exclude_source_ids=_step_ids_cache[campaign_id],
        )
        if not verdict.allowed:
            # 把 status 改回 pending，next_due_at 推后 1 小时避免下次 cron 立刻重试。
            # 必须输出 timezone-aware ISO（带 +00:00 后缀），否则 PG TIMESTAMPTZ
            # 字段会按 server timezone（Asia/Shanghai）解读 naive 字符串 → 倒推
            # 8 小时变成已过期，下次 cron 立刻又扫到，每 15 分钟死循环。
            retry_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            cur.execute(
                "UPDATE campaign_members SET status = 'pending', next_due_at = ?, "
                "last_error_text = ?, updated_at = ? WHERE id = ?",
                (retry_at, str(verdict.skip_reason or "")[:300], _now_iso(), cm_id),
            )
            db.commit()
            skipped_budget += 1
            continue

        # 加入分组 buffer
        member_dict = {
            "cm_id": cm_id,
            "member_id": member_id,
            "external_contact_id": external,
            "trace_id": str(r["trace_id"] or ""),
            "campaign_segment_id": int(r["campaign_segment_id"]),
        }
        campaign_dict = {
            "id": int(r["campaign_id"]),
            "campaign_code": str(r["campaign_code"] or ""),
            "owner_userid": str(r["owner_userid"] or ""),
            "trace_id": str(r["trace_id"] or ""),
        }
        key = (int(r["campaign_segment_id"]), int(step.get("step_index") or 0))
        if key not in groups:
            groups[key] = {"campaign": campaign_dict, "step": step, "members": []}
        groups[key]["members"].append(member_dict)

    # 阶段 2：per-group enqueue 到 broadcast_jobs
    batches_enqueued = 0
    for key, group in groups.items():
        members = group["members"]
        externals = [m["external_contact_id"] for m in members if m.get("external_contact_id")]
        if not externals:
            continue
        campaign = group["campaign"]
        step = group["step"]
        source_ids = _campaign_job_source_ids(
            campaign_id=int(campaign["id"]),
            campaign_segment_id=int(key[0]),
            step_index=int(step.get("step_index") or 0),
        )
        if _open_campaign_job_exists(queue_repo=queue_repo, source_ids=source_ids):
            continue
        resolved = _resolve_step_payload(campaign=campaign, step=step)
        if resolved.get("error"):
            for m in members:
                progress_member_after_send(
                    member_row_id=int(m["cm_id"]),
                    step=step,
                    send_result={"ok": False, "reason": resolved["error"]},
                )
            continue
        request_payload = dict(resolved["base_request"])
        request_payload["external_userid"] = externals
        queue_service.enqueue_job(
            source_type=CAMPAIGN_QUEUE_SOURCE_TYPE,
            source_id=source_ids[0],
            source_table=CAMPAIGN_QUEUE_SOURCE_TABLE,
            scheduled_for=datetime.now(timezone.utc),
            target_external_userids=externals,
            target_summary=_campaign_queue_target_summary(campaign=campaign, step=step),
            content_type=CAMPAIGN_QUEUE_CONTENT_TYPE,
            content_payload={
                "request_payload": request_payload,
                "campaign": campaign,
                "step": step,
                "members": members,
            },
            content_summary=str(request_payload.get("text", {}).get("content") or "")[:200],
            trace_id=str(campaign.get("trace_id") or ""),
        )
        batches_enqueued += 1

    # 阶段 3：同步尚未入队的 pending step（让队列页能看到准确排期）
    future_enqueued = ensure_campaign_scheduled_jobs()

    return {
        "processed": len(due),
        "batches_enqueued": batches_enqueued,
        "future_enqueued": future_enqueued,
        "skipped_budget": skipped_budget,
        "skipped_inline_reply": skipped_inline_reply,
        "completed_no_step": completed_no_step,
        "scanned_at": _now_iso(),
    }


def _pre_enqueue_future_campaign_steps(
    *,
    queue_service: Any,
    queue_repo: Any,
    campaign_id: int | None = None,
    limit: int = 500,
) -> int:
    """扫描所有 pending + 有 next_due_at 的成员，按 campaign segment step 分组排期。

    只排"尚未在 broadcast_jobs 里的"组合，避免重复。
    """
    db = get_db()
    cur = db.cursor()
    where_extra = ""
    args: list[Any] = []
    if campaign_id is not None:
        where_extra = " AND cm.campaign_id = ?"
        args.append(int(campaign_id))
    args.append(int(limit))
    cur.execute(
        f"""
        SELECT cm.id AS cm_id, cm.member_id, cm.external_contact_id,
               cm.campaign_id, cm.campaign_segment_id, cm.current_step_index,
               cm.anchor_date, cm.trace_id, cm.next_due_at,
               c.campaign_code, c.owner_userid
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.status = 'pending'
          AND cm.next_due_at IS NOT NULL
          AND c.run_status = 'active'
          {where_extra}
        ORDER BY cm.next_due_at ASC
        LIMIT ?
        """,
        tuple(args),
    )
    future = cur.fetchall() or []
    if not future:
        return 0

    # 按 (campaign_id, campaign_segment_id, next_step_index) 分组
    groups: dict[str, dict[str, Any]] = {}
    for r in future:
        next_step = _next_step(
            campaign_segment_id=int(r["campaign_segment_id"]),
            after_step_index=int(r["current_step_index"]) if r["current_step_index"] is not None else -1,
        )
        if not next_step:
            continue
        source_ids = _campaign_job_source_ids(
            campaign_id=int(r["campaign_id"]),
            campaign_segment_id=int(r["campaign_segment_id"]),
            step_index=int(next_step.get("step_index") or 0),
        )
        source_id = source_ids[0]
        if _open_campaign_job_exists(queue_repo=queue_repo, source_ids=source_ids):
            continue
        if source_id not in groups:
            due_val = r["next_due_at"]
            if isinstance(due_val, datetime):
                if due_val.tzinfo is None:
                    due_val = due_val.replace(tzinfo=timezone.utc)
                due_str = due_val.isoformat()
            else:
                due_str = str(due_val or "")
            groups[source_id] = {
                "campaign": {
                    "id": int(r["campaign_id"]),
                    "campaign_code": str(r["campaign_code"] or ""),
                    "owner_userid": str(r["owner_userid"] or ""),
                    "trace_id": str(r["trace_id"] or ""),
                },
                "step": next_step,
                "members": [],
                "next_due": due_str,
            }
        external = str(r["external_contact_id"] or "")
        if external:
            groups[source_id]["members"].append({
                "cm_id": int(r["cm_id"]),
                "member_id": int(r["member_id"] or 0),
                "external_contact_id": external,
                "trace_id": str(r["trace_id"] or ""),
                "campaign_segment_id": int(r["campaign_segment_id"]),
            })

    enqueued = 0
    for source_id, group in groups.items():
        members = group["members"]
        externals = [m["external_contact_id"] for m in members if m.get("external_contact_id")]
        if not externals:
            continue
        campaign = group["campaign"]
        step = group["step"]
        queue_service.enqueue_job(
            source_type=CAMPAIGN_QUEUE_SOURCE_TYPE,
            source_id=source_id,
            source_table=CAMPAIGN_QUEUE_SOURCE_TABLE,
            scheduled_for=group["next_due"],
            target_external_userids=externals,
            target_summary=_campaign_queue_target_summary(campaign=campaign, step=step),
            content_type=CAMPAIGN_QUEUE_CONTENT_TYPE,
            content_payload={
                "campaign": campaign,
                "step": step,
                "members": members,
            },
            content_summary=str(step.get("content_text") or "")[:200],
            trace_id=str(campaign.get("trace_id") or ""),
        )
        enqueued += 1
    return enqueued


def ensure_campaign_scheduled_jobs(*, campaign_id: int | None = None, limit: int = 500) -> int:
    from ..broadcast_jobs import repo as queue_repo
    from ..broadcast_jobs import service as queue_service

    return _pre_enqueue_future_campaign_steps(
        queue_service=queue_service,
        queue_repo=queue_repo,
        campaign_id=campaign_id,
        limit=limit,
    )


def register_member_reply(
    *,
    external_contact_id: str = "",
    member_id: int | None = None,
    owner_userid: str = "",
) -> int:
    """reply_monitor 收到 inbound 时调 — 把对应 campaign_member 标记为已回复，停止后续步骤。

    返回被影响的成员数。
    """
    if not external_contact_id and member_id is None:
        return 0
    db = get_db()
    cur = db.cursor()
    normalized_owner = str(owner_userid or "").strip()
    if member_id is not None:
        owner_clause = (
            "AND EXISTS (SELECT 1 FROM campaigns c "
            "WHERE c.id = campaign_members.campaign_id AND c.owner_userid = ?)"
            if normalized_owner else ""
        )
        params: tuple[Any, ...] = (
            (_empty_ts(), _now_iso(), int(member_id), normalized_owner)
            if normalized_owner
            else (_empty_ts(), _now_iso(), int(member_id))
        )
        cur.execute(
            f"""
            UPDATE campaign_members SET
                status = 'replied',
                stop_reason = 'user_replied',
                next_due_at = ?,
                updated_at = ?
            WHERE member_id = ? AND status IN ('pending','running')
              {owner_clause}
            """,
            params,
        )
    else:
        owner_clause = (
            "AND EXISTS (SELECT 1 FROM campaigns c "
            "WHERE c.id = campaign_members.campaign_id AND c.owner_userid = ?)"
            if normalized_owner else ""
        )
        params = (
            (_empty_ts(), _now_iso(), str(external_contact_id), normalized_owner)
            if normalized_owner
            else (_empty_ts(), _now_iso(), str(external_contact_id))
        )
        cur.execute(
            f"""
            UPDATE campaign_members SET
                status = 'replied',
                stop_reason = 'user_replied',
                next_due_at = ?,
                updated_at = ?
            WHERE external_contact_id = ? AND status IN ('pending','running')
              {owner_clause}
            """,
            params,
        )
    db.commit()
    return int(cur.rowcount or 0)


__all__ = [
    "ensure_campaign_scheduled_jobs",
    "process_due_campaign_members",
    "progress_member_after_send",
    "recover_requeued_campaign_job_members",
    "register_member_reply",
]
