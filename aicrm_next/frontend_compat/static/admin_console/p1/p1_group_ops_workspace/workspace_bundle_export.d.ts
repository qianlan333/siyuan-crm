import { type WorkspacePreviewBundle, type WorkspacePreviewBundleItem } from "./workspace_preview_bundle.js";
export interface CopySafeBundleContext {
    workspace?: string;
    finalVerdict?: string;
}
export interface CopySafeClipboard {
    writeText(value: string): Promise<void>;
}
export interface CopySafeResult {
    ok: boolean;
    status: "copied" | "copy_failed";
    message: string;
}
export interface CopySafeBundleItemSummary {
    entityType: WorkspacePreviewBundleItem["entityType"];
    detailId: string;
    title: string;
    status: WorkspacePreviewBundleItem["status"];
    derivedStatus: string;
    visibleInCurrentFilter: boolean;
}
export interface CopySafeBundleJson {
    workspace: string;
    previewOnly: true;
    productionWrite: false;
    realExternalCall: false;
    canClaimPass90Plus: false;
    finalVerdict: string;
    selectedCount: number;
    countsByEntityType: WorkspacePreviewBundle["countsByEntityType"];
    blockedCount: number;
    actionRequiredCount: number;
    governanceMissingCount: number;
    pushCenterPendingCount: number;
    evidenceIncompleteCount: number;
    guardrailSummary: string[];
    selectedItems: CopySafeBundleItemSummary[];
}
export declare function assertCopySafeBundleOutput(output: string): true;
export declare function buildCopySafeBundleJson(bundle: WorkspacePreviewBundle, context?: CopySafeBundleContext): string;
export declare function buildCopySafeBundleText(bundle: WorkspacePreviewBundle, context?: CopySafeBundleContext): string;
export declare function copyBundleSummaryToClipboard(output: string, clipboard?: CopySafeClipboard | undefined): Promise<CopySafeResult>;
