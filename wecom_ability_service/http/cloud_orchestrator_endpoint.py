"""Cloud 编排端 HTTP route aggregator."""

from __future__ import annotations

from .cloud_orchestrator_campaigns import (
    cloud_orchestrator_approve_campaign,
    cloud_orchestrator_batch_start_campaigns,
    cloud_orchestrator_delete_campaign,
    cloud_orchestrator_get_campaign,
    cloud_orchestrator_list_campaigns,
    cloud_orchestrator_pause_campaign,
    cloud_orchestrator_reject_campaign,
    cloud_orchestrator_run_due_campaigns,
    cloud_orchestrator_start_campaign,
)
from .cloud_orchestrator_campaign_details import (
    cloud_orchestrator_add_campaign_step,
    cloud_orchestrator_delete_campaign_step,
    cloud_orchestrator_list_campaign_members,
    cloud_orchestrator_update_campaign_step,
)
from .cloud_orchestrator_media import cloud_orchestrator_upload_image
from .cloud_orchestrator_pages import (
    admin_cloud_orchestrator_campaigns_workspace,
    admin_cloud_orchestrator_integration,
    admin_cloud_orchestrator_observability,
    admin_cloud_orchestrator_workspace,
)
from .cloud_orchestrator_plans import (
    cloud_orchestrator_approve_plan,
    cloud_orchestrator_audit,
    cloud_orchestrator_commit_plan,
    cloud_orchestrator_create_plan,
    cloud_orchestrator_get_plan,
    cloud_orchestrator_list_plans,
    cloud_orchestrator_observability,
    cloud_orchestrator_reject_plan,
    cloud_orchestrator_simulate_plan,
)
from .cloud_orchestrator_segments import (
    cloud_orchestrator_get_segment,
    cloud_orchestrator_list_segments,
    cloud_orchestrator_preview_segment,
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
