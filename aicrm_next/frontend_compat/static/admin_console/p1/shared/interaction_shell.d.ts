import { type DraftState } from "./draft_state.js";
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
export declare function applyReadonlyReorderPreview(state: DraftState, fromIndex: number, toIndex: number): DraftState;
export declare function serializeDraftPreviewForDisplay(state: DraftState): DraftPreviewDisplay;
export declare function renderInteractionShell(payload: BusinessClosurePayload, options?: InteractionShellOptions): string;
