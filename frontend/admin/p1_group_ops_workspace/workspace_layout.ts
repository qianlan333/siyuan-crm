import { escapeHtml } from "../shared/dom.js";
import { renderGuardrailNotice } from "../shared/guardrail_notice.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { renderStatusCard } from "../shared/status_card.js";
import { statusMeta } from "../shared/status_model.js";
import { defaultRequestJson, loadGroupOpsWorkspaceData, parseWorkspaceApiConfig } from "./workspace_api.js";
import {
  buildCopySafeBundleJson,
  buildCopySafeBundleText,
  copyBundleSummaryToClipboard,
  type CopySafeResult
} from "./workspace_bundle_export.js";
import { renderGroupedWorkspaceCanvas } from "./workspace_canvas.js";
import {
  renderWorkspaceDetailPanel,
  renderWorkspaceSelectedPreviewResult,
} from "./workspace_detail.js";
import {
  archiveDraft,
  buildWorkspaceDraftReviewPayload,
  buildWorkspaceDraftPayload,
  createDraft,
  isDraftConflictError,
  requestDraftReview,
  updateDraft,
  type WorkspaceDraftResponse
} from "./workspace_draft_api.js";
import {
  approveGovernanceStep,
  buildApproveGovernanceStepPayload,
  buildExpireGovernanceReviewPayload,
  buildRejectGovernanceStepPayload,
  bridgeGovernanceToPushCenter,
  buildPushCenterBridgePayload,
  buildWorkspaceGovernanceRequestPayload,
  expireGovernanceReview,
  getDraftGovernance,
  getGovernanceReview,
  getGovernancePushCenterBridge,
  isGovernanceConflictError,
  rejectGovernanceStep,
  requestGovernance,
  type WorkspaceGovernanceResponse,
  type WorkspacePushCenterBridgeResponse
} from "./workspace_governance_api.js";
import { ENTITY_FILTER_OPTIONS, STATUS_FILTER_OPTIONS, filterWorkspaceView, type FilteredWorkspaceView } from "./workspace_filters.js";
import { buildWorkspaceCanvasLanes } from "./workspace_grouping.js";
import { moveWorkspaceCanvasSelection, type WorkspaceKeyboardKey } from "./workspace_keyboard.js";
import {
  clearMultiSelection,
  countMultiSelected,
  isEntityMultiSelected,
  selectVisibleItems,
  selectVisibleLaneItems,
  toggleMultiSelectedEntity
} from "./workspace_multi_select.js";
import { buildWorkspacePreviewBundle } from "./workspace_preview_bundle.js";
import {
  P1_GROUP_OPS_WORKSPACE_FIXTURE,
  createUnavailableWorkspaceFixture,
  type WorkspaceEntityType,
  type WorkspaceFixture,
  type WorkspaceListItem
} from "./workspace_fixture.js";
import { renderWorkspacePreviewResult } from "./workspace_preview.js";
import { buildGroupOpsWorkspaceStatusModel, workspaceCanRenderGlobalPass } from "./workspace_status.js";
import {
  createWorkspaceViewState,
  selectEntityInViewState,
  selectionFromViewState,
  toggleWorkspaceCanvasLane,
  updateWorkspaceViewState,
  type WorkspaceCanvasLaneId,
  type WorkspacePanelMode,
  type WorkspacePushCenterBridgeView,
  type WorkspaceViewState
} from "./workspace_view_state.js";

function isSelectedListItem(item: WorkspaceListItem, viewState: WorkspaceViewState): boolean {
  return item.entityType === viewState.selectedEntityType && item.detailId === viewState.selectedEntityId;
}

function renderOption(value: string, currentValue: string): string {
  return `<option value="${escapeHtml(value)}"${value === currentValue ? " selected" : ""}>${escapeHtml(value)}</option>`;
}

function renderFilterToolbar(viewState: WorkspaceViewState, filtered: FilteredWorkspaceView): string {
  return `
    <section class="p1-workspace-filters" aria-label="Workspace local filters" data-view-state-memory-only="true" data-filter-result-count="${filtered.visibleLeftRailItems.length}" data-filter-data-state="${escapeHtml(filtered.dataState)}">
      <div class="p1-workspace-panel-head">
        <h2>Search / filters</h2>
        <p>筛选只作用于已加载的脱敏只读数据；不写 URL、不保存后端、不触发执行。</p>
      </div>
      <div class="p1-workspace-filter-grid">
        <label>
          <span>Keyword</span>
          <input type="search" value="${escapeHtml(viewState.keyword)}" placeholder="plan name or internal id" data-workspace-filter="keyword" autocomplete="off">
        </label>
        <label>
          <span>Plan status</span>
          <select data-workspace-filter="planStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.planStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Entity type</span>
          <select data-workspace-filter="entityTypeFilter">${ENTITY_FILTER_OPTIONS.map((option) => renderOption(option, viewState.entityTypeFilter)).join("")}</select>
        </label>
        <label>
          <span>Execution status</span>
          <select data-workspace-filter="executionStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.executionStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Push Center status</span>
          <select data-workspace-filter="pushCenterStatusFilter">${STATUS_FILTER_OPTIONS.map((option) => renderOption(option, viewState.pushCenterStatusFilter)).join("")}</select>
        </label>
        <label>
          <span>Panel mode</span>
          <select data-workspace-filter="panelMode">
            ${["summary", "detail", "guardrail"].map((option) => renderOption(option, viewState.panelMode)).join("")}
          </select>
        </label>
      </div>
      <p class="p1-workspace-filter-summary">${escapeHtml(filtered.resultSummary)}；原始 evidence status 不会被筛选改变。</p>
    </section>
  `;
}

function renderStateBanner(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  if (filtered.isEmpty) {
    return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--empty" data-empty-search-result="true" data-can-claim-pass90="false">
        <strong>Empty search result</strong>
        <p>${escapeHtml(filtered.emptyReason)}</p>
      </section>
    `;
  }
  if (filtered.dataState === "real_data_unavailable") {
    return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--danger" data-real-data-unavailable="true" data-can-claim-pass90="false">
        <strong>Read-only API unavailable</strong>
        <p>API read failure keeps this workspace in preview fallback; it must not render sent or completed.</p>
      </section>
    `;
  }
  if (filtered.dataState === "partial_data") {
    return `
      <section class="p1-workspace-state-banner p1-workspace-state-banner--warning" data-partial-data="true" data-can-claim-pass90="false">
        <strong>Partial data</strong>
        <p>部分 Push Center 或 governance evidence 仍不完整；缺失项继续显示 evidence-incomplete / governance-missing。</p>
      </section>
    `;
  }
  return `
    <section class="p1-workspace-state-banner" data-readonly-data-ready="true" data-can-claim-pass90="false">
      <strong>Read-only data loaded</strong>
      <p>${escapeHtml(fixture.dataSourceLabel)} 已绑定；筛选不改变任何 evidence status。</p>
    </section>
  `;
}

function renderLeftRailItem(item: WorkspaceListItem, viewState: WorkspaceViewState): string {
  const meta = statusMeta(item.status);
  const selectedClass = isSelectedListItem(item, viewState) ? " p1-workspace-list-item--selected" : "";
  const multiSelected = isEntityMultiSelected(viewState, item.entityType, item.detailId);
  return `
    <button type="button" class="p1-workspace-list-item p1-workspace-list-item--${meta.tone}${selectedClass}" data-kind="${escapeHtml(item.kind)}" data-status="${escapeHtml(item.status)}" data-multi-selected="${multiSelected ? "true" : "false"}" data-workspace-select-type="${escapeHtml(item.entityType)}" data-workspace-select-id="${escapeHtml(item.detailId)}">
      <div class="p1-workspace-list-item__head">
        <span>${escapeHtml(item.kind)}</span>
        ${renderStatusBadge(item.status)}
      </div>
      <strong>${escapeHtml(item.label)}</strong>
      <p>${escapeHtml(item.summary)}</p>
      <span class="p1-workspace-multi-select-affordance" role="checkbox" aria-checked="${multiSelected ? "true" : "false"}" tabindex="0" data-workspace-multi-toggle="true" data-workspace-multi-type="${escapeHtml(item.entityType)}" data-workspace-multi-id="${escapeHtml(item.detailId)}">
        ${multiSelected ? "Selected for preview bundle" : "Select for preview bundle"}
      </span>
    </button>
  `;
}

