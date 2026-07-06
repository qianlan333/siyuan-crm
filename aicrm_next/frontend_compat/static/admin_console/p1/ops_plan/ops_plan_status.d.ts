import { type EvidenceStatus, type ScenarioEvidence } from "../shared/status_model.js";
import { type DropValidationResult, type DragPreviewState, type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
export interface OpsPlanStatusInput {
    title: string;
    rawStatus: string;
    evidenceStatus: string;
    derivedStatus: string;
    summary: string;
    guardrail: string;
    evidenceId?: string;
    route?: string;
    retryable?: boolean;
    operatorActionRequired?: boolean;
}
export interface OpsPlanStatusViewModel {
    scenario: ScenarioEvidence;
    evidenceId: string;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    preview: DragPreviewState;
    blockedNoop: DropValidationResult;
    isSuccessComplete: boolean;
    operatorPrompt: string;
}
export declare function normalizeOpsPlanStatus(rawStatus: string, options?: {
    retryable?: boolean;
    operatorActionRequired?: boolean;
}): EvidenceStatus;
export declare function toOpsPlanScenario(input: OpsPlanStatusInput): ScenarioEvidence;
export declare function opsPlanGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[];
export declare function buildOpsPlanStatusViewModel(input: OpsPlanStatusInput): OpsPlanStatusViewModel;
export declare function opsPlanPromptForStatus(status: EvidenceStatus): string;
export declare function pushCenterPendingIsSent(input: OpsPlanStatusInput): boolean;
export declare function broadcastJobCreatedIsExternalEffectSent(input: OpsPlanStatusInput): boolean;
export declare function readonlyOpsPlanDropDoesNotMutate(input: OpsPlanStatusInput): boolean;
export declare const OPS_PLAN_P1_DEFAULT_INPUTS: OpsPlanStatusInput[];
export declare function defaultOpsPlanViewModels(): OpsPlanStatusViewModel[];
