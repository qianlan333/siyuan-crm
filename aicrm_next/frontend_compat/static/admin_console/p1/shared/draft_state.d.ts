import { type ScenarioEvidence } from "./status_model.js";
import { type ExecutionMode, type InteractionGuardrail } from "./interaction_contract.js";
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
export declare function createDraftState(scenarios: ScenarioEvidence[], options?: DraftStateOptions): DraftState;