function renderWorkspaceHeader(fixture: WorkspaceFixture): string {
  return `
    <section class="admin-card p1-workspace-banner" data-workspace-mode="${escapeHtml(fixture.workspaceMode)}" data-final-verdict="${escapeHtml(fixture.payload.finalVerdict)}" data-data-binding-status="${escapeHtml(fixture.dataBindingStatus)}" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Native workspace preview</h2>
        <p>当前为 draft-only / preview-only；不会发送、不审批、不写生产。数据源：${escapeHtml(fixture.dataSourceLabel)}。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">${escapeHtml(fixture.payload.finalVerdict)}</span>
    </section>
  `;
}

function renderSafePreviewBanner(): string {
  return `
    <section class="p1-workspace-safe-preview-banner" aria-label="Read-only safety state" data-safe-preview-affordance="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safe preview only</strong>
      <span>不会发送、不审批、不写生产；preview 不等于已执行，sent evidence 不等于 governance complete。</span>
    </section>
  `;
}

function renderSafePreviewFooter(): string {
  return `
    <section class="p1-workspace-safe-preview-footer" aria-label="Fixed safe preview summary" data-safe-preview-footer="true" data-preview-only="true" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <strong>Safety summary</strong>
      <p>preview-only=true；production_write=false；real_external_call=false；can_claim_pass_90_plus=false。Requires approval / allowlist / gray-window 的项目仍需运营治理证据。</p>
    </section>
  `;
}

function renderLeftRail(filtered: FilteredWorkspaceView): string {
  const rows = filtered.visibleLeftRailItems.length > 0
    ? filtered.visibleLeftRailItems.map((item) => renderLeftRailItem(item, filtered.viewState)).join("")
    : `<section class="p1-workspace-empty-state" data-empty-search-result="true"><strong>No matching item</strong><p>${escapeHtml(filtered.emptyReason)}</p></section>`;
  return `
    <aside class="p1-workspace-left" aria-label="计划、人群、任务列表">
      <div class="p1-workspace-panel-head">
        <h2>计划 / 人群 / 任务</h2>
        <p>点击计划、人群、节点、执行或 Push Center 项只会更新本地只读 detail selection。</p>
      </div>
      <div class="p1-workspace-bulk-actions" data-multi-select-memory-only="true">
        <button type="button" data-workspace-select-visible="true">Select visible filtered results</button>
        <button type="button" data-workspace-clear-selection="true">Clear selection</button>
      </div>
      <div class="p1-workspace-list">${rows}</div>
    </aside>
  `;
}

function renderBundleSummary(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const bundle = buildWorkspacePreviewBundle(fixture, filtered, filtered.viewState);
  const textSummary = buildCopySafeBundleText(bundle, { finalVerdict: fixture.payload.finalVerdict });
  const jsonSummary = buildCopySafeBundleJson(bundle, { finalVerdict: fixture.payload.finalVerdict });
  const previewOutput = filtered.viewState.copyPreviewFormat === "json" ? jsonSummary : textSummary;
  const copyStatusClass = filtered.viewState.copyStatus === "copy_failed"
    ? " p1-workspace-copy-status--danger"
    : filtered.viewState.copyStatus === "copied"
      ? " p1-workspace-copy-status--success"
      : "";
  const countRows = Object.entries(bundle.countsByEntityType).map(([entityType, count]) => `
    <div><dt>${escapeHtml(entityType)}</dt><dd>${count}</dd></div>
  `).join("");
  const selectedRows = bundle.items.length > 0
    ? bundle.items.map((item) => `
      <button type="button" class="p1-workspace-bundle-item" data-workspace-select-type="${escapeHtml(item.entityType)}" data-workspace-select-id="${escapeHtml(item.detailId)}" data-visible-in-filter="${item.isVisible ? "true" : "false"}">
        <span>${escapeHtml(item.entityType)}</span>
        <strong>${escapeHtml(item.title)}</strong>
        ${renderStatusBadge(item.status)}
        <em>${item.isVisible ? "visible" : "not currently visible"}</em>
      </button>
    `).join("")
    : `<section class="p1-workspace-empty-state" data-empty-preview-bundle="true"><strong>No selected item</strong><p>Use Select for preview bundle; selection remains memory-only and clears on refresh.</p></section>`;
  return `
    <section class="p1-workspace-preview-bundle" aria-live="polite" data-preview-bundle-id="${escapeHtml(bundle.bundleId)}" data-selected-count="${bundle.selectedCount}" data-can-execute="false" data-preview-only="${bundle.previewOnly ? "true" : "false"}" data-production-write-executed="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>${escapeHtml(bundle.title)}</h2>
        <p>Multi-select preview is memory-only. Hidden filtered-out selected items remain in the bundle and are marked as not currently visible.</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>selected</dt><dd>${bundle.selectedCount}</dd></div>
        <div><dt>blocked</dt><dd>${bundle.blockedCount}</dd></div>
        <div><dt>action_required</dt><dd>${bundle.actionRequiredCount}</dd></div>
        <div><dt>governance_missing</dt><dd>${bundle.governanceMissingCount}</dd></div>
        <div><dt>push_center_pending</dt><dd>${bundle.pushCenterPendingCount}</dd></div>
        <div><dt>evidence_incomplete</dt><dd>${bundle.evidenceIncompleteCount}</dd></div>
        <div><dt>hidden_selected</dt><dd>${bundle.hiddenSelectedCount}</dd></div>
        <div><dt>preview-only</dt><dd>true</dd></div>
        <div><dt>can_claim_pass90</dt><dd>false</dd></div>
      </dl>
      <dl class="p1-workspace-mini-fields">${countRows}</dl>
      <p class="p1-workspace-guardrails">${bundle.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ")}</p>
      <section class="p1-workspace-copy-export" data-copy-safe-export="true" data-copy-preview-visible="${filtered.viewState.copyPreviewVisible ? "true" : "false"}" data-copy-preview-format="${escapeHtml(filtered.viewState.copyPreviewFormat)}">
        <div class="p1-workspace-copy-actions" aria-label="只读复制安全摘要">
          <button type="button" data-workspace-copy-bundle="text">复制安全摘要</button>
          <button type="button" data-workspace-copy-bundle="json">复制脱敏 JSON</button>
          <button type="button" data-workspace-toggle-copy-preview="true">查看复制内容预览</button>
        </div>
        <p class="p1-workspace-copy-note">只读复制，不会发送；复制内容不保存后端、不下载文件、不写浏览器持久存储。</p>
        <p class="p1-workspace-copy-status${copyStatusClass}" aria-live="polite" data-copy-status="${escapeHtml(filtered.viewState.copyStatus)}">${escapeHtml(filtered.viewState.copyStatusMessage)}</p>
        ${filtered.viewState.copyPreviewVisible ? `<pre class="p1-workspace-copy-preview" tabindex="0" data-copy-preview="true">${escapeHtml(previewOutput)}</pre>` : ""}
      </section>
      <div class="p1-workspace-bundle-list">${selectedRows}</div>
    </section>
  `;
}

function draftStatusTone(status: WorkspaceViewState["draftSaveStatus"]): string {
  if (status === "saved" || status === "archived") return "success";
  if (status === "failed" || status === "conflict") return "danger";
  if (status === "saving") return "info";
  return "neutral";
}

function draftReviewTone(status: WorkspaceViewState["draftReviewStatus"]): string {
  if (status === "ready_for_review") return "success";
  if (status === "failed" || status === "conflict" || status === "blocked") return "danger";
  if (status === "requesting") return "info";
  return "neutral";
}

function normalizeDraftStatus(value: string | undefined): WorkspaceViewState["currentDraftStatus"] {
  if (value === "draft" || value === "ready_for_review" || value === "archived" || value === "rejected") return value;
  return "not_saved";
}

