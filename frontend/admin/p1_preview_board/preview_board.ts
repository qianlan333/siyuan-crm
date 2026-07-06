import { escapeHtml } from "../shared/dom.js";
import { createDraftState } from "../shared/draft_state.js";
import { explainBlockedDrop, getExecutionModeForStatus, validateDropIntent } from "../shared/drop_validation.js";
import {
  applyReadonlyReorderPreview,
  renderInteractionShell,
  serializeDraftPreviewForDisplay
} from "../shared/interaction_shell.js";
import { renderStatusCard } from "../shared/status_card.js";
import { canRenderGlobalPass, type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
import { P1_PREVIEW_BOARD_FIXTURE, type PreviewBoardFixture } from "./preview_board_fixture.js";

export interface PreviewBoardValidationRow {
  title: string;
  status: ScenarioEvidence["status"];
  executionMode: string;
  blockedReason: string;
  statusAfterDrop: ScenarioEvidence["status"];
}

export interface PreviewBoardModel {
  fixture: PreviewBoardFixture;
  originalStatuses: ScenarioEvidence["status"][];
  previewStatuses: ScenarioEvidence["status"][];
  validationRows: PreviewBoardValidationRow[];
  canRenderGlobalPass90Plus: false;
}

export function buildPreviewBoardModel(payload: BusinessClosurePayload = P1_PREVIEW_BOARD_FIXTURE.payload): PreviewBoardModel {
  const draft = createDraftState(payload.scenarios, {
    id: "p1-cross-page-preview-board",
    createdAt: "2026-06-24T00:00:00.000Z"
  });
  const preview = applyReadonlyReorderPreview(draft, 0, Math.min(2, draft.cards.length - 1));
  const display = serializeDraftPreviewForDisplay(preview);
  const scenarioByCardId = new Map(draft.cards.map((card) => [card.id, payload.scenarios[card.originalIndex]]));
  const validationRows = display.cards.map((card) => {
    const scenario = scenarioByCardId.get(card.id);
    if (!scenario) {
      return {
        title: card.title,
        status: card.status,
        executionMode: card.executionMode,
        blockedReason: "Preview card has no scenario binding.",
        statusAfterDrop: card.status
      };
    }
    const blockedDrop = validateDropIntent(scenario, "blocked_noop");
    return {
      title: scenario.title,
      status: scenario.status,
      executionMode: getExecutionModeForStatus(scenario.status),
      blockedReason: explainBlockedDrop(blockedDrop),
      statusAfterDrop: blockedDrop.statusAfterDrop
    };
  });

  return {
    fixture: {
      ...P1_PREVIEW_BOARD_FIXTURE,
      payload
    },
    originalStatuses: payload.scenarios.map((scenario) => scenario.status),
    previewStatuses: display.cards.map((card) => card.status),
    validationRows,
    canRenderGlobalPass90Plus: false
  };
}

function yesNo(value: boolean): string {
  return value ? "true" : "false";
}

function renderSummary(summary: PreviewBoardFixture["summary"]): string {
  return `
    <dl class="p1-preview-board-summary" aria-label="P1 preview board summary" data-can-claim-pass90="${yesNo(summary.canClaimPass90Plus)}" data-preview-only="${yesNo(summary.previewOnly)}" data-production-write-executed="${yesNo(summary.productionWriteExecuted)}" data-real-external-call-executed="${yesNo(summary.realExternalCallExecuted)}">
      <div><dt>Global verdict</dt><dd>${escapeHtml(summary.globalVerdict)}</dd></div>
      <div><dt>PASS_90_PLUS</dt><dd>${yesNo(summary.canClaimPass90Plus)}</dd></div>
      <div><dt>Preview only</dt><dd>${yesNo(summary.previewOnly)}</dd></div>
      <div><dt>Production write</dt><dd>${yesNo(summary.productionWriteExecuted)}</dd></div>
      <div><dt>External call</dt><dd>${yesNo(summary.realExternalCallExecuted)}</dd></div>
    </dl>
  `;
}

function renderValidationRows(rows: PreviewBoardValidationRow[]): string {
  return rows.map((row) => `
    <article class="p1-preview-board-validation" data-preview-validation="${escapeHtml(row.title)}" data-execution-mode="${escapeHtml(row.executionMode)}" data-status-after-drop="${escapeHtml(row.statusAfterDrop)}">
      <strong>${escapeHtml(row.title)}</strong>
      <span>${escapeHtml(row.executionMode)}</span>
      <p>${escapeHtml(row.blockedReason)}</p>
    </article>
  `).join("");
}

export function renderP1PreviewBoard(fixture: PreviewBoardFixture = P1_PREVIEW_BOARD_FIXTURE): string {
  const globalPass = canRenderGlobalPass(fixture.payload);
  const model = buildPreviewBoardModel(fixture.payload);
  return `
    <section class="p1-preview-board" aria-label="P1 cross-page preview board" data-board="p1-cross-page-preview" data-global-verdict="${escapeHtml(fixture.summary.globalVerdict)}" data-can-claim-pass90="${globalPass ? "true" : "false"}" data-real-external-call-executed="false" data-production-write-executed="false">
      <div class="p1-preview-board__head">
        <div>
          <h2>P1 Preview Board</h2>
          <p>跨页面 fixture-driven 预览：只展示脱敏 evidence 状态、只做前端内存 preview，不保存、不执行、不生成 PASS_90_PLUS。</p>
        </div>
        <span class="p1-closure-pill p1-closure-pill--warning">P1_READY_WITH_EXCEPTIONS</span>
      </div>
      ${renderSummary(fixture.summary)}
      <section class="p1-preview-board__grid" aria-label="Cross-page evidence cards">
        ${fixture.payload.scenarios.map((scenario) => renderStatusCard(scenario, {
          dragHandle: true,
          dragDisabledReason: "Fixture preview only: drag-ready shell is not connected to backend writes or execution."
        })).join("")}
      </section>
      <section class="p1-preview-board__validations" aria-label="Blocked drop validation">
        ${renderValidationRows(model.validationRows)}
      </section>
      ${renderInteractionShell(fixture.payload, {
        id: "p1-cross-page-preview-board",
        title: "Cross-page preview interaction shell",
        description: "复用 shared interaction shell；blocked_noop 和 readonly reorder preview 不改变 evidence status，不触发外部效果，不写生产。"
      })}
    </section>
  `;
}
