import { type DropIntent, type DropValidationResult, type ExecutionMode } from "./interaction_contract.js";
import { type EvidenceStatus, type ScenarioEvidence } from "./status_model.js";
export declare function getExecutionModeForStatus(status: EvidenceStatus): ExecutionMode;
export declare function validateDropIntent(scenario: ScenarioEvidence, intent: DropIntent): DropValidationResult;
export declare function explainBlockedDrop(result: DropValidationResult): string;
