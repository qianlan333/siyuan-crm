import { escapeHtml } from "../shared/dom.js";
import { renderInteractionShell } from "../shared/interaction_shell.js";
import { renderStatusBadge } from "../shared/status_badge.js";
function renderGuardrailChips(guardrails) {
    return guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
}
function detailTargetForCard(cardStatus, fixture) {
    if (!fixture)
        return undefined;
    if (cardStatus === "sent")
        return fixture.detailItems.find((item) => item.entityType === "push_center");
    if (cardStatus === "governance-missing")
        return fixture.detailItems.find((item) => item.entityType === "evidence");
    if (cardStatus === "downstream-pending" || cardStatus === "pending")
        return fixture.detailItems.find((item) => item.entityType === "node");
    if (cardStatus === "evidence-incomplete")
        return fixture.detailItems.find((item) => item.entityType === "execution");
    return fixture.detailItems.find((item) => item.entityType === "plan");
}
function selectedClass(target, selection) {
    if (!target || !selection)
        return "";
    if (selection.selectedEntityType !== target.entityType)
        return "";
    if (selection.selectedEntityType === "plan" && selection.selectedPlanId === target.id)
        return " p1-workspace-canvas-card--selected";
    if (selection.selectedEntityType === "group" && selection.selectedGroupId === target.id)
        return " p1-workspace-canvas-card--selected";
    if (selection.selectedEntityType === "node" && selection.selectedNodeId === target.id)
        return " p1-workspace-canvas-card--selected";
    if (selection.selectedEntityType === "execution" && selection.selectedExecutionId === target.id)
        return " p1-workspace-canvas-card--selected";
    if (selection.selectedEntityType === "push_center" && selection.selectedPushCenterJobId === target.id)
        return " p1-workspace-canvas-card--selected";
    return "";
}
export function renderWorkspaceCanvas(model, fixture, selection) {
    const rows = model.display.cards.map((card) => {
        const target = detailTargetForCard(card.status, fixture);
        const dataTarget = target
            ? ` data-workspace-select-type="${escapeHtml(target.entityType)}" data-workspace-select-id="${escapeHtml(target.id)}"`
            : "";
        return `
    <button type="button" class="p1-workspace-canvas-card${selectedClass(target, selection)}" data-card-id="${escapeHtml(card.id)}" data-evidence-status="${escapeHtml(card.status)}" data-mutated-evidence-status="${card.mutatedEvidenceStatus ? "true" : "false"}"${dataTarget}>
      <div class="p1-workspace-canvas-card__head">
        <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
        <strong>${escapeHtml(card.title)}</strong>
        ${renderStatusBadge(card.status)}
      </div>
      <dl class="p1-workspace-mini-fields">
        <div><dt>Original</dt><dd>${card.originalIndex + 1}</dd></div>
        <div><dt>Preview</dt><dd>${card.draftIndex + 1}</dd></div>
        <div><dt>Mode</dt><dd>${escapeHtml(card.executionMode)}</dd></div>
      </dl>
      <p>Readonly reorder preview only; evidence status remains ${escapeHtml(card.status)}.</p>
      <p class="p1-workspace-guardrails">${renderGuardrailChips(card.guardrails)}</p>
    </button>
  `;
    }).join("");
    return `
    <section class="p1-workspace-canvas" aria-label="Draft-only canvas shell" data-draft-persistence="${escapeHtml(model.display.persistence)}" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>编排预览区 / draft-only canvas shell</h2>
        <p>卡片重排只改变本地 preview 顺序，刷新后丢弃；不会发送、审批或写生产。</p>
      </div>
      <div class="p1-workspace-canvas-grid">${rows}</div>
    </section>
  `;
}
export function renderWorkspacePreviewResult(model) {
    const validationRows = model.validations.map((row) => `
    <article class="p1-workspace-validation" data-status="${escapeHtml(row.status)}" data-execution-mode="${escapeHtml(row.executionMode)}" data-drop-allowed="${row.dropAllowed ? "true" : "false"}" data-status-after-drop="${escapeHtml(row.statusAfterDrop)}">
      <span>${escapeHtml(row.scenarioTitle)}</span>
      <p>${escapeHtml(row.blockedReason)}</p>
      <p class="p1-workspace-guardrails">${renderGuardrailChips(row.guardrails)}</p>
    </article>
  `).join("");
    const sharedShell = renderInteractionShell(model.payload, {
        id: "p1-native-group-ops-workspace-shell",
        title: "Shared interaction shell contract",
        description: "复用 shared interaction shell；blocked_noop 不改变 evidence status，不保存草稿，不产生 PASS_90_PLUS。"
    });
    return `
    <section class="p1-workspace-preview-result" aria-label="Preview result and blocked reason" data-real-external-call-executed="false" data-production-write-executed="false" data-can-claim-pass90="false">
      <div class="p1-workspace-panel-head">
        <h2>Preview result / blocked reason</h2>
        <p>底部只显示前端内存草稿的 validation；真正执行必须未来通过 approval / allowlist / Push Center / external effect gates。</p>
      </div>
      <div class="p1-workspace-validation-grid">${validationRows}</div>
      ${sharedShell}
    </section>
  `;
}
