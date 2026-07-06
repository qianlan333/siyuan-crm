import { type EvidenceStatus } from "../shared/status_model.js";
import { type FilteredWorkspaceView } from "./workspace_filters.js";
import { type WorkspaceEntityType, type WorkspaceFixture } from "./workspace_fixture.js";
import { type WorkspaceViewState } from "./workspace_view_state.js";
export interface WorkspacePreviewBundleItem {
    entityType: WorkspaceEntityType;
    detailId: string;
    title: string;
    status: EvidenceStatus;
    derivedStatus: string;
    isVisible: boolean;
}
export interface WorkspacePreviewBundle {
    bundleId: string;
    title: string;
    selectedCount: number;
    countsByEntityType: Record<WorkspaceEntityType, number>;
    blockedCount: number;
    actionRequiredCount: number;
    governanceMissingCount: number;
    pushCenterPendingCount: number;
    evidenceIncompleteCount: number;
    hiddenSelectedCount: number;
    canExecute: false;
    previewOnly: true;
    productionWrite: false;
    realExternalCall: false;
    canClaimPass90Plus: false;
    guardrails: string[];
    items: WorkspacePreviewBundleItem[];
}
export declare function buildWorkspacePreviewBundle(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView, viewState: WorkspaceViewState): WorkspacePreviewBundle;
