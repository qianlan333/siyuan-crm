import { escapeHtml } from "./dom.js";
import { createDraftState, type DraftState } from "./draft_state.js";
import { validateDropIntent, explainBlockedDrop } from "./drop_validation.js";
import { type BusinessClosurePayload, type ScenarioEvidence } from "./status_model.js";

export interface DraftPreviewCardDisplay {
  id: string;
  title: string;
  originalIndex: number;
  draftIndex: number;
  status: ScenarioEvidence["status"];
  executionMode: string;
  guardrails: string[];
  mutatedEvidenceStatus: false;
}

export interface DraftPreviewDisplay {
  id: string;
  persistence: "memory_only";
  cards: DraftPreviewCardDisplay[];
  realExternalCallExecuted: false;
  productionWriteExecuted: false;
  canClaimPass90Plus: false;
}

export interface InteractionShellOptions {
  id?: string;
  title?: string;
  description?: string;
  createdAt?: string;
}

function normalizeIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  if (index < 0) return 0;
  if (index >= length) return length - 1;
  return index;
}

export function applyReadonlyReorderPreview(state: DraftState, fromIndex: number, toIndex: number): DraftState {
  const from = normalizeIndex(fromIndex, state.cards.length);
  const to = normalizeIndex(toIndex, state.cards.length);
  const reordered = state.cards.map((card) => ({ ...card }));
  const [moved] = reordered.splice(from, 1);
  if (moved) reordered.splice(to, 0, moved);
  return {
    ...state,
    cards: reordered.map((card, draftIndex) => ({
      ...card,
      draftIndex,
      mutatedEvidenceStatus: false
    })),
    realExternalCallExecuted: false,
    productionWriteExecuted: false,
    canClaimPass90Plus: false
  };
}

export function serializeDraftPreviewForDisplay(state: DraftState): DraftPreviewDisplay {
  return {
    id: state.id,
    persistence: state.persistence,
    cards: state.cards.map((card) => ({
      id: card.id,
      title: card.title,
      originalIndex: card.originalIndex,
      draftIndex: card.draftIndex,
      status: card.status,
      executionMode: card.executionMode,
      guardrails: card.guardrails,
      mutatedEvidenceStatus: false
    })),
    realExternalCallExecuted: false,
    productionWriteExecuted: false,
    canClaimPass90Plus: false
  };
}

function renderGuardrails(guardrails: string[]): string {
  return guardrails.map((guardrail) => `<code>${escapeHtml(guardrail)}</code>`).join(" ");
}

export function renderInteractionShell(payload: BusinessClosurePayload, options: InteractionShellOptions = {}): string {
  const draft = createDraftState(payload.scenarios, {
    id: options.id ?? "p1-draft-preview",
    createdAt: options.createdAt ?? "2026-06-23T00:00:00.000Z"
  });
  const preview = applyReadonlyReorderPreview(draft, 0, Math.min(1, draft.cards.length - 1));
  const display = serializeDraftPreviewForDisplay(preview);
  const scenarioByCardId = new Map(draft.cards.map((card) => [card.id, payload.scenarios[card.originalIndex]]));
  const rows = display.cards.map((card) => {
    const scenario = scenarioByCardId.get(card.id);
    const blockedDrop = scenario
      ? validateDropIntent(scenario, "blocked_noop")
      : null;
    const reason = blockedDrop ? explainBlockedDrop(blockedDrop) : "Preview card has no scenario binding.";
    return `
      <article class="p1-draft-shell-card" data-draft-card="${escapeHtml(card.id)}" data-execution-mode="${escapeHtml(card.executionMode)}" data-evidence-status="${escapeHtml(card.status)}" data-mutated-evidence-status="${card.mutatedEvidenceStatus ? "true" : "false"}" data-drop-intent="${blockedDrop ? escapeHtml(blockedDrop.intent) : "preview"}" data-drop-allowed="${blockedDrop?.allowed ? "true" : "false"}" data-status-after-drop="${blockedDrop ? escapeHtml(blockedDrop.statusAfterDrop) : escapeHtml(card.status)}">
        <div class="p1-draft-shell-card__head">
          <span class="p1-drag-handle" aria-hidden="true">⋮⋮</span>
          <strong>${escapeHtml(card.title)}</strong>
        </div>
        <dl class="p1-closure-fields">
          <div><dt>Original</dt><dd>${card.originalIndex + 1}</dd></div>
          <div><dt>Preview</dt><dd>${card.draftIndex + 1}</dd></div>
          <div><dt>Execution</dt><dd>${escapeHtml(card.executionMode)}</dd></div>
        </dl>
        <p>${escapeHtml(reason)}</p>
        <p class="p1-drag-guardrails">${renderGuardrails(card.guardrails)}</p>
      </article>
    `;
  }).join("");

  return `
    <section class="p1-draft-shell" aria-label="Draft-only preview interaction shell" data-persistence="${escapeHtml(display.persistence)}" data-real-external-call-executed="false" data-production-write-executed="false" data-can-claim-pass90="false">
      <div class="p1-draft-shell__head">
        <h2>${escapeHtml(options.title ?? "Draft-only / preview-only interaction shell")}</h2>
        <p>${escapeHtml(options.description ?? "前端内存预览：重排只改变本地 preview 顺序，刷新后丢弃，不保存、不执行、不生成 PASS_90_PLUS。")}</p>
      </div>
      <div class="p1-draft-shell__grid">${rows}</div>
    </section>
  `;
}
