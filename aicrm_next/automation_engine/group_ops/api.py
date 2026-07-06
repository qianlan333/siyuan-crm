from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aicrm_next.shared.errors import ApplicationError, ContractError, NotFoundError
from aicrm_next.common_operation_members import search_operation_members
from aicrm_next.platform_foundation.external_effects.test_receiver import safe_current_base_url

from .application import (
    AddGroupOpsPlanGroupCommand,
    ArchiveGroupOpsPlanCommand,
    CreateGroupOpsNodeCommand,
    CreateAudienceRuleCommand,
    CreateAudienceRuleVersionCommand,
    CreateGroupOpsPlanCommand,
    DeleteGroupOpsNodeCommand,
    DisableGroupOpsPlanCommand,
    EnableGroupOpsPlanCommand,
    GetAudienceRuleResultsQuery,
    GetGroupOpsPlanQuery,
    GetGroupOpsWebhookConfigQuery,
    ImportGroupOpsMembersCommand,
    ListAudienceRulesQuery,
    ListGroupOpsExecutionsQuery,
    ListGroupOpsMembersQuery,
    ListGroupOpsGroupsQuery,
    ListGroupOpsNodesQuery,
    ListGroupOpsOwnersQuery,
    ListGroupOpsPlanGroupsQuery,
    ListGroupOpsPlansQuery,
    PreviewGroupOpsGroupsSyncCommand,
    PreviewGroupOpsPlanRunDueCommand,
    PreviewAudienceRuleCommand,
    PreviewGroupOpsSegmentationCommand,
    ReceiveGroupOpsWebhookCommand,
    RegenerateGroupOpsWebhookCommand,
    RefreshAudienceRuleCommand,
    RefreshGroupOpsMembersFromGroupsCommand,
    RemoveGroupOpsPlanGroupCommand,
    RunGroupOpsPlanDueCommand,
    SaveGroupOpsSegmentationCommand,
    SyncGroupOpsGroupsCommand,
    UpdateGroupOpsNodeCommand,
    UpdateGroupOpsPlanCommand,
)
from .dto import (
    AudienceRuleCreateRequest,
    AudienceRuleRunRequest,
    AudienceRuleVersionCreateRequest,
    GroupOpsBindGroupRequest,
    GroupOpsExecutionsRequest,
    GroupOpsGroupSyncRequest,
    GroupOpsGroupsRequest,
    GroupOpsMemberImportRequest,
    GroupOpsMembersRequest,
    GroupOpsNodeRequest,
    GroupOpsPlanCreateRequest,
    GroupOpsPlanListRequest,
    GroupOpsRunDueRequest,
    GroupOpsPlanUpdateRequest,
    GroupOpsSegmentationRequest,
    GroupOpsWebhookReceiveRequest,
)

router = APIRouter()


def _json_result(payload: dict) -> JSONResponse:
    return JSONResponse(payload, status_code=int(payload.get("status_code") or 200))


def _plan_id(value: int | str) -> int:
    text = str(value or "").strip()
    if text.startswith("plan_"):
        text = text.removeprefix("plan_")
    return int(text)


def _error_code_for(exc: Exception) -> str:
    message = str(exc)
    if "owner_userid must match" in message or "owner_userid/admin_userids must match" in message:
        return "group_owner_mismatch"
    if "content, images, or attachments is required" in message or "content.text or content.attachments" in message:
        return "content_required"
    if "content is required" in message:
        return "content_required"
    if "feature usage / chat activity" in message:
        return "rule_data_source_missing"
    if "no matched recipients" in message:
        return "no_matched_recipients"
    if "webhook plan is not active" in message:
        return "plan_not_active"
    if "group ops plan is not active" in message:
        return "plan_not_active"
    if "invalid webhook token" in message:
        return "invalid_webhook_token"
    if "invalid webhook signature" in message:
        return "invalid_webhook_signature"
    if "allowlist" in message:
        return "allowlist_required"
    if "rate limit" in message:
        return "rate_limited"
    if "max_outbound_tasks" in message:
        return "max_outbound_tasks_required"
    if "customer-group sync is disabled" in message or "wecom group sync" in message:
        return "wecom_group_sync_blocked"
    if isinstance(exc, NotFoundError):
        return "not_found"
    if isinstance(exc, ContractError):
        return "contract_error"
    return "application_error"


def _raise_http(exc: Exception) -> None:
    detail = {
        "ok": False,
        "error_code": _error_code_for(exc),
        "detail": str(exc),
        "route_owner": "ai_crm_next",
    }
    if isinstance(exc, ApplicationError):
        raise HTTPException(status_code=int(exc.status_code), detail=detail) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=detail) from exc
    raise HTTPException(status_code=400, detail=detail) from exc


