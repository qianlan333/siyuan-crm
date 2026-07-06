import { type EvidenceStatus } from "../shared/status_model.js";
import { type WorkspaceCanvasSortMode } from "./workspace_view_state.js";
export interface WorkspaceSortableCanvasCard {
    originalIndex: number;
    status: EvidenceStatus;
    entityType: string;
    updatedOrCreatedTime: string;
}
export declare function sortCanvasCards<T extends WorkspaceSortableCanvasCard>(cards: T[], mode: WorkspaceCanvasSortMode): T[];
