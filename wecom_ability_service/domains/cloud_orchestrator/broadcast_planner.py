"""Cloud 端群发计划核心：draft / simulate / commit。

三态状态机（写在 ``cloud_broadcast_plans.status``）：
- ``draft``     — 选好人、出了候选+解释，话术工单可能在跑（``requires_manual_copy=True`` 表示 fallback）
- ``simulated`` — 跑过 dry-run、已计入预算预估
- ``committed`` — 人工 token 验证后真发，已写入 ``user_ops_send_records``
- ``expired``   — TTL 过期（24h），无效化
- ``rejected``  — 人工撤销

draft → simulated 可以反复（运营调整选人）；committed 只能一次。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ...db import get_db
from .. import miniprogram_library
from ..automation_conversion import (
    copy_workorder_service,
    member_segment_search_service,
)
from ..marketing_automation import frequency_budget_service
from ..marketing_automation import message_dispatch_service
from ..tasks.private_message import MAX_PRIVATE_MESSAGE_ATTACHMENTS
from . import approval_token, audit


logger = logging.getLogger(__name__)


_DEFAULT_TTL_HOURS = 24
_MAX_RECIPIENTS_HARD_CAP = 1000


def _new_plan_id() -> str:
    return f"plan-{uuid.uuid4().hex}"


def _expires_at(hours: int = _DEFAULT_TTL_HOURS) -> str:
    return (_utc_now_naive() + timedelta(hours=int(hours))).isoformat()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enforce_max_recipients(requested: int) -> int:
    cap = _MAX_RECIPIENTS_HARD_CAP
    if requested <= 0:
        return cap
    return min(int(requested), cap)


def _materialize_candidates(
    *,
    selection: dict[str, Any],
    max_recipients: int,
) -> list[dict[str, Any]]:
    """按 selection 跑 segment search，最多 max_recipients 条候选。"""
    pool_keys = list(selection.get("pool_keys") or [])
    profile_keys = list(selection.get("profile_segment_keys") or selection.get("profile_keys") or [])
    behavior_keys = list(selection.get("behavior_tier_keys") or selection.get("behavior_keys") or [])
    keyword = str(selection.get("keyword") or "")
    targets = member_segment_search_service.list_broadcast_targets(
        pool_keys=pool_keys or None,
        profile_keys=profile_keys or None,
        behavior_keys=behavior_keys or None,
        keyword=keyword,
        program_id=None,
    )
    return list(targets)[: int(max_recipients)]


def _summarize_candidates(items: list[dict[str, Any]]) -> dict[str, Any]:
    """对一批 candidates 做画像分布摘要，作为话术工单的 audience_summary。"""
    pool_dist: dict[str, int] = {}
    profile_dist: dict[str, int] = {}
    behavior_dist: dict[str, int] = {}
    for it in items:
        pool_dist[str(it.get("pool_key") or it.get("current_pool") or "unknown")] = (
            pool_dist.get(str(it.get("pool_key") or it.get("current_pool") or "unknown"), 0) + 1
        )
        ps = str(it.get("profile_segment_key") or it.get("profile_segment") or "unknown")
        profile_dist[ps] = profile_dist.get(ps, 0) + 1
        bt = str(it.get("behavior_tier_key") or it.get("behavior_tier") or "unknown")
        behavior_dist[bt] = behavior_dist.get(bt, 0) + 1
    return {
        "candidate_count": len(items),
        "pool_distribution": pool_dist,
        "profile_segment_distribution": profile_dist,
        "behavior_tier_distribution": behavior_dist,
    }


def _check_budget_for_candidates(
    items: list[dict[str, Any]],
    *,
    pool_keys: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """对每个候选跑频次预算检查；返回 (allowed, blocked_with_reason, skipped_by_reason)。"""
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped_by_reason: dict[str, int] = {}
    for it in items:
        member_id = int(it.get("member_id") or it.get("id") or 0) or None
        external = str(it.get("external_contact_id") or it.get("external_userid") or "")
        verdict = frequency_budget_service.check_member_budget(
            member_id=member_id,
            external_contact_id=external,
            channels=("wecom_private", "ai_initiated"),
            pool_keys=tuple(pool_keys) if pool_keys else (),
        )
        if verdict.allowed:
            allowed.append(it)
            continue
        skipped_by_reason["budget_exceeded"] = skipped_by_reason.get("budget_exceeded", 0) + 1
        blocked.append(
            {
                "external_contact_id": external,
                "member_id": member_id,
                "skip_reason": verdict.skip_reason,
                "verdicts": [v.__dict__ for v in verdict.verdicts],
            }
        )
    return allowed, blocked, skipped_by_reason


def _record_plan(
    *,
    plan_id: str,
    trace_id: str,
    session_id: str,
    operator: str,
    intent: str,
    selection: dict[str, Any],
    content_strategy: str,
    content_template: str,
    personalization: list[dict[str, Any]],
    max_recipients: int,
    candidate_count: int,
    skipped_count: int,
    explanation: dict[str, Any],
    variants: list[dict[str, Any]],
    copy_run_ids: list[str],
    requires_manual_copy: bool,
    attachments: list[dict[str, Any]],
    expires_at: str,
    status: str = "draft",
) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO cloud_broadcast_plans
            (plan_id, trace_id, session_id, operator, intent, selection_json,
             content_strategy, content_template, personalization_json,
             max_recipients, candidate_count, skipped_count, explanation_json,
             variants_json, copy_workorder_run_ids, requires_manual_copy,
             attachments_json, status, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            trace_id,
            session_id,
            operator,
            intent[:2000],
            json.dumps(selection, ensure_ascii=False),
            content_strategy,
            content_template[:2000],
            json.dumps(personalization, ensure_ascii=False),
            int(max_recipients),
            int(candidate_count),
            int(skipped_count),
            json.dumps(explanation, ensure_ascii=False)[:8000],
            json.dumps(variants, ensure_ascii=False)[:8000],
            json.dumps(copy_run_ids, ensure_ascii=False),
            bool(requires_manual_copy),
            json.dumps(attachments, ensure_ascii=False),
            status,
            expires_at,
        ),
    )
    db.commit()


def _load_plan(plan_id: str) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM cloud_broadcast_plans WHERE plan_id = ? LIMIT 1",
        (str(plan_id),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _update_plan(plan_id: str, fields: dict[str, Any]) -> bool:
    if not fields:
        return False
    sets = ",".join([f"{k} = ?" for k in fields.keys()])
    sets += ", updated_at = CURRENT_TIMESTAMP"
    values = list(fields.values()) + [str(plan_id)]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"UPDATE cloud_broadcast_plans SET {sets} WHERE plan_id = ?",
        tuple(values),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def _normalize_draft_attachments(
    attachments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """draft 阶段只允许 miniprogram(library_id) / file(media_id|library_id)，不接 AI 自由 appid。"""
    if not attachments:
        return []
    if len(attachments) > MAX_PRIVATE_MESSAGE_ATTACHMENTS:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_ATTACHMENTS} attachments are allowed")
    normalized: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            raise ValueError("attachments entries must be objects")
        msgtype = str(item.get("msgtype") or "").strip().lower()
        if msgtype == "miniprogram":
            mp = item.get("miniprogram") or {}
            if not isinstance(mp, dict):
                raise ValueError("miniprogram payload must be object")
            library_id = mp.get("library_id")
            if not library_id:
                raise ValueError(
                    "draft 阶段 miniprogram 必须通过 library_id 引用素材库，不接受裸 appid"
                )
            try:
                lib_id_int = int(library_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("miniprogram library_id 必须是整数") from exc
            entry: dict[str, Any] = {
                "msgtype": "miniprogram",
                "miniprogram": {"library_id": lib_id_int},
            }
            override_pagepath = str(mp.get("pagepath") or "").strip()
            override_title = str(mp.get("title") or "").strip()
            if override_pagepath:
                entry["miniprogram"]["pagepath"] = override_pagepath
            if override_title:
                entry["miniprogram"]["title"] = override_title
            normalized.append(entry)
        elif msgtype == "file":
            file_payload = item.get("file") or {}
            if not isinstance(file_payload, dict):
                raise ValueError("file payload must be object")
            media_id = str(file_payload.get("media_id") or "").strip()
            library_id = file_payload.get("library_id") or file_payload.get("attachment_library_id") or item.get("attachment_library_id")
            if media_id:
                normalized.append({"msgtype": "file", "file": {"media_id": media_id}})
                continue
            if not library_id:
                raise ValueError("file attachments must include media_id or library_id")
            try:
                lib_id_int = int(library_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("file library_id 必须是整数") from exc
            normalized.append({"msgtype": "file", "file": {"library_id": lib_id_int}})
        else:
            raise ValueError(f"unsupported attachment msgtype: {msgtype!r}")
    return normalized


def draft_broadcast_plan(
    *,
    intent: str,
    selection: dict[str, Any],
    content_strategy: str = "profile_layered",
    content_template: str = "",
    personalization: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    max_recipients: int = 0,
    operator: str = "",
    session_id: str = "",
    trace_id: str = "",
    auto_copy_workorder: bool = True,
    scenario_code: str = copy_workorder_service.SCENARIO_BULK_ACTIVATION,
) -> dict[str, Any]:
    """生成一份群发计划草稿，写 cloud_broadcast_plans，并触发话术工单（默认）。"""
    if not selection:
        raise ValueError("selection is required")
    normalized_attachments = _normalize_draft_attachments(attachments)
    cap = _enforce_max_recipients(int(max_recipients or 0))
    plan_id = _new_plan_id()
    effective_trace = trace_id or audit.new_trace_id("plan")
    effective_session = session_id or audit.new_session_id()
    operator = operator or "cloud_agent"
    expires_at = _expires_at(_DEFAULT_TTL_HOURS)
    candidates = _materialize_candidates(selection=selection, max_recipients=cap)
    audience_summary = _summarize_candidates(candidates)
    pool_keys = list(selection.get("pool_keys") or [])
    allowed, blocked, skipped_by_reason = _check_budget_for_candidates(
        candidates, pool_keys=pool_keys
    )

    target_segments = sorted(audience_summary["profile_segment_distribution"].keys())
    sample_recipients = [
        {
            "external_contact_id": str(it.get("external_contact_id") or ""),
            "profile_segment_key": str(it.get("profile_segment_key") or ""),
            "behavior_tier_key": str(it.get("behavior_tier_key") or ""),
            "current_pool": str(it.get("current_pool") or ""),
        }
        for it in allowed[:5]
    ]

    variants: list[dict[str, Any]] = []
    copy_run_ids: list[str] = []
    requires_manual_copy = False

    if auto_copy_workorder and target_segments:
        copy_result = copy_workorder_service.request_bulk_copy_workorder(
            scenario_code=scenario_code,
            intent=intent,
            audience_summary=audience_summary,
            target_segments=target_segments,
            sample_recipients=sample_recipients,
            trace_id=effective_trace,
            operator=operator,
            plan_id=plan_id,
        )
        variants = list(copy_result.get("variants") or [])
        if copy_result.get("run_id"):
            copy_run_ids.append(str(copy_result["run_id"]))
        requires_manual_copy = bool(copy_result.get("requires_manual_copy"))
    else:
        requires_manual_copy = True

    explanation = {
        "audience_summary": audience_summary,
        "selection_used": selection,
        "skipped_by_reason": skipped_by_reason,
        "blocked_samples": blocked[:10],
        "scenario_code": scenario_code,
        "content_strategy": content_strategy,
    }

    _record_plan(
        plan_id=plan_id,
        trace_id=effective_trace,
        session_id=effective_session,
        operator=operator,
        intent=intent,
        selection=selection,
        content_strategy=content_strategy,
        content_template=content_template,
        personalization=list(personalization or []),
        max_recipients=cap,
        candidate_count=len(allowed),
        skipped_count=len(blocked),
        explanation=explanation,
        variants=variants,
        copy_run_ids=copy_run_ids,
        requires_manual_copy=requires_manual_copy,
        attachments=normalized_attachments,
        expires_at=expires_at,
        status="draft",
    )

    from ..broadcast_jobs import service as queue_service

    target_userids = [
        str(c.get("external_contact_id") or "")
        for c in allowed if c.get("external_contact_id")
    ]
    if target_userids:
        queue_service.enqueue_job(
            source_type="cloud_plan",
            source_id=plan_id,
            source_table="cloud_broadcast_plans",
            scheduled_for=expires_at,
            target_external_userids=target_userids,
            target_summary=f"{intent[:30]} — {len(target_userids)} 人",
            content_type="cloud_plan",
            content_payload={"plan_id": plan_id},
            content_summary=intent[:200],
            requires_approval=True,
            trace_id=effective_trace,
            created_by=operator,
        )

    return {
        "plan_id": plan_id,
        "trace_id": effective_trace,
        "session_id": effective_session,
        "status": "draft",
        "candidate_count": len(allowed),
        "skipped_count": len(blocked),
        "audience_summary": audience_summary,
        "variants": variants,
        "shared_principles": [],
        "requires_manual_copy": requires_manual_copy,
        "copy_workorder_run_ids": copy_run_ids,
        "expires_at": expires_at,
        "explanation": explanation,
        "attachments": normalized_attachments,
    }


def simulate_broadcast(*, plan_id: str) -> dict[str, Any]:
    """对 draft plan 做 dry-run，预估触达 / 跳过 / 预算消耗，并写回 simulate_summary。"""
    plan = _load_plan(plan_id)
    if not plan:
        raise LookupError("plan not found")
    if plan["status"] in ("committed", "rejected", "expired"):
        return {
            "plan_id": plan_id,
            "status": plan["status"],
            "predicted_reach": 0,
            "skipped": [],
            "frequency_budget": {},
            "error": f"plan_status={plan['status']}",
        }

    selection = json.loads(plan["selection_json"] or "{}")
    cap = int(plan["max_recipients"] or _MAX_RECIPIENTS_HARD_CAP)
    candidates = _materialize_candidates(selection=selection, max_recipients=cap)
    pool_keys = list(selection.get("pool_keys") or [])
    allowed, blocked, skipped_by_reason = _check_budget_for_candidates(
        candidates, pool_keys=pool_keys
    )

    budget_overview: dict[str, Any] = {}
    if blocked:
        first_verdicts = blocked[0].get("verdicts") or []
        budget_overview = {
            "blocked_count": len(blocked),
            "sample_verdicts": first_verdicts[:5],
        }

    summary = {
        "predicted_reach": len(allowed),
        "skipped_count": len(blocked),
        "skipped_by_reason": skipped_by_reason,
        "frequency_budget": budget_overview,
        "checked_at": _utc_now_naive().isoformat(),
    }

    _update_plan(
        plan_id,
        {
            "candidate_count": len(allowed),
            "skipped_count": len(blocked),
            "simulate_summary_json": json.dumps(summary, ensure_ascii=False),
            "status": "simulated",
        },
    )
    return {
        "plan_id": plan_id,
        "trace_id": plan["trace_id"],
        "status": "simulated",
        "predicted_reach": len(allowed),
        "skipped": blocked[:50],
        "frequency_budget": budget_overview,
        "summary": summary,
    }


def commit_broadcast_plan(
    *,
    plan_id: str,
    confirm: bool,
    human_approver: str,
    approval_token_value: str,
) -> dict[str, Any]:
    """人工确认后真发。强制 confirm + token 校验 + 状态机锁。"""
    if not confirm:
        raise ValueError("confirm must be true")
    if not human_approver:
        raise ValueError("human_approver is required")
    plan = _load_plan(plan_id)
    if not plan:
        raise LookupError("plan not found")
    if plan["status"] == "committed":
        return {
            "plan_id": plan_id,
            "status": "already_committed",
            "trace_id": plan["trace_id"],
            "commit_send_record_id": plan.get("commit_send_record_id"),
        }
    if plan["status"] in ("expired", "rejected"):
        raise RuntimeError(f"plan status not commitable: {plan['status']}")

    token_check = approval_token.consume_token(
        token=approval_token_value,
        plan_id=plan_id,
        consumer=human_approver,
    )
    if not token_check.get("ok"):
        return {
            "plan_id": plan_id,
            "status": "rejected_token",
            "reason": token_check.get("reason"),
        }

    from ..broadcast_jobs import service as queue_service

    _update_plan(
        plan_id,
        {
            "status": "committed",
            "committed_at": _utc_now_naive().isoformat(),
            "committed_by": str(human_approver),
            "approval_token_hash": "consumed",
        },
    )
    approved = queue_service.approve_job_by_source(
        source_table="cloud_broadcast_plans",
        source_id=plan_id,
        approved_by=human_approver,
    )
    return {
        "plan_id": plan_id,
        "trace_id": plan["trace_id"],
        "status": "committed",
        "broadcast_job_approved": approved,
    }


def execute_committed_plan(*, plan_id: str) -> dict[str, Any]:
    """Handler 从 broadcast_jobs worker 调用 — 执行已 committed 的 plan 真发。"""
    plan = _load_plan(plan_id)
    if not plan:
        return {"ok": False, "error": f"plan not found: {plan_id}"}
    if plan["status"] != "committed":
        return {"ok": False, "error": f"plan status not committed: {plan['status']}"}

    selection = json.loads(plan["selection_json"] or "{}")
    pool_keys = list(selection.get("pool_keys") or [])
    if not pool_keys:
        return {"ok": False, "error": "plan selection missing pool_keys"}
    primary_pool = pool_keys[0]
    owner_userid = str(selection.get("owner_userid") or "")
    if not owner_userid:
        from ..marketing_automation.service import DEFAULT_AUTOMATION_OWNER_USERID
        owner_userid = DEFAULT_AUTOMATION_OWNER_USERID

    variants = json.loads(plan["variants_json"] or "[]")
    content_template = str(plan["content_template"] or "")
    if not content_template and variants:
        primary_variant = next(
            (v for v in variants if v.get("content_text")), None
        )
        if primary_variant:
            content_template = str(primary_variant["content_text"])

    raw_attachments = json.loads(plan.get("attachments_json") or "[]")
    if not isinstance(raw_attachments, list):
        raw_attachments = []
    from .. import attachment_library as _attachment_library

    expanded_attachments = miniprogram_library.expand_attachments_with_library(raw_attachments)
    expanded_attachments = _attachment_library.expand_attachments_with_library(expanded_attachments)

    if not content_template and not expanded_attachments:
        return {"ok": False, "error": "no content_template or variants available"}

    trace_id = str(plan["trace_id"] or "")
    committed_by = str(plan.get("committed_by") or "cloud_agent")

    send_result = message_dispatch_service.send_pool_private_message(
        owner_userid=owner_userid,
        pool_key=primary_pool,
        content=content_template,
        attachments=expanded_attachments or None,
        confirm=True,
        operator=f"cloud:{committed_by}",
        trace_id=trace_id,
        source_kind="cloud_broadcast_plan_commit",
        source_id=plan_id,
    )

    record_id = send_result.get("record_id")
    _update_plan(
        plan_id,
        {
            "commit_batch_id": str(record_id or ""),
            "commit_send_record_id": int(record_id) if record_id else None,
        },
    )
    return {
        "ok": True,
        "sent_count": int(send_result.get("sent_count") or 0),
        "failed_count": int(send_result.get("skipped_count") or 0),
        "outbound_task_id": None,
    }


def reject_broadcast_plan(*, plan_id: str, reason: str = "") -> bool:
    return _update_plan(
        plan_id,
        {
            "status": "rejected",
            "error_message": str(reason or "")[:200],
        },
    )


def list_recent_plans(*, status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    if status:
        cur.execute(
            """
            SELECT plan_id, trace_id, session_id, operator, intent, status,
                   candidate_count, skipped_count, requires_manual_copy,
                   created_at, updated_at, expires_at
            FROM cloud_broadcast_plans
            WHERE status = ?
            ORDER BY id DESC LIMIT ?
            """,
            (str(status), int(limit)),
        )
    else:
        cur.execute(
            """
            SELECT plan_id, trace_id, session_id, operator, intent, status,
                   candidate_count, skipped_count, requires_manual_copy,
                   created_at, updated_at, expires_at
            FROM cloud_broadcast_plans
            ORDER BY id DESC LIMIT ?
            """,
            (int(limit),),
        )
    return [dict(r) for r in (cur.fetchall() or [])]


def get_plan(plan_id: str) -> dict[str, Any] | None:
    plan = _load_plan(plan_id)
    if not plan:
        return None
    plan["selection_json"] = json.loads(plan.get("selection_json") or "{}")
    plan["explanation_json"] = json.loads(plan.get("explanation_json") or "{}")
    plan["variants_json"] = json.loads(plan.get("variants_json") or "[]")
    plan["copy_workorder_run_ids"] = json.loads(plan.get("copy_workorder_run_ids") or "[]")
    plan["personalization_json"] = json.loads(plan.get("personalization_json") or "[]")
    plan["simulate_summary_json"] = json.loads(plan.get("simulate_summary_json") or "{}")
    plan["attachments_json"] = json.loads(plan.get("attachments_json") or "[]")
    return plan


__all__ = [
    "draft_broadcast_plan",
    "simulate_broadcast",
    "commit_broadcast_plan",
    "reject_broadcast_plan",
    "list_recent_plans",
    "get_plan",
]