function renderDraftPersistencePanel(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const draftPayload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState);
  const hasDraft = Boolean(filtered.viewState.currentDraftId);
  const tone = draftStatusTone(filtered.viewState.draftSaveStatus);
  const reviewTone = draftReviewTone(filtered.viewState.draftReviewStatus);
  const canRequestReview = hasDraft
    && filtered.viewState.currentDraftVersion > 0
    && filtered.viewState.currentDraftStatus === "draft"
    && filtered.viewState.draftSaveStatus !== "conflict"
    && filtered.viewState.draftReviewStatus !== "requesting";
  return `
    <section class="p1-workspace-draft-save" aria-label="Save sanitized workspace draft" data-draft-persistence="frontend_save_only" data-preview-only="true" data-real-external-call-executed="false" data-push-center-job-created="false" data-external-effect-job-created="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Draft persistence</h2>
        <p>保存草稿与 request-review 只写 draft 表；Push Center bridge 仅在治理通过后创建 pending projection，不会发送、不会创建 external_effect_job。</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>draft_id</dt><dd>${escapeHtml(filtered.viewState.currentDraftId || "not_saved")}</dd></div>
        <div><dt>draft_status</dt><dd>${escapeHtml(filtered.viewState.currentDraftStatus)}</dd></div>
        <div><dt>version</dt><dd>${filtered.viewState.currentDraftVersion || 0}</dd></div>
        <div><dt>items</dt><dd>${draftPayload.items.length}</dd></div>
        <div><dt>preview_only</dt><dd>true</dd></div>
        <div><dt>real_external_call</dt><dd>false</dd></div>
        <div><dt>ready_for_review</dt><dd>${filtered.viewState.currentDraftStatus === "ready_for_review" ? "true" : "false"}</dd></div>
        <div><dt>approved</dt><dd>false</dd></div>
        <div><dt>can_claim_pass90</dt><dd>false</dd></div>
      </dl>
      <div class="p1-workspace-draft-actions" aria-label="草稿保存操作">
        <button type="button" data-workspace-save-draft="true">${hasDraft ? "Save draft update" : "Save draft"}</button>
        <button type="button" data-workspace-save-as-new-draft="true">Save as new draft</button>
        <button type="button" data-workspace-request-review-draft="true"${canRequestReview ? "" : " disabled"}>Request review</button>
        <button type="button" data-workspace-archive-draft="true"${hasDraft && filtered.viewState.draftSaveStatus !== "archived" ? "" : " disabled"}>Archive draft</button>
      </div>
      <p class="p1-workspace-draft-status p1-workspace-draft-status--${tone}" aria-live="polite" data-draft-save-status="${escapeHtml(filtered.viewState.draftSaveStatus)}">${escapeHtml(filtered.viewState.draftSaveMessage)}</p>
      <p class="p1-workspace-draft-status p1-workspace-draft-status--${reviewTone}" aria-live="polite" data-draft-review-status="${escapeHtml(filtered.viewState.draftReviewStatus)}">${escapeHtml(filtered.viewState.draftReviewMessage)}</p>
      <p class="p1-workspace-draft-guardrail">request-review 不等于 approval；ready_for_review 不等于 approved、sent、completed；草稿不等于 sent/completed。approval bridge、Push Center bridge 与 execution 仍未接入，也不能 claim PASS_90_PLUS。</p>
    </section>
  `;
}

function governanceTone(status: WorkspaceViewState["governanceRequestStatus"]): string {
  if (status === "requested") return "success";
  if (status === "failed" || status === "conflict" || status === "blocked") return "danger";
  if (status === "requesting") return "info";
  return "neutral";
}

type GovernanceStepView = NonNullable<WorkspaceViewState["currentGovernanceReview"]>["steps"][number];

function defaultGovernanceSteps(): GovernanceStepView[] {
  return [
    { step_id: "", step_type: "operator_approval", step_status: "pending" },
    { step_id: "", step_type: "receiver_allowlist", step_status: "pending" },
    { step_id: "", step_type: "gray_window", step_status: "pending" }
  ];
}

