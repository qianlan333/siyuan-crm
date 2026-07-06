import { type FilteredWorkspaceView } from "./workspace_filters.js";
import { type WorkspaceEntityType, type WorkspaceFixture } from "./workspace_fixture.js";
import { type WorkspaceViewState } from "./workspace_view_state.js";
export interface WorkspaceDraftApiConfig {
    draftsUrl: string;
}
export interface WorkspaceDraftRequestOptions {
    method?: "GET" | "POST" | "PATCH";
    headers?: Record<string, string>;
    body?: string;
}
export type WorkspaceDraftRequestJson = (url: string, options?: WorkspaceDraftRequestOptions) => Promise<unknown>;
export interface WorkspaceDraftItemPayload {
    item_type: WorkspaceEntityType;
    item_ref_id: string;
    item_order: number;
    sanitized_item: Record<string, unknown>;
    guardrail_summary: Record<string, unknown>;
}
export interface WorkspaceDraftPayload {
    source_plan_id: string;
    sanitized_payload: Record<string, unknown>;
    guardrail_summary: Record<string, unknown>;
    approval_requirements: Record<string, unknown>;
    items: WorkspaceDraftItemPayload[];
    idempotency_key: string;
    version?: number;
}
export interface WorkspaceDraftReviewPayload {
    version: number;
    idempotency_key: string;
    review_note?: string;
    client_snapshot_hash?: string;
}
export interface WorkspaceDraftResponse {
    ok: boolean;
    operation?: string;
    draft_id?: string;
    draft_status?: string;
    version?: number;
    source_plan_id?: string;
    sanitized_payload?: Record<string, unknown>;
    guardrail_summary?: Record<string, unknown>;
    approval_requirements?: Record<string, unknown>;
    items?: WorkspaceDraftItemPayload[];
    snapshot_hash?: string;
    created_at?: string;
    updated_at?: string;
    archived_at?: string;
    preview_only?: boolean;
    production_write?: boolean;
    ready_for_review?: boolean;
    approved?: boolean;
    real_external_call?: boolean;
    real_external_call_executed?: boolean;
    push_center_job_created?: boolean;
    external_effect_job_created?: boolean;
    broadcast_job_created?: boolean;
    internal_event_created?: boolean;
    can_claim_pass_90_plus?: boolean;
    execution_status?: string;
    error?: string;
    detail?: string;
}
export interface BuildWorkspaceDraftPayloadOptions {
    idempotencyKeyOverride?: string;
    version?: number;
}
export declare const DEFAULT_WORKSPACE_DRAFT_API_CONFIG: WorkspaceDraftApiConfig;
export declare function workspaceSimpleHash(value: string): string;
export declare function assertWorkspaceSensitiveSafe(value: unknown, path?: string): void;
export declare function assertWorkspaceDraftPayloadSafe(payload: WorkspaceDraftPayload): true;
export declare function assertWorkspaceDraftReviewPayloadSafe(payload: WorkspaceDraftReviewPayload): true;
export declare function stableRequestReviewIdempotencyKey(draftId: string, version: number, snapshotHash: string): string;
export declare function buildWorkspaceDraftPayload(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView, viewState: WorkspaceViewState, options?: BuildWorkspaceDraftPayloadOptions): WorkspaceDraftPayload;
export declare function buildWorkspaceDraftReviewPayload(draftId: string, version: number, snapshotHash: string, reviewNote?: string): WorkspaceDraftReviewPayload;
export declare function defaultWorkspaceDraftRequestJson(): WorkspaceDraftRequestJson;
export declare function isDraftConflictError(error: unknown): boolean;
export declare function listDrafts(config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
export declare function getDraft(draftId: string, config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
export declare function createDraft(payload: WorkspaceDraftPayload, config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
export declare function updateDraft(draftId: string, payload: WorkspaceDraftPayload, config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
export declare function archiveDraft(draftId: string, version: number, config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
export declare function requestDraftReview(draftId: string, payload: WorkspaceDraftReviewPayload, config?: WorkspaceDraftApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceDraftResponse>;
