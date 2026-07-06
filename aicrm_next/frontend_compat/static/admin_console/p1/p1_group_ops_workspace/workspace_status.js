import { createDraftState } from "../shared/draft_state.js";
import { explainBlockedDrop, getExecutionModeForStatus, validateDropIntent } from "../shared/drop_validation.js";
import { applyReadonlyReorderPreview, serializeDraftPreviewForDisplay } from "../shared/interaction_shell.js";
import { canRenderGlobalPass } from "../shared/status_model.js";
import { P1_GROUP_OPS_WORKSPACE_FIXTURE } from "./workspace_fixture.js";
export function buildGroupOpsWorkspaceStatusModel(fixture = P1_GROUP_OPS_WORKSPACE_FIXTURE) {
    const draft = createDraftState(fixture.payload.scenarios, {
        id: "p1-group-ops-workspace-draft",
        createdAt: "2026-06-24T00:00:00.000Z"
    });
    const preview = applyReadonlyReorderPreview(draft, 0, Math.min(1, draft.cards.length - 1));
    const display = serializeDraftPreviewForDisplay(preview);
    const validations = fixture.payload.scenarios.map((scenario) => {
        const result = validateDropIntent(scenario, "blocked_noop");
        return {
            scenarioTitle: scenario.title,
            status: scenario.status,
            executionMode: getExecutionModeForStatus(scenario.status),
            guardrails: result.guardrails,
            dropAllowed: result.allowed,
            blockedReason: explainBlockedDrop(result),
            statusAfterDrop: result.statusAfterDrop
        };
    });
    const originalStatuses = fixture.payload.scenarios.map((scenario) => scenario.status);
    const previewStatuses = display.cards.map((card) => card.status);
    const hasSentEvidence = fixture.payload.scenarios.some((scenario) => scenario.status === "sent");
    const hasGovernanceMissing = fixture.payload.scenarios.some((scenario) => scenario.status === "governance-missing");
    return {
        payload: fixture.payload,
        draft,
        preview,
        display,
        validations,
        originalStatuses,
        previewStatuses,
        canClaimPass90Plus: false,
        sentBypassesGovernance: hasSentEvidence && !hasGovernanceMissing,
        realExternalCallExecuted: false,
        productionWriteExecuted: false
    };
}
export function workspaceCanRenderGlobalPass(payload) {
    return canRenderGlobalPass(payload);
}
