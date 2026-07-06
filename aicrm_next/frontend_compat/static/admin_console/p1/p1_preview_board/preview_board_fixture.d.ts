import { type BusinessClosurePayload } from "../shared/status_model.js";
export interface PreviewBoardSummary {
    globalVerdict: "P1_READY_WITH_EXCEPTIONS";
    canClaimPass90Plus: false;
    previewOnly: true;
    productionWriteExecuted: false;
    realExternalCallExecuted: false;
}
export interface PreviewBoardFixture {
    summary: PreviewBoardSummary;
    payload: BusinessClosurePayload;
}
export declare const P1_PREVIEW_BOARD_FIXTURE: PreviewBoardFixture;
