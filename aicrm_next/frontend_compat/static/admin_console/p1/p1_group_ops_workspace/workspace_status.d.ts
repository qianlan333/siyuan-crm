import { type DraftState } from "../shared/draft_state.js";
import { type DraftPreviewDisplay } from "../shared/interaction_shell.js";
import { type ExecutionMode, type InteractionGuardrail } from "../shared/interaction_contract.js";
import { type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
import { type WorkspaceFixture } from "./workspace_fixture.js";
export interface WorkspaceValidationRow {
    scenarioTitle: string;
    status: ScenarioEvidence["status"];
    executionMode: ExecutionMode;
    guardrails: InteractionGuardrail[];
    dropAllowed: boolean;
    blockedReason: string;
    statusAfterDrop: ScenarioEvidence["status"];
}
export interface WorkspaceStatusModel {
    payload: BusinessClosurePayload;
    draft: DraftState;
    preview: DraftState;
    display: DraftPreviewDisplay;
    validations: WorkspaceValidationRow[];
    originalStatuses: ScenarioEvidence["status"][];
    previewStatuses: ScenarioEvidence["status"][];
    canClaimPass90Plus: false;
    sentBypassesGovernance: boolean;
    realExternalCallExecuted: false;
    productionWriteExecuted: false;
}
export declare function buildGroupOpsWorkspaceStatusModel(fixture?: WorkspaceFixture): WorkspaceStatusModel;
export declare function workspaceCanRenderGlobalPass(payload: BusinessClosurePayload): boolean;
