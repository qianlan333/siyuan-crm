import { type EvidenceStatus } from "../shared/status_model.js";
import { type FilteredWorkspaceView } from "./workspace_filters.js";
import { type WorkspaceEntityType, type WorkspaceFixture } from "./workspace_fixture.js";
import { type WorkspaceCanvasLaneId, type WorkspaceViewState } from "./workspace_view_state.js";
export interface WorkspaceCanvasLaneDefinition {
    id: WorkspaceCanvasLaneId;
    title: string;
    description: string;
}
export interface WorkspaceCanvasCard {
    id: string;
    laneId: WorkspaceCanvasLaneId;
    originalIndex: number;
    entityType: WorkspaceEntityType;
    detailId: string;
    title: string;
    status: EvidenceStatus;
    evidenceStatus: string;
    derivedStatus: string;
    summary: string;
    guardrail: string;
    updatedOrCreatedTime: string;
}
export interface WorkspaceCanvasLane {
    id: WorkspaceCanvasLaneId;
    title: string;
    description: string;
    cards: WorkspaceCanvasCard[];
    visibleCount: number;
    blockedCount: number;
    actionRequiredCount: number;
    isCollapsed: boolean;
    isVisible: boolean;
    emptyReason: string;
}
export declare const WORKSPACE_CANVAS_LANE_DEFINITIONS: WorkspaceCanvasLaneDefinition[];
export declare function buildWorkspaceCanvasCards(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView): WorkspaceCanvasCard[];
export declare function buildWorkspaceCanvasLanes(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView, viewState: WorkspaceViewState): WorkspaceCanvasLane[];
