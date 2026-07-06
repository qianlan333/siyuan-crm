import { type BusinessClosurePayload, type EvidenceStatus, type ScenarioEvidence } from "./status_model.js";
export type DragEntity = "audience_segment" | "message_block" | "automation_node" | "condition_node" | "broadcast_job" | "push_center_projection" | "evidence_card" | "config_card";
export type DropIntent = "reorder" | "group" | "connect" | "preview" | "draft_update" | "blocked_noop";
export type ExecutionMode = "readonly" | "draft_only" | "preview_only" | "requires_approval" | "blocked" | "external_config_blocked";
export type InteractionGuardrail = "requires_push_center" | "requires_approval" | "requires_allowlist" | "requires_gray_window" | "requires_external_config" | "no_external_call" | "no_production_write" | "no_direct_send";
export interface DragPreviewState {
    entity: DragEntity;
    label: string;
    sourceScenario?: string;
    status: EvidenceStatus;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
}
export interface DropValidationResult {
    intent: DropIntent;
    allowed: boolean;
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    reason: string;
    statusAfterDrop: EvidenceStatus;
}
export declare function executionModeForStatus(status: EvidenceStatus): ExecutionMode;
export declare function guardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[];
export declare function dragPreviewForScenario(scenario: ScenarioEvidence): DragPreviewState;
export declare function validateDropIntent(scenario: ScenarioEvidence, intent: DropIntent): DropValidationResult;
export declare function canInteractionClaimPass90Plus(payload: BusinessClosurePayload): boolean;