function governanceReviewFromResponse(payload: WorkspaceGovernanceResponse): WorkspaceViewState["currentGovernanceReview"] {
  return {
    review_id: String(payload.review_id || ""),
    draft_id: String(payload.draft_id || ""),
    review_status: String(payload.review_status || "approval_pending"),
    snapshot_hash: String(payload.snapshot_hash || ""),
    steps: (payload.steps && payload.steps.length > 0 ? payload.steps : defaultGovernanceSteps()).map((step) => ({
      step_id: String(step.step_id || ""),
      step_type: String(step.step_type || ""),
      step_status: String(step.step_status || "pending"),
      actor_metadata: step.actor_metadata || {},
      updated_at: String(step.updated_at || "")
    })),
    allowlist_summary: {
      hash: String(payload.allowlist_summary?.hash || ""),
      count: Number(payload.allowlist_summary?.count || 0),
      source_reference_summary: payload.allowlist_summary?.source_reference_summary || {}
    },
    gray_window: {
      start_at: String(payload.gray_window?.start_at || ""),
      end_at: String(payload.gray_window?.end_at || ""),
      timezone: String(payload.gray_window?.timezone || ""),
      window_status: String(payload.gray_window?.window_status || "pending")
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
}

function pushCenterBridgeFromResponse(payload: WorkspacePushCenterBridgeResponse): WorkspacePushCenterBridgeView | null {
  if (!payload.push_center_job_created || !payload.push_center_job_id) return null;
  return {
    review_id: String(payload.review_id || ""),
    draft_id: String(payload.draft_id || ""),
    review_status: String(payload.review_status || ""),
    push_center_job_created: true,
    push_center_job_id: String(payload.push_center_job_id || ""),
    push_center_projection_id: String(payload.push_center_projection_id || payload.push_center_job_id || ""),
    push_center_status: "pending",
    execution_status: "push_center_pending_not_sent",
    external_effect_job_created: false,
    broadcast_job_created: false,
    internal_event_created: false,
    real_external_call: false,
    can_claim_pass_90_plus: false,
    idempotent_replay: Boolean(payload.idempotent_replay)
  };
}

function isActiveGovernanceStatus(status: string): boolean {
  return !["", "governance_not_started", "governance_rejected", "governance_expired", "rejected", "expired"].includes(status);
}

function governanceTerminal(status: string): boolean {
  return ["governance_rejected", "governance_expired"].includes(status);
}

function grayWindowExpired(review: NonNullable<WorkspaceViewState["currentGovernanceReview"]> | null): boolean {
  const endAt = Date.parse(String(review?.gray_window.end_at || ""));
  return Number.isFinite(endAt) && endAt <= Date.now();
}

function governanceStepsAllApproved(review: NonNullable<WorkspaceViewState["currentGovernanceReview"]> | null): boolean {
  const required = new Set(["operator_approval", "receiver_allowlist", "gray_window"]);
  const approved = new Set((review?.steps || [])
    .filter((step) => step.step_status === "approved")
    .map((step) => step.step_type));
  return [...required].every((stepType) => approved.has(stepType));
}

function bridgeTone(status: WorkspaceViewState["pushCenterBridgeStatus"]): string {
  if (status === "bridged") return "success";
  if (status === "failed" || status === "conflict" || status === "blocked") return "danger";
  if (status === "requesting") return "warning";
  return "neutral";
}

function renderStepActorSummary(actorMetadata?: Record<string, unknown>): string {
  const actorLabelPresent = Boolean(actorMetadata?.actor_label_present);
  const actorIdPresent = Boolean(actorMetadata?.actor_id_present);
  if (!actorLabelPresent && !actorIdPresent) return "actor_not_recorded";
  return `actor_label_present=${actorLabelPresent}; actor_id_present=${actorIdPresent}`;
}

function renderGovernanceStepRows(
  review: NonNullable<WorkspaceViewState["currentGovernanceReview"]> | null,
  busy: boolean
): string {
  const steps = review?.steps || defaultGovernanceSteps();
  const reviewId = review?.review_id || "";
  const reviewStatus = review?.review_status || "governance_not_started";
  const terminal = governanceTerminal(reviewStatus);
  const grayExpired = grayWindowExpired(review);
  return steps.map((step) => `
    <li data-governance-step-id="${escapeHtml(step.step_id)}" data-governance-step-type="${escapeHtml(step.step_type)}" data-governance-step-status="${escapeHtml(step.step_status)}">
      <div>
        <strong>${escapeHtml(step.step_type)}</strong>
        <span>${escapeHtml(step.step_status)}</span>
      </div>
      <small>${escapeHtml(renderStepActorSummary(step.actor_metadata))}${step.updated_at ? `；updated_at=${escapeHtml(step.updated_at)}` : ""}</small>
      ${step.step_type === "gray_window" && grayExpired && step.step_status === "pending" ? `<small data-governance-step-expired="true">gray-window 已过期，不能 approve，只能 expire。</small>` : ""}
      <div class="p1-workspace-governance-step-actions" aria-label="${escapeHtml(step.step_type)} step 操作">
        <button type="button" data-workspace-governance-step-action="approve" data-governance-review-id="${escapeHtml(reviewId)}" data-governance-step-id="${escapeHtml(step.step_id)}" data-governance-step-type="${escapeHtml(step.step_type)}"${reviewId && step.step_id && step.step_status === "pending" && !terminal && !busy && !(step.step_type === "gray_window" && grayExpired) ? "" : " disabled"}>Approve</button>
        <button type="button" data-workspace-governance-step-action="reject" data-governance-review-id="${escapeHtml(reviewId)}" data-governance-step-id="${escapeHtml(step.step_id)}" data-governance-step-type="${escapeHtml(step.step_type)}"${reviewId && step.step_id && step.step_status === "pending" && !terminal && !busy ? "" : " disabled"}>Reject</button>
      </div>
    </li>
  `).join("");
}

function renderGovernancePanel(filtered: FilteredWorkspaceView): string {
  const viewState = filtered.viewState;
  const hasDraft = Boolean(viewState.currentDraftId);
  const hasSnapshot = Boolean(viewState.currentDraftSnapshotHash);
  const isReadyForReview = viewState.currentDraftStatus === "ready_for_review";
  const currentReview = viewState.currentGovernanceReview;
  const currentBridge = viewState.currentPushCenterBridge;
  const activeReviewExists = Boolean(viewState.currentGovernanceReviewId) && isActiveGovernanceStatus(viewState.currentGovernanceStatus);
  let payloadPreview;
  let payloadSafe = false;
  let disabledReason = "";
  try {
    if (hasDraft && hasSnapshot) {
      payloadPreview = buildWorkspaceGovernanceRequestPayload(viewState.currentDraftId, viewState.currentDraftSnapshotHash);
      payloadSafe = true;
    }
  } catch (error) {
    disabledReason = error instanceof Error ? error.message : "governance_payload_invalid";
  }
  if (!hasDraft) disabledReason = "保存 draft 后才能 request governance。";
  else if (!isReadyForReview) disabledReason = "draft_status 必须是 ready_for_review。";
  else if (!hasSnapshot) disabledReason = "snapshot_hash 缺失，请重新保存草稿。";
  else if (activeReviewExists) disabledReason = "已有 active governance review；请刷新查看。";
  else if (!payloadSafe) disabledReason ||= "governance payload 未通过脱敏校验。";
  const canRequestGovernance = hasDraft
    && isReadyForReview
    && hasSnapshot
    && !activeReviewExists
    && payloadSafe
    && viewState.governanceRequestStatus !== "requesting";
  const allowlistHash = currentReview?.allowlist_summary.hash || payloadPreview?.allowlist_summary.allowlist_hash || "not_requested";
  const allowlistCount = currentReview?.allowlist_summary.count ?? payloadPreview?.allowlist_summary.allowlist_count ?? 0;
  const sourceReference = currentReview?.allowlist_summary.source_reference_summary
    || payloadPreview?.allowlist_summary.source_reference
    || { summary_only: true };
  const grayWindow = {
    ...(payloadPreview?.gray_window || {
      start_at: "not_requested",
      end_at: "not_requested",
      timezone: "not_requested"
    }),
    ...(currentReview?.gray_window || {}),
    window_status: currentReview?.gray_window.window_status || "pending"
  };
  const tone = governanceTone(viewState.governanceRequestStatus);
  const bridgeStatusTone = bridgeTone(viewState.pushCenterBridgeStatus);
  const busy = viewState.governanceRequestStatus === "requesting";
  const canExpireReview = Boolean(currentReview?.review_id)
    && isActiveGovernanceStatus(viewState.currentGovernanceStatus)
    && !busy;
  let bridgeDisabledReason = "";
  let bridgePayloadSafe = false;
  let bridgePayloadPreview;
  try {
    if (currentReview) {
      bridgePayloadPreview = buildPushCenterBridgePayload(currentReview);
      bridgePayloadSafe = true;
    }
  } catch (error) {
    bridgeDisabledReason = error instanceof Error ? error.message : "push_center_bridge_payload_invalid";
  }
  const alreadyBridged = Boolean(currentBridge?.push_center_job_id);
  if (!hasDraft) bridgeDisabledReason = "保存 draft 后才能 bridge。";
  else if (!isReadyForReview) bridgeDisabledReason = "draft_status 必须是 ready_for_review。";
  else if (!currentReview?.review_id) bridgeDisabledReason = "需要先创建 governance review。";
  else if (viewState.currentGovernanceStatus !== "governance_approved") bridgeDisabledReason = "governance_status 必须是 governance_approved。";
  else if (!governanceStepsAllApproved(currentReview)) bridgeDisabledReason = "operator / allowlist / gray-window 三个 step 都必须 approved。";
  else if (grayWindowExpired(currentReview)) bridgeDisabledReason = "gray-window 已过期，不能 bridge。";
  else if (alreadyBridged) bridgeDisabledReason = "已经存在 Push Center pending bridge projection。";
  else if (!bridgePayloadSafe) bridgeDisabledReason ||= "Push Center bridge payload 未通过脱敏校验。";
  const canBridgePushCenter = hasDraft
    && isReadyForReview
    && Boolean(currentReview?.review_id)
    && viewState.currentGovernanceStatus === "governance_approved"
    && governanceStepsAllApproved(currentReview)
    && !grayWindowExpired(currentReview)
    && !alreadyBridged
    && bridgePayloadSafe
    && viewState.pushCenterBridgeStatus !== "requesting";
  const bridgeMessage = canBridgePushCenter && viewState.pushCenterBridgeStatus === "idle"
    ? "governance_approved 已满足；可 bridge 到 Push Center pending projection，但不会发送。"
    : viewState.pushCenterBridgeMessage;
  return `
    <section class="p1-workspace-governance-panel" aria-label="Governance request panel" data-governance-panel="frontend_bridge_integration" data-approved="false" data-governance-approved="${viewState.currentGovernanceStatus === "governance_approved" ? "true" : "false"}" data-execution-status="${currentBridge ? "push_center_pending_not_sent" : "not_execution"}" data-push-center-job-created="${currentBridge ? "true" : "false"}" data-external-effect-job-created="false" data-broadcast-job-created="false" data-internal-event-created="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Governance panel</h2>
        <p>治理 step 操作只更新 approval / allowlist / gray-window 状态；Push Center bridge 只进入 pending，不发送。</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>draft_status</dt><dd>${escapeHtml(viewState.currentDraftStatus)}</dd></div>
        <div><dt>governance_status</dt><dd>${escapeHtml(viewState.currentGovernanceStatus)}</dd></div>
        <div><dt>review_id</dt><dd>${escapeHtml(viewState.currentGovernanceReviewId || "not_requested")}</dd></div>
        <div><dt>approved</dt><dd>false</dd></div>
        <div><dt>governance_approved</dt><dd>${viewState.currentGovernanceStatus === "governance_approved" ? "true" : "false"}</dd></div>
        <div><dt>execution_status</dt><dd>${currentBridge ? "push_center_pending_not_sent" : "not_execution"}</dd></div>
        <div><dt>push_center_job_created</dt><dd>${currentBridge ? "true" : "false"}</dd></div>
        <div><dt>push_center_status</dt><dd>${escapeHtml(currentBridge?.push_center_status || "not_bridged")}</dd></div>
        <div><dt>external_effect_job_created</dt><dd>false</dd></div>
        <div><dt>broadcast_job_created</dt><dd>false</dd></div>
        <div><dt>internal_event_created</dt><dd>false</dd></div>
        <div><dt>real_external_call</dt><dd>false</dd></div>
        <div><dt>can_claim_pass90</dt><dd>false</dd></div>
      </dl>
      <div class="p1-workspace-governance-actions" aria-label="治理 request 操作">
        <button type="button" data-workspace-request-governance="true"${canRequestGovernance ? "" : " disabled"}>Request governance</button>
        <button type="button" data-workspace-refresh-governance="true"${hasDraft ? "" : " disabled"}>Refresh governance</button>
        <button type="button" data-workspace-expire-governance-review="true"${canExpireReview ? "" : " disabled"}>Expire review</button>
      </div>
      <p class="p1-workspace-draft-status p1-workspace-draft-status--${tone}" aria-live="polite" data-governance-request-status="${escapeHtml(viewState.governanceRequestStatus)}">${escapeHtml(viewState.governanceRequestMessage)}</p>
      ${disabledReason && !canRequestGovernance ? `<p class="p1-workspace-draft-guardrail" data-governance-disabled-reason="${escapeHtml(disabledReason)}">${escapeHtml(disabledReason)}</p>` : ""}
      <section class="p1-workspace-governance-timeline" aria-label="Governance pending step timeline">
        <h3>Step timeline</h3>
        <ul>${renderGovernanceStepRows(currentReview, busy)}</ul>
      </section>
      <dl class="p1-workspace-mini-fields">
        <div><dt>allowlist_hash</dt><dd>${escapeHtml(allowlistHash)}</dd></div>
        <div><dt>allowlist_count</dt><dd>${allowlistCount}</dd></div>
        <div><dt>source_reference</dt><dd>${escapeHtml(JSON.stringify(sourceReference))}</dd></div>
        <div><dt>window_start</dt><dd>${escapeHtml(grayWindow.start_at)}</dd></div>
        <div><dt>window_end</dt><dd>${escapeHtml(grayWindow.end_at)}</dd></div>
        <div><dt>timezone</dt><dd>${escapeHtml(grayWindow.timezone)}</dd></div>
        <div><dt>window_status</dt><dd>${escapeHtml(grayWindow.window_status || "pending")}</dd></div>
      </dl>
      <section class="p1-workspace-governance-bridge" aria-label="Push Center bridge pending panel" data-push-center-bridge-panel="true" data-bridge-status="${escapeHtml(viewState.pushCenterBridgeStatus)}" data-push-center-status="${escapeHtml(currentBridge?.push_center_status || "not_bridged")}" data-execution-status="${currentBridge ? "push_center_pending_not_sent" : "not_execution"}" data-external-effect-job-created="false" data-broadcast-job-created="false" data-internal-event-created="false" data-real-external-call-executed="false" data-can-claim-pass90="false">
        <h3>Push Center bridge</h3>
        <p>Bridge 只进入 Push Center pending，不会发送；Push Center pending 不等于 sent/completed。</p>
        <div class="p1-workspace-governance-actions" aria-label="Push Center bridge 操作">
          <button type="button" data-workspace-bridge-push-center="true"${canBridgePushCenter ? "" : " disabled"}>Bridge to Push Center</button>
          <button type="button" data-workspace-refresh-push-center-bridge="true"${currentReview?.review_id ? "" : " disabled"}>Refresh bridge status</button>
        </div>
        <p class="p1-workspace-draft-status p1-workspace-draft-status--${bridgeStatusTone}" aria-live="polite" data-push-center-bridge-status="${escapeHtml(viewState.pushCenterBridgeStatus)}">${escapeHtml(bridgeMessage)}</p>
        ${bridgeDisabledReason && !canBridgePushCenter ? `<p class="p1-workspace-draft-guardrail" data-push-center-bridge-disabled-reason="${escapeHtml(bridgeDisabledReason)}">${escapeHtml(bridgeDisabledReason)}</p>` : ""}
        <dl class="p1-workspace-mini-fields">
          <div><dt>bridge_idempotency_key</dt><dd>${escapeHtml(bridgePayloadPreview?.idempotency_key || viewState.currentPushCenterBridgeIdempotencyKey || "not_ready")}</dd></div>
          <div><dt>push_center_job_id</dt><dd>${escapeHtml(currentBridge?.push_center_job_id || "not_bridged")}</dd></div>
          <div><dt>push_center_projection_id</dt><dd>${escapeHtml(currentBridge?.push_center_projection_id || "not_bridged")}</dd></div>
          <div><dt>push_center_status</dt><dd>${escapeHtml(currentBridge?.push_center_status || "not_bridged")}</dd></div>
          <div><dt>execution_status</dt><dd>${currentBridge ? "push_center_pending_not_sent" : "not_execution"}</dd></div>
          <div><dt>external_effect_job_created</dt><dd>false</dd></div>
          <div><dt>broadcast_job_created</dt><dd>false</dd></div>
          <div><dt>internal_event_created</dt><dd>false</dd></div>
          <div><dt>real_external_call</dt><dd>false</dd></div>
          <div><dt>can_claim_pass90</dt><dd>false</dd></div>
        </dl>
      </section>
      <p class="p1-workspace-draft-guardrail">governance request 不等于 approval；pending steps 不等于 approved；step approved 不等于发送；governance_approved 不等于 execution。Bridge 只创建 Push Center pending projection，不创建 external_effect_job、broadcast_job、internal_event，不发送，不能 claim PASS_90_PLUS；真实发送仍由 Push Center / external effect boundary 控制。</p>
    </section>
  `;
}

function renderPropertyPanel(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): string {
  const selection = selectionFromViewState(fixture, filtered.viewState);
  const multiSelectedCount = countMultiSelected(filtered.viewState);
  const cards = fixture.payload.scenarios.map((scenario) => renderStatusCard(scenario, {
    dragHandle: true,
    dragDisabledReason: "P1 native workspace uses readonly preview only; no direct send."
  })).join("");
  const governanceScenario = fixture.payload.scenarios.find((scenario) => scenario.status === "governance-missing");
  const guardrailNotice = governanceScenario ? renderGuardrailNotice(governanceScenario) : "";
  const canPass = workspaceCanRenderGlobalPass(fixture.payload);

  return `
    <aside class="p1-workspace-right" aria-label="属性面板与护栏">
      <div class="p1-workspace-panel-head">
        <h2>属性面板 / guardrail / evidence state</h2>
        <p>Group Ops 发送 evidence 已存在，但 governance evidence incomplete；真正执行必须走 approval / allowlist / Push Center / external effect gates。</p>
      </div>
      <section class="p1-workspace-guardrail-summary" data-can-render-pass90="${canPass ? "true" : "false"}">
        <strong>Guardrail summary</strong>
        ${guardrailNotice}
        <p>P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS；sent evidence 不等于 governance complete。</p>
      </section>
      ${renderDraftPersistencePanel(fixture, filtered)}
      ${renderGovernancePanel(filtered)}
      ${filtered.viewState.activeSelectionMode === "multi" && multiSelectedCount > 0 ? renderBundleSummary(fixture, filtered) : renderWorkspaceDetailPanel(fixture, selection)}
      <div class="p1-workspace-status-stack">${cards}</div>
    </aside>
  `;
}

function attachSelectionHandlers(
  root: HTMLElement,
  fixture: WorkspaceFixture,
  viewState: WorkspaceViewState
): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLElement>("[data-workspace-select-type][data-workspace-select-id]");
  nodes.forEach((node) => {
    node.addEventListener("click", () => {
      const entityType = node.dataset.workspaceSelectType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceSelectId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, selectEntityInViewState(viewState, entityType, detailId));
    });
  });
}

function attachFilterHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-workspace-filter]");
  nodes.forEach((node) => {
    const eventName = node.tagName === "INPUT" ? "input" : "change";
    node.addEventListener(eventName, () => {
      const key = node.dataset.workspaceFilter as keyof WorkspaceViewState | undefined;
      if (!key) return;
      renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
        [key]: node.value
      } as Partial<WorkspaceViewState>));
    });
  });
}

function attachCanvasLaneHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const nodes = root.querySelectorAll<HTMLElement>("[data-workspace-lane-toggle]");
  nodes.forEach((node) => {
    node.addEventListener("click", () => {
      const laneId = node.dataset.workspaceLaneToggle;
      if (!laneId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleWorkspaceCanvasLane(viewState, laneId as WorkspaceCanvasLaneId));
    });
  });
}

function entityTypeForLane(laneId: string): WorkspaceEntityType | null {
  if (laneId === "plans") return "plan";
  if (laneId === "groups") return "group";
  if (laneId === "nodes") return "node";
  if (laneId === "executions") return "execution";
  if (laneId === "push_center") return "push_center";
  if (laneId === "evidence") return "evidence";
  return null;
}

function attachMultiSelectHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll<HTMLElement>("[data-workspace-multi-toggle]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const entityType = node.dataset.workspaceMultiType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceMultiId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(viewState, entityType, detailId));
    });
    node.addEventListener("keydown", (event) => {
      if (event.key !== " " && event.key !== "Enter") return;
      event.preventDefault();
      event.stopPropagation();
      const entityType = node.dataset.workspaceMultiType as WorkspaceEntityType | undefined;
      const detailId = node.dataset.workspaceMultiId;
      if (!entityType || !detailId) return;
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(viewState, entityType, detailId));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-clear-selection]").forEach((node) => {
    node.addEventListener("click", () => {
      renderP1GroupOpsWorkspace(root, fixture, clearMultiSelection(viewState));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-select-visible]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      renderP1GroupOpsWorkspace(root, fixture, selectVisibleItems(filtered.viewState, filtered.visibleLeftRailItems));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-select-lane]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const entityType = entityTypeForLane(node.dataset.workspaceSelectLane || "");
      if (!entityType) return;
      const filtered = filterWorkspaceView(fixture, viewState);
      renderP1GroupOpsWorkspace(root, fixture, selectVisibleLaneItems(filtered.viewState, filtered.visibleLeftRailItems, entityType));
    });
  });
}

function copyStatusUpdate(result: CopySafeResult): Pick<WorkspaceViewState, "copyStatus" | "copyStatusMessage"> {
  return {
    copyStatus: result.status,
    copyStatusMessage: result.ok
      ? "复制成功：只读脱敏摘要已进入剪贴板，不会发送。"
      : `复制失败：${result.message}`
  };
}

function attachBundleExportHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll<HTMLElement>("[data-workspace-toggle-copy-preview]").forEach((node) => {
    node.addEventListener("click", () => {
      const nextFormat = viewState.copyPreviewFormat === "text" ? "json" : "text";
      renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
        copyPreviewVisible: !viewState.copyPreviewVisible || viewState.copyPreviewFormat !== nextFormat,
        copyPreviewFormat: nextFormat,
        copyStatus: "idle",
        copyStatusMessage: "只读复制预览已更新；不会发送。"
      }));
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-copy-bundle]").forEach((node) => {
    node.addEventListener("click", () => {
      const format = node.dataset.workspaceCopyBundle === "json" ? "json" : "text";
      const filtered = filterWorkspaceView(fixture, viewState);
      const bundle = buildWorkspacePreviewBundle(fixture, filtered, filtered.viewState);
      const output = format === "json"
        ? buildCopySafeBundleJson(bundle, { finalVerdict: fixture.payload.finalVerdict })
        : buildCopySafeBundleText(bundle, { finalVerdict: fixture.payload.finalVerdict });
      copyBundleSummaryToClipboard(output).then((result) => {
        renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
          copyPreviewVisible: true,
          copyPreviewFormat: format,
          ...copyStatusUpdate(result)
        }));
      });
    });
  });
}

function draftStateFromResponse(
  viewState: WorkspaceViewState,
  payload: WorkspaceDraftResponse,
  message: string
): Partial<WorkspaceViewState> {
  const status = normalizeDraftStatus(payload.draft_status);
  return {
    currentDraftId: payload.draft_id || viewState.currentDraftId,
    currentDraftVersion: Number(payload.version || viewState.currentDraftVersion || 0),
    currentDraftSnapshotHash: String(payload.snapshot_hash || viewState.currentDraftSnapshotHash || ""),
    currentDraftIdempotencyKey: viewState.currentDraftIdempotencyKey,
    currentDraftStatus: status,
    draftSaveStatus: payload.draft_status === "archived" ? "archived" : "saved",
    draftSaveMessage: message
  };
}

function governanceStateFromResponse(
  payload: WorkspaceGovernanceResponse,
  message: string
): Partial<WorkspaceViewState> {
  const review = governanceReviewFromResponse(payload) as NonNullable<WorkspaceViewState["currentGovernanceReview"]>;
  return {
    currentGovernanceReviewId: review.review_id,
    currentGovernanceStatus: review.review_status,
    currentGovernanceReview: review,
    governanceRequestStatus: "requested",
    governanceRequestMessage: message
  };
}

function pushCenterBridgeStateFromResponse(
  payload: WorkspacePushCenterBridgeResponse,
  message: string
): Partial<WorkspaceViewState> {
  const bridge = pushCenterBridgeFromResponse(payload);
  return {
    currentPushCenterBridge: bridge,
    pushCenterBridgeStatus: bridge ? "bridged" : "idle",
    pushCenterBridgeMessage: message,
    currentPushCenterBridgeIdempotencyKey: ""
  };
}

function governanceStepById(
  review: NonNullable<WorkspaceViewState["currentGovernanceReview"]> | null,
  stepId: string
): NonNullable<WorkspaceViewState["currentGovernanceReview"]>["steps"][number] | null {
  return (review?.steps || []).find((step) => step.step_id === stepId) || null;
}

function firstActiveGovernanceReview(items: WorkspaceGovernanceResponse[]): WorkspaceGovernanceResponse | null {
  return items.find((item) => isActiveGovernanceStatus(String(item.review_status || "")))
    || items[0]
    || null;
}

function attachDraftPersistenceHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const renderWithDraftUpdates = (updates: Partial<WorkspaceViewState>) => {
    renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, updates));
  };
  root.querySelectorAll<HTMLElement>("[data-workspace-save-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      const basePayload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState, {
        version: filtered.viewState.currentDraftVersion || undefined
      });
      const idempotencyKey = filtered.viewState.currentDraftIdempotencyKey || basePayload.idempotency_key;
      renderWithDraftUpdates({
        currentDraftIdempotencyKey: idempotencyKey,
        draftSaveStatus: "saving",
        draftSaveMessage: "正在保存脱敏草稿；不会发送、不审批、不创建 Push Center job。"
      });
      const request = filtered.viewState.currentDraftId && filtered.viewState.currentDraftVersion > 0
        ? updateDraft(filtered.viewState.currentDraftId, { ...basePayload, idempotency_key: idempotencyKey, version: filtered.viewState.currentDraftVersion })
        : createDraft({ ...basePayload, idempotency_key: idempotencyKey });
      request
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            ...draftStateFromResponse(filtered.viewState, response, "草稿已保存；仍为 preview-only，不可执行。"),
            currentDraftIdempotencyKey: idempotencyKey
          }));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            currentDraftIdempotencyKey: idempotencyKey,
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: isDraftConflictError(error)
              ? "保存冲突：服务端版本更新了，请重新加载草稿或另存为新草稿；不会自动覆盖。"
              : "保存失败：草稿未写入；不会发送、不审批、不创建外部任务。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-save-as-new-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      const filtered = filterWorkspaceView(fixture, viewState);
      const idempotencyKey = `p1-gow-draft-new:${Date.now()}`;
      const payload = buildWorkspaceDraftPayload(fixture, filtered, filtered.viewState, { idempotencyKeyOverride: idempotencyKey });
      renderWithDraftUpdates({
        currentDraftId: "",
        currentDraftVersion: 0,
        currentDraftSnapshotHash: "",
        currentDraftIdempotencyKey: idempotencyKey,
        currentDraftReviewIdempotencyKey: "",
        currentDraftStatus: "not_saved",
        draftReviewStatus: "idle",
        draftReviewMessage: "新草稿保存后才能 request-review；不会审批。",
        draftSaveStatus: "saving",
        draftSaveMessage: "正在另存为新脱敏草稿；不会执行。"
      });
      createDraft(payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            ...draftStateFromResponse(filtered.viewState, response, "已另存为新草稿；仍不可执行。"),
            currentDraftIdempotencyKey: idempotencyKey
          }));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            currentDraftIdempotencyKey: idempotencyKey,
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: "另存失败：未写入草稿表，不会发送。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-archive-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      if (!viewState.currentDraftId || viewState.currentDraftVersion <= 0) return;
      const filtered = filterWorkspaceView(fixture, viewState);
      renderWithDraftUpdates({
        draftSaveStatus: "saving",
        draftSaveMessage: "正在归档草稿；只更新 draft 状态，不删除 audit，不执行任务。"
      });
      archiveDraft(viewState.currentDraftId, viewState.currentDraftVersion)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, draftStateFromResponse(filtered.viewState, response, "草稿已归档；不会执行。")));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            draftSaveStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftSaveMessage: isDraftConflictError(error)
              ? "归档冲突：请重新加载草稿版本。"
              : "归档失败：未执行任何发送或外呼。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-request-review-draft]").forEach((node) => {
    node.addEventListener("click", () => {
      if (!viewState.currentDraftId || viewState.currentDraftVersion <= 0 || viewState.currentDraftStatus !== "draft") {
        renderWithDraftUpdates({
          draftReviewStatus: "blocked",
          draftReviewMessage: "只有已保存且状态仍为 draft 的草稿可以 request-review；不会自动推进。"
        });
        return;
      }
      const filtered = filterWorkspaceView(fixture, viewState);
      const payload = buildWorkspaceDraftReviewPayload(
        filtered.viewState.currentDraftId,
        filtered.viewState.currentDraftVersion,
        filtered.viewState.currentDraftSnapshotHash
      );
      renderWithDraftUpdates({
        currentDraftReviewIdempotencyKey: payload.idempotency_key,
        draftReviewStatus: "requesting",
        draftReviewMessage: "正在提交 request-review；只更新 draft 状态，不审批、不发送、不创建下游任务。"
      });
      requestDraftReview(filtered.viewState.currentDraftId, payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            ...draftStateFromResponse(filtered.viewState, response, "草稿已进入 ready_for_review；仍未审批、未发送。"),
            currentDraftReviewIdempotencyKey: payload.idempotency_key,
            draftReviewStatus: "ready_for_review",
            draftReviewMessage: "ready_for_review 已记录；这不是 approval，也不是 Push Center bridge。"
          }));
        })
        .catch((error) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(filtered.viewState, {
            currentDraftReviewIdempotencyKey: payload.idempotency_key,
            draftReviewStatus: isDraftConflictError(error) ? "conflict" : "failed",
            draftReviewMessage: isDraftConflictError(error)
              ? "request-review 冲突：服务端版本更新了，请重新加载草稿；不会覆盖。"
              : "request-review 失败：草稿未推进，不会审批、不发送。"
          }));
        });
    });
  });
}

function attachGovernanceHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelectorAll !== "function") return;
  const renderWithGovernanceUpdates = (updates: Partial<WorkspaceViewState>) => {
    renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, updates));
  };
  const refreshAfterConflict = (message: string) => {
    if (!viewState.currentGovernanceReviewId) {
      renderWithGovernanceUpdates({
        governanceRequestStatus: "conflict",
        governanceRequestMessage: message
      });
      return;
    }
    getGovernanceReview(viewState.currentGovernanceReviewId)
      .then((response) => {
        renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, governanceStateFromResponse(response, message)));
      })
      .catch(() => {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "conflict",
          governanceRequestMessage: "governance step 冲突，刷新 review 失败；不会覆盖本地状态。"
        });
      });
  };
  root.querySelectorAll<HTMLElement>("[data-workspace-request-governance]").forEach((node) => {
    node.addEventListener("click", () => {
      if (
        !viewState.currentDraftId
        || viewState.currentDraftStatus !== "ready_for_review"
        || !viewState.currentDraftSnapshotHash
        || (viewState.currentGovernanceReviewId && isActiveGovernanceStatus(viewState.currentGovernanceStatus))
      ) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: "governance request 需要 saved ready_for_review draft、snapshot_hash，且不能已有 active review。"
        });
        return;
      }
      let payload;
      try {
        payload = buildWorkspaceGovernanceRequestPayload(viewState.currentDraftId, viewState.currentDraftSnapshotHash);
      } catch (error) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: error instanceof Error ? error.message : "governance payload 未通过脱敏校验。"
        });
        return;
      }
      renderWithGovernanceUpdates({
        currentGovernanceIdempotencyKey: payload.idempotency_key,
        governanceRequestStatus: "requesting",
        governanceRequestMessage: "正在 request governance；只写 governance review/step 表，不审批、不执行。"
      });
      requestGovernance(viewState.currentDraftId, payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
            currentGovernanceIdempotencyKey: payload.idempotency_key,
            ...governanceStateFromResponse(response, "governance request 已记录 approval_pending；三个治理 step 仍为 pending。")
          }));
        })
        .catch((error) => {
          if (isGovernanceConflictError(error)) {
            getDraftGovernance(viewState.currentDraftId)
              .then((response) => {
                const active = firstActiveGovernanceReview(response.items);
                renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
                  currentGovernanceIdempotencyKey: payload.idempotency_key,
                  ...(active
                    ? governanceStateFromResponse(active, "已存在 active governance review；已刷新为只读 pending 状态。")
                    : {
                      governanceRequestStatus: "conflict",
                      governanceRequestMessage: "governance request 冲突：请刷新治理状态；不会覆盖。"
                    })
                }));
              })
              .catch(() => {
                renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
                  currentGovernanceIdempotencyKey: payload.idempotency_key,
                  governanceRequestStatus: "conflict",
                  governanceRequestMessage: "governance request 冲突，且读取现有 review 失败；不会覆盖本地状态。"
                }));
              });
            return;
          }
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
            currentGovernanceIdempotencyKey: payload.idempotency_key,
            governanceRequestStatus: "failed",
            governanceRequestMessage: "governance request 失败：未审批、未发送、未创建 Push Center job。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-refresh-governance]").forEach((node) => {
    node.addEventListener("click", () => {
      if (!viewState.currentDraftId && !viewState.currentGovernanceReviewId) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: "没有可刷新的 draft 或 governance review。"
        });
        return;
      }
      renderWithGovernanceUpdates({
        governanceRequestStatus: "requesting",
        governanceRequestMessage: "正在读取 governance review；不会执行任何治理 step。"
      });
      const request = viewState.currentGovernanceReviewId
        ? getGovernanceReview(viewState.currentGovernanceReviewId).then((response) => response)
        : getDraftGovernance(viewState.currentDraftId).then((response) => firstActiveGovernanceReview(response.items));
      request
        .then((response) => {
          if (!response) {
            renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
              governanceRequestStatus: "idle",
              governanceRequestMessage: "当前 draft 尚无 governance review；ready_for_review 后可 request governance。"
            }));
            return;
          }
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, governanceStateFromResponse(response, "governance review 已刷新；仍为 not_execution。")));
        })
        .catch(() => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
            governanceRequestStatus: "failed",
            governanceRequestMessage: "刷新 governance 失败；不会审批、不会执行。"
          }));
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-governance-step-action]").forEach((node) => {
    node.addEventListener("click", () => {
      const action = node.dataset.workspaceGovernanceStepAction;
      const review = viewState.currentGovernanceReview;
      const reviewId = viewState.currentGovernanceReviewId || review?.review_id || "";
      const stepId = node.dataset.governanceStepId || "";
      const step = governanceStepById(review, stepId);
      if (!review || !reviewId || !step) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: "governance step 操作需要已加载的 review 和 step；不会执行。"
        });
        return;
      }
      if (step.step_status !== "pending") {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "conflict",
          governanceRequestMessage: "该 governance step 已经 transition；不会重复推进。"
        });
        return;
      }
      let request;
      let successMessage = "";
      try {
        if (action === "approve") {
          const payload = buildApproveGovernanceStepPayload(review, step);
          successMessage = step.step_type === "receiver_allowlist"
            ? "receiver allowlist step 已 approve；仅使用 hash/count summary，不含 raw receiver list。"
            : step.step_type === "gray_window"
              ? "gray-window step 已 approve；仍不会发送。"
              : "operator approval step 已 approve；这不是 Push Center bridge。";
          renderWithGovernanceUpdates({
            currentGovernanceIdempotencyKey: payload.idempotency_key,
            governanceRequestStatus: "requesting",
            governanceRequestMessage: "正在 approve governance step；只写 governance 表，不执行。"
          });
          request = approveGovernanceStep(reviewId, step.step_id, payload);
        } else if (action === "reject") {
          const payload = buildRejectGovernanceStepPayload(review, step);
          successMessage = "governance step 已 reject；review 标记为 governance_rejected，不会创建下游任务。";
          renderWithGovernanceUpdates({
            currentGovernanceIdempotencyKey: payload.idempotency_key,
            governanceRequestStatus: "requesting",
            governanceRequestMessage: "正在 reject governance step；不会执行。"
          });
          request = rejectGovernanceStep(reviewId, step.step_id, payload);
        } else {
          renderWithGovernanceUpdates({
            governanceRequestStatus: "blocked",
            governanceRequestMessage: "未知 governance step action；不会执行。"
          });
          return;
        }
      } catch (error) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: error instanceof Error ? error.message : "governance step payload 未通过脱敏或窗口校验。"
        });
        return;
      }
      request
        .then((response) => {
          const message = response.review_status === "governance_approved"
            ? "三个 governance steps 已 approved，状态为 governance_approved；仍为 not_execution。"
            : successMessage;
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, governanceStateFromResponse(response, message)));
        })
        .catch((error) => {
          if (isGovernanceConflictError(error)) {
            refreshAfterConflict("governance step conflict / already transitioned；已尝试刷新 review，未覆盖本地状态。");
            return;
          }
          renderWithGovernanceUpdates({
            governanceRequestStatus: "failed",
            governanceRequestMessage: "governance step 操作失败：未发送、未创建 Push Center job。"
          });
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-expire-governance-review]").forEach((node) => {
    node.addEventListener("click", () => {
      const review = viewState.currentGovernanceReview;
      const reviewId = viewState.currentGovernanceReviewId || review?.review_id || "";
      if (!review || !reviewId) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: "expire review 需要已加载 governance review；不会执行。"
        });
        return;
      }
      let payload;
      try {
        payload = buildExpireGovernanceReviewPayload(review);
      } catch (error) {
        renderWithGovernanceUpdates({
          governanceRequestStatus: "blocked",
          governanceRequestMessage: error instanceof Error ? error.message : "expire payload 未通过脱敏校验。"
        });
        return;
      }
      renderWithGovernanceUpdates({
        currentGovernanceIdempotencyKey: payload.idempotency_key,
        governanceRequestStatus: "requesting",
        governanceRequestMessage: "正在 expire governance review；只更新治理表，不执行。"
      });
      expireGovernanceReview(reviewId, payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, governanceStateFromResponse(response, "governance review 已 expire；不会创建任何下游任务。")));
        })
        .catch((error) => {
          if (isGovernanceConflictError(error)) {
            refreshAfterConflict("expire governance review conflict；已尝试刷新 review，未覆盖本地状态。");
            return;
          }
          renderWithGovernanceUpdates({
            governanceRequestStatus: "failed",
            governanceRequestMessage: "expire governance review 失败；不会审批、不会执行。"
          });
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-bridge-push-center]").forEach((node) => {
    node.addEventListener("click", () => {
      const review = viewState.currentGovernanceReview;
      const reviewId = viewState.currentGovernanceReviewId || review?.review_id || "";
      if (!review || !reviewId) {
        renderWithGovernanceUpdates({
          pushCenterBridgeStatus: "blocked",
          pushCenterBridgeMessage: "Push Center bridge 需要已加载的 governance review；不会执行。"
        });
        return;
      }
      if (
        viewState.currentDraftStatus !== "ready_for_review"
        || viewState.currentGovernanceStatus !== "governance_approved"
        || !governanceStepsAllApproved(review)
        || grayWindowExpired(review)
        || viewState.currentPushCenterBridge
      ) {
        renderWithGovernanceUpdates({
          pushCenterBridgeStatus: "blocked",
          pushCenterBridgeMessage: "Bridge precondition 未满足：需要 ready_for_review + governance_approved + 三步 approved + 未过期 gray-window + 尚未 bridged。"
        });
        return;
      }
      let payload;
      try {
        payload = buildPushCenterBridgePayload(review);
      } catch (error) {
        renderWithGovernanceUpdates({
          pushCenterBridgeStatus: "blocked",
          pushCenterBridgeMessage: error instanceof Error ? error.message : "Push Center bridge payload 未通过脱敏校验。"
        });
        return;
      }
      renderWithGovernanceUpdates({
        currentPushCenterBridgeIdempotencyKey: payload.idempotency_key,
        pushCenterBridgeStatus: "requesting",
        pushCenterBridgeMessage: "正在 bridge 到 Push Center pending；不会发送、不会创建 external effect。"
      });
      bridgeGovernanceToPushCenter(reviewId, payload)
        .then((response) => {
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
            ...pushCenterBridgeStateFromResponse(response, "Push Center bridge 已创建 pending projection；仍不是 sent/completed。"),
            currentPushCenterBridgeIdempotencyKey: payload.idempotency_key
          }));
        })
        .catch((error) => {
          if (isGovernanceConflictError(error)) {
            getGovernancePushCenterBridge(reviewId)
              .then((response) => {
                renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, {
                  ...pushCenterBridgeStateFromResponse(response, "Bridge conflict / already bridged；已刷新 pending projection 状态。"),
                  currentPushCenterBridgeIdempotencyKey: payload.idempotency_key
                }));
              })
              .catch(() => {
                renderWithGovernanceUpdates({
                  currentPushCenterBridgeIdempotencyKey: payload.idempotency_key,
                  pushCenterBridgeStatus: "conflict",
                  pushCenterBridgeMessage: "Bridge conflict，且刷新 bridge status 失败；不会 fallback 执行。"
                });
              });
            return;
          }
          renderWithGovernanceUpdates({
            currentPushCenterBridgeIdempotencyKey: payload.idempotency_key,
            pushCenterBridgeStatus: "failed",
            pushCenterBridgeMessage: "Push Center bridge 失败：未发送、未创建 external_effect_job。"
          });
        });
    });
  });
  root.querySelectorAll<HTMLElement>("[data-workspace-refresh-push-center-bridge]").forEach((node) => {
    node.addEventListener("click", () => {
      const reviewId = viewState.currentGovernanceReviewId || viewState.currentGovernanceReview?.review_id || "";
      if (!reviewId) {
        renderWithGovernanceUpdates({
          pushCenterBridgeStatus: "blocked",
          pushCenterBridgeMessage: "没有可刷新的 governance review；不会执行。"
        });
        return;
      }
      renderWithGovernanceUpdates({
        pushCenterBridgeStatus: "requesting",
        pushCenterBridgeMessage: "正在读取 Push Center bridge status；不会发送。"
      });
      getGovernancePushCenterBridge(reviewId)
        .then((response) => {
          const bridge = pushCenterBridgeFromResponse(response);
          renderP1GroupOpsWorkspace(root, fixture, updateWorkspaceViewState(viewState, pushCenterBridgeStateFromResponse(
            response,
            bridge
              ? "Push Center bridge status 已刷新：pending/not sent。"
              : "当前 review 尚未 bridge；仍为 not_execution。"
          )));
        })
        .catch(() => {
          renderWithGovernanceUpdates({
            pushCenterBridgeStatus: "failed",
            pushCenterBridgeMessage: "刷新 Push Center bridge status 失败；不会发送。"
          });
        });
    });
  });
}