@router.get("/api/admin/automation-conversion/group-ops/plans")
@router.get("/api/automation/group-ops/plans")
def list_group_ops_plans(
    keyword: str = "",
    plan_type: str = "",
    type: str = "",
    status: str = "",
    operatorMemberId: str = "",
    operator_member_id: str = "",
    page: int = 1,
    pageSize: int = 0,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    if pageSize:
        limit = pageSize
        offset = max(0, int(page or 1) - 1) * int(pageSize)
    return _json_result(
        ListGroupOpsPlansQuery()(
            GroupOpsPlanListRequest(
                keyword=keyword,
                plan_type=plan_type or type,
                operator_member_id=operatorMemberId or operator_member_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.get("/api/admin/automation-conversion/group-ops/owners")
def list_group_ops_owners() -> JSONResponse:
    try:
        members = search_operation_members(scope="group_ops", page_size=100)
        if not members["items"]:
            return _json_result(ListGroupOpsOwnersQuery()())
        snapshot_owners = {}
        try:
            snapshot_payload = ListGroupOpsOwnersQuery()()
            snapshot_owners = {item["userid"]: item for item in snapshot_payload.get("items", []) if item.get("userid")}
        except Exception:
            snapshot_owners = {}
        return _json_result(
            {
                "ok": True,
                "items": [
                    {
                        "userid": item["user_id"],
                        "name": item["display_name"] or item["user_id"],
                        "group_count": int(snapshot_owners.get(item["user_id"], {}).get("group_count") or 0),
                        **item,
                    }
                    for item in members["items"]
                ],
                "total": members["total"],
                "route_owner": "ai_crm_next",
            }
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans")
@router.post("/api/automation/group-ops/plans")
def create_group_ops_plan(payload: GroupOpsPlanCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateGroupOpsPlanCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}")
@router.get("/api/automation/group-ops/plans/{plan_id}")
def get_group_ops_plan(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(GetGroupOpsPlanQuery()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/group-ops/plans/{plan_id}")
@router.patch("/api/automation/group-ops/plans/{plan_id}")
@router.put("/api/automation/group-ops/plans/{plan_id}")
def update_group_ops_plan(plan_id: int | str, payload: GroupOpsPlanUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateGroupOpsPlanCommand()(_plan_id(plan_id), payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/enable")
@router.post("/api/automation/group-ops/plans/{plan_id}/enable")
def enable_group_ops_plan(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(EnableGroupOpsPlanCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/disable")
@router.post("/api/automation/group-ops/plans/{plan_id}/disable")
def disable_group_ops_plan(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(DisableGroupOpsPlanCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/group-ops/plans/{plan_id}")
@router.delete("/api/automation/group-ops/plans/{plan_id}")
def archive_group_ops_plan(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(ArchiveGroupOpsPlanCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups")
def list_group_ops_plan_groups(plan_id: int) -> JSONResponse:
    try:
        return _json_result(ListGroupOpsPlanGroupsQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups")
def add_group_ops_plan_group(plan_id: int, payload: GroupOpsBindGroupRequest) -> JSONResponse:
    try:
        return _json_result(AddGroupOpsPlanGroupCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups/{chat_id}")
def remove_group_ops_plan_group(plan_id: int, chat_id: str) -> JSONResponse:
    try:
        return _json_result(RemoveGroupOpsPlanGroupCommand()(plan_id, chat_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes")
def list_group_ops_nodes(plan_id: int) -> JSONResponse:
    try:
        return _json_result(ListGroupOpsNodesQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes")
def create_group_ops_node(plan_id: int, payload: GroupOpsNodeRequest) -> JSONResponse:
    try:
        return _json_result(CreateGroupOpsNodeCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes/{node_id}")
def update_group_ops_node(plan_id: int, node_id: int, payload: GroupOpsNodeRequest) -> JSONResponse:
    try:
        return _json_result(UpdateGroupOpsNodeCommand()(plan_id, node_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes/{node_id}")
def delete_group_ops_node(plan_id: int, node_id: int) -> JSONResponse:
    try:
        return _json_result(DeleteGroupOpsNodeCommand()(plan_id, node_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/groups")
def list_group_ops_groups(
    keyword: str = "",
    owner_userid: str = "",
    plan_id: int | None = None,
    bind_status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    return _json_result(
        ListGroupOpsGroupsQuery()(
            GroupOpsGroupsRequest(
                keyword=keyword,
                owner_userid=owner_userid,
                plan_id=plan_id,
                bind_status=bind_status,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.post("/api/admin/automation-conversion/group-ops/groups/sync/preview")
def preview_group_ops_groups_sync(payload: GroupOpsGroupSyncRequest) -> JSONResponse:
    try:
        return _json_result(PreviewGroupOpsGroupsSyncCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/groups/sync")
def sync_group_ops_groups(payload: GroupOpsGroupSyncRequest) -> JSONResponse:
    try:
        return _json_result(SyncGroupOpsGroupsCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/run-due/preview")
def preview_group_ops_plan_run_due(plan_id: int, payload: GroupOpsRunDueRequest) -> JSONResponse:
    try:
        return _json_result(PreviewGroupOpsPlanRunDueCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/run-due")
def run_group_ops_plan_due(plan_id: int, payload: GroupOpsRunDueRequest, request: Request) -> JSONResponse:
    try:
        if payload.external_effect_test_loopback:
            payload = payload.model_copy(update={"test_receiver_base_url": safe_current_base_url(request)})
        return _json_result(RunGroupOpsPlanDueCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/webhook")
@router.get("/api/automation/group-ops/plans/{plan_id}/webhook")
def get_group_ops_webhook_config(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(GetGroupOpsWebhookConfigQuery()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/webhook/regenerate")
@router.post("/api/automation/group-ops/plans/{plan_id}/webhook/reset-token")
def regenerate_group_ops_webhook(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(RegenerateGroupOpsWebhookCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/automation/group-ops/plans/{plan_id}/members")
def list_group_ops_members(
    plan_id: int | str,
    layerKey: str = "",
    layer_key: str = "",
    sourceType: str = "",
    source_type: str = "",
    keyword: str = "",
    page: int = 1,
    pageSize: int = 0,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    try:
        if pageSize:
            limit = pageSize
            offset = max(0, int(page or 1) - 1) * int(pageSize)
        return _json_result(
            ListGroupOpsMembersQuery()(
                _plan_id(plan_id),
                GroupOpsMembersRequest(
                    layer_key=layerKey or layer_key,
                    source_type=sourceType or source_type,
                    keyword=keyword,
                    limit=limit,
                    offset=offset,
                ),
            )
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/plans/{plan_id}/members/import")
def import_group_ops_members(plan_id: int | str, payload: GroupOpsMemberImportRequest) -> JSONResponse:
    try:
        return _json_result(ImportGroupOpsMembersCommand()(_plan_id(plan_id), payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/plans/{plan_id}/members/refresh-from-groups")
def refresh_group_ops_members_from_groups(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(RefreshGroupOpsMembersFromGroupsCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/automation/group-ops/audience-rules")
def list_audience_rules() -> JSONResponse:
    try:
        return _json_result(ListAudienceRulesQuery()())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/audience-rules")
def create_audience_rule(payload: AudienceRuleCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateAudienceRuleCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/audience-rules/{rule_key}/versions")
def create_audience_rule_version(rule_key: str, payload: AudienceRuleVersionCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateAudienceRuleVersionCommand()(rule_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/audience-rules/{rule_key}/preview")
def preview_audience_rule(rule_key: str, payload: AudienceRuleRunRequest) -> JSONResponse:
    try:
        return _json_result(PreviewAudienceRuleCommand()(rule_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/audience-rules/{rule_key}/refresh")
def refresh_audience_rule(rule_key: str, payload: AudienceRuleRunRequest) -> JSONResponse:
    try:
        return _json_result(RefreshAudienceRuleCommand()(rule_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/automation/group-ops/audience-rules/{rule_key}/results")
def get_audience_rule_results(rule_key: str, planId: int | str = 0, plan_id: int | str = 0, version: int = 1) -> JSONResponse:
    try:
        return _json_result(GetAudienceRuleResultsQuery()(rule_key, plan_id=_plan_id(planId or plan_id), version=version))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/automation/group-ops/plans/{plan_id}/segmentation")
def save_group_ops_segmentation(plan_id: int | str, payload: GroupOpsSegmentationRequest) -> JSONResponse:
    try:
        return _json_result(SaveGroupOpsSegmentationCommand()(_plan_id(plan_id), payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/plans/{plan_id}/segmentation/preview")
def preview_group_ops_segmentation(plan_id: int | str) -> JSONResponse:
    try:
        return _json_result(PreviewGroupOpsSegmentationCommand()(_plan_id(plan_id)))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/automation/group-ops/plans/{plan_id}/executions")
def list_group_ops_executions(
    plan_id: int | str,
    triggerEventId: str = "",
    trigger_event_id: str = "",
    status: str = "",
    actionType: str = "",
    action_type: str = "",
    layerKey: str = "",
    layer_key: str = "",
    recipient: str = "",
    startAt: str = "",
    start_at: str = "",
    endAt: str = "",
    end_at: str = "",
    page: int = 1,
    pageSize: int = 0,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    try:
        if pageSize:
            limit = pageSize
            offset = max(0, int(page or 1) - 1) * int(pageSize)
        return _json_result(
            ListGroupOpsExecutionsQuery()(
                _plan_id(plan_id),
                GroupOpsExecutionsRequest(
                    trigger_event_id=triggerEventId or trigger_event_id,
                    status=status,
                    action_type=actionType or action_type,
                    layer_key=layerKey or layer_key,
                    recipient=recipient,
                    start_at=startAt or start_at,
                    end_at=endAt or end_at,
                    limit=limit,
                    offset=offset,
                ),
            )
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/webhooks/{webhook_key}")
def receive_group_ops_webhook(
    webhook_key: str,
    payload: GroupOpsWebhookReceiveRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
) -> JSONResponse:
    try:
        if payload.external_effect_test_loopback:
            payload = payload.model_copy(update={"test_receiver_base_url": safe_current_base_url(request)})
        return _json_result(
            ReceiveGroupOpsWebhookCommand()(
                webhook_key,
                payload,
                authorization=authorization,
                idempotency_key=x_idempotency_key or "",
                signature=x_signature or "",
            )
        )
    except Exception as exc:
        _raise_http(exc)
