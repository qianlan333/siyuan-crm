import assert from "node:assert/strict";

import { renderP1GroupOpsWorkspace } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_layout.js";
import {
  DEFAULT_WORKSPACE_API_CONFIG,
  loadGroupOpsWorkspaceData
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_api.js";
import {
  filterWorkspaceView
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_filters.js";
import {
  buildWorkspaceCanvasLanes
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_grouping.js";
import {
  densityClassName,
  densityDescription
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_density.js";
import {
  keyboardHintText,
  moveWorkspaceCanvasSelection
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_keyboard.js";
import {
  clearMultiSelection,
  countMultiSelected,
  selectVisibleItems,
  toggleMultiSelectedEntity
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_multi_select.js";
import {
  buildWorkspacePreviewBundle
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_preview_bundle.js";
import {
  assertCopySafeBundleOutput,
  buildCopySafeBundleJson,
  buildCopySafeBundleText,
  copyBundleSummaryToClipboard
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_bundle_export.js";
import {
  sortCanvasCards
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_sorting.js";
import {
  createWorkspaceSelectionState,
  findWorkspaceDetail,
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_detail.js";
import {
  archiveDraft,
  assertWorkspaceDraftReviewPayloadSafe,
  assertWorkspaceDraftPayloadSafe,
  buildWorkspaceDraftReviewPayload,
  buildWorkspaceDraftPayload,
  createDraft,
  getDraft,
  isDraftConflictError,
  listDrafts,
  requestDraftReview,
  updateDraft
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_draft_api.js";
import * as WorkspaceGovernanceApi from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_governance_api.js";
import {
  assertGovernanceResponseSafe,
  assertPushCenterBridgeResponseSafe,
  assertWorkspaceGovernanceStepPayloadSafe,
  assertWorkspacePushCenterBridgePayloadSafe,
  approveGovernanceStep,
  bridgeGovernanceToPushCenter,
  buildApproveGovernanceStepPayload,
  buildExpireGovernanceReviewPayload,
  buildPushCenterBridgePayload,
  buildRejectGovernanceStepPayload,
  assertWorkspaceGovernancePayloadSafe,
  buildWorkspaceGovernanceRequestPayload,
  expireGovernanceReview,
  getDraftGovernance,
  getGovernanceReview,
  getGovernancePushCenterBridge,
  isGovernanceConflictError,
  rejectGovernanceStep,
  requestGovernance,
  stableGovernanceStepIdempotencyKey,
  stableGovernanceIdempotencyKey,
  stablePushCenterBridgeIdempotencyKey
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_governance_api.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_fixture.js";
import {
  buildGroupOpsWorkspaceStatusModel,
  workspaceCanRenderGlobalPass
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_status.js";
import {
  createWorkspaceViewState,
  selectEntityInViewState,
  toggleWorkspaceCanvasLane,
  updateWorkspaceViewState
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_view_state.js";

function assertNoSensitiveFixtureStrings(value) {
  for (const forbidden of [
    "raw_external_userid",
    "receiver_plaintext",
    "wrOgAAA001",
    "owner_001",
    "raw_callback_body",
    "raw_target_list",
    "raw_member_id",
    "openid",
    "unionid",
    "Authorization",
    "access_token",
    "corpsecret",
    "suite secret",
    "fixture text",
    "13800138000",
    "secret",
    "token"
  ]) {
    assert.equal(value.includes(forbidden), false, `unexpected sensitive fixture string: ${forbidden}`);
  }
}

const model = buildGroupOpsWorkspaceStatusModel(P1_GROUP_OPS_WORKSPACE_FIXTURE);
assert.deepEqual(model.originalStatuses, [
  "sent",
  "governance-missing",
  "downstream-pending",
  "external-config-blocked"
]);
assert.deepEqual(model.originalStatuses.slice().sort(), model.previewStatuses.slice().sort());
assert.equal(model.canClaimPass90Plus, false);
assert.equal(model.sentBypassesGovernance, false);
assert.equal(workspaceCanRenderGlobalPass(P1_GROUP_OPS_WORKSPACE_FIXTURE.payload), false);

for (const row of model.validations) {
  assert.equal(row.dropAllowed, false);
  assert.equal(row.statusAfterDrop, row.status);
  assert.ok(row.blockedReason.length > 0);
}

const governanceRow = model.validations.find((row) => row.status === "governance-missing");
assert.ok(governanceRow);
assert.ok(governanceRow.guardrails.includes("requires_approval"));
assert.ok(governanceRow.guardrails.includes("requires_allowlist"));
assert.ok(governanceRow.guardrails.includes("requires_gray_window"));

const sentRow = model.validations.find((row) => row.status === "sent");
assert.ok(sentRow);
assert.ok(sentRow.guardrails.includes("requires_push_center"));
assert.ok(sentRow.guardrails.includes("no_direct_send"));
assert.ok(sentRow.guardrails.includes("no_external_call"));
assert.ok(sentRow.guardrails.includes("no_production_write"));

const root = { innerHTML: "" };
renderP1GroupOpsWorkspace(root, P1_GROUP_OPS_WORKSPACE_FIXTURE);
assert.equal(root.innerHTML.includes("P1 Native workspace preview"), true);
assert.equal(root.innerHTML.includes("draft-only / preview-only"), true);
assert.equal(root.innerHTML.includes("计划 / 人群 / 任务"), true);
assert.equal(root.innerHTML.includes("Read-only grouped canvas"), true);
assert.equal(root.innerHTML.includes("Plans"), true);
assert.equal(root.innerHTML.includes("Audiences / Groups"), true);
assert.equal(root.innerHTML.includes("Tasks / Nodes"), true);
assert.equal(root.innerHTML.includes("Executions"), true);
assert.equal(root.innerHTML.includes("Push Center"), true);
assert.equal(root.innerHTML.includes("Evidence / Guardrails"), true);
assert.equal(root.innerHTML.includes("属性面板 / guardrail / evidence state"), true);
assert.equal(root.innerHTML.includes("Search / filters"), true);
assert.equal(root.innerHTML.includes("data-view-state-memory-only=\"true\""), true);
assert.equal(root.innerHTML.includes("data-canvas-local-state=\"true\""), true);
assert.equal(root.innerHTML.includes("data-canvas-sort-mode=\"default\""), true);
assert.equal(root.innerHTML.includes("data-canvas-group-mode=\"entity_lane\""), true);
assert.equal(root.innerHTML.includes("data-density=\"comfortable\""), true);
assert.equal(root.innerHTML.includes("Safe preview only"), true);
assert.equal(root.innerHTML.includes("data-safe-preview-affordance=\"true\""), true);
assert.equal(root.innerHTML.includes("data-safe-preview-footer=\"true\""), true);
assert.equal(root.innerHTML.includes("Keyboard preview"), true);
assert.equal(root.innerHTML.includes("Select for preview bundle"), true);
assert.equal(root.innerHTML.includes("Draft persistence"), true);
assert.equal(root.innerHTML.includes("Save draft"), true);
assert.equal(root.innerHTML.includes("Save as new draft"), true);
assert.equal(root.innerHTML.includes("Request review"), true);
assert.equal(root.innerHTML.includes("Archive draft"), true);
assert.equal(root.innerHTML.includes("draft_status"), true);
assert.equal(root.innerHTML.includes("ready_for_review"), true);
assert.equal(root.innerHTML.includes("approved</dt><dd>false"), true);
assert.equal(root.innerHTML.includes("data-draft-persistence=\"frontend_save_only\""), true);
assert.equal(root.innerHTML.includes("data-push-center-job-created=\"false\""), true);
assert.equal(root.innerHTML.includes("data-external-effect-job-created=\"false\""), true);
assert.equal(root.innerHTML.includes("Push Center bridge 仅在治理通过后创建 pending projection"), true);
assert.equal(root.innerHTML.includes("data-multi-selected=\"false\""), true);
assert.equal(root.innerHTML.includes("Plan detail"), true);
assert.equal(root.innerHTML.includes("Selected preview result"), true);
assert.equal(root.innerHTML.includes("Preview result / blocked reason"), true);
assert.equal(root.innerHTML.includes("data-p1-native-workspace=\"group_ops\""), true);
assert.equal(root.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(root.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(root.innerHTML.includes("sent evidence 不等于 governance complete"), true);
assert.equal(root.innerHTML.includes("Push Center pending 不等于 completed"), true);
assert.equal(root.innerHTML.includes("evidence-incomplete 不等于 success"), true);
assert.equal(root.innerHTML.includes("P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS"), true);
assert.equal(root.innerHTML.includes("request-review 不等于 approval"), true);
assert.equal(root.innerHTML.includes("ready_for_review 不等于 approved"), true);
assert.equal(root.innerHTML.includes("Governance panel"), true);
assert.equal(root.innerHTML.includes("Request governance"), true);
assert.equal(root.innerHTML.includes("Refresh governance"), true);
assert.equal(root.innerHTML.includes("Bridge to Push Center"), true);
assert.equal(root.innerHTML.includes("Refresh bridge status"), true);
assert.equal(root.innerHTML.includes("data-governance-panel=\"frontend_bridge_integration\""), true);
assert.equal(root.innerHTML.includes("data-push-center-bridge-panel=\"true\""), true);
assert.equal(root.innerHTML.includes("data-workspace-request-governance=\"true\" disabled"), true);
assert.equal(root.innerHTML.includes("data-workspace-bridge-push-center=\"true\" disabled"), true);
assert.equal(root.innerHTML.includes("governance request 不等于 approval"), true);
assert.equal(root.innerHTML.includes("pending steps 不等于 approved"), true);
assert.equal(root.innerHTML.includes("execution_status</dt><dd>not_execution"), true);
assert.equal(root.innerHTML.includes("push_center_job_created</dt><dd>false"), true);
assert.equal(root.innerHTML.includes("Bridge 只进入 Push Center pending，不会发送"), true);
assert.equal(root.innerHTML.includes("push_center_pending_not_sent"), false);
assert.equal(root.innerHTML.includes("external_effect_job_created</dt><dd>false"), true);
assert.equal(root.innerHTML.includes("broadcast_job_created</dt><dd>false"), true);
assert.equal(root.innerHTML.includes("internal_event_created</dt><dd>false"), true);
assert.equal(root.innerHTML.includes("data-selected-entity-type=\"plan\""), true);
assert.equal(root.innerHTML.includes("data-can-render-pass90=\"true\""), false);
assertNoSensitiveFixtureStrings(root.innerHTML);

const defaultSelection = createWorkspaceSelectionState(P1_GROUP_OPS_WORKSPACE_FIXTURE);
const selectedPlan = findWorkspaceDetail(P1_GROUP_OPS_WORKSPACE_FIXTURE, defaultSelection);
assert.equal(selectedPlan.entityType, "plan");

const defaultViewState = createWorkspaceViewState(P1_GROUP_OPS_WORKSPACE_FIXTURE);
const selectedNode = selectEntityInViewState(defaultViewState, "node", "node-preview-task");
const nodeRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(nodeRoot, P1_GROUP_OPS_WORKSPACE_FIXTURE, selectedNode);
assert.equal(nodeRoot.innerHTML.includes("data-selected-entity-type=\"node\""), true);
assert.equal(nodeRoot.innerHTML.includes("Node / task summary"), true);
assert.equal(nodeRoot.innerHTML.includes("preview-only"), true);
assertNoSensitiveFixtureStrings(nodeRoot.innerHTML);

const selectedExecution = selectEntityInViewState(defaultViewState, "execution", "execution-preview-empty");
const executionRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(executionRoot, P1_GROUP_OPS_WORKSPACE_FIXTURE, selectedExecution);
assert.equal(executionRoot.innerHTML.includes("data-selected-entity-type=\"execution\""), true);
assert.equal(executionRoot.innerHTML.includes("Execution summary"), true);
assert.equal(model.originalStatuses.includes("sent"), true);
assert.equal(buildGroupOpsWorkspaceStatusModel(P1_GROUP_OPS_WORKSPACE_FIXTURE).originalStatuses[0], "sent");
assertNoSensitiveFixtureStrings(executionRoot.innerHTML);

const requests = [];
const fixture = await loadGroupOpsWorkspaceData(DEFAULT_WORKSPACE_API_CONFIG, async (url) => {
  requests.push(url);
  if (url.includes("/plans?")) {
    return {
      ok: true,
      source_status: "fixture_local_contract",
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [
        {
          id: 7,
          plan_name: "真实群运营计划",
          plan_type: "standard",
          status: "active",
          bound_group_count: 2,
          today_estimated_reach: 42,
          owner_userid: "owner_001"
        }
      ],
      total: 1
    };
  }
  if (url.endsWith("/7")) {
    return {
      ok: true,
      source_status: "fixture_local_contract",
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      plan: { id: 7, plan_name: "真实群运营计划", status: "active" },
      groups_summary: { bound_group_count: 2, estimated_reach: 42, internal_member_count: 3, external_member_count: 39 },
      nodes: [{ id: 1, action_title: "welcome", text_content: "fixture text" }]
    };
  }
  if (url.endsWith("/7/groups")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ chat_id: "wrOgAAA001", group_name_snapshot: "不可渲染群名" }],
      summary: { bound_group_count: 2, estimated_reach: 42 },
      total: 2
    };
  }
  if (url.endsWith("/7/nodes")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ id: 1, action_title: "welcome", text_content: "fixture text" }],
      total: 1
    };
  }
  if (url.includes("/7/executions")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      side_effect_safety: { db_write_executed: false, real_external_call_executed: false },
      items: [{ id: 11, status: "pending", raw_external_userid: "wrOgAAA001", phone: "13800138000" }],
      total: 1
    };
  }
  if (url.includes("/push-center/jobs")) {
    return {
      ok: true,
      route_owner: "ai_crm_next",
      real_external_call_executed: false,
      items: [
        {
          projection_id: "external_effect_job:97",
          effective_status: "sent",
          retryable: false,
          operator_action_required: false
        }
      ],
      total: 1
    };
  }
  throw new Error(`Unexpected URL: ${url}`);
});

assert.equal(requests.length, 6);
assert.equal(fixture.dataBindingStatus, "real_data_bound");
assert.equal(fixture.dataSourceLabel, "fixture_local_contract");
assert.equal(fixture.realExternalCallExecuted, false);
assert.equal(fixture.productionWriteExecuted, false);
assert.equal(fixture.payload.canClaimPass90Plus, false);
assert.equal(fixture.leftRailItems.some((item) => item.label === "真实群运营计划"), true);
assert.equal(fixture.leftRailItems.some((item) => item.summary.includes("2 个绑定群")), true);
assert.equal(fixture.payload.scenarios.some((scenario) => scenario.status === "governance-missing"), true);
assert.equal(fixture.payload.scenarios.some((scenario) => scenario.status === "sent"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "plan" && item.title === "真实群运营计划"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "group" && item.fields.some((field) => field.label === "bound_group_count" && field.value === "2")), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "node"), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "execution" && item.fields.some((field) => field.value === "11")), true);
assert.equal(fixture.detailItems.some((item) => item.entityType === "push_center" && item.fields.some((field) => field.value === "external_effect_job:97")), true);

const realViewState = createWorkspaceViewState(fixture);
const keywordFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { keyword: "真实群运营" }));
assert.equal(keywordFiltered.visibleLeftRailItems.length, 1);
assert.equal(keywordFiltered.visibleLeftRailItems[0].entityType, "plan");
assert.equal(keywordFiltered.viewState.selectedEntityType, "plan");

const planStatusFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { planStatusFilter: "ready" }));
assert.equal(planStatusFiltered.visibleLeftRailItems.length, 1);
assert.equal(planStatusFiltered.visibleLeftRailItems[0].status, "ready");

const executionFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "execution", executionStatusFilter: "pending" }));
assert.equal(executionFiltered.visibleLeftRailItems.length, 1);
assert.equal(executionFiltered.visibleLeftRailItems[0].entityType, "execution");
assert.equal(executionFiltered.viewState.selectedEntityType, "execution");

const pushFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "push_center", pushCenterStatusFilter: "sent" }));
assert.equal(pushFiltered.visibleLeftRailItems.length, 1);
assert.equal(pushFiltered.visibleLeftRailItems[0].entityType, "push_center");

const evidenceFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "evidence" }));
assert.equal(evidenceFiltered.visibleLeftRailItems.length, 1);
assert.equal(evidenceFiltered.visibleLeftRailItems[0].entityType, "evidence");

const selectedPushThenPlanOnly = filterWorkspaceView(
  fixture,
  updateWorkspaceViewState(selectEntityInViewState(realViewState, "push_center", "push_center-external_effect_job:97"), { entityTypeFilter: "plan" })
);
assert.equal(selectedPushThenPlanOnly.viewState.selectedEntityType, "plan");
assert.equal(selectedPushThenPlanOnly.viewState.selectedEntityId, "plan-7");

const emptyFiltered = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { keyword: "no matching redacted item" }));
assert.equal(emptyFiltered.isEmpty, true);
assert.equal(emptyFiltered.viewState.panelMode, "summary");

const realRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realRoot, fixture);
assert.equal(realRoot.innerHTML.includes("真实群运营计划"), true);
assert.equal(realRoot.innerHTML.includes("real_data_bound"), true);
assert.equal(realRoot.innerHTML.includes("Search / filters"), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"plans\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"groups\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"nodes\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"executions\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"push_center\""), true);
assert.equal(realRoot.innerHTML.includes("data-canvas-lane-id=\"evidence\""), true);
assert.equal(realRoot.innerHTML.includes("Read-only data loaded"), true);
assert.equal(realRoot.innerHTML.includes("external_effect_job:97"), true);
assert.equal(realRoot.innerHTML.includes("wrOgAAA001"), false);
assert.equal(realRoot.innerHTML.includes("owner_001"), false);
assert.equal(realRoot.innerHTML.includes("不可渲染群名"), false);
assert.equal(realRoot.innerHTML.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-production-write-executed=\"false\""), true);
assert.equal(realRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assertNoSensitiveFixtureStrings(realRoot.innerHTML);

const savedDraftState = updateWorkspaceViewState(realViewState, {
  currentDraftId: "gowd_safe",
  currentDraftVersion: 2,
  currentDraftSnapshotHash: "snapshot_safe",
  currentDraftStatus: "draft",
  draftSaveStatus: "saved",
  draftSaveMessage: "草稿已保存；仍为 preview-only，不可执行。"
});
const savedDraftRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(savedDraftRoot, fixture, savedDraftState);
assert.equal(savedDraftRoot.innerHTML.includes("draft_status</dt><dd>draft"), true);
assert.equal(savedDraftRoot.innerHTML.includes("data-workspace-request-review-draft=\"true\" disabled"), false);
assert.equal(savedDraftRoot.innerHTML.includes("Request review"), true);
assert.equal(savedDraftRoot.innerHTML.includes("ready_for_review</dt><dd>false"), true);
assertNoSensitiveFixtureStrings(savedDraftRoot.innerHTML);

const readyReviewState = updateWorkspaceViewState(savedDraftState, {
  currentDraftVersion: 3,
  currentDraftStatus: "ready_for_review",
  currentDraftReviewIdempotencyKey: "p1-gow-request-review:gowd_safe:2:snapshot_safe",
  draftReviewStatus: "ready_for_review",
  draftReviewMessage: "ready_for_review 已记录；这不是 approval，也不是 Push Center bridge。"
});
const readyReviewRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(readyReviewRoot, fixture, readyReviewState);
assert.equal(readyReviewRoot.innerHTML.includes("draft_status</dt><dd>ready_for_review"), true);
assert.equal(readyReviewRoot.innerHTML.includes("ready_for_review</dt><dd>true"), true);
assert.equal(readyReviewRoot.innerHTML.includes("approved</dt><dd>false"), true);
assert.equal(readyReviewRoot.innerHTML.includes("data-workspace-request-review-draft=\"true\" disabled"), true);
assert.equal(readyReviewRoot.innerHTML.includes("data-workspace-request-governance=\"true\" disabled"), false);
assert.equal(readyReviewRoot.innerHTML.includes("allowlist_hash"), true);
assert.equal(readyReviewRoot.innerHTML.includes("window_status</dt><dd>pending"), true);
assert.equal(readyReviewRoot.innerHTML.includes("这不是 approval"), true);
assertNoSensitiveFixtureStrings(readyReviewRoot.innerHTML);

const governanceApprovedReviewView = {
  review_id: "gowg_safe",
  draft_id: "gowd_safe",
  review_status: "governance_approved",
  snapshot_hash: "snapshot_safe",
  steps: [
    { step_id: "gows_operator", step_type: "operator_approval", step_status: "approved", actor_metadata: { actor_label_present: true }, updated_at: "2026-06-24T12:00:00Z" },
    { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "approved", actor_metadata: { actor_id_present: true }, updated_at: "2026-06-24T12:01:00Z" },
    { step_id: "gows_gray", step_type: "gray_window", step_status: "approved", actor_metadata: { actor_label_present: true }, updated_at: "2026-06-24T12:02:00Z" }
  ],
  allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
  gray_window: {
    start_at: "2026-06-24T09:00:00+08:00",
    end_at: "2099-06-25T10:00:00+08:00",
    timezone: "Asia/Shanghai",
    window_status: "approved"
  },
  approved: false,
  execution_status: "not_execution",
  push_center_job_created: false,
  external_effect_job_created: false,
  broadcast_job_created: false,
  internal_event_created: false,
  real_external_call: false,
  can_claim_pass_90_plus: false
};
const bridgeReadyState = updateWorkspaceViewState(readyReviewState, {
  currentGovernanceReviewId: "gowg_safe",
  currentGovernanceStatus: "governance_approved",
  currentGovernanceReview: governanceApprovedReviewView,
  governanceRequestStatus: "requested",
  governanceRequestMessage: "三个 governance steps 已 approved，状态为 governance_approved；仍为 not_execution。"
});
const bridgeReadyRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(bridgeReadyRoot, fixture, bridgeReadyState);
assert.equal(bridgeReadyRoot.innerHTML.includes("governance_approved</dt><dd>true"), true);
assert.equal(bridgeReadyRoot.innerHTML.includes("data-workspace-bridge-push-center=\"true\" disabled"), false);
assert.equal(bridgeReadyRoot.innerHTML.includes("push_center_bridge_payload_invalid"), false);
assert.equal(bridgeReadyRoot.innerHTML.includes("Push Center bridge 仅适用于 governance_approved"), false);
assertNoSensitiveFixtureStrings(bridgeReadyRoot.innerHTML);

const bridgedState = updateWorkspaceViewState(bridgeReadyState, {
  currentPushCenterBridge: {
    review_id: "gowg_safe",
    draft_id: "gowd_safe",
    review_status: "governance_approved",
    push_center_job_created: true,
    push_center_job_id: "p1-gow-push-center:gowg_safe",
    push_center_projection_id: "p1-gow-push-center:gowg_safe",
    push_center_status: "pending",
    execution_status: "push_center_pending_not_sent",
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false
  },
  pushCenterBridgeStatus: "bridged",
  pushCenterBridgeMessage: "Push Center bridge 已创建 pending projection；仍不是 sent/completed。"
});
const bridgedRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(bridgedRoot, fixture, bridgedState);
assert.equal(bridgedRoot.innerHTML.includes("push_center_job_created</dt><dd>true"), true);
assert.equal(bridgedRoot.innerHTML.includes("push_center_status</dt><dd>pending"), true);
assert.equal(bridgedRoot.innerHTML.includes("push_center_pending_not_sent"), true);
assert.equal(bridgedRoot.innerHTML.includes("external_effect_job_created</dt><dd>false"), true);
assert.equal(bridgedRoot.innerHTML.includes("broadcast_job_created</dt><dd>false"), true);
assert.equal(bridgedRoot.innerHTML.includes("internal_event_created</dt><dd>false"), true);
assert.equal(bridgedRoot.innerHTML.includes("data-workspace-bridge-push-center=\"true\" disabled"), true);
assert.equal(bridgedRoot.innerHTML.includes("execution_status</dt><dd>sent"), false);
assert.equal(bridgedRoot.innerHTML.includes("push_center_status</dt><dd>sent"), false);
assert.equal(bridgedRoot.innerHTML.includes("execution_status</dt><dd>completed"), false);
assertNoSensitiveFixtureStrings(bridgedRoot.innerHTML);

const lanes = buildWorkspaceCanvasLanes(fixture, filterWorkspaceView(fixture, realViewState), realViewState);
assert.deepEqual(lanes.map((lane) => lane.id), ["plans", "groups", "nodes", "executions", "push_center", "evidence"]);
assert.equal(lanes.every((lane) => lane.cards.length === 1), true);
assert.equal(lanes.find((lane) => lane.id === "evidence").blockedCount, 1);
assert.equal(lanes.find((lane) => lane.id === "evidence").actionRequiredCount, 1);
assert.equal(lanes.find((lane) => lane.id === "push_center").visibleCount, 1);
assert.equal(keyboardHintText().includes("No task is executed"), true);
assert.equal(keyboardHintText().includes("Space toggles bundle selection"), true);
assert.equal(densityClassName("compact"), "p1-workspace-density--compact");
assert.equal(densityDescription("compact").includes("does not hide status or guardrails"), true);

const statusSorted = sortCanvasCards([
  { originalIndex: 0, status: "sent", entityType: "push_center", updatedOrCreatedTime: "" },
  { originalIndex: 1, status: "governance-missing", entityType: "evidence", updatedOrCreatedTime: "" },
  { originalIndex: 2, status: "pending", entityType: "execution", updatedOrCreatedTime: "" }
], "blocked_first");
assert.deepEqual(statusSorted.map((card) => card.status), ["governance-missing", "pending", "sent"]);

const collapsedViewState = toggleWorkspaceCanvasLane(realViewState, "push_center");
const collapsedLanes = buildWorkspaceCanvasLanes(fixture, filterWorkspaceView(fixture, collapsedViewState), collapsedViewState);
assert.equal(collapsedLanes.find((lane) => lane.id === "push_center").isCollapsed, true);
const collapsedRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(collapsedRoot, fixture, collapsedViewState);
assert.equal(collapsedRoot.innerHTML.includes("data-canvas-lane-id=\"push_center\" data-lane-collapsed=\"true\""), true);
assertNoSensitiveFixtureStrings(collapsedRoot.innerHTML);

const compactViewState = updateWorkspaceViewState(realViewState, { density: "compact" });
const compactRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(compactRoot, fixture, compactViewState);
assert.equal(compactRoot.innerHTML.includes("data-density=\"compact\""), true);
assert.equal(compactRoot.innerHTML.includes("p1-workspace-density--compact"), true);
assert.equal(compactRoot.innerHTML.includes("Compact density keeps cards shorter"), true);
assert.equal(fixture.leftRailItems.some((item) => item.status === "sent"), true);
assertNoSensitiveFixtureStrings(compactRoot.innerHTML);

const keyboardDown = moveWorkspaceCanvasSelection(lanes, realViewState, "ArrowRight");
assert.equal(keyboardDown.selectedEntityType, "group");
assert.equal(keyboardDown.selectedEntityId, "group-plan-7");
const keyboardEnter = moveWorkspaceCanvasSelection(lanes, keyboardDown, "Enter");
assert.equal(keyboardEnter.selectedEntityType, "group");
assert.equal(keyboardEnter.selectedEntityId, "group-plan-7");
const keyboardEscape = moveWorkspaceCanvasSelection(lanes, keyboardEnter, "Escape");
assert.equal(keyboardEscape.panelMode, "summary");
assert.equal(fixture.payload.canClaimPass90Plus, false);

const multiSelectedPlan = toggleMultiSelectedEntity(realViewState, "plan", "plan-7");
assert.equal(multiSelectedPlan.activeSelectionMode, "multi");
assert.equal(countMultiSelected(multiSelectedPlan), 1);
assert.equal(multiSelectedPlan.previewBundleId.includes("preview-bundle-1"), true);
const multiSelectedBundle = toggleMultiSelectedEntity(multiSelectedPlan, "evidence", "evidence-plan-7-governance");
assert.equal(countMultiSelected(multiSelectedBundle), 2);
const bundle = buildWorkspacePreviewBundle(fixture, filterWorkspaceView(fixture, multiSelectedBundle), multiSelectedBundle);
assert.equal(bundle.selectedCount, 2);
assert.equal(bundle.canExecute, false);
assert.equal(bundle.previewOnly, true);
assert.equal(bundle.productionWrite, false);
assert.equal(bundle.realExternalCall, false);
assert.equal(bundle.canClaimPass90Plus, false);
assert.equal(bundle.governanceMissingCount, 1);
assert.equal(bundle.blockedCount, 1);
assert.equal(bundle.guardrails.includes("any blocked item -> bundle cannot execute"), true);
const draftPayload = buildWorkspaceDraftPayload(fixture, filterWorkspaceView(fixture, multiSelectedBundle), multiSelectedBundle);
const draftPayloadRepeat = buildWorkspaceDraftPayload(fixture, filterWorkspaceView(fixture, multiSelectedBundle), multiSelectedBundle);
assert.equal(draftPayload.idempotency_key, draftPayloadRepeat.idempotency_key);
assert.equal(draftPayload.source_plan_id, "plan-7");
assert.equal(draftPayload.sanitized_payload.preview_only, true);
assert.equal(draftPayload.guardrail_summary.real_external_call, false);
assert.equal(draftPayload.guardrail_summary.push_center_job_created, false);
assert.equal(draftPayload.guardrail_summary.external_effect_job_created, false);
assert.equal(draftPayload.guardrail_summary.can_claim_pass_90_plus, false);
assert.equal(draftPayload.approval_requirements.request_review_required, true);
assert.equal(draftPayload.approval_requirements.governance_review_required, true);
assert.equal(draftPayload.approval_requirements.push_center_bridge_requires_governance_approved, true);
assert.equal(draftPayload.items.length, 2);
assert.equal(draftPayload.items.every((item) => ["plan", "evidence"].includes(item.item_type)), true);
assertWorkspaceDraftPayloadSafe(draftPayload);
const reviewPayload = buildWorkspaceDraftReviewPayload("gowd_safe", 2, "snapshot_safe");
const reviewPayloadRepeat = buildWorkspaceDraftReviewPayload("gowd_safe", 2, "snapshot_safe");
assert.equal(reviewPayload.idempotency_key, "p1-gow-request-review:gowd_safe:2:snapshot_safe");
assert.equal(reviewPayload.idempotency_key, reviewPayloadRepeat.idempotency_key);
assert.equal(reviewPayload.version, 2);
assert.equal(reviewPayload.client_snapshot_hash, "snapshot_safe");
assertWorkspaceDraftReviewPayloadSafe(reviewPayload);
const governancePayload = buildWorkspaceGovernanceRequestPayload("gowd_safe", "snapshot_safe", {
  allowlistHash: "allowlist-safe-hash",
  allowlistCount: 2,
  grayWindow: {
    start_at: "2026-06-24T09:00:00+08:00",
    end_at: "2099-06-25T10:00:00+08:00",
    timezone: "Asia/Shanghai"
  }
});
const governancePayloadRepeat = buildWorkspaceGovernanceRequestPayload("gowd_safe", "snapshot_safe", {
  allowlistHash: "allowlist-safe-hash",
  allowlistCount: 2,
  grayWindow: {
    start_at: "2026-06-24T09:00:00+08:00",
    end_at: "2099-06-25T10:00:00+08:00",
    timezone: "Asia/Shanghai"
  }
});
assert.equal(governancePayload.idempotency_key, governancePayloadRepeat.idempotency_key);
assert.equal(governancePayload.idempotency_key.startsWith("p1-gow-governance:gowd_safe:snapshot_safe:allowlist-safe-hash:"), true);
assert.equal(stableGovernanceIdempotencyKey("draft", "snapshot", "allowlist", "window"), "p1-gow-governance:draft:snapshot:allowlist:window");
assert.equal(governancePayload.client_snapshot_hash, "snapshot_safe");
assert.equal(governancePayload.allowlist_summary.allowlist_count, 2);
assertWorkspaceGovernancePayloadSafe(governancePayload);
assert.equal(typeof WorkspaceGovernanceApi.approveGovernanceStep, "function");
assert.equal(typeof WorkspaceGovernanceApi.rejectGovernanceStep, "function");
assert.equal(typeof WorkspaceGovernanceApi.expireGovernanceReview, "function");
assert.equal(typeof WorkspaceGovernanceApi.bridgeGovernanceToPushCenter, "function");
assert.equal(typeof WorkspaceGovernanceApi.getGovernancePushCenterBridge, "function");
assert.equal(Object.keys(WorkspaceGovernanceApi).some((name) => /execute|send|run/i.test(name)), false);
for (const bait of [
  { sanitized_payload: { ["raw_" + "external_userid"]: "wrOgAAA001" } },
  { sanitized_payload: { contact: "13800138000" } },
  { items: [{ item_type: "group", item_ref_id: "safe", item_order: 0, sanitized_item: { ["raw_" + "receiver"]: "unsafe" }, guardrail_summary: {} }] },
  { guardrail_summary: { ["access_" + "token"]: "unsafe" } },
  { approval_requirements: { ["Authorization".toLowerCase()]: "unsafe" } }
]) {
  assert.throws(() => assertWorkspaceDraftPayloadSafe({ ...draftPayload, ...bait }), /draft_payload_sensitive/);
}
for (const bait of [
  { version: 2, idempotency_key: "p1-safe", review_note: "13800138000" },
  { version: 2, idempotency_key: "p1-safe", client_snapshot_hash: "access_" + "token" }
]) {
  assert.throws(() => assertWorkspaceDraftReviewPayloadSafe(bait), /draft_payload_sensitive/);
}
for (const bait of [
  { allowlist_summary: { ...governancePayload.allowlist_summary, ["raw_" + "receiver"]: "unsafe" } },
  { allowlist_summary: { ...governancePayload.allowlist_summary, phone: "13800138000" } },
  { request_note: "raw_" + "target" },
  { gray_window: { ...governancePayload.gray_window, ["Authorization".toLowerCase()]: "unsafe" } }
]) {
  assert.throws(() => assertWorkspaceGovernancePayloadSafe({ ...governancePayload, ...bait }), /draft_payload_sensitive/);
}
const governanceReviewContext = {
  review_id: "gowg_safe",
  review_status: "approval_pending",
  allowlist_summary: { hash: "allowlist-safe-hash", count: 2 },
  gray_window: {
    start_at: "2026-06-24T09:00:00+08:00",
    end_at: "2099-06-25T10:00:00+08:00",
    timezone: "Asia/Shanghai",
    window_status: "pending"
  }
};
const operatorStepContext = { step_id: "gows_operator", step_type: "operator_approval", step_status: "pending" };
const allowlistStepContext = { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" };
const grayWindowStepContext = { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" };
const governanceApprovedContext = {
  ...governanceReviewContext,
  review_status: "governance_approved",
  snapshot_hash: "snapshot_safe",
  gray_window: {
    ...governanceReviewContext.gray_window,
    window_status: "approved"
  }
};
const operatorApprovePayload = buildApproveGovernanceStepPayload(governanceReviewContext, operatorStepContext, { approvalNote: "safe approval note" });
const allowlistApprovePayload = buildApproveGovernanceStepPayload(governanceReviewContext, allowlistStepContext);
const grayApprovePayload = buildApproveGovernanceStepPayload(governanceReviewContext, grayWindowStepContext);
const rejectStepPayload = buildRejectGovernanceStepPayload(governanceReviewContext, operatorStepContext, { rejectReason: "safe reject reason" });
const expireReviewPayload = buildExpireGovernanceReviewPayload(governanceReviewContext, { expireReason: "safe expire reason" });
const bridgePayload = buildPushCenterBridgePayload(governanceApprovedContext);
const bridgePayloadRepeat = buildPushCenterBridgePayload(governanceApprovedContext);
assert.equal(operatorApprovePayload.idempotency_key.startsWith("p1-gow-step-approve:gowg_safe:gows_operator:pending:"), true);
assert.equal(allowlistApprovePayload.allowlist_hash, "allowlist-safe-hash");
assert.equal(allowlistApprovePayload.allowlist_count, 2);
assert.equal(grayApprovePayload.idempotency_key.startsWith("p1-gow-step-approve:gowg_safe:gows_gray:pending:"), true);
assert.equal(rejectStepPayload.idempotency_key.startsWith("p1-gow-step-reject:gowg_safe:gows_operator:pending:"), true);
assert.equal(expireReviewPayload.idempotency_key.startsWith("p1-gow-review-expire:gowg_safe:approval_pending:"), true);
assert.equal(stableGovernanceStepIdempotencyKey("approve", "review", "step", "pending", "hash"), "p1-gow-step-approve:review:step:pending:hash");
assert.equal(stableGovernanceStepIdempotencyKey("expire", "review", "review", "approval_pending", "hash"), "p1-gow-review-expire:review:approval_pending:hash");
assert.equal(bridgePayload.idempotency_key, bridgePayloadRepeat.idempotency_key);
assert.equal(bridgePayload.idempotency_key.startsWith("p1-gow-push-center-bridge:gowg_safe:snapshot_safe:allowlist-safe-hash:"), true);
assert.equal(stablePushCenterBridgeIdempotencyKey("review", "snapshot", "allowlist", "window"), "p1-gow-push-center-bridge:review:snapshot:allowlist:window");
assert.equal(bridgePayload.client_snapshot_hash, "snapshot_safe");
assert.equal(bridgePayload.allowlist_hash, "allowlist-safe-hash");
assert.equal(bridgePayload.allowlist_count, 2);
assertWorkspaceGovernanceStepPayloadSafe(operatorApprovePayload);
assertWorkspacePushCenterBridgePayloadSafe(bridgePayload);
for (const bait of [
  { approval_note: "raw_" + "receiver" },
  { reject_reason: "13800138000" },
  { expire_reason: "access_" + "token" },
  { allowlist_hash: "raw_" + "target" }
]) {
  assert.throws(() => assertWorkspaceGovernanceStepPayloadSafe({ ...operatorApprovePayload, ...bait }), /draft_payload_sensitive/);
}
for (const bait of [
  { bridge_note: "raw_" + "receiver" },
  { bridge_note: "13800138000" },
  { allowlist_hash: "raw_" + "target" },
  { gray_window_summary: { ...bridgePayload.gray_window_summary, ["Authorization".toLowerCase()]: "unsafe" } }
]) {
  assert.throws(() => assertWorkspacePushCenterBridgePayloadSafe({ ...bridgePayload, ...bait }), /draft_payload_sensitive/);
}
assert.throws(
  () => buildWorkspaceGovernanceRequestPayload("gowd_safe", "snapshot_safe", {
    allowlistHash: "allowlist-safe-hash",
    grayWindow: {
      start_at: "2026-06-24T10:00:00+08:00",
      end_at: "2026-06-24T09:00:00+08:00",
      timezone: "Asia/Shanghai"
    }
  }),
  /governance_payload_invalid_gray_window/
);
const draftRequests = [];
const requestJson = async (url, options = {}) => {
  draftRequests.push({ url, options });
  if (options.method === "POST" && url.endsWith("/governance/request")) {
    return {
      ok: true,
      operation: "request_governance",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "approval_pending",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "pending" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
      ],
      allowlist_summary: {
        hash: "allowlist-safe-hash",
        count: 2,
        source_reference_summary: { reference_type: "p1_workspace_governance", summary_only: true }
      },
      gray_window: {
        start_at: "2026-06-24T09:00:00+08:00",
        end_at: "2099-06-25T10:00:00+08:00",
        timezone: "Asia/Shanghai",
        window_status: "pending"
      },
      preview_only: true,
      production_write: true,
      approved: false,
      ready_for_review: true,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/steps/gows_operator/approve")) {
    return {
      ok: true,
      operation: "approve_governance_step",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "allowlist_pending",
      step_id: "gows_operator",
      step_type: "operator_approval",
      step_status: "approved",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "approved", actor_metadata: { actor_label_present: true }, updated_at: "2026-06-24T12:00:00Z" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
      preview_only: true,
      production_write: true,
      approved: false,
      governance_approved: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/steps/gows_allowlist/approve")) {
    return {
      ok: true,
      operation: "approve_governance_step",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "gray_window_pending",
      step_id: "gows_allowlist",
      step_type: "receiver_allowlist",
      step_status: "approved",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "approved" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "approved", actor_metadata: { actor_id_present: true }, updated_at: "2026-06-24T12:01:00Z" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
      preview_only: true,
      production_write: true,
      approved: false,
      governance_approved: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/steps/gows_gray/approve")) {
    return {
      ok: true,
      operation: "approve_governance_step",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "governance_approved",
      step_id: "gows_gray",
      step_type: "gray_window",
      step_status: "approved",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "approved" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "approved" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "approved", actor_metadata: { actor_label_present: true }, updated_at: "2026-06-24T12:02:00Z" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "approved" },
      preview_only: true,
      production_write: true,
      approved: false,
      governance_approved: true,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/steps/gows_operator/reject")) {
    return {
      ok: true,
      operation: "reject_governance_step",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "governance_rejected",
      step_id: "gows_operator",
      step_type: "operator_approval",
      step_status: "rejected",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "rejected", actor_metadata: { actor_label_present: true }, updated_at: "2026-06-24T12:03:00Z" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
      preview_only: true,
      production_write: true,
      approved: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/governance/gowg_safe/expire")) {
    return {
      ok: true,
      operation: "expire_governance_review",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "governance_expired",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "expired" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "expired" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "expired" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "expired" },
      preview_only: true,
      production_write: true,
      approved: false,
      governance_approved: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/governance/gowg_safe/bridge-push-center")) {
    return {
      ok: true,
      operation: "bridge_push_center",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "governance_approved",
      push_center_job_created: true,
      push_center_job_id: "p1-gow-push-center:gowg_safe",
      push_center_projection_id: "p1-gow-push-center:gowg_safe",
      push_center_status: "pending",
      push_center_metadata: {
        source: "p1_group_ops_workspace",
        draft_id: "gowd_safe",
        review_id: "gowg_safe",
        governance_status: "governance_approved",
        snapshot_hash: "snapshot_safe",
        allowlist_hash: "allowlist-safe-hash",
        allowlist_count: 2,
        gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "approved" },
        no_external_call: true
      },
      preview_only: true,
      production_write: true,
      production_write_scope: "governance_bridge_metadata_only",
      approved: false,
      governance_approved: true,
      ready_for_review: true,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      execution_status: "push_center_pending_not_sent",
      can_claim_pass_90_plus: false
    };
  }
  if (url.endsWith("/governance/gowg_safe/push-center-bridge")) {
    return {
      ok: true,
      operation: "get_push_center_bridge",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "governance_approved",
      push_center_job_created: true,
      push_center_job_id: "p1-gow-push-center:gowg_safe",
      push_center_projection_id: "p1-gow-push-center:gowg_safe",
      push_center_status: "pending",
      push_center_metadata: {
        source: "p1_group_ops_workspace",
        no_external_call: true,
        snapshot_hash: "snapshot_safe",
        allowlist_hash: "allowlist-safe-hash",
        allowlist_count: 2
      },
      preview_only: true,
      production_write: false,
      production_write_scope: "none",
      approved: false,
      governance_approved: true,
      ready_for_review: true,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      execution_status: "push_center_pending_not_sent",
      can_claim_pass_90_plus: false
    };
  }
  if (url.endsWith("/governance/gowg_safe")) {
    return {
      ok: true,
      operation: "get_governance",
      review_id: "gowg_safe",
      draft_id: "gowd_safe",
      snapshot_hash: "snapshot_safe",
      review_status: "approval_pending",
      steps: [
        { step_id: "gows_operator", step_type: "operator_approval", step_status: "pending" },
        { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
        { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
      ],
      allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
      gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
      preview_only: true,
      production_write: false,
      approved: false,
      ready_for_review: true,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (url.endsWith("/drafts/gowd_safe/governance")) {
    return {
      ok: true,
      items: [
        {
          ok: true,
          review_id: "gowg_safe",
          draft_id: "gowd_safe",
          snapshot_hash: "snapshot_safe",
          review_status: "approval_pending",
          steps: [
            { step_id: "gows_operator", step_type: "operator_approval", step_status: "pending" },
            { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
            { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
          ],
          allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
          gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
          preview_only: true,
          production_write: false,
          approved: false,
          ready_for_review: true,
          push_center_job_created: false,
          external_effect_job_created: false,
          broadcast_job_created: false,
          internal_event_created: false,
          real_external_call: false,
          real_external_call_executed: false,
          can_claim_pass_90_plus: false,
          execution_status: "not_execution"
        }
      ],
      preview_only: true,
      production_write: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      real_external_call: false,
      real_external_call_executed: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/request-review")) {
    return {
      ok: true,
      operation: "request_review",
      draft_id: "gowd_safe",
      draft_status: "ready_for_review",
      ready_for_review: true,
      approved: false,
      version: 3,
      preview_only: true,
      production_write: true,
      real_external_call: false,
      real_external_call_executed: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST" && url.endsWith("/archive")) {
    return {
      ok: true,
      operation: "archive",
      draft_id: "gowd_safe",
      draft_status: "archived",
      version: 2,
      preview_only: true,
      production_write: true,
      real_external_call: false,
      real_external_call_executed: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "PATCH") {
    return {
      ok: true,
      operation: "update",
      draft_id: "gowd_safe",
      draft_status: "draft",
      version: 2,
      preview_only: true,
      production_write: true,
      real_external_call: false,
      real_external_call_executed: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  if (options.method === "POST") {
    return {
      ok: true,
      operation: "create",
      draft_id: "gowd_safe",
      draft_status: "draft",
      version: 1,
      preview_only: true,
      production_write: true,
      real_external_call: false,
      real_external_call_executed: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      can_claim_pass_90_plus: false,
      execution_status: "not_execution"
    };
  }
  return {
    ok: true,
    total: 0,
    items: [],
    preview_only: true,
    production_write: false,
    real_external_call: false,
    real_external_call_executed: false,
    push_center_job_created: false,
    external_effect_job_created: false,
    can_claim_pass_90_plus: false,
    execution_status: "not_execution"
  };
};
const createdDraft = await createDraft(draftPayload, undefined, requestJson);
const updatedDraft = await updateDraft("gowd_safe", { ...draftPayload, version: 1 }, undefined, requestJson);
const archivedDraft = await archiveDraft("gowd_safe", 2, undefined, requestJson);
await listDrafts(undefined, requestJson);
await getDraft("gowd_safe", undefined, requestJson);
assert.equal(createdDraft.draft_id, "gowd_safe");
assert.equal(updatedDraft.version, 2);
assert.equal(archivedDraft.draft_status, "archived");
assert.equal(draftRequests.some((entry) => entry.url.includes("/push-center")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("external-effect")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("broadcast")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("internal-event")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("request-review")), false);
assert.equal(draftRequests.some((entry) => entry.options.method === "POST"), true);
assert.equal(draftRequests.some((entry) => entry.options.method === "PATCH"), true);
assert.equal(JSON.parse(draftRequests.find((entry) => entry.options.method === "POST" && !entry.url.endsWith("/archive")).options.body).idempotency_key, draftPayload.idempotency_key);
const reviewedDraft = await requestDraftReview("gowd_safe", reviewPayload, undefined, requestJson);
assert.equal(reviewedDraft.draft_status, "ready_for_review");
assert.equal(reviewedDraft.ready_for_review, true);
assert.equal(reviewedDraft.approved, false);
const governanceReview = await requestGovernance("gowd_safe", governancePayload, undefined, requestJson);
assert.equal(governanceReview.review_status, "approval_pending");
assert.equal(governanceReview.approved, false);
assert.equal(governanceReview.execution_status, "not_execution");
assert.equal(governanceReview.steps.length, 3);
assert.equal(governanceReview.steps.every((step) => step.step_status === "pending"), true);
assertGovernanceResponseSafe(governanceReview);
const fetchedGovernance = await getGovernanceReview("gowg_safe", undefined, requestJson);
assert.equal(fetchedGovernance.review_id, "gowg_safe");
const draftGovernance = await getDraftGovernance("gowd_safe", undefined, requestJson);
assert.equal(draftGovernance.items.length, 1);
assert.equal(draftGovernance.items[0].review_status, "approval_pending");
const approvedOperatorStep = await approveGovernanceStep("gowg_safe", "gows_operator", operatorApprovePayload, undefined, requestJson);
assert.equal(approvedOperatorStep.step_status, "approved");
assert.equal(approvedOperatorStep.review_status, "allowlist_pending");
assert.equal(approvedOperatorStep.execution_status, "not_execution");
const approvedAllowlistStep = await approveGovernanceStep("gowg_safe", "gows_allowlist", allowlistApprovePayload, undefined, requestJson);
assert.equal(approvedAllowlistStep.step_status, "approved");
assert.equal(approvedAllowlistStep.review_status, "gray_window_pending");
const approvedGrayStep = await approveGovernanceStep("gowg_safe", "gows_gray", grayApprovePayload, undefined, requestJson);
assert.equal(approvedGrayStep.review_status, "governance_approved");
assert.equal(approvedGrayStep.governance_approved, true);
assert.equal(approvedGrayStep.approved, false);
assert.equal(approvedGrayStep.execution_status, "not_execution");
assertGovernanceResponseSafe(approvedGrayStep);
const bridgeResponse = await bridgeGovernanceToPushCenter("gowg_safe", bridgePayload, undefined, requestJson);
assert.equal(bridgeResponse.push_center_job_created, true);
assert.equal(bridgeResponse.push_center_status, "pending");
assert.equal(bridgeResponse.execution_status, "push_center_pending_not_sent");
assert.equal(bridgeResponse.external_effect_job_created, false);
assert.equal(bridgeResponse.broadcast_job_created, false);
assert.equal(bridgeResponse.internal_event_created, false);
assert.equal(bridgeResponse.real_external_call, false);
assert.equal(bridgeResponse.can_claim_pass_90_plus, false);
assertPushCenterBridgeResponseSafe(bridgeResponse);
const bridgeRefresh = await getGovernancePushCenterBridge("gowg_safe", undefined, requestJson);
assert.equal(bridgeRefresh.push_center_job_id, "p1-gow-push-center:gowg_safe");
assert.equal(bridgeRefresh.execution_status, "push_center_pending_not_sent");
assertPushCenterBridgeResponseSafe(bridgeRefresh);
const rejectedOperatorStep = await rejectGovernanceStep("gowg_safe", "gows_operator", rejectStepPayload, undefined, requestJson);
assert.equal(rejectedOperatorStep.review_status, "governance_rejected");
const expiredGovernance = await expireGovernanceReview("gowg_safe", expireReviewPayload, undefined, requestJson);
assert.equal(expiredGovernance.review_status, "governance_expired");
assert.equal(expiredGovernance.execution_status, "not_execution");
const reviewRequest = draftRequests.find((entry) => entry.url.endsWith("/request-review"));
assert.ok(reviewRequest);
assert.equal(reviewRequest.options.method, "POST");
const reviewRequestBody = JSON.parse(reviewRequest.options.body);
assert.equal(reviewRequestBody.idempotency_key, reviewPayload.idempotency_key);
assert.equal(reviewRequestBody.version, 2);
const governanceRequest = draftRequests.find((entry) => entry.url.endsWith("/governance/request"));
assert.ok(governanceRequest);
assert.equal(governanceRequest.options.method, "POST");
const governanceRequestBody = JSON.parse(governanceRequest.options.body);
assert.equal(governanceRequestBody.idempotency_key, governancePayload.idempotency_key);
assert.equal(governanceRequestBody.client_snapshot_hash, "snapshot_safe");
assert.equal(governanceRequestBody.allowlist_summary.allowlist_hash, "allowlist-safe-hash");
assert.equal(governanceRequestBody.gray_window.timezone, "Asia/Shanghai");
const approveRequest = draftRequests.find((entry) => entry.url.endsWith("/steps/gows_operator/approve"));
assert.ok(approveRequest);
assert.equal(approveRequest.options.method, "POST");
assert.equal(JSON.parse(approveRequest.options.body).idempotency_key, operatorApprovePayload.idempotency_key);
const allowlistApproveRequest = draftRequests.find((entry) => entry.url.endsWith("/steps/gows_allowlist/approve"));
assert.ok(allowlistApproveRequest);
assert.equal(JSON.parse(allowlistApproveRequest.options.body).allowlist_hash, "allowlist-safe-hash");
assert.equal(JSON.parse(allowlistApproveRequest.options.body).allowlist_count, 2);
const rejectRequest = draftRequests.find((entry) => entry.url.endsWith("/steps/gows_operator/reject"));
assert.ok(rejectRequest);
const expireRequest = draftRequests.find((entry) => entry.url.endsWith("/governance/gowg_safe/expire"));
assert.ok(expireRequest);
const bridgeRequest = draftRequests.find((entry) => entry.url.endsWith("/governance/gowg_safe/bridge-push-center"));
assert.ok(bridgeRequest);
assert.equal(bridgeRequest.options.method, "POST");
const bridgeRequestBody = JSON.parse(bridgeRequest.options.body);
assert.equal(bridgeRequestBody.idempotency_key, bridgePayload.idempotency_key);
assert.equal(bridgeRequestBody.client_snapshot_hash, "snapshot_safe");
assert.equal(bridgeRequestBody.allowlist_hash, "allowlist-safe-hash");
assert.equal(bridgeRequestBody.allowlist_count, 2);
const bridgeReadRequest = draftRequests.find((entry) => entry.url.endsWith("/governance/gowg_safe/push-center-bridge"));
assert.ok(bridgeReadRequest);
assert.equal(bridgeReadRequest.options.method, undefined);
assert.equal(draftRequests.filter((entry) => entry.url.endsWith("/governance/gowg_safe/bridge-push-center")
  || entry.url.endsWith("/governance/gowg_safe/push-center-bridge")).length, 2);
assert.equal(draftRequests.some((entry) => entry.url.includes("external-effect")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("broadcast")), false);
assert.equal(draftRequests.some((entry) => entry.url.includes("internal-event")), false);
assert.equal(isDraftConflictError(new Error("409 conflict")), true);
assert.equal(isGovernanceConflictError(new Error("409 active governance review exists")), true);
await assert.rejects(
  () => createDraft({ ...draftPayload, guardrail_summary: { ...draftPayload.guardrail_summary, ["raw_" + "target"]: "unsafe" } }, undefined, requestJson),
  /draft_payload_sensitive/
);
await assert.rejects(
  () => requestDraftReview("gowd_safe", { ...reviewPayload, review_note: "raw_" + "target" }, undefined, requestJson),
  /draft_payload_sensitive/
);
await assert.rejects(
  () => requestDraftReview("gowd_bad", reviewPayload, undefined, async () => ({
    ok: true,
    draft_id: "gowd_bad",
    draft_status: "ready_for_review",
    approved: true,
    preview_only: true,
    production_write: true,
    real_external_call: false,
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    can_claim_pass_90_plus: false
  })),
  /draft_api_response_violates_execution_guardrail/
);
await assert.rejects(
  () => requestGovernance("gowd_bad", governancePayload, undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    review_status: "approval_pending",
    approved: true,
    preview_only: true,
    production_write: true,
    real_external_call: false,
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    can_claim_pass_90_plus: false,
    execution_status: "not_execution"
  })),
  /governance_api_response_violates_execution_guardrail/
);
await assert.rejects(
  () => requestGovernance("gowd_bad", governancePayload, undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    review_status: "sent",
    approved: false,
    preview_only: true,
    production_write: true,
    real_external_call: false,
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    can_claim_pass_90_plus: false,
    execution_status: "not_execution"
  })),
  /governance_api_response_claims_execution_state/
);
await assert.rejects(
  () => approveGovernanceStep("gowg_bad", "gows_bad", operatorApprovePayload, undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    review_status: "governance_approved",
    step_status: "approved",
    approved: false,
    push_center_job_id: "pcj_unsafe",
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false,
    execution_status: "not_execution"
  })),
  /governance_api_response_claims_execution_state/
);
await assert.rejects(
  () => bridgeGovernanceToPushCenter("gowg_bad", bridgePayload, undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    draft_id: "gowd_bad",
    push_center_job_created: true,
    push_center_job_id: "p1-gow-push-center:gowg_bad",
    push_center_status: "sent",
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false,
    execution_status: "sent"
  })),
  /push_center_bridge_response/
);
await assert.rejects(
  () => bridgeGovernanceToPushCenter("gowg_bad", bridgePayload, undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    draft_id: "gowd_bad",
    push_center_job_created: true,
    push_center_job_id: "p1-gow-push-center:gowg_bad",
    push_center_status: "pending",
    external_effect_job_created: true,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false,
    execution_status: "push_center_pending_not_sent"
  })),
  /push_center_bridge_response_violates_execution_guardrail/
);
await assert.rejects(
  () => getGovernancePushCenterBridge("gowg_bad", undefined, async () => ({
    ok: true,
    review_id: "gowg_bad",
    draft_id: "gowd_bad",
    push_center_job_created: false,
    push_center_job_id: "p1-gow-push-center:unsafe",
    push_center_status: "not_bridged",
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false,
    execution_status: "not_execution"
  })),
  /push_center_bridge_response_not_safe_read_state/
);
const governanceReviewRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(governanceReviewRoot, fixture, updateWorkspaceViewState(readyReviewState, {
  currentGovernanceReviewId: "gowg_safe",
  currentGovernanceStatus: "approval_pending",
  currentGovernanceReview: {
    review_id: "gowg_safe",
    draft_id: "gowd_safe",
    review_status: "approval_pending",
    steps: [
      { step_id: "gows_operator", step_type: "operator_approval", step_status: "pending" },
      { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "pending" },
      { step_id: "gows_gray", step_type: "gray_window", step_status: "pending" }
    ],
    allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
    gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "pending" },
    approved: false,
    execution_status: "not_execution",
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false
  },
  governanceRequestStatus: "requested",
  governanceRequestMessage: "governance request 已记录 approval_pending；三个治理 step 仍为 pending。"
}));
assert.equal(governanceReviewRoot.innerHTML.includes("review_id</dt><dd>gowg_safe"), true);
assert.equal(governanceReviewRoot.innerHTML.includes("governance_status</dt><dd>approval_pending"), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-governance-step-id=\"gows_operator\" data-governance-step-type=\"operator_approval\" data-governance-step-status=\"pending\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-governance-step-id=\"gows_allowlist\" data-governance-step-type=\"receiver_allowlist\" data-governance-step-status=\"pending\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-governance-step-id=\"gows_gray\" data-governance-step-type=\"gray_window\" data-governance-step-status=\"pending\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-workspace-governance-step-action=\"approve\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-workspace-governance-step-action=\"reject\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-workspace-expire-governance-review=\"true\""), true);
assert.equal(governanceReviewRoot.innerHTML.includes("data-workspace-request-governance=\"true\" disabled"), true);
assert.equal(governanceReviewRoot.innerHTML.includes("pending steps 不等于 approved"), true);
assert.equal(governanceReviewRoot.innerHTML.includes("governance_approved 不等于 execution"), true);
assertNoSensitiveFixtureStrings(governanceReviewRoot.innerHTML);
const governanceApprovedRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(governanceApprovedRoot, fixture, updateWorkspaceViewState(readyReviewState, {
  currentGovernanceReviewId: "gowg_safe",
  currentGovernanceStatus: "governance_approved",
  currentGovernanceReview: {
    review_id: "gowg_safe",
    draft_id: "gowd_safe",
    review_status: "governance_approved",
    steps: [
      { step_id: "gows_operator", step_type: "operator_approval", step_status: "approved" },
      { step_id: "gows_allowlist", step_type: "receiver_allowlist", step_status: "approved" },
      { step_id: "gows_gray", step_type: "gray_window", step_status: "approved" }
    ],
    allowlist_summary: { hash: "allowlist-safe-hash", count: 2, source_reference_summary: { summary_only: true } },
    gray_window: { start_at: "2026-06-24T09:00:00+08:00", end_at: "2099-06-25T10:00:00+08:00", timezone: "Asia/Shanghai", window_status: "approved" },
    approved: false,
    execution_status: "not_execution",
    push_center_job_created: false,
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false
  },
  governanceRequestStatus: "requested",
  governanceRequestMessage: "三个 governance steps 已 approved，状态为 governance_approved；仍为 not_execution。"
}));
assert.equal(governanceApprovedRoot.innerHTML.includes("governance_status</dt><dd>governance_approved"), true);
assert.equal(governanceApprovedRoot.innerHTML.includes("governance_approved</dt><dd>true"), true);
assert.equal(governanceApprovedRoot.innerHTML.includes("execution_status</dt><dd>not_execution"), true);
assert.equal(governanceApprovedRoot.innerHTML.includes("push_center_job_created</dt><dd>false"), true);
assert.equal(governanceApprovedRoot.innerHTML.includes("completed</dt>"), false);
assertNoSensitiveFixtureStrings(governanceApprovedRoot.innerHTML);
const bundleText = buildCopySafeBundleText(bundle, { finalVerdict: fixture.payload.finalVerdict });
const bundleJson = buildCopySafeBundleJson(bundle, { finalVerdict: fixture.payload.finalVerdict });
const bundleJsonPayload = JSON.parse(bundleJson);
assert.equal(bundleText.includes("previewOnly: true"), true);
assert.equal(bundleText.includes("productionWrite: false"), true);
assert.equal(bundleText.includes("realExternalCall: false"), true);
assert.equal(bundleText.includes("canClaimPass90Plus: false"), true);
assert.equal(bundleText.includes("This bundle is read-only and cannot execute."), true);
assert.equal(bundleText.includes("sent evidence is not governance complete."), true);
assert.equal(bundleJsonPayload.workspace, "P1 Group Ops Workspace");
assert.equal(bundleJsonPayload.previewOnly, true);
assert.equal(bundleJsonPayload.productionWrite, false);
assert.equal(bundleJsonPayload.realExternalCall, false);
assert.equal(bundleJsonPayload.canClaimPass90Plus, false);
assert.equal(bundleJsonPayload.selectedCount, 2);
assert.equal(bundleJsonPayload.blockedCount, 1);
assert.equal(bundleJsonPayload.selectedItems.length, 2);
assertCopySafeBundleOutput(bundleText);
assertCopySafeBundleOutput(bundleJson);
for (const bait of [
  "raw_external_userid=wrOgAAA001",
  "phone=13800138000",
  "receiver_plaintext=member id",
  "token=abc",
  "secret=abc",
  "Authorization header",
  "openid value",
  "unionid value",
  "raw message body",
  "raw callback body"
]) {
  assert.throws(() => assertCopySafeBundleOutput(`safe summary ${bait}`), /copy_safe_output_contains_sensitive/);
}
const copiedValues = [];
const copyResult = await copyBundleSummaryToClipboard(bundleText, {
  writeText: async (value) => {
    copiedValues.push(value);
  }
});
assert.equal(copyResult.ok, true);
assert.equal(copiedValues.length, 1);
assert.equal(copiedValues[0], bundleText);
const failedCopy = await copyBundleSummaryToClipboard(bundleText, {
  writeText: async () => {
    throw new Error("clipboard denied");
  }
});
assert.equal(failedCopy.ok, false);
assert.equal(failedCopy.status, "copy_failed");
const multiRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(multiRoot, fixture, multiSelectedBundle);
assert.equal(multiRoot.innerHTML.includes("Read-only preview bundle (2)"), true);
assert.equal(multiRoot.innerHTML.includes("data-preview-bundle-id=\"preview-bundle-2-"), true);
assert.equal(multiRoot.innerHTML.includes("data-can-execute=\"false\""), true);
assert.equal(multiRoot.innerHTML.includes("Selected for preview bundle"), true);
assert.equal(multiRoot.innerHTML.includes("复制安全摘要"), true);
assert.equal(multiRoot.innerHTML.includes("复制脱敏 JSON"), true);
assert.equal(multiRoot.innerHTML.includes("查看复制内容预览"), true);
assert.equal(multiRoot.innerHTML.includes("只读复制，不会发送"), true);
assert.equal(multiRoot.innerHTML.includes("data-copy-safe-export=\"true\""), true);
assertNoSensitiveFixtureStrings(multiRoot.innerHTML);

const hiddenFilteredView = filterWorkspaceView(fixture, updateWorkspaceViewState(multiSelectedBundle, { entityTypeFilter: "execution" }));
const hiddenBundle = buildWorkspacePreviewBundle(fixture, hiddenFilteredView, hiddenFilteredView.viewState);
assert.equal(hiddenBundle.hiddenSelectedCount, 2);
const hiddenRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(hiddenRoot, fixture, hiddenFilteredView.viewState);
assert.equal(hiddenRoot.innerHTML.includes("not currently visible"), true);
assertNoSensitiveFixtureStrings(hiddenRoot.innerHTML);

const visibleSelection = selectVisibleItems(realViewState, filterWorkspaceView(fixture, realViewState).visibleLeftRailItems);
assert.equal(countMultiSelected(visibleSelection), fixture.leftRailItems.length);
const clearedSelection = clearMultiSelection(visibleSelection);
assert.equal(countMultiSelected(clearedSelection), 0);
assert.equal(clearedSelection.activeSelectionMode, "single");

const executionCanvasFilter = filterWorkspaceView(fixture, updateWorkspaceViewState(realViewState, { entityTypeFilter: "execution" }));
const executionLanes = buildWorkspaceCanvasLanes(fixture, executionCanvasFilter, executionCanvasFilter.viewState);
assert.equal(executionLanes.find((lane) => lane.id === "executions").cards.length, 1);
assert.equal(executionLanes.find((lane) => lane.id === "plans").cards.length, 0);

const realSelection = createWorkspaceViewState(fixture);
const realExecutionSelection = selectEntityInViewState(realSelection, "execution", "execution-plan-7");
const realExecutionRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realExecutionRoot, fixture, realExecutionSelection);
assert.equal(realExecutionRoot.innerHTML.includes("data-selected-entity-type=\"execution\""), true);
assert.equal(realExecutionRoot.innerHTML.includes("Execution summary"), true);
assert.equal(realExecutionRoot.innerHTML.includes("pending"), true);
assert.equal(realExecutionRoot.innerHTML.includes("wrOgAAA001"), false);
assert.equal(realExecutionRoot.innerHTML.includes("13800138000"), false);
assertNoSensitiveFixtureStrings(realExecutionRoot.innerHTML);

const realPushSelection = selectEntityInViewState(realSelection, "push_center", "push_center-external_effect_job:97");
const realPushRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(realPushRoot, fixture, realPushSelection);
assert.equal(realPushRoot.innerHTML.includes("data-selected-entity-type=\"push_center\""), true);
assert.equal(realPushRoot.innerHTML.includes("Push Center projection summary"), true);
assert.equal(realPushRoot.innerHTML.includes("governance complete"), true);
assertNoSensitiveFixtureStrings(realPushRoot.innerHTML);

const emptyFixture = await loadGroupOpsWorkspaceData(DEFAULT_WORKSPACE_API_CONFIG, async (url) => {
  if (url.includes("/plans?")) {
    return { ok: true, source_status: "fixture_empty", items: [], total: 0 };
  }
  throw new Error(`Unexpected URL for empty fixture: ${url}`);
});
const emptyRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(emptyRoot, emptyFixture);
assert.equal(emptyFixture.dataBindingStatus, "real_data_unavailable");
assert.equal(emptyRoot.innerHTML.includes("Read-only API unavailable"), true);
assert.equal(emptyRoot.innerHTML.includes("data-real-data-unavailable=\"true\""), true);
assert.equal(emptyRoot.innerHTML.includes("PASS_90_PLUS"), true);
assert.equal(emptyRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assertNoSensitiveFixtureStrings(emptyRoot.innerHTML);

const filteredRoot = { innerHTML: "" };
renderP1GroupOpsWorkspace(filteredRoot, fixture, updateWorkspaceViewState(realViewState, { keyword: "no matching redacted item" }));
assert.equal(filteredRoot.innerHTML.includes("Empty search result"), true);
assert.equal(filteredRoot.innerHTML.includes("data-empty-search-result=\"true\""), true);
assert.equal(filteredRoot.innerHTML.includes("external_effect_job:97"), true);
assertNoSensitiveFixtureStrings(filteredRoot.innerHTML);

console.log("p1 native group ops workspace OK");