function attachKeyboardHandlers(root: HTMLElement, fixture: WorkspaceFixture, viewState: WorkspaceViewState): void {
  if (typeof root.querySelector !== "function") return;
  const canvas = root.querySelector<HTMLElement>("[data-keyboard-navigation]");
  if (!canvas) return;
  canvas.addEventListener("keydown", (event) => {
    const allowedKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", " ", "Escape"];
    if (!allowedKeys.includes(event.key)) return;
    event.preventDefault();
    const filtered = filterWorkspaceView(fixture, viewState);
    const lanes = buildWorkspaceCanvasLanes(fixture, filtered, filtered.viewState);
    if (event.key === " ") {
      renderP1GroupOpsWorkspace(root, fixture, toggleMultiSelectedEntity(filtered.viewState, filtered.viewState.selectedEntityType, filtered.viewState.selectedEntityId));
      return;
    }
    renderP1GroupOpsWorkspace(root, fixture, moveWorkspaceCanvasSelection(lanes, filtered.viewState, event.key as WorkspaceKeyboardKey));
  });
}

export function renderP1GroupOpsWorkspace(
  root: HTMLElement,
  fixture: WorkspaceFixture = P1_GROUP_OPS_WORKSPACE_FIXTURE,
  viewState: WorkspaceViewState = createWorkspaceViewState(fixture)
): void {
  const model = buildGroupOpsWorkspaceStatusModel(fixture);
  const filtered = filterWorkspaceView(fixture, viewState);
  const selection = selectionFromViewState(fixture, filtered.viewState);
  root.innerHTML = `
    <section class="p1-native-group-ops-workspace" data-p1-native-workspace="group_ops" data-draft-only="true" data-preview-only="true" data-can-claim-pass90="false" data-view-state-memory-only="true" data-selected-entity-type="${escapeHtml(filtered.viewState.selectedEntityType)}" data-selected-entity-id="${escapeHtml(filtered.viewState.selectedEntityId)}" data-panel-mode="${escapeHtml(filtered.viewState.panelMode)}">
      ${renderWorkspaceHeader(fixture)}
      ${renderSafePreviewBanner()}
      ${renderFilterToolbar(filtered.viewState, filtered)}
      ${renderStateBanner(fixture, filtered)}
      <div class="p1-workspace-grid">
        ${renderLeftRail(filtered)}
        ${renderGroupedWorkspaceCanvas(fixture, filtered, filtered.viewState)}
        ${renderPropertyPanel(fixture, filtered)}
      </div>
      ${renderWorkspaceSelectedPreviewResult(fixture, selection)}
      ${renderWorkspacePreviewResult(model)}
      ${renderSafePreviewFooter()}
    </section>
  `;
  attachSelectionHandlers(root, fixture, filtered.viewState);
  attachFilterHandlers(root, fixture, filtered.viewState);
  attachCanvasLaneHandlers(root, fixture, filtered.viewState);
  attachMultiSelectHandlers(root, fixture, filtered.viewState);
  attachBundleExportHandlers(root, fixture, filtered.viewState);
  attachDraftPersistenceHandlers(root, fixture, filtered.viewState);
  attachGovernanceHandlers(root, fixture, filtered.viewState);
  attachKeyboardHandlers(root, fixture, filtered.viewState);
}

function boot(): void {
  const root = document.getElementById("p1GroupOpsWorkspaceApp");
  if (!root) return;
  renderP1GroupOpsWorkspace(root);
  loadGroupOpsWorkspaceData(parseWorkspaceApiConfig(), defaultRequestJson())
    .then((fixture) => {
      renderP1GroupOpsWorkspace(root, fixture);
    })
    .catch(() => {
      renderP1GroupOpsWorkspace(root, createUnavailableWorkspaceFixture("read_only_api_unavailable"));
    });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
