import { escapeHtml } from "../shared/dom.js";
import { renderStatusCard } from "../shared/status_card.js";
import {
  type WeComStatusInput,
  WECOM_P1_DEFAULT_INPUTS,
  buildWeComStatusViewModel
} from "./wecom_status.js";

export interface WeComOverviewPayload {
  cards: WeComStatusInput[];
  evidenceSummary: {
    authStartRoute: string;
    authStartStatus: string;
    authCallbackRoute: string;
    authCallbackStatus: string;
    contactCallbackRoute: string;
    contactCallbackStatus: string;
    eventsRoute: string;
    eventsStatus: string;
    adminVisibility: string;
    callbackLinkedEvent: string;
    validCallbackSignature: string;
    authRecord: string;
    idempotencyEvidence: string;
    permissionScope: string;
    realExternalCallExecuted: boolean;
    finalStatus: string;
  };
}

const DEFAULT_EVIDENCE_SUMMARY = {
  authStartRoute: "/auth/wecom/start",
  authStartStatus: "controlled_external_call_blocked_503",
  authCallbackRoute: "/auth/wecom/callback",
  authCallbackStatus: "controlled_external_call_blocked_503",
  contactCallbackRoute: "/wecom/external-contact/callback",
  contactCallbackStatus: "fail_closed_400_missing_signature",
  eventsRoute: "/api/wecom/events",
  eventsStatus: "fail_closed_400_missing_signature",
  adminVisibility: "admin_internal_events_reachable",
  callbackLinkedEvent: "not_found",
  validCallbackSignature: "missing",
  authRecord: "not_found",
  idempotencyEvidence: "not_found",
  permissionScope: "not_found",
  realExternalCallExecuted: false,
  finalStatus: "BLOCKED_CONFIG_NOT_APPROVED"
};

function parsePayload(): WeComOverviewPayload {
  const payloadNode = document.getElementById("weComP1StatusPayload");
  if (!payloadNode?.textContent) {
    return { cards: WECOM_P1_DEFAULT_INPUTS, evidenceSummary: DEFAULT_EVIDENCE_SUMMARY };
  }
  const parsed = JSON.parse(payloadNode.textContent) as Partial<WeComOverviewPayload>;
  return {
    cards: parsed.cards?.length ? parsed.cards : WECOM_P1_DEFAULT_INPUTS,
    evidenceSummary: { ...DEFAULT_EVIDENCE_SUMMARY, ...(parsed.evidenceSummary || {}) }
  };
}

function renderEvidenceSummary(summary: WeComOverviewPayload["evidenceSummary"]): string {
  return `
    <section class="p1-wecom-evidence" aria-label="WeCom external config evidence summary" data-final-status="${escapeHtml(summary.finalStatus)}">
      <div class="p1-wecom-evidence__head">
        <h2>企微外部配置证据摘要</h2>
        <p>当前为 external-config-blocked；routes 可达且 fail-closed，但没有 valid callback signature / auth record / permission scope evidence。</p>
      </div>
      <dl class="p1-wecom-evidence__grid">
        <div><dt>Auth start</dt><dd>${escapeHtml(summary.authStartStatus)}</dd></div>
        <div><dt>Auth callback</dt><dd>${escapeHtml(summary.authCallbackStatus)}</dd></div>
        <div><dt>Contact callback</dt><dd>${escapeHtml(summary.contactCallbackStatus)}</dd></div>
        <div><dt>Events route</dt><dd>${escapeHtml(summary.eventsStatus)}</dd></div>
        <div><dt>Admin visibility</dt><dd>${escapeHtml(summary.adminVisibility)}</dd></div>
        <div><dt>Linked event</dt><dd>${escapeHtml(summary.callbackLinkedEvent)}</dd></div>
        <div><dt>Signature</dt><dd>${escapeHtml(summary.validCallbackSignature)}</dd></div>
        <div><dt>Auth record</dt><dd>${escapeHtml(summary.authRecord)}</dd></div>
        <div><dt>Idempotency</dt><dd>${escapeHtml(summary.idempotencyEvidence)}</dd></div>
        <div><dt>Permission</dt><dd>${escapeHtml(summary.permissionScope)}</dd></div>
        <div><dt>Real call</dt><dd>${summary.realExternalCallExecuted ? "true" : "false"}</dd></div>
        <div><dt>Final</dt><dd>${escapeHtml(summary.finalStatus)}</dd></div>
      </dl>
    </section>
  `;
}

function renderReadonlyInteractionShell(cards: WeComStatusInput[]): string {
  const rows = cards.map((card) => {
    const viewModel = buildWeComStatusViewModel(card);
    const guardrails = viewModel.guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
    return `
      <article class="p1-wecom-interaction-card" data-wecom-evidence="${escapeHtml(viewModel.evidenceId)}" data-execution-mode="${escapeHtml(viewModel.executionMode)}" data-drop-intent="${escapeHtml(viewModel.blockedNoop.intent)}" data-drop-allowed="${viewModel.blockedNoop.allowed ? "true" : "false"}" data-status-after-drop="${escapeHtml(viewModel.blockedNoop.statusAfterDrop)}">
        <div class="p1-wecom-interaction-card__head">
          <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
          <strong>${escapeHtml(viewModel.scenario.title)}</strong>
        </div>
        <dl class="p1-closure-fields">
          <div><dt>Execution</dt><dd>${escapeHtml(viewModel.executionMode)}</dd></div>
          <div><dt>Drop</dt><dd>${escapeHtml(viewModel.blockedNoop.intent)}</dd></div>
          <div><dt>After</dt><dd>${escapeHtml(viewModel.blockedNoop.statusAfterDrop)}</dd></div>
        </dl>
        <p>${escapeHtml(viewModel.operatorPrompt)}</p>
        <p class="p1-drag-guardrails">${guardrails}</p>
      </article>
    `;
  }).join("");
  return `
    <section class="p1-wecom-interaction-shell" aria-label="WeCom read-only interaction shell">
      <div class="p1-wecom-shell-head">
        <h2>只读交互契约</h2>
        <p>Drag handle 只是视觉占位；blocked_noop 不改变状态，也不会触发真实授权、callback、渠道写入或外呼。</p>
      </div>
      <div class="p1-wecom-interaction-grid">${rows}</div>
    </section>
  `;
}

export function renderWeComOverview(root: HTMLElement, payload: WeComOverviewPayload): void {
  const cards = payload.cards.length ? payload.cards : WECOM_P1_DEFAULT_INPUTS;
  const cardHtml = cards.map((card) => {
    const viewModel = buildWeComStatusViewModel(card);
    return renderStatusCard(viewModel.scenario, {
      dragHandle: true,
      dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
    });
  }).join("");
  root.innerHTML = `
    <section class="p1-wecom-banner" data-wecom-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 WeCom external config status slice</h2>
        <p>只读展示 WeCom Auth / Callback / Channel Entry exception；不执行授权、callback、配置写入或外呼。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--danger">BLOCKED_CONFIG_NOT_APPROVED</span>
    </section>
    ${renderEvidenceSummary(payload.evidenceSummary)}
    <section class="p1-closure-grid" aria-label="WeCom P1 status cards">
      ${cardHtml}
    </section>
    ${renderReadonlyInteractionShell(cards)}
  `;
}

function boot(): void {
  const root = document.getElementById("weComP1StatusApp");
  if (!root) return;
  renderWeComOverview(root, parsePayload());
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
}
