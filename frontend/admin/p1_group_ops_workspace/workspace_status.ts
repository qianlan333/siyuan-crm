import { createDraftState, type DraftState } from "../shared/draft_state.js";
import {
  explainBlockedDrop,
  getExecutionModeForStatus,
  validateDropIntent
} from "../shared/drop_validation.js";
import {
  applyReadonlyReorderPreview,
  serializeDraftPreviewForDisplay,
  type DraftPreviewDisplay
} from "../shared/interaction_shell.js";
import { type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
import { canRenderGlobalPass, type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE, type WorkspaceFixture } from "./workspace_fixture.js";

export interface WorkspaceValidationRow {
  scenarioTitle: string;
  status: ScenarioEvidence["status"];
  executionMode: ExecutionMode;
  guardrails: InteractionGuardrail[];
  dropAllowed: boolean;
  blockedReason: string;
  statusAfterDrop: ScenarioEvidence["status"];
}

export interface WorkspaceStatusModel {
  payload: BusinessClosurePayload;
  draft: DraftState;
  preview: DraftState;
  display: DraftPreviewDisplay;
  validations: WorkspaceValidationRow[];
  originalStatuses: ScenarioEvidence["status"][];
  previewStatuses: ScenarioEvidence["status"][];
  canClaimPass90Plus: false;
  sentBypassesGovernance: boolean;
  realExternalCallExecuted: false;
  productionWriteExecuted: false;
}

export function buildGroupOpsWorkspaceStatusModel(
  fixture: WorkspaceFixture = P1_GROUP_OPS_WORKSPACE_FIXTURE
): WorkspaceStatusModel {
  const draft = createDraftState(fixture.payload.scenarios, {
    id: "p1-group-ops-workspace-draft",
    createdAt: "2026-06-24T00:00:00.000Z"
  });
  const preview = applyReadonlyReorderPreview(draft, 0, Math.min(1, draft.cards.length - 1));
  const display = serializeDraftPreviewForDisplay(preview);
  const validations = fixture.payload.scenarios.map((scenario) => {
    const result = validateDropIntent(scenario, "blocked_noop");
    return {
      scenarioTitle: scenario.title,
      status: scenario.status,
      executionMode: getExecutionModeForStatus(scenario.status),
      guardrails: result.guardrails,
      dropAllowed: result.allowed,
      blockedReason: explainBlockedDrop(result),
      statusAfterDrop: result.statusAfterDrop
    };
  });
  const originalStatuses = fixture.payload.scenarios.map((scenario) => scenario.status);
  const previewStatuses = display.cards.map((card) => card.status);
  const hasSentEvidence = fixture.payload.scenarios.some((scenario) => scenario.status === "sent");
  const hasGovernanceMissing = fixture.payload.scenarios.some((scenario) => scenario.status === "governance-missing");

  return {
    payload: fixture.payload,
    draft,
    preview,
    display,
    validations,
    originalStatuses,
    previewStatuses,
    canClaimPass90Plus: false,
    sentBypassesGovernance: hasSentEvidence && !hasGovernanceMissing,
    realExternalCallExecuted: false,
    productionWriteExecuted: false
  };
}

export function workspaceCanRenderGlobalPass(payload: BusinessClosurePayload): boolean {
  return canRenderGlobalPass(payload);
}
