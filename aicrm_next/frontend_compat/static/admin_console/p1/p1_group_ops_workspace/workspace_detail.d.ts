import { type WorkspaceDetailItem, type WorkspaceEntityType, type WorkspaceFixture, type WorkspaceSelectionState } from "./workspace_fixture.js";
export declare function createWorkspaceSelectionState(fixture: WorkspaceFixture): WorkspaceSelectionState;
export declare function selectedDetailId(selection: WorkspaceSelectionState): string;
export declare function findWorkspaceDetail(fixture: WorkspaceFixture, selection: WorkspaceSelectionState): WorkspaceDetailItem;
export declare function selectWorkspaceEntity(current: WorkspaceSelectionState, entityType: WorkspaceEntityType, detailId: string): WorkspaceSelectionState;
export declare function renderWorkspaceDetailPanel(fixture: WorkspaceFixture, selection: WorkspaceSelectionState): string;
export declare function renderWorkspaceSelectedPreviewResult(fixture: WorkspaceFixture, selection: WorkspaceSelectionState): string;
