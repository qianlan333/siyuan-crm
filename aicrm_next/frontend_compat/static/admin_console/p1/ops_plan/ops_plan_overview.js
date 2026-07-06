import { escapeHtml } from "../shared/dom.js";
import { renderInteractionShell } from "../shared/interaction_shell.js";
import { renderStatusCard } from "../shared/status_card.js";
import { OPS_PLAN_P1_DEFAULT_INPUTS, buildOpsPlanStatusViewModel } from "./ops_plan_status.js";
const DEFAULT_EVIDENCE_SUMMARY = {
    planId: "p0-1283-plan-20260615152503",
    planType: "cloud_plan",
    internalEvent: "ops_plan.approved",
    consumerName: "broadcast_task_planner_consumer",
    plannerResult: "planner_created_broadcast_job",
    broadcastJobId: "broadcast_job:3644",
    pushCenterStatus: "pending",
    downstreamStatus: "downstream_pending",
    externalEffectJob: "not_created",
    realExternalCallExecuted: false,
    finalStatus: "EVIDENCE_COLLECTED"
};
function parsePayload() {
    const payloadNode = document.getElementById("opsPlanP1StatusPayload");
    if (!payloadNode?.textContent) {
        return { cards: OPS_PLAN_P1_DEFAULT_INPUTS, evidenceSummary: DEFAULT_EVIDENCE_SUMMARY };
    }
    const parsed = JSON.parse(payloadNode.textContent);
    return {
        cards: parsed.cards?.length ? parsed.cards : OPS_PLAN_P1_DEFAULT_INPUTS,
        evidenceSummary: { ...DEFAULT_EVIDENCE_SUMMARY, ...(parsed.evidenceSummary || {}) }
    };
}
function renderEvidenceSummary(summary) {
    return `
    <section class="p1-ops-plan-evidence" aria-label="Ops Plan downstream evidence summary" data-final-status="${escapeHtml(summary.finalStatus)}">
      <div class="p1-ops-plan-evidence__head">
        <h2>Ops Plan 下游证据摘要</h2>
        <p>Next-native cloud_plan 已到 broadcast_job / Push Center pending；下游 external effect 尚未执行。</p>
      </div>
      <dl class="p1-ops-plan-evidence__grid">
        <div><dt>Plan</dt><dd>${escapeHtml(summary.planId)}</dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(summary.planType)}</dd></div>
        <div><dt>Event</dt><dd>${escapeHtml(summary.internalEvent)}</dd></div>
        <div><dt>Consumer</dt><dd>${escapeHtml(summary.consumerName)}</dd></div>
        <div><dt>Planner</dt><dd>${escapeHtml(summary.plannerResult)}</dd></div>
        <div><dt>Broadcast job</dt><dd>${escapeHtml(summary.broadcastJobId)}</dd></div>
        <div><dt>Push Center</dt><dd>${escapeHtml(summary.pushCenterStatus)}</dd></div>
        <div><dt>Downstream</dt><dd>${escapeHtml(summary.downstreamStatus)}</dd></div>
        <div><dt>External effect</dt><dd>${escapeHtml(summary.externalEffectJob)}</dd></div>
        <div><dt>Real call</dt><dd>${summary.realExternalCallExecuted ? "true" : "false"}</dd></div>
        <div><dt>Final</dt><dd>${escapeHtml(summary.finalStatus)}</dd></div>
      </dl>
    </section>
  `;
}
function renderOpsPlanInteractionShell(cards) {
    return renderInteractionShell({
        finalVerdict: "P1_READY_WITH_EXCEPTIONS",
        canClaimPass90Plus: false,
        scenarios: cards.map((card) => buildOpsPlanStatusViewModel(card).scenario)
    }, {
        id: "ops-plan-draft-preview",
        title: "Ops Plan draft-only preview shell",
        description: "计划证据卡只做前端内存 reorder preview；downstream pending、broadcast_job created 和 Push Center pending 都不会渲染成 completed 或 sent。"
    });
}
export function renderOpsPlanOverview(root, payload) {
    const cards = payload.cards.length ? payload.cards : OPS_PLAN_P1_DEFAULT_INPUTS;
    const cardHtml = cards.map((card) => {
        const viewModel = buildOpsPlanStatusViewModel(card);
        return renderStatusCard(viewModel.scenario, {
            dragHandle: true,
            dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
        });
    }).join("");
    root.innerHTML = `
    <section class="p1-ops-plan-banner" data-ops-plan-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Ops Plan downstream status slice</h2>
        <p>只读展示 approval -> planner -> broadcast_job -> Push Center pending；不执行下游 external effect。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">EVIDENCE_COLLECTED</span>
    </section>
    ${renderEvidenceSummary(payload.evidenceSummary)}
    <section class="p1-closure-grid" aria-label="Ops Plan P1 status cards">
      ${cardHtml}
    </section>
    ${renderOpsPlanInteractionShell(cards)}
  `;
}
function boot() {
    const root = document.getElementById("opsPlanP1StatusApp");
    if (!root)
        return;
    renderOpsPlanOverview(root, parsePayload());
}
if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    }
    else {
        boot();
    }
}
