import { type EvidenceStatus, type ScenarioEvidence } from "../shared/status_model.js";
import { type DropValidationResult, type DragPreviewState, type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
export interface WeComStatusInput {
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
export interface WeComStatusViewModel {
    scenario: ScenarioEvidence;
    evidenceId: string;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    preview: DragPreviewState;
    blockedNoop: DropValidationResult;
    isSuccessComplete: boolean;
    operatorPrompt: string;
}
export declare function normalizeWeComStatus(rawStatus: string, options?: {
    retryable?: boolean;
    operatorActionRequired?: boolean;
}): EvidenceStatus;
export declare function toWeComScenario(input: WeComStatusInput): ScenarioEvidence;
export declare function weComGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[];
export declare function buildWeComStatusViewModel(input: WeComStatusInput): WeComStatusViewModel;
export declare function weComPromptForStatus(status: EvidenceStatus): string;
export declare function externalConfigBlockedIsAuthorized(input: WeComStatusInput): boolean;
export declare function callbackFailClosedIsSuccess(input: WeComStatusInput): boolean;
export declare function missingSignatureIsVerified(input: WeComStatusInput): boolean;
export declare function missingWeComEvidenceIsComplete(input: WeComStatusInput): boolean;
export declare function readonlyWeComDropDoesNotMutate(input: WeComStatusInput): boolean;
export declare const WECOM_P1_DEFAULT_INPUTS: WeComStatusInput[];
export declare function defaultWeComViewModels(): WeComStatusViewModel[];
