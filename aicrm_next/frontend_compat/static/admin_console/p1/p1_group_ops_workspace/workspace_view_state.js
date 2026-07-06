export const WORKSPACE_CANVAS_LANE_IDS = [
    "plans",
    "groups",
    "nodes",
    "executions",
    "push_center",
    "evidence"
];
export const WORKSPACE_CANVAS_SORT_MODES = [
    "default",
    "status",
    "entity_type",
    "updated_or_created_time",
    "blocked_first",
    "action_required_first"
];
export const WORKSPACE_CANVAS_GROUP_MODES = ["entity_lane"];
function defaultLaneCollapsedState() {
    return {
        plans: false,
        groups: false,
        nodes: false,
        executions: false,
        push_center: false,
        evidence: false
    };
}
function defaultSelectedEntityIds() {
    return {
        plan: [],
        group: [],
        node: [],
        execution: [],
        push_center: [],
        evidence: []
    };
}
function selectedIdFromSelection(selection) {
    if (selection.selectedEntityType === "plan")
        return selection.selectedPlanId;
    if (selection.selectedEntityType === "group")
        return selection.selectedGroupId;
    if (selection.selectedEntityType === "node")
        return selection.selectedNodeId;
    if (selection.selectedEntityType === "execution")
        return selection.selectedExecutionId;
    if (selection.selectedEntityType === "push_center")
        return selection.selectedPushCenterJobId;
    return "evidence";
}
export function createWorkspaceViewState(fixture) {
    return {
        keyword: "",
        planStatusFilter: "all",
        entityTypeFilter: "all",
        executionStatusFilter: "all",
        pushCenterStatusFilter: "all",
        selectedEntityType: fixture.defaultSelection.selectedEntityType,
        selectedEntityId: selectedIdFromSelection(fixture.defaultSelection),
        panelMode: "detail",
        laneCollapsedState: defaultLaneCollapsedState(),
        canvasSortMode: "default",
        canvasGroupMode: "entity_lane",
        visibleLaneIds: [...WORKSPACE_CANVAS_LANE_IDS],
        density: "comfortable",
        focusedCanvasLaneId: "plans",
        focusedCanvasCardId: selectedIdFromSelection(fixture.defaultSelection),
        selectedEntityIds: defaultSelectedEntityIds(),
        activeSelectionMode: "single",
        lastSelectedEntity: null,
        previewBundleId: "preview-bundle-empty",
        bulkGuardrailSummary: [],
        copyPreviewVisible: false,
        copyPreviewFormat: "text",
        copyStatus: "idle",
        copyStatusMessage: "只读复制尚未触发。",
        currentDraftId: "",
        currentDraftVersion: 0,
        currentDraftSnapshotHash: "",
        currentDraftIdempotencyKey: "",
        currentDraftReviewIdempotencyKey: "",
        currentDraftStatus: "not_saved",
        draftSaveStatus: "idle",
        draftSaveMessage: "草稿尚未保存；保存只写 draft 表，不会发送。",
        draftReviewStatus: "idle",
        draftReviewMessage: "request-review 仅适用于已保存的 draft；不会审批、不会进入执行。",
        currentGovernanceReviewId: "",
        currentGovernanceStatus: "governance_not_started",
        currentGovernanceIdempotencyKey: "",
        currentGovernanceReview: null,
        governanceRequestStatus: "idle",
        governanceRequestMessage: "治理 request 仅适用于 ready_for_review draft；不会审批、不会发送。",
        currentPushCenterBridge: null,
        pushCenterBridgeStatus: "idle",
        pushCenterBridgeMessage: "Push Center bridge 仅适用于 governance_approved review；bridge 只进入 pending，不会发送。",
        currentPushCenterBridgeIdempotencyKey: ""
    };
}
export function selectEntityInViewState(viewState, selectedEntityType, selectedEntityId) {
    return {
        ...viewState,
        selectedEntityType,
        selectedEntityId,
        panelMode: selectedEntityType === "evidence" ? "guardrail" : "detail",
        focusedCanvasLaneId: selectedEntityType === "plan"
            ? "plans"
            : selectedEntityType === "group"
                ? "groups"
                : selectedEntityType === "node"
                    ? "nodes"
                    : selectedEntityType === "execution"
                        ? "executions"
                        : selectedEntityType === "push_center"
                            ? "push_center"
                            : "evidence",
        focusedCanvasCardId: selectedEntityId
    };
}
export function updateWorkspaceViewState(viewState, updates) {
    return {
        ...viewState,
        ...updates,
        keyword: updates.keyword !== undefined ? updates.keyword.trim() : viewState.keyword,
        laneCollapsedState: updates.laneCollapsedState
            ? { ...viewState.laneCollapsedState, ...updates.laneCollapsedState }
            : viewState.laneCollapsedState,
        visibleLaneIds: updates.visibleLaneIds ? [...updates.visibleLaneIds] : viewState.visibleLaneIds,
        focusedCanvasLaneId: updates.focusedCanvasLaneId || viewState.focusedCanvasLaneId,
        focusedCanvasCardId: updates.focusedCanvasCardId || viewState.focusedCanvasCardId,
        selectedEntityIds: updates.selectedEntityIds
            ? { ...viewState.selectedEntityIds, ...updates.selectedEntityIds }
            : viewState.selectedEntityIds,
        bulkGuardrailSummary: updates.bulkGuardrailSummary ? [...updates.bulkGuardrailSummary] : viewState.bulkGuardrailSummary
    };
}
export function toggleWorkspaceCanvasLane(viewState, laneId) {
    return updateWorkspaceViewState(viewState, {
        laneCollapsedState: {
            ...viewState.laneCollapsedState,
            [laneId]: !viewState.laneCollapsedState[laneId]
        }
    });
}
export function selectionFromViewState(fixture, viewState) {
    const selection = { ...fixture.defaultSelection, selectedEntityType: viewState.selectedEntityType };
    if (viewState.selectedEntityType === "plan")
        selection.selectedPlanId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "group")
        selection.selectedGroupId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "node")
        selection.selectedNodeId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "execution")
        selection.selectedExecutionId = viewState.selectedEntityId;
    if (viewState.selectedEntityType === "push_center")
        selection.selectedPushCenterJobId = viewState.selectedEntityId;
    return selection;
}
