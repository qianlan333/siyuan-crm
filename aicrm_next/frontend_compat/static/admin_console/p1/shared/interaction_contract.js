import { canRenderGlobalPass } from "./status_model.js";
const BASE_GUARDRAILS = [
    "requires_push_center",
    "no_external_call",
    "no_production_write",
    "no_direct_send"
];
export function executionModeForStatus(status) {
    if (status === "external-config-blocked")
        return "external_config_blocked";
    if (status === "governance-missing")
        return "requires_approval";
    if (status === "operator-action-required" || status === "retryable")
        return "requires_approval";
    if (status === "blocked" || status === "failed-terminal")
        return "blocked";
    if (status === "downstream-pending" || status === "pending" || status === "evidence-incomplete")
        return "preview_only";
    return "readonly";
}
export function guardrailsForScenario(scenario) {
    const guardrails = new Set(BASE_GUARDRAILS);
    if (scenario.status === "external-config-blocked")
        guardrails.add("requires_external_config");
    if (scenario.status === "governance-missing") {
        guardrails.add("requires_approval");
        guardrails.add("requires_allowlist");
        guardrails.add("requires_gray_window");
    }
    if (scenario.status === "operator-action-required" || scenario.status === "retryable")
        guardrails.add("requires_approval");
    return Array.from(guardrails);
}
export function dragPreviewForScenario(scenario) {
    return {
        entity: scenario.key === "wecom_auth" ? "config_card" : "evidence_card",
        label: scenario.title,
        sourceScenario: scenario.key,
        status: scenario.status,
        executionMode: executionModeForStatus(scenario.status),
        guardrails: guardrailsForScenario(scenario)
    };
}
export function validateDropIntent(scenario, intent) {
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
export function canInteractionClaimPass90Plus(payload) {
    return canRenderGlobalPass(payload);
}
