import { type ScenarioEvidence } from "./status_model.js";
import { dragPreviewForScenario, type ExecutionMode, type InteractionGuardrail } from "./interaction_contract.js";
import { getExecutionModeForStatus } from "./drop_validation.js";

export interface DraftCardState {
  id: string;
  scenarioKey: string;
  title: string;
  originalIndex: number;
  draftIndex: number;
  status: ScenarioEvidence["status"];
  evidenceStatus: string;
  derivedStatus: string;
  executionMode: ExecutionMode;
  guardrails: InteractionGuardrail[];
  mutatedEvidenceStatus: false;
}

export interface DraftState {
  id: string;
  createdAt: string;
  persistence: "memory_only";
  cards: DraftCardState[];
  realExternalCallExecuted: false;
  productionWriteExecuted: false;
  canClaimPass90Plus: false;
}

export interface DraftStateOptions {
  id?: string;
  createdAt?: string;
}

function draftCardId(scenario: ScenarioEvidence, index: number): string {
  return `${scenario.key}:${index}`;
}

export function createDraftState(scenarios: ScenarioEvidence[], options: DraftStateOptions = {}): DraftState {
  return {
    id: options.id ?? "p1-interaction-shell-draft",
    createdAt: options.createdAt ?? new Date(0).toISOString(),
    persistence: "memory_only",
    cards: scenarios.map((scenario, index) => {
      const preview = dragPreviewForScenario(scenario);
      return {
        id: draftCardId(scenario, index),
        scenarioKey: scenario.key,
        title: scenario.title,
        originalIndex: index,
        draftIndex: index,
        status: scenario.status,
        evidenceStatus: scenario.evidenceStatus,
        derivedStatus: scenario.derivedStatus,
        executionMode: getExecutionModeForStatus(scenario.status),
        guardrails: preview.guardrails,
        mutatedEvidenceStatus: false
      };
    }),
    realExternalCallExecuted: false,
    productionWriteExecuted: false,
    canClaimPass90Plus: false
  };
}
