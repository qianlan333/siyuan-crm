import { type EvidenceStatus, type ScenarioEvidence } from "../shared/status_model.js";
import { type DropValidationResult, type DragPreviewState, type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
export interface GroupOpsStatusInput {
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
export interface GroupOpsStatusViewModel {
    scenario: ScenarioEvidence;
    evidenceId: string;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    preview: DragPreviewState;
    blockedNoop: DropValidationResult;
    isSuccessComplete: boolean;
    operatorPrompt: string;
}
export declare function normalizeGroupOpsStatus(rawStatus: string, options?: {
    retryable?: boolean;
    operatorActionRequired?: boolean;
}): EvidenceStatus;
export declare function toGroupOpsScenario(input: GroupOpsStatusInput): ScenarioEvidence;
export declare function buildGroupOpsStatusViewModel(input: GroupOpsStatusInput): GroupOpsStatusViewModel;
export declare function groupOpsGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[];
export declare function groupOpsPromptForStatus(status: EvidenceStatus): string;
export declare function groupOpsSentIsGovernanceComplete(input: GroupOpsStatusInput): boolean;
export declare function readonlyGroupOpsDropDoesNotMutate(input: GroupOpsStatusInput): boolean;
export declare const GROUP_OPS_P1_DEFAULT_INPUTS: GroupOpsStatusInput[];
export declare function defaultGroupOpsViewModels(): GroupOpsStatusViewModel[];
