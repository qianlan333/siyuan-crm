import { type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";
import { type PreviewBoardFixture } from "./preview_board_fixture.js";
export interface PreviewBoardValidationRow {
    title: string;
    status: ScenarioEvidence["status"];
    executionMode: string;
    blockedReason: string;
    statusAfterDrop: ScenarioEvidence["status"];
}
export interface PreviewBoardModel {
    fixture: PreviewBoardFixture;
    originalStatuses: ScenarioEvidence["status"][];
    previewStatuses: ScenarioEvidence["status"][];
    validationRows: PreviewBoardValidationRow[];
    canRenderGlobalPass90Plus: false;
}
export declare function buildPreviewBoardModel(payload?: BusinessClosurePayload): PreviewBoardModel;
export declare function renderP1PreviewBoard(fixture?: PreviewBoardFixture): string;
