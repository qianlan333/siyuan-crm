import { type WorkspaceFixture, type WorkspaceSelectionState } from "./workspace_fixture.js";
import { type WorkspaceStatusModel } from "./workspace_status.js";
export declare function renderWorkspaceCanvas(model: WorkspaceStatusModel, fixture?: WorkspaceFixture, selection?: WorkspaceSelectionState): string;
export declare function renderWorkspacePreviewResult(model: WorkspaceStatusModel): string;
