from __future__ import annotations

import logging

from flask import Response, jsonify, request

from ..domains.campaigns import service as campaign_service
from ..domains.cloud_orchestrator import approval_token as approval_token_module


logger = logging.getLogger(__name__)


def cloud_orchestrator_list_campaigns() -> Response:
    review_status = (request.args.get("review_status") or "").strip()
    run_status = (request.args.get("run_status") or "").strip()
    limit = int(request.args.get("limit") or 500)
    rows = campaign_service.list_campaigns(
        review_status=review_status,
        run_status=run_status,
        limit=limit,
    )
    return jsonify({"ok": True, "campaigns": rows})


def cloud_orchestrator_get_campaign(campaign_code: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    overview = campaign_service.assemble_campaign_overview(campaign_id=int(camp["id"]))
    return jsonify({"ok": True, "campaign": overview})


def cloud_orchestrator_approve_campaign(campaign_code: str) -> Response:
    body = request.get_json(silent=True) or {}
    operator = str(body.get("operator") or "").strip()
    if not operator:
        return jsonify({"ok": False, "error": "operator is required"}), 400
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    if camp.get("run_status") not in ("draft", "paused") and camp.get("review_status") not in ("draft", "pending_review"):
        return jsonify(
            {"ok": False, "error": f"campaign_not_approvable status={camp.get('run_status')}"}
        ), 400
    result = approval_token_module.issue_token(
        plan_id=str(camp["campaign_code"]),
        operator=operator,
        ttl_seconds=int(body.get("ttl_seconds") or 300),
        scope="start_campaign",
        metadata={"display_name": camp.get("display_name", "")[:120]},
    )
    return jsonify({"ok": True, "approval": result})


def cloud_orchestrator_start_campaign(campaign_code: str) -> Response:
    body = request.get_json(silent=True) or {}
    token = str(body.get("approval_token") or "").strip()
    approver = str(body.get("human_approver") or "").strip()
    if not token or not approver:
        return jsonify({"ok": False, "error": "approval_token and human_approver are required"}), 400
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    try:
        result = campaign_service.start_campaign(
            campaign_id=int(camp["id"]),
            human_approver=approver,
            approval_token_value=token,
        )
        return jsonify({"ok": True, "campaign": result})
    except (PermissionError, RuntimeError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_pause_campaign(campaign_code: str) -> Response:
    body = request.get_json(silent=True) or {}
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    result = campaign_service.pause_campaign(
        campaign_id=int(camp["id"]),
        reason=str(body.get("reason") or ""),
    )
    return jsonify({"ok": True, "campaign": result})


def cloud_orchestrator_batch_start_campaigns() -> Response:
    """按 group_code 批量审批+启动同组所有 draft campaign。"""

    body = request.get_json(silent=True) or {}
    group_code = str(body.get("group_code") or "").strip()
    operator = str(body.get("operator") or "").strip()
    if not group_code or not operator:
        return jsonify({"ok": False, "error": "group_code and operator are required"}), 400

    all_camps = campaign_service.list_campaigns(limit=500)
    group_camps = [c for c in all_camps if c.get("group_code") == group_code]
    if not group_camps:
        return jsonify({"ok": False, "error": "no campaigns found for group_code"}), 404

    started, skipped, failed = [], [], []
    for camp in group_camps:
        code = camp["campaign_code"]
        if camp.get("run_status") not in ("draft", "paused") or camp.get("review_status") not in ("draft", "pending_review"):
            skipped.append(code)
            continue
        try:
            tok = approval_token_module.issue_token(
                plan_id=code, operator=operator, ttl_seconds=300,
                scope="start_campaign",
                metadata={"display_name": camp.get("display_name", "")[:120]},
            )
            campaign_service.start_campaign(
                campaign_id=int(camp["id"]),
                human_approver=operator,
                approval_token_value=tok.get("token", ""),
            )
            started.append(code)
        except Exception as exc:
            failed.append({"code": code, "error": str(exc)})

    return jsonify({
        "ok": True,
        "started_count": len(started),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "started": started,
        "skipped": skipped,
        "failed": failed,
    })


def cloud_orchestrator_reject_campaign(campaign_code: str) -> Response:
    body = request.get_json(silent=True) or {}
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    ok = campaign_service.reject_campaign(
        campaign_id=int(camp["id"]),
        reason=str(body.get("reason") or ""),
    )
    return jsonify({"ok": ok})


def cloud_orchestrator_delete_campaign(campaign_code: str) -> Response:
    """硬删 campaign - DELETE FROM campaigns + 全部子表行。

    active 状态返 409，让调用方先暂停；其他状态都可删。
    """

    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    try:
        result = campaign_service.delete_campaign(campaign_id=int(camp["id"]))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def cloud_orchestrator_run_due_campaigns() -> Response:
    """供 cron 调用：扫一批 due 的 campaign_member 各推一步。"""

    from ..domains.campaigns.scheduler import process_due_campaign_members

    body = request.get_json(silent=True) or {}
    batch_size = int(body.get("batch_size") or request.args.get("batch_size") or 200)
    try:
        result = process_due_campaign_members(batch_size=max(1, min(batch_size, 1000)))
        return jsonify({"ok": True, **result})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("cloud_orchestrator_run_due_campaigns failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


__all__ = [
    "cloud_orchestrator_approve_campaign",
    "cloud_orchestrator_batch_start_campaigns",
    "cloud_orchestrator_delete_campaign",
    "cloud_orchestrator_get_campaign",
    "cloud_orchestrator_list_campaigns",
    "cloud_orchestrator_pause_campaign",
    "cloud_orchestrator_reject_campaign",
    "cloud_orchestrator_run_due_campaigns",
    "cloud_orchestrator_start_campaign",
]
