import { type EvidenceStatus, type ScenarioEvidence } from "../shared/status_model.js";
import { type DropValidationResult, type DragPreviewState, type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
export type PushCenterScenarioKey = "group_ops" | "ops_plan_broadcast" | "wecom_auth" | "external_orders";
export interface PushCenterStatusInput {
    key: PushCenterScenarioKey;
    title: string;
    rawStatus: string;
    evidenceStatus: string;
    derivedStatus: string;
    summary: string;
    guardrail: string;
    route?: string;
    retryable?: boolean;
    operatorActionRequired?: boolean;
}
export interface PushCenterStatusViewModel {
    scenario: ScenarioEvidence;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    preview: DragPreviewState;
    blockedNoop: DropValidationResult;
    isSuccessComplete: boolean;
    operatorPrompt: string;
}
export declare function normalizePushCenterStatus(rawStatus: string, options?: {
    retryable?: boolean;
    operatorActionRequired?: boolean;
}): EvidenceStatus;
export declare function toPushCenterScenario(input: PushCenterStatusInput): ScenarioEvidence;
export declare function buildPushCenterStatusViewModel(input: PushCenterStatusInput): PushCenterStatusViewModel;
export declare function operatorPromptForStatus(status: EvidenceStatus): string;
export declare function readonlyDropDoesNotMutate(input: PushCenterStatusInput): boolean;
export declare const PUSH_CENTER_P1_DEFAULT_INPUTS: PushCenterStatusInput[];
export declare function defaultPushCenterViewModels(): PushCenterStatusViewModel[];
