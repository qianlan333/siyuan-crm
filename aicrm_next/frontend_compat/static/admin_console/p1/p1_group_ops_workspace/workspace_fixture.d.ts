import { type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
export interface WorkspaceListItem {
    id: string;
    label: string;
    kind: "plan" | "group" | "node" | "execution" | "push_center" | "evidence";
    status: ScenarioEvidence["status"];
    summary: string;
    detailId: string;
    entityType: WorkspaceEntityType;
}
export type WorkspaceEntityType = "plan" | "group" | "node" | "execution" | "push_center" | "evidence";
export interface WorkspaceDetailField {
    label: string;
    value: string;
}
export interface WorkspaceDetailItem {
    id: string;
    entityType: WorkspaceEntityType;
    title: string;
    status: ScenarioEvidence["status"];
    evidenceStatus: string;
    derivedStatus: string;
    summary: string;
    guardrail: string;
    fields: WorkspaceDetailField[];
}
export interface WorkspaceSelectionState {
    selectedPlanId: string;
    selectedGroupId: string;
    selectedNodeId: string;
    selectedExecutionId: string;
    selectedPushCenterJobId: string;
    selectedEntityType: WorkspaceEntityType;
}
export interface WorkspaceFixture {
    payload: BusinessClosurePayload;
    leftRailItems: WorkspaceListItem[];
    detailItems: WorkspaceDetailItem[];
    defaultSelection: WorkspaceSelectionState;
    workspaceMode: "draft_only_preview_only";
    dataSourceLabel: string;
    dataBindingStatus: "fixture_fallback" | "real_data_bound" | "real_data_unavailable";
    realExternalCallExecuted: false;
    productionWriteExecuted: false;
}
export declare const GROUP_OPS_WORKSPACE_SCENARIOS: ScenarioEvidence[];
export declare const P1_GROUP_OPS_WORKSPACE_FIXTURE: WorkspaceFixture;
export declare function createUnavailableWorkspaceFixture(dataSourceLabel?: string): WorkspaceFixture;
