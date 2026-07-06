import { type BusinessClosurePayload, type EvidenceStatus, type ScenarioEvidence, canRenderGlobalPass } from "./status_model.js";

export type DragEntity =
  | "audience_segment"
  | "message_block"
  | "automation_node"
  | "condition_node"
  | "broadcast_job"
  | "push_center_projection"
  | "evidence_card"
  | "config_card";

export type DropIntent =
  | "reorder"
  | "group"
  | "connect"
  | "preview"
  | "draft_update"
  | "blocked_noop";

export type ExecutionMode =
  | "readonly"
  | "draft_only"
  | "preview_only"
  | "requires_approval"
  | "blocked"
  | "external_config_blocked";

export type InteractionGuardrail =
  | "requires_push_center"
  | "requires_approval"
  | "requires_allowlist"
  | "requires_gray_window"
  | "requires_external_config"
  | "no_external_call"
  | "no_production_write"
  | "no_direct_send";

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

const BASE_GUARDRAILS: InteractionGuardrail[] = [
  "requires_push_center",
  "no_external_call",
  "no_production_write",
  "no_direct_send"
];

export function executionModeForStatus(status: EvidenceStatus): ExecutionMode {
  if (status === "external-config-blocked") return "external_config_blocked";
  if (status === "governance-missing") return "requires_approval";
  if (status === "operator-action-required" || status === "retryable") return "requires_approval";
  if (status === "blocked" || status === "failed-terminal") return "blocked";
  if (status === "downstream-pending" || status === "pending" || status === "evidence-incomplete") return "preview_only";
  return "readonly";
}

export function guardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[] {
  const guardrails = new Set<InteractionGuardrail>(BASE_GUARDRAILS);
  if (scenario.status === "external-config-blocked") guardrails.add("requires_external_config");
  if (scenario.status === "governance-missing") {
    guardrails.add("requires_approval");
    guardrails.add("requires_allowlist");
    guardrails.add("requires_gray_window");
  }
  if (scenario.status === "operator-action-required" || scenario.status === "retryable") guardrails.add("requires_approval");
  return Array.from(guardrails);
}

export function dragPreviewForScenario(scenario: ScenarioEvidence): DragPreviewState {
  return {
    entity: scenario.key === "wecom_auth" ? "config_card" : "evidence_card",
    label: scenario.title,
    sourceScenario: scenario.key,
    status: scenario.status,
    executionMode: executionModeForStatus(scenario.status),
    guardrails: guardrailsForScenario(scenario)
  };
}

export function validateDropIntent(scenario: ScenarioEvidence, intent: DropIntent): DropValidationResult {
  const executionMode = executionModeForStatus(scenario.status);
  const guardrails = guardrailsForScenario(scenario);
  if (intent === "blocked_noop") {
    return {
      intent,
      allowed: false,
      executionMode,
      guardrails,
      reason: "Blocked noop never mutates evidence status.",
      statusAfterDrop: scenario.status
    };
  }
  if (executionMode === "readonly" && intent === "preview") {
    return {
      intent,
      allowed: true,
      executionMode,
      guardrails,
      reason: "Readonly preview is allowed and cannot execute external effects.",
      statusAfterDrop: scenario.status
    };
  }
  return {
    intent,
    allowed: false,
    executionMode,
    guardrails,
    reason: "Drop is blocked until required guardrails are satisfied.",
    statusAfterDrop: scenario.status
  };
}

export function canInteractionClaimPass90Plus(payload: BusinessClosurePayload): boolean {
  return canRenderGlobalPass(payload);
}
