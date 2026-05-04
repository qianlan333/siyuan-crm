from __future__ import annotations

from typing import Any, Mapping

from ...customer_center.pulse_service import build_customer_pulse
from ...domains.customer_pulse import service as customer_pulse_domain_service
from ...domains.customer_pulse.access import (
    assert_customer_pulse_any_permission,
    assert_customer_pulse_evidence_view,
    assert_customer_pulse_feedback_permission,
    assert_customer_pulse_inbox_view,
    assert_customer_pulse_internal_job_access,
    assert_customer_pulse_page_visible,
    assert_customer_pulse_request_context,
    assert_customer_pulse_widget_view,
    customer_pulse_permission_summary,
    customer_pulse_template_access_payload,
    resolve_customer_pulse_read_scope,
)
from ...domains.followup_orchestrator import service as followup_orchestrator_domain_service
from .dto import (
    ApplyFollowupMissionActionCommandDTO,
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseCustomerDetailQueryDTO,
    CustomerPulseDetailQueryDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseStatsQueryDTO,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerPulseCardActionCommandDTO,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupCustomerQueryDTO,
    FollowupFeatureGateQueryDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMyMissionsQueryDTO,
    FollowupOverviewQueryDTO,
    FollowupTeamBoardQueryDTO,
    PreviewCustomerPulseCardActionCommandDTO,
    PreviewFollowupMissionItemActionCommandDTO,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommandDTO,
    SyncFollowupMissionsCommandDTO,
    UndoCustomerPulseCardActionCommandDTO,
    UndoFollowupMissionItemActionCommandDTO,
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return dict(value or {})


def get_customer_pulse_feature_gate_legacy(dto: CustomerPulseFeatureGateQueryDTO) -> dict[str, Any]:
    access_context = _dict(dto.access_context)
    assert_customer_pulse_request_context(access_context)
    return {
        "enabled": customer_pulse_domain_service.is_customer_pulse_inbox_enabled(access_context=access_context),
        "feature_gate": customer_pulse_domain_service.customer_pulse_feature_gate_summary(access_context=access_context),
        "permissions": customer_pulse_permission_summary(access_context),
        "template_access": customer_pulse_template_access_payload(access_context),
    }


def list_customer_pulse_inbox_legacy(dto: CustomerPulseInboxQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    filters = _dict(dto.filters)
    filters.setdefault("limit", 50)
    return customer_pulse_domain_service.build_customer_pulse_inbox_payload(
        **filters,
        tenant_context=access_context,
        metric_source=_normalized_text(dto.metric_source) or "admin_customer_pulse_api",
    )


def get_customer_pulse_stats_legacy(dto: CustomerPulseStatsQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_page_visible(_dict(dto.access_context))
    return customer_pulse_domain_service.build_customer_pulse_ops_dashboard_payload(
        days=int(dto.days or 7),
        tenant_context=access_context,
        owner_userids=list(dto.owner_userids or []),
    )


def get_customer_pulse_detail_legacy(dto: CustomerPulseDetailQueryDTO) -> dict[str, Any]:
    external_userid = _normalized_text(dto.external_userid)
    if not external_userid:
        raise LookupError("customer not found")

    access_context = _dict(dto.access_context)
    assert_customer_pulse_request_context(access_context)

    if not customer_pulse_domain_service.is_customer_pulse_inbox_enabled(access_context=access_context):
        return {
            "external_userid": external_userid,
            "pulse": build_customer_pulse(external_userid),
            "customer_pulse": customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
                external_userid,
                tenant_context=access_context,
            ),
        }

    assert_customer_pulse_widget_view(access_context)
    read_scope = resolve_customer_pulse_read_scope(access_context=access_context)
    customer_pulse = customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
        external_userid,
        track_metrics=True,
        metric_source="customer_profile_widget_api",
        tenant_context=read_scope.get("tenant_context"),
        tenant_key=_normalized_text(read_scope.get("tenant_key")),
        allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
    )
    if customer_pulse.get("enabled") and not customer_pulse.get("card"):
        customer_pulse_domain_service.refresh_customer_pulse_cards(
            limit=1,
            operator=_normalized_text(read_scope.get("operator")) or "customer_profile_page",
            external_userids=[external_userid],
            tenant_context=read_scope.get("tenant_context"),
            tenant_key=_normalized_text(read_scope.get("tenant_key")),
            allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
        )
        customer_pulse = customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
            external_userid,
            track_metrics=True,
            metric_source="customer_profile_widget_api",
            tenant_context=read_scope.get("tenant_context"),
            tenant_key=_normalized_text(read_scope.get("tenant_key")),
            allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
        )

    return {
        "external_userid": external_userid,
        "pulse": build_customer_pulse(external_userid),
        "customer_pulse": customer_pulse,
    }


