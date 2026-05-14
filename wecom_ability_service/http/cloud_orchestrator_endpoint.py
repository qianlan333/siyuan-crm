"""Cloud 编排端 HTTP 端点 — CRM 暴露给"等待审阅 / 启动 / 观察"的运营操作。

CRM 不做 LLM 调用；外部 Agent（Claude Code）通过 MCP HTTP 连。

端点：
- ``GET/POST /api/admin/cloud-orchestrator/plans`` — 单次广播草稿（兼容旧路径）
- ``POST     /plans/<plan_id>/{simulate,approve,commit,reject}`` — 单次广播流转
- ``GET      /api/admin/cloud-orchestrator/segments[/...]`` — 命名分层只读
- ``GET      /api/admin/cloud-orchestrator/campaigns[/...]`` — Campaign 列表 / 详情 / 启动
- ``GET      /api/admin/cloud-orchestrator/{audit,observability}`` — 排错入口
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Response, jsonify, render_template, request

from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation
from ..domains.campaigns import service as campaign_service
from ..domains.cloud_orchestrator import (
    approval_token as approval_token_module,
    audit as audit_module,
    broadcast_planner,
)
from ..domains.segments import service as segments_service


logger = logging.getLogger(__name__)


def cloud_orchestrator_create_plan() -> Response:
    """不走 LLM、直接由前端选好筛选条件创建 plan（开箱即用兜底通道）。"""
    body = request.get_json(silent=True) or {}
    try:
        result = broadcast_planner.draft_broadcast_plan(
            intent=str(body.get("intent") or ""),
            selection=dict(body.get("selection") or {}),
            content_strategy=str(body.get("content_strategy") or "profile_layered"),
            content_template=str(body.get("content_template") or ""),
            personalization=list(body.get("personalization") or []),
            attachments=list(body.get("attachments") or []),
            max_recipients=int(body.get("max_recipients") or 0),
            operator=str(body.get("operator") or "ui_user"),
            scenario_code=str(body.get("scenario_code") or "bulk_activation"),
            auto_copy_workorder=bool(body.get("auto_copy_workorder", True)),
        )
        return jsonify({"ok": True, "plan": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_list_plans() -> Response:
    status = (request.args.get("status") or "").strip()
    limit = int(request.args.get("limit") or 20)
    rows = broadcast_planner.list_recent_plans(status=status, limit=limit)
    return jsonify({"ok": True, "plans": rows})


def cloud_orchestrator_get_plan(plan_id: str) -> Response:
    plan = broadcast_planner.get_plan(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    return jsonify({"ok": True, "plan": plan})


def cloud_orchestrator_simulate_plan(plan_id: str) -> Response:
    try:
        result = broadcast_planner.simulate_broadcast(plan_id=plan_id)
        return jsonify({"ok": True, "simulation": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_approve_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    operator = str(body.get("operator") or "").strip()
    if not operator:
        return jsonify({"ok": False, "error": "operator is required"}), 400
    plan = broadcast_planner.get_plan(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    if plan["status"] not in ("draft", "simulated"):
        return jsonify(
            {"ok": False, "error": f"plan_not_approvable status={plan['status']}"}
        ), 400
    result = approval_token_module.issue_token(
        plan_id=plan_id,
        operator=operator,
        ttl_seconds=int(body.get("ttl_seconds") or 300),
        metadata={"intent": plan.get("intent", "")[:200]},
    )
    return jsonify({"ok": True, "approval": result})


def cloud_orchestrator_commit_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    token = str(body.get("approval_token") or "").strip()
    approver = str(body.get("human_approver") or "").strip()
    confirm = bool(body.get("confirm"))
    if not token or not approver:
        return jsonify({"ok": False, "error": "approval_token and human_approver are required"}), 400
    if not confirm:
        return jsonify({"ok": False, "error": "confirm must be true"}), 400
    try:
        result = broadcast_planner.commit_broadcast_plan(
            plan_id=plan_id,
            confirm=confirm,
            human_approver=approver,
            approval_token_value=token,
        )
        return jsonify({"ok": True, "commit": result})
    except (ValueError, LookupError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_reject_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    reason = str(body.get("reason") or "").strip()
    ok = broadcast_planner.reject_broadcast_plan(plan_id=plan_id, reason=reason)
    return jsonify({"ok": ok})


def cloud_orchestrator_audit() -> Response:
    session_id = (request.args.get("session_id") or "").strip()
    trace_id = (request.args.get("trace_id") or "").strip()
    limit = int(request.args.get("limit") or 500)
    rows = audit_module.list_recent_audit(
        session_id=session_id,
        trace_id=trace_id,
        limit=limit,
    )
    return jsonify({"ok": True, "audit": rows})


def cloud_orchestrator_observability() -> Response:
    """监控数据汇总：plan 漏斗 / 审计错误 / Cloud 调用延迟分位。"""
    from datetime import datetime, timedelta

    from ..db import get_db

    cutoff_7d = (datetime.utcnow() - timedelta(days=7)).isoformat()
    cutoff_1d = (datetime.utcnow() - timedelta(days=1)).isoformat()

    db = get_db()
    cur = db.cursor()
    funnel: dict[str, int] = {}
    cur.execute(
        """
        SELECT status, COUNT(*) AS c FROM cloud_broadcast_plans
        WHERE created_at >= ?
        GROUP BY status
        """,
        (cutoff_7d,),
    )
    for row in cur.fetchall() or []:
        funnel[str(row["status"] or "unknown")] = int(row["c"] or 0)
    cur.execute(
        """
        SELECT status, COUNT(*) AS c FROM cloud_agent_audit_log
        WHERE created_at >= ?
        GROUP BY status
        """,
        (cutoff_1d,),
    )
    audit_status: dict[str, int] = {}
    for row in cur.fetchall() or []:
        audit_status[str(row["status"] or "unknown")] = int(row["c"] or 0)
    cur.execute(
        """
        SELECT tool_name, COUNT(*) AS c, AVG(latency_ms) AS avg_ms,
               SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS err_count
        FROM cloud_agent_audit_log
        WHERE created_at >= ?
        GROUP BY tool_name
        ORDER BY c DESC LIMIT 20
        """,
        (cutoff_1d,),
    )
    tool_stats = []
    for row in cur.fetchall() or []:
        tool_stats.append(
            {
                "tool": str(row["tool_name"] or ""),
                "count": int(row["c"] or 0),
                "avg_latency_ms": int(row["avg_ms"] or 0),
                "error_count": int(row["err_count"] or 0),
            }
        )
    cur.execute(
        """
        SELECT id, status, latency_ms, tool_name, error_message, trace_id, created_at
        FROM cloud_agent_audit_log
        WHERE status = 'error'
        ORDER BY id DESC LIMIT 10
        """
    )
    recent_errors = [dict(r) for r in (cur.fetchall() or [])]
    return jsonify(
        {
            "ok": True,
            "plan_funnel_7d": funnel,
            "audit_status_1d": audit_status,
            "tool_stats_1d": tool_stats,
            "recent_errors": recent_errors,
        }
    )


def admin_cloud_orchestrator_workspace() -> Response:
    """旧 AI 对话页已删除 → 重定向到 Campaign 审阅页。"""
    from flask import redirect

    return redirect("/admin/cloud-orchestrator/campaigns", code=302)


def admin_cloud_orchestrator_observability() -> Response:
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/cloud_observability.html",
        page_title="Cloud Orchestrator · 可观察性",
        page_summary="工单 / 审计 / 漏斗 / Tool 调用统计。出问题时按 trace_id 一查到底。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "可观察性"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[
            {"label": "返回助手", "href": "/admin/cloud-orchestrator", "variant": "primary"},
        ],
    )


def cloud_orchestrator_list_segments() -> Response:
    status = (request.args.get("status") or "active").strip()
    keyword = (request.args.get("keyword") or "").strip()
    limit = int(request.args.get("limit") or 200)
    rows = segments_service.list_segments(
        status=status,
        keyword=keyword,
        source_type=(request.args.get("source_type") or "").strip(),
        limit=limit,
    )
    return jsonify({"ok": True, "segments": rows})


def cloud_orchestrator_get_segment(segment_code: str) -> Response:
    seg = segments_service.get_segment(segment_code=segment_code)
    if not seg:
        return jsonify({"ok": False, "error": "segment_not_found"}), 404
    return jsonify({"ok": True, "segment": seg})


def cloud_orchestrator_preview_segment(segment_code: str) -> Response:
    try:
        result = segments_service.preview_segment_members(
            segment_code=segment_code,
            limit=int(request.args.get("limit") or 50),
        )
        return jsonify({"ok": True, "preview": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


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


def cloud_orchestrator_delete_campaign_step(campaign_code: str, step_index: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    try:
        result = campaign_service.delete_campaign_step(
            campaign_id=int(camp["id"]),
            step_index=int(step_index),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_add_campaign_step(campaign_code: str) -> Response:
    """在指定 segment 末尾追加一个 step。需要前端传 ``campaign_segment_id``。"""
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    body = request.get_json(silent=True) or {}
    seg_id = int(body.get("campaign_segment_id") or 0)
    if not seg_id:
        return jsonify({"ok": False, "error": "campaign_segment_id required"}), 400
    try:
        result = campaign_service.append_campaign_step(
            campaign_id=int(camp["id"]),
            campaign_segment_id=seg_id,
            day_offset=int(body.get("day_offset") or 0),
            send_time=str(body.get("send_time") or "10:00"),
            content_text=str(body.get("content_text") or ""),
            stop_on_reply=bool(body.get("stop_on_reply", True)),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_upload_image() -> Response:
    """运营本地选图 → 上传到企微素材库 → 返回 media_id 给前端写进 step。

    复用已有 ``WeComClient._upload_private_message_image``，避免重写一遍企微 API。
    限制 5MB / 仅图片类型，防止滥用接口。
    """
    from ..wecom_client import WeComClient, WeComClientError

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing image"}), 400
    content_type = (file.mimetype or "").lower()
    if not content_type.startswith("image/"):
        return jsonify({"ok": False, "error": f"only image/* allowed, got {content_type}"}), 400
    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"ok": False, "error": "empty file"}), 400
    if len(file_bytes) > 5 * 1024 * 1024:
        return jsonify({"ok": False, "error": "file too large (max 5MB)"}), 400
    try:
        client = WeComClient.from_app()
        media_id = client._upload_private_message_image(
            file.filename, file_bytes, content_type,
        )
    except WeComClientError as exc:
        logger.exception("cloud_orchestrator_upload_image wecom error")
        return jsonify({"ok": False, "error": f"wecom upload failed: {exc}"}), 502
    return jsonify({
        "ok": True,
        "media_id": media_id,
        "file_name": file.filename,
        "content_type": content_type,
        "size": len(file_bytes),
    })


def cloud_orchestrator_update_campaign_step(campaign_code: str, step_index: str) -> Response:
    """编辑单个 step 的话术 / 时间 / 图片 / day_offset / 回复后停止开关。仅 draft 态可改。"""
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    body = request.get_json(silent=True) or {}
    try:
        result = campaign_service.update_campaign_step(
            campaign_id=int(camp["id"]),
            step_index=int(step_index),
            content_text=body.get("content_text"),
            send_time=body.get("send_time"),
            day_offset=body.get("day_offset"),
            stop_on_reply=body.get("stop_on_reply"),
            image_library_ids=body.get("image_library_ids"),
            image_media_ids=body.get("image_media_ids"),
            miniprogram_library_ids=body.get("miniprogram_library_ids"),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_list_campaign_members(campaign_code: str) -> Response:
    """Campaign 命中成员清单。每条带 external_contact_id，前端再链到 /admin/customers/<external_userid>。"""
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    status = (request.args.get("status") or "").strip()
    limit = int(request.args.get("limit") or 100)
    offset = int(request.args.get("offset") or 0)
    result = campaign_service.list_campaign_members(
        campaign_id=int(camp["id"]),
        status=status,
        limit=limit,
        offset=offset,
    )
    return jsonify({"ok": True, **result})


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
    """硬删 campaign — DELETE FROM campaigns + 全部子表行。

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
    """供 cron 调用：扫一批 due 的 campaign_member 各推一步。

    与 ``automation-conversion/reply-monitor/run-due`` 同一类外部触发入口。
    服务器配 ``*/1 * * * * curl -fsS -X POST http://127.0.0.1:5001/api/admin/cloud-orchestrator/campaigns/run-due``
    或 systemd timer 每分钟 / 5 分钟跑一次即可。

    没有 active campaign 或 due 都未到时，返回 processed=0；调用是幂等的。
    """
    from ..domains.campaigns.scheduler import process_due_campaign_members

    body = request.get_json(silent=True) or {}
    batch_size = int(body.get("batch_size") or request.args.get("batch_size") or 200)
    try:
        result = process_due_campaign_members(batch_size=max(1, min(batch_size, 1000)))
        return jsonify({"ok": True, **result})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("cloud_orchestrator_run_due_campaigns failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


def admin_cloud_orchestrator_campaigns_workspace() -> Response:
    """Campaign 待审 / 审阅工作台。"""
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/cloud_campaigns_workspace.html",
        page_title="AI 助手 · 运营计划审阅",
        page_summary="Agent 上架的多分层多步骤运营计划在这里审阅启动。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "运营计划审阅"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[
            {"label": "可观察性", "href": "/admin/cloud-orchestrator/observability", "variant": "ghost"},
        ],
    )


