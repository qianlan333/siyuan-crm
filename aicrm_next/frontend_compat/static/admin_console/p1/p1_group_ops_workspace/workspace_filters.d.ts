import { type WorkspaceDetailItem, type WorkspaceEntityType, type WorkspaceFixture, type WorkspaceListItem } from "./workspace_fixture.js";
import { type WorkspaceFilterValue, type WorkspaceViewState } from "./workspace_view_state.js";
export interface FilteredWorkspaceView {
    visibleLeftRailItems: WorkspaceListItem[];
    visibleDetailItems: WorkspaceDetailItem[];
    viewState: WorkspaceViewState;
    emptyReason: string;
    isEmpty: boolean;
    dataState: "ready" | "real_data_unavailable" | "partial_data";
    resultSummary: string;
}
export declare const STATUS_FILTER_OPTIONS: WorkspaceFilterValue[];
export declare const ENTITY_FILTER_OPTIONS: Array<"all" | WorkspaceEntityType>;
export declare function filterWorkspaceView(fixture: WorkspaceFixture, viewState: WorkspaceViewState): FilteredWorkspaceView;
