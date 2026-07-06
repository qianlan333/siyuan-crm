import {
  executionModeForStatus,
  guardrailsForScenario,
  validateDropIntent as validateContractDropIntent,
  type DropIntent,
  type DropValidationResult,
  type ExecutionMode
} from "./interaction_contract.js";
import { type EvidenceStatus, type ScenarioEvidence } from "./status_model.js";

export function getExecutionModeForStatus(status: EvidenceStatus): ExecutionMode {
  if (status === "ready") return "draft_only";
  if (status === "retryable") return "preview_only";
  if (status === "downstream-pending" || status === "pending" || status === "evidence-incomplete") return "preview_only";
  return executionModeForStatus(status);
}

export function validateDropIntent(scenario: ScenarioEvidence, intent: DropIntent): DropValidationResult {
  const executionMode = getExecutionModeForStatus(scenario.status);
  const guardrails = guardrailsForScenario(scenario);

  if (intent === "blocked_noop") {
    return {
      ...validateContractDropIntent(scenario, intent),
      executionMode,
      reason: "blocked_noop is a visible no-op; evidence status and production state are unchanged."
    };
  }

  if (executionMode === "external_config_blocked") {
    return {
      intent,
      allowed: false,
      executionMode,
      guardrails,
      reason: "External configuration is blocked; this card cannot enter draft-only execution.",
      statusAfterDrop: scenario.status
    };
  }

  if (executionMode === "blocked" || executionMode === "requires_approval") {
    return {
      intent,
      allowed: false,
      executionMode,
      guardrails,
      reason: "Interaction is blocked until approval, allowlist, gray-window, or terminal-state review is complete.",
      statusAfterDrop: scenario.status
    };
  }

  if (intent === "draft_update" && executionMode === "draft_only") {
    return {
      intent,
      allowed: true,
      executionMode,
      guardrails,
      reason: "Memory-only draft update is allowed; no backend write or external effect is executed.",
      statusAfterDrop: scenario.status
    };
  }

  if (intent === "preview" || intent === "reorder") {
    return {
      intent,
      allowed: true,
      executionMode,
      guardrails,
      reason: "Read-only preview is allowed and cannot mutate evidence state.",
      statusAfterDrop: scenario.status
    };
  }

  return {
    intent,
    allowed: false,
    executionMode,
    guardrails,
    reason: "Drop intent is outside the P1 preview-only shell.",
    statusAfterDrop: scenario.status
  };
}

export function explainBlockedDrop(result: DropValidationResult): string {
  if (result.allowed) return "Allowed preview only; no production write or external call.";
  return result.reason;
}