def get_customer_pulse_customer_detail_legacy(dto: CustomerPulseCustomerDetailQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_request_context(_dict(dto.access_context))
    return customer_pulse_domain_service.build_customer_pulse_customer_detail_payload(
        _normalized_text(dto.external_userid),
        track_metrics=bool(dto.track_metrics),
        tenant_context=access_context,
        tenant_key=_normalized_text(dto.tenant_key),
        allowed_owner_userids=list(dto.allowed_owner_userids or []),
    )


def get_customer_pulse_card_legacy(dto: CustomerPulseCardQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_request_context(_dict(dto.access_context))
    return customer_pulse_domain_service.get_customer_pulse_card_payload(
        int(dto.card_id),
        tenant_context=access_context,
    )


def get_customer_pulse_card_evidence_legacy(dto: CustomerPulseCardEvidenceQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_evidence_view(_dict(dto.access_context))
    return customer_pulse_domain_service.get_customer_pulse_card_evidence_payload(
        int(dto.card_id),
        tenant_context=access_context,
    )


def refresh_customer_pulse_cards_legacy(dto: RefreshCustomerPulseCardsCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_page_visible(_dict(dto.access_context))
    return customer_pulse_domain_service.refresh_customer_pulse_cards(
        external_userids=list(dto.external_userids or []),
        limit=int(dto.limit or 50),
        operator=_normalized_text(dto.operator),
        tenant_context=access_context,
        allowed_owner_userids=list(dto.allowed_owner_userids or []),
    )


def enqueue_customer_pulse_recompute_legacy(dto: EnqueueCustomerPulseRecomputeCommandDTO) -> dict[str, Any]:
    job_scope = assert_customer_pulse_internal_job_access(_dict(dto.access_context))
    normalized_operator = _normalized_text(dto.operator)
    external_userids = [
        _normalized_text(item)
        for item in dto.external_userids
        if _normalized_text(item)
    ]
    if _normalized_text(dto.external_userid):
        external_userids.insert(0, _normalized_text(dto.external_userid))
    external_userids = list(dict.fromkeys(external_userids))

    if len(external_userids) <= 1:
        return customer_pulse_domain_service.enqueue_customer_pulse_recompute(
            external_userid=(external_userids[0] if external_userids else ""),
            owner_userid=_normalized_text(dto.owner_userid),
            delay_seconds=int(dto.delay_seconds or 0),
            operator=normalized_operator,
            trigger_source=_normalized_text(dto.trigger_source),
            trigger_ref_type=_normalized_text(dto.trigger_ref_type),
            trigger_ref_id=_normalized_text(dto.trigger_ref_id),
            tenant_context=_dict(job_scope.get("tenant_context")),
        )

    jobs = [
        customer_pulse_domain_service.enqueue_customer_pulse_recompute(
            external_userid=external_userid,
            owner_userid=_normalized_text(dto.owner_userid),
            delay_seconds=int(dto.delay_seconds or 0),
            operator=normalized_operator,
            trigger_source=_normalized_text(dto.trigger_source),
            trigger_ref_type=_normalized_text(dto.trigger_ref_type),
            trigger_ref_id=_normalized_text(dto.trigger_ref_id),
            tenant_context=_dict(job_scope.get("tenant_context")),
        )
        for external_userid in external_userids
    ]
    return {"ok": True, "jobs": jobs, "count": len(jobs)}


def run_due_customer_pulse_snapshot_job_legacy(dto: RunDueCustomerPulseSnapshotJobCommandDTO) -> dict[str, Any]:
    job_scope = assert_customer_pulse_internal_job_access(_dict(dto.access_context))
    return customer_pulse_domain_service.run_due_customer_pulse_snapshot_job(
        limit=int(dto.limit or 50),
        rescan_limit=int(dto.rescan_limit or 20),
        operator=_normalized_text(dto.operator),
        tenant_context=_dict(job_scope.get("tenant_context")),
        allowed_owner_userids=list(dto.allowed_owner_userids or job_scope.get("allowed_owner_userids") or []),
    )


def preview_customer_pulse_card_action_legacy(dto: PreviewCustomerPulseCardActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_request_context(_dict(dto.access_context))
    return customer_pulse_domain_service.preview_customer_pulse_card_action(
        int(dto.card_id),
        action_type=_normalized_text(dto.action_type),
        track_click=bool(dto.track_click),
        metric_source=_normalized_text(dto.metric_source),
        operator=_normalized_text(dto.operator),
        tenant_context=access_context,
    )


def execute_customer_pulse_card_action_legacy(dto: ExecuteCustomerPulseCardActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_request_context(_dict(dto.access_context))
    return customer_pulse_domain_service.execute_customer_pulse_card_action(
        int(dto.card_id),
        action_type=_normalized_text(dto.action_type),
        extra_payload=_dict(dto.action_payload),
        operator=_normalized_text(dto.operator),
        tenant_context=access_context,
    )


def undo_customer_pulse_card_action_legacy(dto: UndoCustomerPulseCardActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_request_context(_dict(dto.access_context))
    return customer_pulse_domain_service.undo_customer_pulse_card_action_execution(
        int(dto.execution_id),
        operator=_normalized_text(dto.operator),
        tenant_context=access_context,
    )


def submit_customer_pulse_feedback_legacy(dto: SubmitCustomerPulseFeedbackCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_feedback_permission(_dict(dto.access_context))
    payload = _dict(dto.feedback_payload)
    return customer_pulse_domain_service.submit_customer_pulse_feedback(
        int(dto.card_id),
        feedback_type=_normalized_text(dto.feedback_type),
        operator=_normalized_text(dto.operator),
        note=_normalized_text(payload.get("note") or payload.get("comments") or payload.get("comment")),
        payload=payload,
        tenant_context=access_context,
    )


def get_followup_feature_gate_legacy(dto: FollowupFeatureGateQueryDTO) -> dict[str, Any]:
    access_context = _dict(dto.access_context)
    assert_customer_pulse_request_context(access_context)
    return {
        "enabled": followup_orchestrator_domain_service.is_followup_orchestrator_enabled(access_context=access_context),
        "feature_gate": followup_orchestrator_domain_service.followup_orchestrator_feature_gate_summary(access_context=access_context),
        "permissions": customer_pulse_permission_summary(access_context),
        "template_access": customer_pulse_template_access_payload(access_context),
    }


def get_followup_overview_legacy(dto: FollowupOverviewQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_overview_payload(
        scope=_normalized_text(dto.scope) or "team",
        owner_userid=_normalized_text(dto.owner_userid),
        external_userid=_normalized_text(dto.external_userid),
        limit=int(dto.limit or 50),
        auto_sync=bool(dto.auto_sync),
        access_context=access_context,
    )


def get_followup_customer_legacy(dto: FollowupCustomerQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_customer_payload(
        external_userid=_normalized_text(dto.external_userid),
        access_context=access_context,
    )


def list_followup_my_missions_legacy(dto: FollowupMyMissionsQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_my_missions_payload(
        actor_userid=_normalized_text(dto.actor_userid),
        limit=int(dto.limit or 50),
        auto_sync=bool(dto.auto_sync),
        access_context=access_context,
    )


def get_followup_team_board_legacy(dto: FollowupTeamBoardQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.build_followup_orchestrator_team_board_payload(
        limit=int(dto.limit or 50),
        auto_sync=bool(dto.auto_sync),
        access_context=access_context,
    )


def get_followup_mission_detail_legacy(dto: FollowupMissionDetailQueryDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.get_followup_orchestrator_mission_detail_payload(
        mission_key=_normalized_text(dto.mission_key),
        access_context=access_context,
        tenant_key=_normalized_text(dto.tenant_key),
    )


def sync_followup_missions_legacy(dto: SyncFollowupMissionsCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.sync_followup_orchestrator_missions(
        scope=_normalized_text(dto.scope) or "team",
        owner_userid=_normalized_text(dto.owner_userid),
        external_userid=_normalized_text(dto.external_userid),
        limit=int(dto.limit or 50),
        access_context=access_context,
    )


def apply_followup_mission_action_legacy(dto: ApplyFollowupMissionActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.apply_followup_orchestrator_mission_action(
        mission_key=_normalized_text(dto.mission_key),
        action_type=_normalized_text(dto.action_type),
        actor_userid=_normalized_text(dto.actor_userid),
        actor_role=_normalized_text(dto.actor_role),
        operator=_normalized_text(dto.operator),
        tenant_context=access_context,
        mission_item_key=_normalized_text(dto.mission_item_key),
        note=_normalized_text(dto.note),
    )


def preview_followup_mission_item_action_legacy(dto: PreviewFollowupMissionItemActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.preview_followup_orchestrator_mission_item_action(
        mission_key=_normalized_text(dto.mission_key),
        mission_item_key=_normalized_text(dto.mission_item_key),
        action_type=_normalized_text(dto.action_type),
        actor_userid=_normalized_text(dto.actor_userid),
        operator=_normalized_text(dto.operator),
        access_context=access_context,
    )


def execute_followup_mission_item_action_legacy(dto: ExecuteFollowupMissionItemActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.execute_followup_orchestrator_mission_item_action(
        mission_key=_normalized_text(dto.mission_key),
        mission_item_key=_normalized_text(dto.mission_item_key),
        action_type=_normalized_text(dto.action_type),
        actor_userid=_normalized_text(dto.actor_userid),
        actor_role=_normalized_text(dto.actor_role),
        operator=_normalized_text(dto.operator),
        note=_normalized_text(dto.note),
        extra_payload=_dict(dto.action_payload),
        access_context=access_context,
    )


def undo_followup_mission_item_action_legacy(dto: UndoFollowupMissionItemActionCommandDTO) -> dict[str, Any]:
    access_context = assert_customer_pulse_inbox_view(_dict(dto.access_context))
    return followup_orchestrator_domain_service.undo_followup_orchestrator_mission_item_action(
        mission_key=_normalized_text(dto.mission_key),
        mission_item_key=_normalized_text(dto.mission_item_key),
        execution_id=int(dto.execution_id or 0),
        actor_userid=_normalized_text(dto.actor_userid),
        actor_role=_normalized_text(dto.actor_role),
        operator=_normalized_text(dto.operator),
        access_context=access_context,
    )


__all__ = [
    "apply_followup_mission_action_legacy",
    "enqueue_customer_pulse_recompute_legacy",
    "execute_customer_pulse_card_action_legacy",
    "execute_followup_mission_item_action_legacy",
    "get_customer_pulse_card_evidence_legacy",
    "get_customer_pulse_card_legacy",
    "get_customer_pulse_customer_detail_legacy",
    "get_customer_pulse_detail_legacy",
    "get_customer_pulse_feature_gate_legacy",
    "get_customer_pulse_stats_legacy",
    "get_followup_customer_legacy",
    "get_followup_feature_gate_legacy",
    "get_followup_mission_detail_legacy",
    "get_followup_overview_legacy",
    "get_followup_team_board_legacy",
    "list_customer_pulse_inbox_legacy",
    "list_followup_my_missions_legacy",
    "preview_customer_pulse_card_action_legacy",
    "preview_followup_mission_item_action_legacy",
    "refresh_customer_pulse_cards_legacy",
    "run_due_customer_pulse_snapshot_job_legacy",
    "submit_customer_pulse_feedback_legacy",
    "sync_followup_missions_legacy",
    "undo_customer_pulse_card_action_legacy",
    "undo_followup_mission_item_action_legacy",
]
