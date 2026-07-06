import { dragPreviewForScenario } from "./interaction_contract.js";
import { getExecutionModeForStatus } from "./drop_validation.js";
function draftCardId(scenario, index) {
    return `${scenario.key}:${index}`;
}
export function createDraftState(scenarios, options = {}) {
    return {
        id: options.id ?? "p1-interaction-shell-draft",
        createdAt: options.createdAt ?? new Date(0).toISOString(),
        persistence: "memory_only",
        cards: scenarios.map((scenario, index) => {
            const preview = dragPreviewForScenario(scenario);
            return {
                id: draftCardId(scenario, index),
                scenarioKey: scenario.key,
                title: scenario.title,
                originalIndex: index,
                draftIndex: index,
                status: scenario.status,
                evidenceStatus: scenario.evidenceStatus,
                derivedStatus: scenario.derivedStatus,
                executionMode: getExecutionModeForStatus(scenario.status),
                guardrails: preview.guardrails,
                mutatedEvidenceStatus: false
            };
        }),
        realExternalCallExecuted: false,
        productionWriteExecuted: false,
        canClaimPass90Plus: false
    };
}
