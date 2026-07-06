import { escapeHtml } from "../shared/dom.js";
import { renderInteractionShell } from "../shared/interaction_shell.js";
import { renderStatusCard } from "../shared/status_card.js";
import {
  type GroupOpsStatusInput,
  GROUP_OPS_P1_DEFAULT_INPUTS,
  buildGroupOpsStatusViewModel
} from "./group_ops_status.js";

export interface GroupOpsOverviewPayload {
  cards: GroupOpsStatusInput[];
  evidenceSummary: {
    effectJobId: string;
    pushCenterStatus: string;
    realExternalCallEvidence: string;
    retryable: boolean;
    operatorActionRequired: boolean;
    finalStatus: string;
  };
}

const DEFAULT_EVIDENCE_SUMMARY = {
  effectJobId: "external_effect_job:97",
  pushCenterStatus: "sent",
  realExternalCallEvidence: "collected_in_prior_report",
  retryable: false,
  operatorActionRequired: false,
  finalStatus: "EVIDENCE_COLLECTED"
};

function parsePayload(): GroupOpsOverviewPayload {
  const payloadNode = document.getElementById("groupOpsP1StatusPayload");
  if (!payloadNode?.textContent) {
    return { cards: GROUP_OPS_P1_DEFAULT_INPUTS, evidenceSummary: DEFAULT_EVIDENCE_SUMMARY };
  }
  const parsed = JSON.parse(payloadNode.textContent) as Partial<GroupOpsOverviewPayload>;
  return {
    cards: parsed.cards?.length ? parsed.cards : GROUP_OPS_P1_DEFAULT_INPUTS,
    evidenceSummary: { ...DEFAULT_EVIDENCE_SUMMARY, ...(parsed.evidenceSummary || {}) }
  };
}

function renderEvidenceSummary(summary: GroupOpsOverviewPayload["evidenceSummary"]): string {
  return `
    <section class="p1-group-ops-evidence" aria-label="Group Ops send evidence summary" data-final-status="${escapeHtml(summary.finalStatus)}">
      <div class="p1-group-ops-evidence__head">
        <h2>发送证据摘要</h2>
        <p>发送链路已取证，但治理记录仍需独立 attach。</p>
      </div>
      <dl class="p1-group-ops-evidence__grid">
        <div><dt>Effect job</dt><dd>${escapeHtml(summary.effectJobId)}</dd></div>
        <div><dt>Push Center</dt><dd>${escapeHtml(summary.pushCenterStatus)}</dd></div>
        <div><dt>Real call evidence</dt><dd>${escapeHtml(summary.realExternalCallEvidence)}</dd></div>
        <div><dt>Retryable</dt><dd>${summary.retryable ? "true" : "false"}</dd></div>
        <div><dt>Operator action</dt><dd>${summary.operatorActionRequired ? "true" : "false"}</dd></div>
        <div><dt>Final status</dt><dd>${escapeHtml(summary.finalStatus)}</dd></div>
      </dl>
    </section>
  `;
}

function renderGroupOpsInteractionShell(cards: GroupOpsStatusInput[]): string {
  return renderInteractionShell({
    finalVerdict: "P1_READY_WITH_EXCEPTIONS",
    canClaimPass90Plus: false,
    scenarios: cards.map((card) => buildGroupOpsStatusViewModel(card).scenario)
  }, {
    id: "group-ops-draft-preview",
    title: "Group Ops draft-only preview shell",
    description: "证据卡只做前端内存 reorder preview；sent 不代表治理完成，也不会触发发送、审批、名单或灰度窗口配置。"
  });
}

export function renderGroupOpsOverview(root: HTMLElement, payload: GroupOpsOverviewPayload): void {
  const cards = payload.cards.length ? payload.cards : GROUP_OPS_P1_DEFAULT_INPUTS;
  const cardHtml = cards.map((card) => {
    const viewModel = buildGroupOpsStatusViewModel(card);
    return renderStatusCard(viewModel.scenario, {
      dragHandle: true,
      dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
    });
  }).join("");
  root.innerHTML = `
    <section class="p1-group-ops-banner" data-group-ops-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Group Ops status slice</h2>
        <p>只读展示发送 evidence 与 governance residual risk；不新增发送、审批、名单或灰度窗口配置能力。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">EVIDENCE_COLLECTED</span>
    </section>
    ${renderEvidenceSummary(payload.evidenceSummary)}
    <section class="p1-closure-grid" aria-label="Group Ops P1 status cards">
      ${cardHtml}
    </section>
    ${renderGroupOpsInteractionShell(cards)}
  `;
}

function boot(): void {
  const root = document.getElementById("groupOpsP1StatusApp");
  if (!root) return;
  renderGroupOpsOverview(root, parsePayload());
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
