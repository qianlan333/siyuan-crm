import {
  type WorkspaceEntityType,
  type WorkspaceFixture,
  type WorkspaceSelectionState
} from "./workspace_fixture.js";

export type WorkspacePanelMode = "summary" | "detail" | "guardrail";
export type WorkspaceFilterValue = "all" | string;
export type WorkspaceCanvasLaneId = "plans" | "groups" | "nodes" | "executions" | "push_center" | "evidence";
export type WorkspaceCanvasSortMode =
  | "default"
  | "status"
  | "entity_type"
  | "updated_or_created_time"
  | "blocked_first"
  | "action_required_first";
export type WorkspaceCanvasGroupMode = "entity_lane";
export type WorkspaceDensity = "compact" | "comfortable";
export type WorkspaceSelectionMode = "single" | "multi";
export type WorkspaceCopyPreviewFormat = "text" | "json";
export type WorkspaceCopyStatus = "idle" | "copied" | "copy_failed";
export type WorkspaceDraftSaveStatus = "idle" | "saving" | "saved" | "failed" | "conflict" | "archived";
export type WorkspaceDraftStatus = "not_saved" | "draft" | "ready_for_review" | "archived" | "rejected";
export type WorkspaceDraftReviewStatus = "idle" | "requesting" | "ready_for_review" | "failed" | "conflict" | "blocked";
export type WorkspaceGovernanceRequestStatus = "idle" | "requesting" | "requested" | "failed" | "conflict" | "blocked";
export type WorkspacePushCenterBridgeStatus = "idle" | "requesting" | "bridged" | "failed" | "conflict" | "blocked";

export interface WorkspaceGovernanceReviewView {
  review_id: string;
  draft_id: string;
  review_status: string;
  snapshot_hash: string;
  steps: {
    step_id: string;
    step_type: string;
    step_status: string;
    actor_metadata?: Record<string, unknown>;
    updated_at?: string;
  }[];
  allowlist_summary: {
    hash: string;
    count: number;
    source_reference_summary: Record<string, unknown>;
  };
  gray_window: {
    start_at: string;
    end_at: string;
    timezone: string;
    window_status: string;
  };
  approved: false;
  execution_status: "not_execution";
  push_center_job_created: false;
  external_effect_job_created: false;
  broadcast_job_created: false;
  internal_event_created: false;
  real_external_call: false;
  can_claim_pass_90_plus: false;
}

export interface WorkspacePushCenterBridgeView {
  review_id: string;
  draft_id: string;
  review_status: string;
  push_center_job_created: true;
  push_center_job_id: string;
  push_center_projection_id: string;
  push_center_status: "pending";
  execution_status: "push_center_pending_not_sent";
  external_effect_job_created: false;
  broadcast_job_created: false;
  internal_event_created: false;
  real_external_call: false;
  can_claim_pass_90_plus: false;
  idempotent_replay?: boolean;
}

export const WORKSPACE_CANVAS_LANE_IDS: WorkspaceCanvasLaneId[] = [
  "plans",
  "groups",
  "nodes",
  "executions",
  "push_center",
  "evidence"
];

export const WORKSPACE_CANVAS_SORT_MODES: WorkspaceCanvasSortMode[] = [
  "default",
  "status",
  "entity_type",
  "updated_or_created_time",
  "blocked_first",
  "action_required_first"
];

export const WORKSPACE_CANVAS_GROUP_MODES: WorkspaceCanvasGroupMode[] = ["entity_lane"];

export type WorkspaceLaneCollapsedState = Record<WorkspaceCanvasLaneId, boolean>;
export type WorkspaceSelectedEntityIds = Record<WorkspaceEntityType, string[]>;

export interface WorkspaceSelectedEntityRef {
  entityType: WorkspaceEntityType;
  id: string;
}

