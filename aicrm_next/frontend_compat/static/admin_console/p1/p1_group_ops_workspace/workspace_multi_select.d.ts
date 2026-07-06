import { type WorkspaceViewState } from "./workspace_view_state.js";
import { type WorkspaceEntityType, type WorkspaceListItem } from "./workspace_fixture.js";
export declare function isEntityMultiSelected(viewState: WorkspaceViewState, entityType: WorkspaceEntityType, detailId: string): boolean;
export declare function countMultiSelected(viewState: WorkspaceViewState): number;
export declare function toggleMultiSelectedEntity(viewState: WorkspaceViewState, entityType: WorkspaceEntityType, detailId: string): WorkspaceViewState;
export declare function clearMultiSelection(viewState: WorkspaceViewState): WorkspaceViewState;
export declare function selectVisibleItems(viewState: WorkspaceViewState, items: WorkspaceListItem[]): WorkspaceViewState;
export declare function selectVisibleLaneItems(viewState: WorkspaceViewState, items: WorkspaceListItem[], entityType: WorkspaceEntityType): WorkspaceViewState;