def admin_cloud_orchestrator_integration() -> Response:
    """运营拿 MCP 接入凭证的页（演示版本，正式做需要绑定登录用户）。"""
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/cloud_integration_workspace.html",
        page_title="AI 助手 · 接入凭证",
        page_summary="Claude Code / Codex 等外部 Agent 接入 CRM 的 MCP 凭证。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "接入凭证"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[],
    )


def register_routes(bp):
    bp.route(
        "/admin/cloud-orchestrator",
        methods=["GET"],
    )(admin_cloud_orchestrator_workspace)
    bp.route(
        "/admin/cloud-orchestrator/campaigns",
        methods=["GET"],
    )(admin_cloud_orchestrator_campaigns_workspace)
    bp.route(
        "/admin/cloud-orchestrator/integration",
        methods=["GET"],
    )(admin_cloud_orchestrator_integration)
    bp.route(
        "/admin/cloud-orchestrator/observability",
        methods=["GET"],
    )(admin_cloud_orchestrator_observability)
    bp.route(
        "/api/admin/cloud-orchestrator/plans",
        methods=["POST"],
    )(cloud_orchestrator_create_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/plans",
        methods=["GET"],
    )(cloud_orchestrator_list_plans)
    bp.route(
        "/api/admin/cloud-orchestrator/plans/<plan_id>",
        methods=["GET"],
    )(cloud_orchestrator_get_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/plans/<plan_id>/simulate",
        methods=["POST"],
    )(cloud_orchestrator_simulate_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/plans/<plan_id>/approve",
        methods=["POST"],
    )(cloud_orchestrator_approve_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/plans/<plan_id>/commit",
        methods=["POST"],
    )(cloud_orchestrator_commit_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/plans/<plan_id>/reject",
        methods=["POST"],
    )(cloud_orchestrator_reject_plan)
    bp.route(
        "/api/admin/cloud-orchestrator/audit",
        methods=["GET"],
    )(cloud_orchestrator_audit)
    bp.route(
        "/api/admin/cloud-orchestrator/observability",
        methods=["GET"],
    )(cloud_orchestrator_observability)
    # ---- Segments ----
    bp.route(
        "/api/admin/cloud-orchestrator/segments",
        methods=["GET"],
    )(cloud_orchestrator_list_segments)
    bp.route(
        "/api/admin/cloud-orchestrator/segments/<segment_code>",
        methods=["GET"],
    )(cloud_orchestrator_get_segment)
    bp.route(
        "/api/admin/cloud-orchestrator/segments/<segment_code>/preview",
        methods=["GET"],
    )(cloud_orchestrator_preview_segment)
    # ---- Campaigns ----
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/batch-start",
        methods=["POST"],
    )(cloud_orchestrator_batch_start_campaigns)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns",
        methods=["GET"],
    )(cloud_orchestrator_list_campaigns)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>",
        methods=["GET"],
    )(cloud_orchestrator_get_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/approve",
        methods=["POST"],
    )(cloud_orchestrator_approve_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/start",
        methods=["POST"],
    )(cloud_orchestrator_start_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/pause",
        methods=["POST"],
    )(cloud_orchestrator_pause_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/reject",
        methods=["POST"],
    )(cloud_orchestrator_reject_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>",
        methods=["DELETE"],
    )(cloud_orchestrator_delete_campaign)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        methods=["POST"],
    )(cloud_orchestrator_run_due_campaigns)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/members",
        methods=["GET"],
    )(cloud_orchestrator_list_campaign_members)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/steps/<step_index>",
        methods=["PATCH", "POST"],
    )(cloud_orchestrator_update_campaign_step)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/steps/<step_index>",
        methods=["DELETE"],
    )(cloud_orchestrator_delete_campaign_step)
    bp.route(
        "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/steps",
        methods=["POST"],
    )(cloud_orchestrator_add_campaign_step)
    bp.route(
        "/api/admin/cloud-orchestrator/media/upload",
        methods=["POST"],
    )(cloud_orchestrator_upload_image)


__all__ = ["register_routes"]
