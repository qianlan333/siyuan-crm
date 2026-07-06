import { escapeHtml } from "./dom.js";
import { renderGuardrailNotice } from "./guardrail_notice.js";
import { renderStatusBadge } from "./status_badge.js";
import { type ScenarioEvidence, statusMeta } from "./status_model.js";

export interface StatusCardOptions {
  dragHandle?: boolean;
  dragDisabledReason?: string;
}

export function renderStatusCard(scenario: ScenarioEvidence, options: StatusCardOptions = {}): string {
  const meta = statusMeta(scenario.status);
  const dragHandle = options.dragHandle
    ? `<span class="p1-drag-handle" aria-hidden="true" data-drag-handle="readonly">⋮⋮</span>`
    : "";
  const disabledReason = options.dragDisabledReason
    ? `<div class="p1-drag-disabled-reason">${escapeHtml(options.dragDisabledReason)}</div>`
    : "";
  return `
    <article class="p1-closure-card p1-closure-card--${meta.tone}" data-scenario="${escapeHtml(scenario.key)}" data-status="${escapeHtml(scenario.status)}" data-drag-ready="${options.dragHandle ? "readonly" : "none"}">
      <div class="p1-closure-card__head">
        <div class="p1-closure-title-row">${dragHandle}<h2>${escapeHtml(scenario.title)}</h2></div>
        ${renderStatusBadge(scenario.status)}
      </div>
      <dl class="p1-closure-fields">
        <div><dt>Evidence</dt><dd>${escapeHtml(scenario.evidenceStatus)}</dd></div>
        <div><dt>Derived</dt><dd>${escapeHtml(scenario.derivedStatus)}</dd></div>
        <div><dt>Completion</dt><dd>${meta.isSuccessComplete ? "complete" : "incomplete"}</dd></div>
      </dl>
      <p>${escapeHtml(scenario.summary)}</p>
      ${renderGuardrailNotice(scenario)}
      ${disabledReason}
    </article>
  `;
}