export interface WorkspaceViewState {
  keyword: string;
  planStatusFilter: WorkspaceFilterValue;
  entityTypeFilter: "all" | WorkspaceEntityType;
  executionStatusFilter: WorkspaceFilterValue;
  pushCenterStatusFilter: WorkspaceFilterValue;
  selectedEntityType: WorkspaceEntityType;
  selectedEntityId: string;
  panelMode: WorkspacePanelMode;
  laneCollapsedState: WorkspaceLaneCollapsedState;
  canvasSortMode: WorkspaceCanvasSortMode;
  canvasGroupMode: WorkspaceCanvasGroupMode;
  visibleLaneIds: WorkspaceCanvasLaneId[];
  density: WorkspaceDensity;
  focusedCanvasLaneId: WorkspaceCanvasLaneId;
  focusedCanvasCardId: string;
  selectedEntityIds: WorkspaceSelectedEntityIds;
  activeSelectionMode: WorkspaceSelectionMode;
  lastSelectedEntity: WorkspaceSelectedEntityRef | null;
  previewBundleId: string;
  bulkGuardrailSummary: string[];
  copyPreviewVisible: boolean;
  copyPreviewFormat: WorkspaceCopyPreviewFormat;
  copyStatus: WorkspaceCopyStatus;
  copyStatusMessage: string;
  currentDraftId: string;
  currentDraftVersion: number;
  currentDraftSnapshotHash: string;
  currentDraftIdempotencyKey: string;
  currentDraftReviewIdempotencyKey: string;
  currentDraftStatus: WorkspaceDraftStatus;
  draftSaveStatus: WorkspaceDraftSaveStatus;
  draftSaveMessage: string;
  draftReviewStatus: WorkspaceDraftReviewStatus;
  draftReviewMessage: string;
  currentGovernanceReviewId: string;
  currentGovernanceStatus: string;
  currentGovernanceIdempotencyKey: string;
  currentGovernanceReview: WorkspaceGovernanceReviewView | null;
  governanceRequestStatus: WorkspaceGovernanceRequestStatus;
  governanceRequestMessage: string;
  currentPushCenterBridge: WorkspacePushCenterBridgeView | null;
  pushCenterBridgeStatus: WorkspacePushCenterBridgeStatus;
  pushCenterBridgeMessage: string;
  currentPushCenterBridgeIdempotencyKey: string;
}

function defaultLaneCollapsedState(): WorkspaceLaneCollapsedState {
  return {
    plans: false,
    groups: false,
    nodes: false,
    executions: false,
    push_center: false,
    evidence: false
  };
}

function defaultSelectedEntityIds(): WorkspaceSelectedEntityIds {
  return {
    plan: [],
    group: [],
    node: [],
    execution: [],
    push_center: [],
    evidence: []
  };
}

function selectedIdFromSelection(selection: WorkspaceSelectionState): string {
  if (selection.selectedEntityType === "plan") return selection.selectedPlanId;
  if (selection.selectedEntityType === "group") return selection.selectedGroupId;
  if (selection.selectedEntityType === "node") return selection.selectedNodeId;
  if (selection.selectedEntityType === "execution") return selection.selectedExecutionId;
  if (selection.selectedEntityType === "push_center") return selection.selectedPushCenterJobId;
  return "evidence";
}

export function createWorkspaceViewState(fixture: WorkspaceFixture): WorkspaceViewState {
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

export function selectEntityInViewState(
  viewState: WorkspaceViewState,
  selectedEntityType: WorkspaceEntityType,
  selectedEntityId: string
): WorkspaceViewState {
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

export function updateWorkspaceViewState(
  viewState: WorkspaceViewState,
  updates: Partial<WorkspaceViewState>
): WorkspaceViewState {
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

export function toggleWorkspaceCanvasLane(
  viewState: WorkspaceViewState,
  laneId: WorkspaceCanvasLaneId
): WorkspaceViewState {
  return updateWorkspaceViewState(viewState, {
    laneCollapsedState: {
      ...viewState.laneCollapsedState,
      [laneId]: !viewState.laneCollapsedState[laneId]
    }
  });
}

export function selectionFromViewState(
  fixture: WorkspaceFixture,
  viewState: WorkspaceViewState
): WorkspaceSelectionState {
  const selection = { ...fixture.defaultSelection, selectedEntityType: viewState.selectedEntityType };
  if (viewState.selectedEntityType === "plan") selection.selectedPlanId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "group") selection.selectedGroupId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "node") selection.selectedNodeId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "execution") selection.selectedExecutionId = viewState.selectedEntityId;
  if (viewState.selectedEntityType === "push_center") selection.selectedPushCenterJobId = viewState.selectedEntityId;
  return selection;
}
