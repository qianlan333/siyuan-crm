import { escapeHtml } from "../shared/dom.js";
import { explainBlockedDrop, getExecutionModeForStatus, validateDropIntent } from "../shared/drop_validation.js";
import { renderGuardrailNotice } from "../shared/guardrail_notice.js";
import { renderStatusBadge } from "../shared/status_badge.js";
import { renderStatusCard } from "../shared/status_card.js";
const ENTITY_LABELS = {
    plan: "Plan detail",
    group: "Group / audience summary",
    node: "Node / task summary",
    execution: "Execution summary",
    push_center: "Push Center projection",
    evidence: "Evidence / guardrail summary"
};
export function createWorkspaceSelectionState(fixture) {
    return { ...fixture.defaultSelection };
}
export function selectedDetailId(selection) {
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
export function findWorkspaceDetail(fixture, selection) {
    const id = selectedDetailId(selection);
    const exact = fixture.detailItems.find((item) => item.id === id && item.entityType === selection.selectedEntityType);
    if (exact)
        return exact;
    const sameType = fixture.detailItems.find((item) => item.entityType === selection.selectedEntityType);
    if (sameType)
        return sameType;
    return fixture.detailItems[0];
}
export function selectWorkspaceEntity(current, entityType, detailId) {
    const next = { ...current, selectedEntityType: entityType };
    if (entityType === "plan")
        next.selectedPlanId = detailId;
    if (entityType === "group")
        next.selectedGroupId = detailId;
    if (entityType === "node")
        next.selectedNodeId = detailId;
    if (entityType === "execution")
        next.selectedExecutionId = detailId;
    if (entityType === "push_center")
        next.selectedPushCenterJobId = detailId;
    return next;
}
function scenarioFromDetail(detail) {
    return {
        key: detail.entityType === "evidence" ? "group_ops" : "group_ops",
        title: detail.title,
        status: detail.status,
        evidenceStatus: detail.evidenceStatus,
        derivedStatus: detail.derivedStatus,
        summary: detail.summary,
        guardrail: detail.guardrail
    };
}
function renderDetailFields(detail) {
    return detail.fields.map((field) => `
    <div>
      <dt>${escapeHtml(field.label)}</dt>
      <dd>${escapeHtml(field.value)}</dd>
    </div>
  `).join("");
}
export function renderWorkspaceDetailPanel(fixture, selection) {
    const detail = findWorkspaceDetail(fixture, selection);
    const scenario = scenarioFromDetail(detail);
    const validation = validateDropIntent(scenario, "blocked_noop");
    return `
    <div class="p1-workspace-detail" data-selected-entity-type="${escapeHtml(detail.entityType)}" data-selected-detail-id="${escapeHtml(detail.id)}" data-selected-status="${escapeHtml(detail.status)}">
      <div class="p1-workspace-detail__title">
        <span>${escapeHtml(ENTITY_LABELS[detail.entityType])}</span>
        ${renderStatusBadge(detail.status)}
      </div>
      <h3>${escapeHtml(detail.title)}</h3>
      <p>${escapeHtml(detail.summary)}</p>
      <dl class="p1-workspace-detail-fields">${renderDetailFields(detail)}</dl>
      ${renderStatusCard(scenario, {
        dragHandle: true,
        dragDisabledReason: "Read-only drilldown only; selection does not mutate evidence status."
    })}
      ${renderGuardrailNotice(scenario)}
      <section class="p1-workspace-guardrail-summary" data-execution-mode="${escapeHtml(getExecutionModeForStatus(detail.status))}" data-drop-allowed="${validation.allowed ? "true" : "false"}">
        <strong>Blocked reason</strong>
        <p>${escapeHtml(explainBlockedDrop(validation))}</p>
      </section>
    </div>
  `;
}
export function renderWorkspaceSelectedPreviewResult(fixture, selection) {
    const detail = findWorkspaceDetail(fixture, selection);
    const validation = validateDropIntent(scenarioFromDetail(detail), "blocked_noop");
    return `
    <section class="p1-workspace-selected-preview" aria-label="Selected object preview result" data-selected-entity-type="${escapeHtml(detail.entityType)}" data-preview-only="true" data-real-external-call-executed="false" data-production-write-executed="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Selected preview result</h2>
        <p>当前选中 ${escapeHtml(ENTITY_LABELS[detail.entityType])}；只读 drilldown 不保存 selection，不执行任务。</p>
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>preview-only</dt><dd>true</dd></div>
        <div><dt>production_write</dt><dd>false</dd></div>
        <div><dt>real_external_call</dt><dd>false</dd></div>
        <div><dt>can_claim_pass_90_plus</dt><dd>false</dd></div>
        <div><dt>execution_mode</dt><dd>${escapeHtml(validation.executionMode)}</dd></div>
        <div><dt>status_after_drop</dt><dd>${escapeHtml(validation.statusAfterDrop)}</dd></div>
      </dl>
      <p>${escapeHtml(explainBlockedDrop(validation))}</p>
      <p class="p1-workspace-guardrails">${validation.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ")}</p>
    </section>
  `;
}
